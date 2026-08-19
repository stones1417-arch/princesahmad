from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from django.conf import settings

from apps.communications.services.masking import mask_value
from apps.communications.services.otp_validation import (
    OTPRecipientValidationError,
    normalize_otp_recipient,
)

from .base import (
    BaseCommunicationProvider,
    ProviderResult,
)


logger = logging.getLogger(
    "communications"
)


class ProviderConnectionError(
    Exception
):
    pass


class ProviderAuthenticationError(
    Exception
):
    pass


class ProviderResponseError(
    Exception
):
    pass


class ProviderRateLimitedError(
    ProviderResponseError
):
    pass


class UnsupportedChannelError(
    Exception
):
    pass


class OperationalMessagingNotConfiguredError(
    Exception
):
    pass


class AuthenticaProvider(
    BaseCommunicationProvider
):
    """
    Authentica provider.

    يدعم حاليًا عقد OTP الرسمي:

    POST /api/v2/send-otp
    POST /api/v2/verify-otp

    مع المصادقة:

    X-Authorization: <API KEY>

    القنوات المدعومة للـOTP:

    sms
    whatsapp
    email

    ولا يتم تخمين endpoints الخاصة
    بالرسائل التشغيلية العامة.
    """

    provider_code = "authentica"

    OTP_CHANNELS = {
        "sms",
        "whatsapp",
        "email",
    }

    OTP_SEND_ENDPOINT = (
        "/api/v2/send-otp"
    )

    OTP_VERIFY_ENDPOINT = (
        "/api/v2/verify-otp"
    )

    def __init__(
        self,
        session: requests.Session | None = None,
    ):
        self.session = (
            session
            or requests.Session()
        )

        self.base_url = str(
            settings.AUTHENTICA_BASE_URL
            or ""
        ).strip()

        self.timeout = int(
            settings.COMMUNICATION_TIMEOUT
        )

    # ======================================================
    # Operational Communication
    # ======================================================

    def send_operational_sms(
        self,
        *,
        recipient: str,
        message: str,
    ) -> ProviderResult:
        del recipient, message
        self._require_operational_contract("sms")
        raise OperationalMessagingNotConfiguredError(
            "عقد رسائل SMS التشغيلية غير معتمد بعد."
        )

    def send_operational_whatsapp(
        self,
        *,
        recipient: str,
        message: str,
    ) -> ProviderResult:
        del recipient, message
        self._require_operational_contract("whatsapp")
        raise OperationalMessagingNotConfiguredError(
            "عقد رسائل WhatsApp التشغيلية غير معتمد بعد."
        )

    @staticmethod
    def _require_operational_contract(channel: str) -> None:
        endpoint = getattr(settings, f"AUTHENTICA_{channel.upper()}_ENDPOINT", "")
        sender = getattr(settings, f"AUTHENTICA_{channel.upper()}_SENDER", "")
        if not settings.OPERATIONAL_MESSAGING_ENABLED or not endpoint or not sender:
            raise OperationalMessagingNotConfiguredError(
                "رسائل التكليف التشغيلية غير مهيأة."
            )

    def send_sms(
        self,
        *,
        recipient: str,
        message: str,
    ) -> ProviderResult:
        return self._send(
            "sms",
            {
                "recipient": recipient,
                "message": message,
                "sender": (
                    settings.AUTHENTICA_SMS_SENDER
                ),
            },
        )

    def send_whatsapp(
        self,
        *,
        recipient: str,
        message: str,
    ) -> ProviderResult:
        return self._send(
            "whatsapp",
            {
                "recipient": recipient,
                "message": message,
                "sender": (
                    settings.AUTHENTICA_WHATSAPP_SENDER
                ),
            },
        )

    def send_email(
        self,
        *,
        recipient: str,
        subject: str,
        message: str,
    ) -> ProviderResult:
        return self._send(
            "email",
            {
                "recipient": recipient,
                "subject": subject,
                "body": message,
                "sender": (
                    settings.AUTHENTICA_EMAIL_SENDER
                ),
            },
        )

    # ======================================================
    # OTP Send
    # ======================================================

    def request_otp(
        self,
        *,
        channel: str,
        recipient: str,
        purpose: str,
        template_id: (
            str
            | int
            | None
        ) = None,
    ) -> ProviderResult:
        """
        إرسال OTP عبر Authentica.

        العقد الرسمي:

        POST /api/v2/send-otp

        body:
        method
        phone/email
        template_id اختياري
        """

        del purpose

        self._ensure_communications_enabled()

        channel = self._normalize_otp_channel(
            channel
        )

        configured_endpoint = str(
            settings.AUTHENTICA_OTP_REQUEST_ENDPOINT
            or ""
        ).strip()

        if (
            configured_endpoint
            != self.OTP_SEND_ENDPOINT
        ):
            raise UnsupportedChannelError(
                "مسار إرسال OTP لا يطابق "
                "عقد Authentica الرسمي."
            )

        try:
            request_payload = (
                self._build_otp_payload(
                    channel,
                    recipient,
                    template_id,
                )
            )

        except OTPRecipientValidationError as exc:
            raise UnsupportedChannelError(
                str(exc)
            ) from exc

        started = time.monotonic()

        try:
            response = self.session.post(
                self._secure_url(
                    configured_endpoint
                ),
                json=request_payload,
                headers=self._otp_headers(),
                timeout=self.timeout,
            )

        except requests.Timeout as exc:
            raise ProviderConnectionError(
                "انتهت مهلة الاتصال بالمزود."
            ) from exc

        except requests.RequestException as exc:
            raise ProviderConnectionError(
                "تعذر الاتصال بمزود الاتصالات."
            ) from exc

        elapsed_ms = round(
            (
                time.monotonic()
                - started
            )
            * 1000
        )

        logger.info(
            (
                "authentica_otp_response "
                "channel=%s status=%s "
                "elapsed_ms=%s"
            ),
            channel,
            response.status_code,
            elapsed_ms,
        )

        self._raise_for_provider_status(
            response
        )

        return self._normalize_otp_response(
            response
        )

    # ======================================================
    # OTP Verify
    # ======================================================

    def verify_otp(
        self,
        *,
        channel: str,
        recipient: str,
        otp: str,
    ) -> ProviderResult:
        """
        التحقق من OTP.

        العقد الرسمي:

        POST /api/v2/verify-otp

        body SMS/WhatsApp:
        {
            "phone": "...",
            "otp": "..."
        }

        body Email:
        {
            "email": "...",
            "otp": "..."
        }

        ملاحظة:
        لا يتم تسجيل قيمة OTP في logs.
        """

        self._ensure_communications_enabled()

        channel = self._normalize_otp_channel(
            channel
        )

        configured_endpoint = str(
            settings.AUTHENTICA_OTP_VERIFY_ENDPOINT
            or ""
        ).strip()

        if (
            configured_endpoint
            != self.OTP_VERIFY_ENDPOINT
        ):
            raise UnsupportedChannelError(
                "مسار التحقق من OTP لا يطابق "
                "عقد Authentica الرسمي."
            )

        if (
            not isinstance(
                otp,
                str,
            )
            or not otp.strip()
        ):
            raise UnsupportedChannelError(
                "رمز OTP مطلوب."
            )

        try:
            normalized_recipient = (
                normalize_otp_recipient(
                    channel,
                    recipient,
                )
            )

        except OTPRecipientValidationError as exc:
            raise UnsupportedChannelError(
                str(exc)
            ) from exc

        payload: dict[
            str,
            str,
        ] = {
            "otp": otp.strip(),
        }

        if channel == "email":
            payload[
                "email"
            ] = normalized_recipient

        else:
            payload[
                "phone"
            ] = normalized_recipient

        started = time.monotonic()

        try:
            response = self.session.post(
                self._secure_url(
                    configured_endpoint
                ),
                json=payload,
                headers=self._otp_headers(),
                timeout=self.timeout,
            )

        except requests.Timeout as exc:
            raise ProviderConnectionError(
                "انتهت مهلة الاتصال بالمزود."
            ) from exc

        except requests.RequestException as exc:
            raise ProviderConnectionError(
                "تعذر الاتصال بمزود الاتصالات."
            ) from exc

        elapsed_ms = round(
            (
                time.monotonic()
                - started
            )
            * 1000
        )

        logger.info(
            (
                "authentica_otp_verify_response "
                "channel=%s status=%s "
                "elapsed_ms=%s"
            ),
            channel,
            response.status_code,
            elapsed_ms,
        )

        self._raise_for_provider_status(
            response
        )

        return (
            self._normalize_otp_verification_response(
                response
            )
        )

    # ======================================================
    # Generic Operational Send
    # ======================================================

    def _send(
        self,
        channel: str,
        payload: dict[
            str,
            str,
        ],
    ) -> ProviderResult:
        self._ensure_communications_enabled()

        endpoint = getattr(
            settings,
            (
                f"AUTHENTICA_"
                f"{channel.upper()}_ENDPOINT"
            ),
            "",
        )

        mapping = getattr(
            settings,
            (
                f"AUTHENTICA_"
                f"{channel.upper()}_"
                f"PAYLOAD_MAPPING"
            ),
            {},
        )

        if (
            not endpoint
            or not mapping
        ):
            raise UnsupportedChannelError(
                "لم يتم إعداد endpoint "
                "أو خريطة payload الموثقة "
                "للقناة."
            )

        url = self._secure_url(
            endpoint
        )

        request_payload = (
            self.build_payload(
                channel,
                payload,
            )
        )

        if not request_payload:
            raise UnsupportedChannelError(
                "خريطة payload لا تنتج "
                "بيانات صالحة للإرسال."
            )

        started = time.monotonic()

        try:
            response = self.session.post(
                url,
                json=request_payload,
                headers=self._headers(),
                timeout=self.timeout,
            )

        except requests.Timeout as exc:
            raise ProviderConnectionError(
                "انتهت مهلة الاتصال بالمزود."
            ) from exc

        except requests.RequestException as exc:
            raise ProviderConnectionError(
                "تعذر الاتصال بمزود الاتصالات."
            ) from exc

        elapsed_ms = round(
            (
                time.monotonic()
                - started
            )
            * 1000
        )

        logger.info(
            (
                "authentica_response "
                "channel=%s status=%s "
                "elapsed_ms=%s"
            ),
            channel,
            response.status_code,
            elapsed_ms,
        )

        self._raise_for_provider_status(
            response
        )

        return self.normalize_response(
            response,
            channel=channel,
        )

    # ======================================================
    # Generic Verification Operation
    # ======================================================

    def _send_operation(
        self,
        *,
        endpoint: str,
        mapping: dict,
        values: dict[
            str,
            str,
        ],
    ) -> ProviderResult:
        self._ensure_communications_enabled()

        if (
            not endpoint
            or not mapping
            or not settings.AUTHENTICA_OTP_RESPONSE_MAPPING
        ):
            raise UnsupportedChannelError(
                "عملية التحقق غير مهيأة "
                "بالوثائق الرسمية."
            )

        payload = {
            provider_key: (
                values[source_key]
            )
            for (
                source_key,
                provider_key,
            )
            in mapping.items()
            if (
                source_key in values
                and provider_key
                and values[source_key]
            )
        }

        if not payload:
            raise UnsupportedChannelError(
                "خريطة payload لا تنتج "
                "بيانات صالحة للإرسال."
            )

        try:
            response = self.session.post(
                self._secure_url(
                    endpoint
                ),
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )

        except requests.Timeout as exc:
            raise ProviderConnectionError(
                "انتهت مهلة الاتصال بالمزود."
            ) from exc

        except requests.RequestException as exc:
            raise ProviderConnectionError(
                "تعذر الاتصال بمزود الاتصالات."
            ) from exc

        self._raise_for_provider_status(
            response
        )

        return (
            self._normalize_response_mapping(
                response,
                settings.AUTHENTICA_OTP_RESPONSE_MAPPING,
            )
        )

    # ======================================================
    # OTP Payload
    # ======================================================

    @staticmethod
    def _build_otp_payload(
        channel: str,
        recipient: str,
        template_id: (
            str
            | int
            | None
        ),
    ) -> dict[
        str,
        str | int,
    ]:
        normalized_recipient = (
            normalize_otp_recipient(
                channel,
                recipient,
            )
        )

        configured_template_id = (
            getattr(
                settings,
                (
                    "AUTHENTICA_"
                    f"{channel.upper()}_"
                    "OTP_TEMPLATE_ID"
                ),
                "",
            )
        )

        configured_template_id = str(
            configured_template_id
            or ""
        ).strip()

        if (
            template_id is not None
            and configured_template_id
            and str(template_id)
            != configured_template_id
        ):
            raise UnsupportedChannelError(
                "قالب OTP غير متوافق "
                "مع القناة المحددة."
            )

        payload: dict[
            str,
            str | int,
        ] = {
            "method": channel,
        }

        if channel == "email":
            payload[
                "email"
            ] = normalized_recipient

        else:
            payload[
                "phone"
            ] = normalized_recipient

        if configured_template_id:
            payload[
                "template_id"
            ] = configured_template_id

        elif template_id is not None:
            payload[
                "template_id"
            ] = template_id

        return payload

    # ======================================================
    # OTP Send Response
    # ======================================================

    def _normalize_otp_response(
        self,
        response: requests.Response,
    ) -> ProviderResult:
        """
        تفسير استجابة Send OTP.

        إذا كان هناك mapping موثق نستخدمه.

        وإلا، بما أن HTTP status تم التحقق
        منه قبل الوصول إلى هنا وكان 2xx،
        نحفظ payload ونعتبر الطلب pending.
        """

        payload = self._safe_json_object(
            response
        )

        mapping = getattr(
            settings,
            "AUTHENTICA_OTP_RESPONSE_MAPPING",
            {},
        )

        if mapping:
            return (
                self._normalize_response_mapping(
                    response,
                    mapping,
                )
            )

        return ProviderResult(
            status="pending",
            payload=payload,
        )

    # ======================================================
    # OTP Verify Response
    # ======================================================

    def _normalize_otp_verification_response(
        self,
        response: requests.Response,
    ) -> ProviderResult:
        """
        تفسير نجاح Verify OTP.

        قبل استدعاء هذه الدالة تم بالفعل:

        - رفض 401/403
        - رفض 429
        - رفض أي HTTP >= 400

        لذلك الوصول هنا يعني أن Authentica
        أعاد HTTP نجاحًا.

        إذا كان لدينا Response Mapping موثق
        نستخدمه.

        وإذا لم يوجد mapping، لا نخمن اسم
        حقل status داخل JSON؛ بل نعتمد نجاح
        HTTP نفسه ونرجع verified.
        """

        payload = self._safe_json_object(
            response
        )

        mapping = getattr(
            settings,
            "AUTHENTICA_OTP_RESPONSE_MAPPING",
            {},
        )

        if mapping:
            return self._normalize_response_mapping(
                response,
                mapping,
                verified_success_values={
                    "success",
                    "verified",
                },
            )

        return ProviderResult(
            status="verified",
            payload=payload,
        )

    # ======================================================
    # Payload Builder
    # ======================================================

    def build_payload(
        self,
        channel: str,
        values: dict[
            str,
            str,
        ],
    ) -> dict[
        str,
        str,
    ]:
        mapping = getattr(
            settings,
            (
                f"AUTHENTICA_"
                f"{channel.upper()}_"
                f"PAYLOAD_MAPPING"
            ),
            {},
        )

        return {
            provider_key: (
                values[source_key]
            )
            for (
                source_key,
                provider_key,
            )
            in mapping.items()
            if (
                source_key in values
                and provider_key
                and values[source_key]
            )
        }

    # ======================================================
    # Dry Run
    # ======================================================

    def dry_run_payload(
        self,
        channel: str,
    ) -> dict[
        str,
        Any,
    ]:
        return self.dry_run_request(
            channel
        )["payload"]

    def dry_run_request(
        self,
        channel: str,
    ) -> dict[
        str,
        Any,
    ]:
        configuration = (
            self._dry_run_configuration(
                channel
            )
        )

        missing = [
            name
            for (
                name,
                value,
            )
            in configuration[
                "required"
            ].items()
            if not value
        ]

        if missing:
            return {
                "status": "NOT_CONFIGURED",
                "missing": missing,
            }

        if channel == "otp":
            try:
                endpoint = self._secure_url(
                    configuration[
                        "endpoint"
                    ]
                )

                headers = (
                    self._otp_headers()
                )

                payload = (
                    self._build_otp_payload(
                        "sms",
                        "+966501234518",
                        None,
                    )
                )

            except (
                ProviderConnectionError,
                ProviderAuthenticationError,
                UnsupportedChannelError,
            ):
                return {
                    "status": "NOT_CONFIGURED",
                    "missing": [
                        (
                            "AUTHENTICA_"
                            "OTP_REQUEST_ENDPOINT"
                        )
                    ],
                }

            return {
                "status": "READY",
                "endpoint": endpoint,
                "headers": {
                    name: "********"
                    for name in headers
                },
                "payload": mask_value(
                    payload
                ),
            }

        samples = {
            "recipient": (
                "+966501234518"
                if channel != "email"
                else "a@example.com"
            ),
            "message": (
                "Authentica dry-run message"
            ),
            "body": (
                "Authentica dry-run email body"
            ),
            "subject": (
                "Authentica dry-run subject"
            ),
            "sender": (
                configuration["sender"]
            ),
            "channel": "sms",
            "purpose": "login",
        }

        payload = {
            provider_key: (
                samples[source_key]
            )
            for (
                source_key,
                provider_key,
            )
            in configuration[
                "mapping"
            ].items()
            if (
                source_key in samples
                and provider_key
                and samples[source_key]
            )
        }

        if not payload:
            return {
                "status": "NOT_CONFIGURED",
                "missing": [
                    configuration[
                        "mapping_name"
                    ]
                ],
            }

        try:
            endpoint = self._secure_url(
                configuration[
                    "endpoint"
                ]
            )

            headers = self._headers()

        except (
            ProviderConnectionError,
            ProviderAuthenticationError,
        ):
            return {
                "status": "NOT_CONFIGURED",
                "missing": [
                    "AUTHENTICA_BASE_URL"
                ],
            }

        return {
            "status": "READY",
            "endpoint": endpoint,
            "headers": {
                name: "********"
                for name in headers
            },
            "payload": mask_value(
                payload
            ),
        }

    # ======================================================
    # Dry Run Configuration
    # ======================================================

    @staticmethod
    def _dry_run_configuration(
        channel: str,
    ) -> dict[
        str,
        Any,
    ]:
        if channel == "otp":
            return {
                "endpoint": (
                    settings.AUTHENTICA_OTP_REQUEST_ENDPOINT
                ),
                "mapping": {},
                "sender": "",
                "mapping_name": (
                    "AUTHENTICA_"
                    "OTP_REQUEST_ENDPOINT"
                ),
                "required": {
                    "AUTHENTICA_BASE_URL": (
                        settings.AUTHENTICA_BASE_URL
                    ),
                    "AUTHENTICA_API_KEY": (
                        settings.AUTHENTICA_API_KEY
                    ),
                    (
                        "AUTHENTICA_"
                        "OTP_REQUEST_ENDPOINT"
                    ): (
                        settings.AUTHENTICA_OTP_REQUEST_ENDPOINT
                    ),
                },
            }

        prefix = channel.upper()

        mapping_name = (
            f"AUTHENTICA_{prefix}_"
            f"PAYLOAD_MAPPING"
        )

        endpoint_name = (
            f"AUTHENTICA_{prefix}_ENDPOINT"
        )

        sender_name = (
            f"AUTHENTICA_{prefix}_SENDER"
        )

        endpoint = getattr(
            settings,
            endpoint_name,
            "",
        )

        mapping = getattr(
            settings,
            mapping_name,
            {},
        )

        sender = getattr(
            settings,
            sender_name,
            "",
        )

        required = {
            endpoint_name: endpoint,
            mapping_name: mapping,
        }

        if channel in {
            "sms",
            "whatsapp",
            "email",
        }:
            required[
                sender_name
            ] = sender

        return {
            "endpoint": endpoint,
            "mapping": mapping,
            "sender": sender,
            "mapping_name": mapping_name,
            "required": required,
        }

    # ======================================================
    # Generic Response Normalization
    # ======================================================

    def normalize_response(
        self,
        response: requests.Response,
        channel: str | None = None,
    ) -> ProviderResult:
        mapping = getattr(
            settings,
            (
                "AUTHENTICA_"
                f"{(channel or '').upper()}_"
                "RESPONSE_MAPPING"
            ),
            {},
        )

        return (
            self._normalize_response_mapping(
                response,
                mapping,
            )
        )

    def _normalize_response_mapping(
        self,
        response: requests.Response,
        mapping: dict,
        verified_success_values: set[str] | None = None,
    ) -> ProviderResult:
        payload = self._safe_json_object(
            response
        )

        message_id = self._read_mapped_value(
            payload,
            mapping.get(
                "provider_message_id"
            ),
        )

        raw_status = (
            self._read_mapped_value(
                payload,
                mapping.get(
                    "status"
                ),
            )
        )

        normalized_raw_status = str(
            raw_status
        ).strip().lower()

        status = settings.AUTHENTICA_STATUS_MAPPING.get(
            normalized_raw_status,
            "",
        )

        if (
            verified_success_values
            and normalized_raw_status
            in verified_success_values
        ):
            status = "verified"

        if not status:
            raise ProviderResponseError(
                "تعذر مطابقة حالة الاستجابة "
                "مع إعدادات المزود."
            )

        return ProviderResult(
            status=status,
            provider_message_id=message_id,
            payload=payload,
        )

    # ======================================================
    # Health Check
    # ======================================================

    def health_check(
        self,
    ) -> dict[
        str,
        bool,
    ]:
        return {
            "sms": (
                self._is_channel_configured(
                    "sms"
                )
            ),
            "whatsapp": (
                self._is_channel_configured(
                    "whatsapp"
                )
            ),
            "email": (
                self._is_channel_configured(
                    "email"
                )
            ),
        }

    # ======================================================
    # Headers
    # ======================================================

    def _headers(
        self,
    ) -> dict[
        str,
        str,
    ]:
        values = {
            "api_key": (
                settings.AUTHENTICA_API_KEY
            ),
            "api_secret": (
                settings.AUTHENTICA_API_SECRET
            ),
        }

        headers: dict[
            str,
            str,
        ] = {}

        for (
            name,
            value_template,
        ) in (
            settings.AUTHENTICA_AUTH_HEADERS.items()
        ):
            try:
                headers[
                    name
                ] = str(
                    value_template
                ).format(
                    **values
                )

            except KeyError as exc:
                raise ProviderAuthenticationError(
                    "قالب ترويسات "
                    "المصادقة غير صالح."
                ) from exc

        return headers

    @staticmethod
    def _otp_headers(
    ) -> dict[
        str,
        str,
    ]:
        if not settings.AUTHENTICA_API_KEY:
            raise ProviderAuthenticationError(
                "مفتاح Authentica غير مهيأ."
            )

        return {
            "Accept": "application/json",
            "Content-Type": (
                "application/json"
            ),
            "X-Authorization": (
                settings.AUTHENTICA_API_KEY
            ),
        }

    # ======================================================
    # URL Security
    # ======================================================

    def _secure_url(
        self,
        endpoint: str,
    ) -> str:
        endpoint = str(
            endpoint
            or ""
        ).strip()

        if not endpoint:
            raise ProviderConnectionError(
                "مسار Authentica غير مهيأ."
            )

        if urlparse(
            endpoint
        ).scheme:
            url = endpoint

        else:
            url = urljoin(
                (
                    self.base_url.rstrip("/")
                    + "/"
                ),
                endpoint.lstrip("/"),
            )

        parsed = urlparse(
            url
        )

        if parsed.scheme != "https":
            raise ProviderConnectionError(
                "يجب أن يستخدم مزود "
                "الاتصالات HTTPS."
            )

        if not parsed.netloc:
            raise ProviderConnectionError(
                "عنوان مزود الاتصالات "
                "غير صالح."
            )

        return url

    # ======================================================
    # Provider HTTP Status Handling
    # ======================================================

    @staticmethod
    def _raise_for_provider_status(
        response: requests.Response,
    ) -> None:
        """
        توحيد التعامل مع HTTP status.

        لا يتم هنا تفسير business payload.
        """

        if response.status_code in {
            401,
            403,
        }:
            raise ProviderAuthenticationError(
                "فشلت مصادقة مزود الاتصالات."
            )

        if response.status_code == 429:
            raise ProviderRateLimitedError(
                "تم تجاوز حد طلبات "
                "مزود الاتصالات."
            )

        if response.status_code >= 500:
            raise ProviderResponseError(
                "حدث خطأ لدى مزود الاتصالات."
            )

        if response.status_code >= 400:
            raise ProviderResponseError(
                "رفض مزود الاتصالات الطلب."
            )

    # ======================================================
    # Safe JSON
    # ======================================================

    @staticmethod
    def _safe_json_object(
        response: requests.Response,
    ) -> dict[
        str,
        Any,
    ]:
        """
        قراءة JSON Response بأمان.

        لا يتم تسجيل محتوى response.
        """

        try:
            payload = response.json()

        except ValueError as exc:
            raise ProviderResponseError(
                "أعاد المزود استجابة "
                "غير صالحة."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise ProviderResponseError(
                "أعاد المزود بنية "
                "استجابة غير مدعومة."
            )

        return payload

    # ======================================================
    # OTP Channel Validation
    # ======================================================

    @classmethod
    def _normalize_otp_channel(
        cls,
        channel: str,
    ) -> str:
        normalized = str(
            channel
            or ""
        ).strip().lower()

        if normalized not in cls.OTP_CHANNELS:
            raise UnsupportedChannelError(
                "قناة OTP غير مدعومة."
            )

        allowed_channels = {
            str(
                item
            ).strip().lower()
            for item in getattr(
                settings,
                "AUTHENTICA_OTP_ALLOWED_CHANNELS",
                (),
            )
            if str(
                item
            ).strip()
        }

        if (
            allowed_channels
            and normalized
            not in allowed_channels
        ):
            raise UnsupportedChannelError(
                "قناة OTP غير مسموح بها "
                "في إعدادات المنصة."
            )

        return normalized

    # ======================================================
    # Communications Enabled
    # ======================================================

    @staticmethod
    def _ensure_communications_enabled(
    ) -> None:
        from apps.core.system_settings import SystemSettingsService

        if not SystemSettingsService.get_effective_value(
            "communications_enabled"
        ):
            raise ProviderConnectionError(
                "الإرسال الخارجي معطل "
                "في إعدادات المنصة."
            )

    # ======================================================
    # Mapping Reader
    # ======================================================

    @staticmethod
    def _read_mapped_value(
        payload: dict[
            str,
            Any,
        ],
        path: str | None,
    ) -> str:
        if not path:
            return ""

        value: Any = payload

        for part in path.split("."):
            if (
                not isinstance(
                    value,
                    dict,
                )
                or part not in value
            ):
                return ""

            value = value[
                part
            ]

        if value is None:
            return ""

        return str(
            value
        )

    # ======================================================
    # Operational Channel Readiness
    # ======================================================

    @staticmethod
    def _is_channel_configured(
        channel: str,
    ) -> bool:
        prefix = (
            f"AUTHENTICA_"
            f"{channel.upper()}"
        )

        mapping = getattr(
            settings,
            f"{prefix}_PAYLOAD_MAPPING",
            {},
        )

        response_mapping = getattr(
            settings,
            f"{prefix}_RESPONSE_MAPPING",
            {},
        )

        sender = getattr(
            settings,
            f"{prefix}_SENDER",
            "",
        )

        endpoint = getattr(
            settings,
            f"{prefix}_ENDPOINT",
            "",
        )

        return bool(
            endpoint
            and mapping
            and response_mapping.get(
                "status"
            )
            and sender
        )