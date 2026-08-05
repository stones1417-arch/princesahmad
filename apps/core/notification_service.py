from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.notifications.models import Notification


@dataclass(frozen=True)
class NotificationPayload:
    title: str
    message: str
    level: str = "info"
    url: str = ""


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

    @classmethod
    def normalize_level(cls, level: str) -> str:
        level = (level or cls.LEVEL_INFO).strip().lower()
        return level if level in cls.VALID_LEVELS else cls.LEVEL_INFO

    @classmethod
    def _valid_user(cls, user):
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            return None
        return user

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
    ) -> NotificationPayload:
        payload = NotificationPayload(
            title=(title or "").strip(),
            message=(message or "").strip(),
            level=cls.normalize_level(level),
            url=(url or "").strip(),
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
            Notification.objects.create(
                user=recipient,
                title=payload.title,
                message=payload.message,
                level=payload.level,
                url=payload.url,
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
    ) -> NotificationPayload:
        User = get_user_model()
        users = User.objects.filter(is_active=True, is_staff=True)

        return cls.notify(
            title=title,
            message=message,
            level=level,
            users=users,
            url=url,
        )

    @classmethod
    def success(cls, *, title: str, message: str, user=None, users=None, url: str = ""):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_SUCCESS,
            user=user,
            users=users,
            url=url,
        )

    @classmethod
    def warning(cls, *, title: str, message: str, user=None, users=None, url: str = ""):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_WARNING,
            user=user,
            users=users,
            url=url,
        )

    @classmethod
    def danger(cls, *, title: str, message: str, user=None, users=None, url: str = ""):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_DANGER,
            user=user,
            users=users,
            url=url,
        )

    @classmethod
    def info(cls, *, title: str, message: str, user=None, users=None, url: str = ""):
        return cls.notify(
            title=title,
            message=message,
            level=cls.LEVEL_INFO,
            user=user,
            users=users,
            url=url,
        )