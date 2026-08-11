from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.notifications.models import Notification
from apps.roles.services.section_access import (
    get_allowed_sections,
    has_institutional_scope,
)


@dataclass(frozen=True)
class NotificationPayload:
    title: str
    message: str
    level: str = "info"
    url: str = ""
    section: str = "all"


class NotificationService:
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_DANGER = "danger"

    VALID_LEVELS = {
        LEVEL_INFO,
        LEVEL_SUCCESS,
        LEVEL_WARNING,
        LEVEL_DANGER,
    }

    SECTION_ALL = Notification.OperationalSection.ALL
    VALID_SECTIONS = {
        Notification.OperationalSection.MALE,
        Notification.OperationalSection.FEMALE,
        Notification.OperationalSection.ALL,
    }

    @classmethod
    def normalize_level(cls, level: str) -> str:
        level = (level or cls.LEVEL_INFO).strip().lower()
        return level if level in cls.VALID_LEVELS else cls.LEVEL_INFO

    @classmethod
    def normalize_section(cls, section: str) -> str:
        normalized_section = (section or cls.SECTION_ALL).strip().lower()
        if normalized_section in cls.VALID_SECTIONS:
            return normalized_section
        return cls.SECTION_ALL

    @classmethod
    def _valid_user(cls, user):
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return None
        return user

    @classmethod
    def _can_receive_section(cls, user, section: str) -> bool:
        if section == cls.SECTION_ALL:
            return True

        employee = getattr(user, "employee", None)
        if employee:
            if user.is_superuser or (
                has_institutional_scope(user)
                and len(get_allowed_sections(user)) == 2
            ):
                return True
            return employee.operational_section == section

        return user.is_superuser or (
            user.is_staff
            and section in get_allowed_sections(user)
        )

    @classmethod
    def notify(
        cls,
        *,
        title: str,
        message: str,
        level: str = LEVEL_INFO,
        user=None,
        users: Iterable | None = None,
        url: str = "",
        section: str = SECTION_ALL,
        assignment=None,
    ) -> NotificationPayload:
        assignment_section = getattr(assignment, "section", None)
        payload = NotificationPayload(
            title=(title or "").strip(),
            message=(message or "").strip(),
            level=cls.normalize_level(level),
            url=(url or "").strip(),
            section=cls.normalize_section(assignment_section or section),
        )

        recipients = []

        single_user = cls._valid_user(user)
        if single_user:
            recipients.append(single_user)

        if users:
            for item in users:
                valid_user = cls._valid_user(item)
                if valid_user and valid_user not in recipients:
                    recipients.append(valid_user)

        for recipient in recipients:
            if not cls._can_receive_section(recipient, payload.section):
                continue
            Notification.objects.create(
                user=recipient,
                title=payload.title,
                message=payload.message,
                level=payload.level,
                url=payload.url,
                section=payload.section,
            )

        return payload

    @classmethod
    def notify_staff(
        cls,
        *,
        title: str,
        message: str,
        level: str = LEVEL_INFO,
        url: str = "",
        section: str = SECTION_ALL,
    ) -> NotificationPayload:
        User = get_user_model()
        users = User.objects.filter(is_active=True, is_staff=True)

        return cls.notify(
            title=title,
            message=message,
            level=level,
            users=users,
            url=url,
            section=section,
        )

    @classmethod
    def success(
        cls,
        *,
        title: str,
        message: str,
        user=None,
        users=None,
        url: str = "",
        section: str = SECTION_ALL,
        assignment=None,
    ):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_SUCCESS,
            user=user,
            users=users,
            url=url,
            section=section,
            assignment=assignment,
        )

    @classmethod
    def warning(
        cls,
        *,
        title: str,
        message: str,
        user=None,
        users=None,
        url: str = "",
        section: str = SECTION_ALL,
        assignment=None,
    ):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_WARNING,
            user=user,
            users=users,
            url=url,
            section=section,
            assignment=assignment,
        )

    @classmethod
    def danger(
        cls,
        *,
        title: str,
        message: str,
        user=None,
        users=None,
        url: str = "",
        section: str = SECTION_ALL,
        assignment=None,
    ):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_DANGER,
            user=user,
            users=users,
            url=url,
            section=section,
            assignment=assignment,
        )

    @classmethod
    def info(
        cls,
        *,
        title: str,
        message: str,
        user=None,
        users=None,
        url: str = "",
        section: str = SECTION_ALL,
        assignment=None,
    ):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_INFO,
            user=user,
            users=users,
            url=url,
            section=section,
            assignment=assignment,
        )