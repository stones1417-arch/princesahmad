from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.communications.models import OTPVerification
from apps.accounts.services.two_factor_audit_service import record_2fa_event

from .masking import mask_value
from .otp_validation import OTPRecipientValidationError, normalize_otp_recipient


security_logger = logging.getLogger("platform.security")


class VerificationNotConfiguredError(Exception):
	pass


class OTPRateLimitedError(Exception):
	pass


class OTPResendCooldownError(Exception):
	pass


class AuthenticaOTPService:
	"""Persist OTP metadata only and delegate all transport to the provider."""

	def __init__(self, provider):
		self.provider = provider

	def request_otp(self, *, user, employee, channel, recipient, purpose):
		self._validate_channel(channel)
		recipient = self._normalized_recipient(channel, recipient)
		try:
			self._check_request_rate_limit(user=user, purpose=purpose)
		except OTPRateLimitedError:
			record_2fa_event(user=user, event="2fa_rate_limited", channel=channel)
			raise
		record_2fa_event(user=user, event="2fa_send_started", channel=channel)
		with transaction.atomic():
			OTPVerification.objects.select_for_update().filter(
				user=user,
				purpose=purpose,
				status__in=(
					OTPVerification.Status.PENDING,
					OTPVerification.Status.SENT,
				),
			).update(status=OTPVerification.Status.REJECTED)
			verification = OTPVerification.objects.create(
				user=user,
				employee=employee,
				channel=channel,
				recipient_masked=mask_value(recipient),
				purpose=purpose,
				status=OTPVerification.Status.PENDING,
				expires_at=timezone.now() + timedelta(seconds=settings.AUTHENTICA_OTP_TTL_SECONDS),
			)
		if not settings.COMMUNICATIONS_ENABLED:
			verification.status = OTPVerification.Status.SIMULATED
			verification.save(update_fields=["status", "updated_at"])
			return verification
		try:
			result = self.provider.request_otp(
				channel=channel, recipient=recipient, purpose=purpose
			)
		except Exception:
			record_2fa_event(user=user, event="2fa_send_failed", channel=channel)
			raise
		verification.provider_request_id = result.provider_message_id
		verification.status = result.status
		verification.save(update_fields=["provider_request_id", "status", "updated_at"])
		record_2fa_event(
			user=user,
			event="2fa_send_succeeded" if result.status in {OTPVerification.Status.PENDING, OTPVerification.Status.SENT} else "2fa_send_failed",
			channel=channel,
			status=result.status,
			metadata={"verification_id": verification.pk},
		)
		return verification

	def verify_otp(self, *, verification, otp, recipient=None):
		if verification.status not in {
			OTPVerification.Status.PENDING,
			OTPVerification.Status.SENT,
		}:
			record_2fa_event(
				user=verification.user,
				event="2fa_replay_blocked" if verification.status == OTPVerification.Status.VERIFIED else "2fa_verify_failed",
				channel=verification.channel,
				status=verification.status,
				metadata={"verification_id": verification.pk},
			)
			return verification
		if verification.expires_at and verification.expires_at <= timezone.now():
			verification.status = OTPVerification.Status.EXPIRED
			verification.save(update_fields=["status", "updated_at"])
			record_2fa_event(user=verification.user, event="2fa_expired", channel=verification.channel, status=verification.status, metadata={"verification_id": verification.pk})
			return verification
		if verification.attempts >= settings.AUTHENTICA_OTP_MAX_ATTEMPTS:
			verification.status = OTPVerification.Status.REJECTED
			verification.save(update_fields=["status", "updated_at"])
			record_2fa_event(user=verification.user, event="2fa_max_attempts_reached", channel=verification.channel, status=verification.status, metadata={"verification_id": verification.pk})
			return verification
		if not settings.COMMUNICATIONS_ENABLED:
			raise VerificationNotConfiguredError("التحقق الخارجي معطل.")
		recipient = self._normalized_recipient(verification.channel, recipient)
		try:
			result = self.provider.verify_otp(
				channel=verification.channel, recipient=recipient, otp=otp
			)
		except Exception:
			record_2fa_event(user=verification.user, event="2fa_verify_failed", channel=verification.channel, metadata={"verification_id": verification.pk})
			raise
		if result.status == OTPVerification.Status.VERIFIED:
			security_logger.info(
				"Two-factor provider verification succeeded.",
				extra={
					"event": "two_factor_provider_verified",
					"user_id": verification.user_id,
				},
			)
		verification.attempts += 1
		verification.status = (
			OTPVerification.Status.SENT
			if result.status == OTPVerification.Status.FAILED
			else result.status
		)
		if result.status == OTPVerification.Status.VERIFIED:
			verification.verified_at = timezone.now()
		verification.save(update_fields=["attempts", "status", "verified_at", "updated_at"])
		record_2fa_event(
			user=verification.user,
			event="2fa_verify_succeeded" if verification.status == OTPVerification.Status.VERIFIED else "2fa_verify_failed",
			channel=verification.channel,
			status=verification.status,
			metadata={"verification_id": verification.pk, "attempt_number": verification.attempts},
		)
		if verification.status == OTPVerification.Status.VERIFIED:
			security_logger.info(
				"Two-factor verification record marked verified.",
				extra={
					"event": "two_factor_record_verified",
					"user_id": verification.user_id,
				},
			)
		return verification

	def resend_otp(self, *, verification, recipient):
		if verification.status == OTPVerification.Status.VERIFIED:
			return verification
		cooldown = timedelta(seconds=settings.AUTHENTICA_OTP_RESEND_COOLDOWN_SECONDS)
		if verification.created_at >= timezone.now() - cooldown:
			raise OTPResendCooldownError("إعادة الإرسال غير متاحة بعد.")
		return self.request_otp(
			user=verification.user,
			employee=verification.employee,
			channel=verification.channel,
			recipient=recipient,
			purpose=verification.purpose,
		)

	@staticmethod
	def _validate_channel(channel):
		allowed = {"sms", "whatsapp", "email"}
		if channel not in allowed or channel not in settings.AUTHENTICA_OTP_ALLOWED_CHANNELS:
			raise VerificationNotConfiguredError("قناة OTP غير مسموحة.")

	@staticmethod
	def _normalized_recipient(channel, recipient):
		try:
			return normalize_otp_recipient(channel, recipient)
		except OTPRecipientValidationError as exc:
			raise VerificationNotConfiguredError(str(exc)) from exc

	@staticmethod
	def _check_request_rate_limit(*, user, purpose):
		if not user:
			return
		since = timezone.now() - timedelta(seconds=settings.AUTHENTICA_OTP_RATE_LIMIT_WINDOW)
		attempts = OTPVerification.objects.filter(
			user=user, purpose=purpose, created_at__gte=since
		).count()
		if attempts >= settings.AUTHENTICA_OTP_RATE_LIMIT_ATTEMPTS:
			raise OTPRateLimitedError("تم تجاوز حد طلبات OTP.")
