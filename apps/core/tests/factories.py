from __future__ import annotations

from datetime import date, time
from itertools import count
from typing import Any

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.hr.models import Employee
from apps.locations.models import Door, Zone
from apps.scheduling.models import ShiftPlan, ShiftType


User = get_user_model()


class Sequence:
    """
    مولد قيم متسلسلة لتجنب تضارب البيانات داخل الاختبارات.
    """

    def __init__(
        self,
        *,
        start: int = 1,
    ) -> None:
        self._counter = count(start)

    def next(self) -> int:
        return next(self._counter)


user_sequence = Sequence(start=1)
employee_sequence = Sequence(start=10000)
zone_sequence = Sequence(start=1)
door_sequence = Sequence(start=1)
shift_type_sequence = Sequence(start=1)


def _model_field_names(model) -> set[str]:
    """
    إرجاع أسماء الحقول الفعلية لنموذج Django.

    يساعد ذلك في جعل المصانع قابلة للعمل حتى مع اختلاف
    بعض الحقول بين إصدارات النماذج.
    """

    return {
        field.name
        for field in model._meta.fields
    }


def _filter_valid_fields(
    model,
    data: dict[str, Any],
) -> dict[str, Any]:
    """
    حذف أي قيمة لا يقابلها حقل فعلي داخل النموذج.
    """

    field_names = _model_field_names(
        model
    )

    return {
        key: value
        for key, value in data.items()
        if key in field_names
    }


def create_user(
    *,
    username: str | None = None,
    password: str = "StrongTestPassword123!",
    email: str | None = None,
    is_staff: bool = False,
    is_superuser: bool = False,
    is_active: bool = True,
    **extra_fields: Any,
):
    """
    إنشاء مستخدم صالح للاختبارات.
    """

    sequence_value = user_sequence.next()

    username = (
        username
        or f"test_user_{sequence_value}"
    )

    email = (
        email
        or f"{username}@example.com"
    )

    if is_superuser:
        return User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            **extra_fields,
        )

    return User.objects.create_user(
        username=username,
        email=email,
        password=password,
        is_staff=is_staff,
        is_active=is_active,
        **extra_fields,
    )


def create_employee(
    *,
    full_name: str | None = None,
    employee_number: str | None = None,
    user=None,
    is_active: bool = True,
    **overrides: Any,
) -> Employee:
    """
    إنشاء موظف مع مراعاة اختلاف حقول نموذج Employee.

    الحقول الاختيارية لا تُمرر إلا إذا كانت موجودة
    فعليًا داخل النموذج.
    """

    sequence_value = employee_sequence.next()

    model_fields = _model_field_names(
        Employee
    )

    data: dict[str, Any] = {
        "full_name": (
            full_name
            or f"موظف اختبار {sequence_value}"
        ),
        "employee_number": (
            employee_number
            or str(sequence_value)
        ),
    }

    optional_defaults = {
        "user": user,
        "is_active": is_active,
        "work_status": "active",
        "can_work_on_doors": True,
        "can_execute_maintenance": False,
        "phone_number": (
            f"050{sequence_value:07d}"[-10:]
        ),
        "national_id": (
            f"10{sequence_value:08d}"[-10:]
        ),
    }

    for field_name, value in optional_defaults.items():
        if (
            field_name in model_fields
            and value is not None
        ):
            data[field_name] = value

    data.update(
        overrides
    )

    valid_data = _filter_valid_fields(
        Employee,
        data,
    )

    employee = Employee(
        **valid_data
    )

    employee.full_clean()
    employee.save()

    return employee


def create_shift_type(
    *,
    name: str | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
    is_active: bool = True,
    **overrides: Any,
) -> ShiftType:
    """
    إنشاء نوع وردية صالح للاختبارات.
    """

    sequence_value = shift_type_sequence.next()

    model_fields = _model_field_names(
        ShiftType
    )

    data: dict[str, Any] = {
        "name": (
            name
            or f"وردية اختبار {sequence_value}"
        ),
    }

    optional_defaults = {
        "start_time": (
            start_time
            or time(8, 0)
        ),
        "end_time": (
            end_time
            or time(16, 0)
        ),
        "is_active": is_active,
        "ordering": sequence_value,
    }

    for field_name, value in optional_defaults.items():
        if field_name in model_fields:
            data[field_name] = value

    data.update(
        overrides
    )

    valid_data = _filter_valid_fields(
        ShiftType,
        data,
    )

    shift_type = ShiftType(
        **valid_data
    )

    shift_type.full_clean()
    shift_type.save()

    return shift_type


def create_shift_plan(
    *,
    shift_type: ShiftType | None = None,
    shift_date: date | None = None,
    is_active: bool = False,
    is_finished: bool = False,
    **overrides: Any,
) -> ShiftPlan:
    """
    إنشاء خطة وردية صالحة للاختبارات.

    يعالج الحقول الإلزامية الأكثر شيوعًا مثل:
    - shift_type
    - date
    - is_active
    - is_finished

    ولا يمرر إلا الحقول الموجودة فعليًا في النموذج.
    """

    shift_type = (
        shift_type
        or create_shift_type()
    )

    model_fields = _model_field_names(
        ShiftPlan
    )

    data: dict[str, Any] = {}

    optional_defaults = {
        "shift_type": shift_type,
        "date": (
            shift_date
            or timezone.localdate()
        ),
        "is_active": is_active,
        "is_finished": is_finished,
    }

    for field_name, value in optional_defaults.items():
        if field_name in model_fields:
            data[field_name] = value

    data.update(
        overrides
    )

    valid_data = _filter_valid_fields(
        ShiftPlan,
        data,
    )

    shift_plan = ShiftPlan(
        **valid_data
    )

    shift_plan.full_clean()
    shift_plan.save()

    return shift_plan


def create_zone(
    *,
    name: str | None = None,
    **overrides: Any,
) -> Zone:
    """
    إنشاء منطقة صالحة للاختبارات.
    """

    sequence_value = zone_sequence.next()

    data: dict[str, Any] = {
        "name": (
            name
            or f"منطقة اختبار {sequence_value}"
        ),
    }

    data.update(
        overrides
    )

    valid_data = _filter_valid_fields(
        Zone,
        data,
    )

    zone = Zone(
        **valid_data
    )

    zone.full_clean()
    zone.save()

    return zone


def create_door(
    *,
    door_number: int | None = None,
    zone: Zone | None = None,
    is_active: bool = True,
    **overrides: Any,
) -> Door:
    """
    إنشاء باب صالح للاختبارات.

    رقم الباب يجب أن يكون بين 1 و41.
    """

    if door_number is None:
        door_number = door_sequence.next()

    door_number = int(
        door_number
    )

    if not 1 <= door_number <= 41:
        raise ValueError(
            "رقم باب الاختبار يجب أن يكون بين 1 و41."
        )

    zone = (
        zone
        or create_zone()
    )

    model_fields = _model_field_names(
        Door
    )

    data: dict[str, Any] = {
        "door_number": door_number,
        "zone": zone,
        "is_active": is_active,
    }

    if "name" in model_fields:
        data["name"] = (
            f"باب {door_number}"
        )

    data.update(
        overrides
    )

    valid_data = _filter_valid_fields(
        Door,
        data,
    )

    door = Door(
        **valid_data
    )

    door.full_clean()
    door.save()

    return door