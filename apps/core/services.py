from __future__ import annotations

from django.db import transaction

from apps.dashboard.activity_logger import log_activity


class BaseService:
    """
    الخدمة الأساسية لجميع خدمات المنصة.
    """

    module_name = "النظام"

    @classmethod
    def log(
        cls,
        *,
        request,
        action,
        description: str,
    ):
        return log_activity(
            user=request.user if request else None,
            module=cls.module_name,
            action=action,
            description=description,
            request=request,
        )

    @staticmethod
    def atomic():
        return transaction.atomic()