from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.breaks.models import Break
from apps.communications.services.assignment_message_service import (
    dispatch_assignment_message,
)
from apps.core.notification_service import NotificationService
from apps.hr.models import Employee
from apps.locations.door_directions import get_door_sort_order, normalize_door_code
from apps.locations.models import Door

from .assignment_history_service import (
    assignment_snapshot,
    record_assignment_created,
    update_assignment_with_history,
)
from .models import DoorAssignment


logger = logging.getLogger(__name__)


def _safe_dispatch_assignment_message(
    *,
    assignment_id,
    event_type,
    actor=None,
    channels=("sms", "whatsapp"),
    correlation_id=None,
):
    try:
        assignment = (
            DoorAssignment.objects
            .select_related(
                "employee",
                "employee__user",
                "door",
                "shift_plan",
                "shift_plan__shift_type",
            )
            .get(pk=assignment_id)
        )
        dispatch_assignment_message(
            assignment,
            channels=channels,
            actor=actor,
            event_type=event_type,
            correlation_id=correlation_id,
        )
    except Exception:
        logger.exception(
            "Assignment notification dispatch failed safely.",
            extra={
                "assignment_id": assignment_id,
                "event_type": event_type,
            },
        )


def _schedule_assignment_notification(
    *,
    assignment_id,
    event_type,
    actor=None,
    channels=("sms", "whatsapp"),
    correlation_id=None,
):
    callback = lambda: _safe_dispatch_assignment_message(
        assignment_id=assignment_id,
        event_type=event_type,
        actor=actor,
        channels=channels,
        correlation_id=correlation_id,
    )
    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(callback)
        return
    callback()


REST_DAY_MAP = {
    Break.RestDays.FRIDAY_SATURDAY: {4, 5},
    Break.RestDays.SATURDAY_SUNDAY: {5, 6},
    Break.RestDays.SUNDAY_MONDAY: {6, 0},
    Break.RestDays.MONDAY_TUESDAY: {0, 1},
    Break.RestDays.TUESDAY_WEDNESDAY: {1, 2},
    Break.RestDays.WEDNESDAY_THURSDAY: {2, 3},
    Break.RestDays.THURSDAY_FRIDAY: {3, 4},
}


@dataclass
class DistributionReport:
    """
    نتيجة فحص حالة توزيع الوردية.
    """

    total_doors: int = 0
    covered_doors: int = 0
    uncovered_doors: int = 0

    doors_without_supervisor: int = 0
    doors_without_monitor: int = 0

    available_employees: int = 0
    employees_on_break: int = 0

    total_assignments: int = 0

    coverage_percent: int = 0
    quality_score: int = 0
    quality_label: str = "غير مكتمل"

    warnings: list[str] = field(
        default_factory=list,
    )

    suggestions: list[str] = field(
        default_factory=list,
    )


class DistributionService:
    """
    المصدر الرسمي لجميع عمليات توزيع موظفي الأبواب.

    مسؤول عن:
    - التحقق من صلاحية التوزيع.
    - إنشاء التوزيع.
    - إلغاء التوزيع.
    - توزيع الموظفين تلقائيًا.
    - فحص جودة التوزيع.
    - إعداد وتنفيذ إعادة التوازن.
    - تسجيل جميع العمليات في سجل التدقيق المركزي.
    """

    @staticmethod
    def operational_doors():
        """Official operative doors using the canonical text-safe codes and sort order."""
        return (
            Door.objects
            .filter(
                is_active=True,
            )
            .exclude(
                name__iexact="السلام",
            )
            .order_by(
                "sort_order",
                "door_number",
            )
        )

    @staticmethod
    def shift_date(shift_plan) -> date:
        """
        استخراج تاريخ الوردية مع دعم أكثر من اسم محتمل للحقل.
        """
        for field_name in (
            "date",
            "shift_date",
            "start_date",
        ):
            value = getattr(
                shift_plan,
                field_name,
                None,
            )

            if value:
                if hasattr(value, "date"):
                    return value.date()

                return value

        return date.today()

    @staticmethod
    def _shift_datetime_range(
        shift_plan,
    ) -> tuple[datetime, datetime] | None:
        """
        إرجاع نطاق الوردية بالوقت الكامل مع دعم فاصل الأوقات
        من الوردية أو نوع الوردية عند وجود قيم مفقودة.
        """
        if not getattr(
            shift_plan,
            "date",
            None,
        ):
            return None

        if getattr(
            shift_plan,
            "start_time",
            None,
        ) is None:
            shift_type = getattr(
                shift_plan,
                "shift_type",
                None,
            )
            if shift_type is not None:
                start_time = getattr(
                    shift_type,
                    "start_time",
                    None,
                )
            else:
                start_time = None
        else:
            start_time = shift_plan.start_time

        if getattr(
            shift_plan,
            "end_time",
            None,
        ) is None:
            shift_type = getattr(
                shift_plan,
                "shift_type",
                None,
            )
            if shift_type is not None:
                end_time = getattr(
                    shift_type,
                    "end_time",
                    None,
                )
            else:
                end_time = None
        else:
            end_time = shift_plan.end_time

        if start_time is None or end_time is None:
            return None

        start_datetime = timezone.make_aware(
            datetime.combine(
                shift_plan.date,
                start_time,
            ),
            timezone.get_current_timezone(),
        )

        crosses_midnight = bool(
            getattr(
                shift_plan,
                "crosses_midnight",
                False,
            )
            or end_time <= start_time
        )

        end_date = (
            shift_plan.date + timedelta(days=1)
            if crosses_midnight
            else shift_plan.date
        )
        end_datetime = timezone.make_aware(
            datetime.combine(
                end_date,
                end_time,
            ),
            timezone.get_current_timezone(),
        )

        return start_datetime, end_datetime

    @classmethod
    def _has_overlap_with_other_active_shift(
        cls,
        *,
        employee,
        shift_plan,
        exclude_pk=None,
    ) -> bool:
        """
        تحديد ما إذا كان الموظف لديه وردية أخرى نشطة
        تتداخل زمنياً مع هذه الوردية.
        """
        candidate_range = cls._shift_datetime_range(
            shift_plan,
        )

        if candidate_range is None:
            return False

        candidate_start, candidate_end = candidate_range

        active_assignments = (
            DoorAssignment.objects
            .filter(
                employee=employee,
                is_active=True,
            )
            .select_related(
                "shift_plan",
                "shift_plan__shift_type",
            )
        )

        if exclude_pk:
            active_assignments = active_assignments.exclude(
                pk=exclude_pk,
            )

        for assignment in active_assignments:
            if assignment.shift_plan_id == getattr(
                shift_plan,
                "pk",
                None,
            ):
                continue

            other_range = cls._shift_datetime_range(
                assignment.shift_plan,
            )

            if other_range is None:
                continue

            other_start, other_end = other_range

            if (
                candidate_start < other_end
                and candidate_end > other_start
            ):
                return True

        return False

    @classmethod
    def employee_is_on_break(
        cls,
        *,
        employee,
        shift_plan,
    ) -> bool:
        """
        تحديد هل الموظف في راحته الأسبوعية في تاريخ الوردية.
        """
        shift_type = getattr(
            shift_plan,
            "shift_type",
            None,
        )

        if not shift_type:
            return False

        weekly_break = (
            Break.objects
            .filter(
                employee=employee,
                shift_type=shift_type,
                is_active=True,
            )
            .only(
                "rest_days",
            )
            .first()
        )

        if not weekly_break:
            return False

        weekdays = REST_DAY_MAP.get(
            weekly_break.rest_days,
            set(),
        )

        return (
            cls.shift_date(
                shift_plan,
            ).weekday()
            in weekdays
        )

    @classmethod
    def validate_assignment(
        cls,
        *,
        shift_plan,
        employee,
        door,
        role,
        exclude_pk=None,
    ):
        """
        التحقق من جميع قواعد التوزيع قبل الحفظ.
        """
        errors = []

        employee_section = str(
            getattr(employee, "operational_section", "")
            or ""
        ).strip().lower()

        if employee_section not in {
            DoorAssignment.AssignmentSection.MALE,
            DoorAssignment.AssignmentSection.FEMALE,
        }:
            errors.append(
                "يجب تحديد القسم التشغيلي للموظف قبل التوزيع."
            )

        if not getattr(
            shift_plan,
            "is_active",
            False,
        ):
            errors.append(
                "لا يمكن التوزيع على وردية غير نشطة."
            )

        if not employee.is_available_for_assignment:
            errors.append(
                "الموظف غير متاح للتسكين على الأبواب."
            )

        if cls.employee_is_on_break(
            employee=employee,
            shift_plan=shift_plan,
        ):
            errors.append(
                "لا يمكن توزيع الموظف في يوم راحته الأسبوعية."
            )

        if (
            role == DoorAssignment.Role.TECHNICIAN
            and not employee.can_execute_maintenance
        ):
            errors.append(
                "الموظف ليس ضمن فريق الصيانة."
            )

        if not getattr(
            door,
            "is_active",
            False,
        ):
            errors.append(
                "لا يمكن التوزيع على باب غير نشط."
            )

        door_number = getattr(
            door,
            "door_number",
            None,
        )

        try:
            normalized_code = normalize_door_code(door_number)
            get_door_sort_order(normalized_code)
        except ValidationError:
            errors.append(
                "الباب خارج النطاق التشغيلي المعتمد أو غير مدعوم في الكتالوج الرسمي."
            )

        door_section = getattr(
            door,
            "operational_section",
            None,
        )

        if (
            employee_section
            == DoorAssignment.AssignmentSection.MALE
            and door_section
            not in {
                Door.OperationalSection.MALE,
                Door.OperationalSection.SHARED,
            }
        ):
            errors.append(
                "لا يمكن توزيع الموظف الرجالي على باب نسائي."
            )

        if (
            employee_section
            == DoorAssignment.AssignmentSection.FEMALE
            and door_section
            not in {
                Door.OperationalSection.FEMALE,
                Door.OperationalSection.SHARED,
            }
        ):
            errors.append(
                "لا يمكن توزيع الموظفة على باب رجالي."
            )

        duplicate_assignment = (
            DoorAssignment.objects
            .filter(
                shift_plan=shift_plan,
                employee=employee,
                is_active=True,
            )
        )

        if exclude_pk:
            duplicate_assignment = (
                duplicate_assignment.exclude(
                    pk=exclude_pk,
                )
            )

        if duplicate_assignment.exists():
            errors.append(
                "الموظف موزع مسبقًا في هذه الوردية."
            )

        if cls._has_overlap_with_other_active_shift(
            employee=employee,
            shift_plan=shift_plan,
            exclude_pk=exclude_pk,
        ):
            errors.append(
                "الموظف لديه وردية متعارضة في نفس الفترة الزمنية."
            )

        if role == DoorAssignment.Role.SUPERVISOR:
            supervisor_assignment = (
                DoorAssignment.objects
                .filter(
                    shift_plan=shift_plan,
                    door=door,
                    section=employee_section,
                    is_active=True,
                    is_supervisor=True,
                )
            )

            if exclude_pk:
                supervisor_assignment = (
                    supervisor_assignment.exclude(
                        pk=exclude_pk,
                    )
                )

            if supervisor_assignment.exists():
                errors.append(
                    "يوجد مشرف نشط لهذا الباب بالفعل."
                )

        if errors:
            raise ValidationError(
                errors,
            )

    @classmethod
    @transaction.atomic
    def create_assignment(
        cls,
        *,
        shift_plan,
        employee,
        door,
        role,
        section=None,
        assigned_by=None,
        notes="",
        history_reason="",
        request=None,
    ):
        """
        إنشاء توزيع جديد وتسجيله في audit.AssignmentHistory.
        """
        employee_section = str(
            section
            or getattr(employee, "operational_section", "")
            or ""
        ).strip().lower()

        if employee_section != str(
            getattr(employee, "operational_section", "")
            or ""
        ).strip().lower():
            raise ValidationError(
                "قسم التسكين لا يطابق قسم الموظف."
            )

        cls.validate_assignment(
            shift_plan=shift_plan,
            employee=employee,
            door=door,
            role=role,
        )

        try:
            assignment = DoorAssignment.objects.create(
                shift_plan=shift_plan,
                door=door,
                employee=employee,
                section=employee_section,
                role=role,
                is_supervisor=(
                    role
                    == DoorAssignment.Role.SUPERVISOR
                ),
                is_active=True,
                notes=notes,
                assigned_by=assigned_by,
            )

        except IntegrityError as error:
            raise ValidationError(
                "تعذر إنشاء التوزيع بسبب تعارض أو تكرار في البيانات."
            ) from error

        record_assignment_created(
            assignment=assignment,
            request=request,
            user=assigned_by,
            reason=(
                history_reason
                or notes
                or "إنشاء توزيع موظف"
            ),
        )

        NotificationService.success(
            title="تكليف جديد",
            message=(
                f"القسم: {assignment.get_section_display()} | "
                f"الباب: {door.door_number} | "
                f"الوردية: {shift_plan.shift_type.name} | "
                f"الموظف: {employee.full_name} | "
                f"الدور: {assignment.get_role_display()} | "
                "الحالة: تم الإرسال"
            ),
            users=get_user_model().objects.filter(is_active=True),
            url="/distribution/",
            assignment=assignment,
        )

        _schedule_assignment_notification(
            assignment_id=assignment.pk,
            event_type="assignment_created",
            actor=assigned_by,
            correlation_id=f"assignment:{assignment.pk}:created",
        )

        return assignment

    @classmethod
    @transaction.atomic
    def deactivate_assignment(
        cls,
        *,
        assignment,
        performed_by=None,
        reason="",
        request=None,
    ):
        """
        إلغاء توزيع نشط دون حذف السجل.
        """
        assignment = (
            DoorAssignment.objects
            .select_for_update()
            .get(
                pk=assignment.pk,
            )
        )

        if not assignment.is_active:
            raise ValidationError(
                "هذا التوزيع ملغى مسبقًا."
            )

        updated_assignment, changed = (
            update_assignment_with_history(
                assignment=assignment,
                changes={
                    "is_active": False,
                },
                request=request,
                user=performed_by,
                reason=(
                    reason
                    or "إلغاء التوزيع يدويًا"
                ),
            )
        )

        if not changed:
            raise ValidationError(
                "لم يتم إجراء أي تغيير على التوزيع."
            )

        return updated_assignment

    @classmethod
    def eligible_employees(
        cls,
        *,
        shift_plan,
    ):
        """
        الموظفون المؤهلون وغير الموزعين في الوردية.
        """
        employees = (
            Employee.objects
            .filter(
                is_active=True,
                work_status=Employee.WorkStatus.ACTIVE,
                can_work_on_doors=True,
                operational_section__in=(
                    Employee.OperationalSection.MALE,
                    Employee.OperationalSection.FEMALE,
                ),
            )
            .exclude(
                door_assignments__shift_plan=shift_plan,
                door_assignments__is_active=True,
            )
            .order_by(
                "employee_number",
            )
            .distinct()
        )

        return [
            employee
            for employee in employees
            if not cls.employee_is_on_break(
                employee=employee,
                shift_plan=shift_plan,
            )
        ]

    @staticmethod
    def infer_role(employee):
        """
        استنتاج الدور التشغيلي الأنسب للموظف.
        """
        supervisor_titles = {
            Employee.JobTitle.FAJR_SUPERVISOR,
            Employee.JobTitle.DUHA_SUPERVISOR,
            Employee.JobTitle.EVENING_SUPERVISOR,
            Employee.JobTitle.SUPPORT_SUPERVISOR,
            Employee.JobTitle.FAJR_DEPUTY,
            Employee.JobTitle.DUHA_DEPUTY,
            Employee.JobTitle.EVENING_DEPUTY,
            Employee.JobTitle.DOORS_HEAD,
            Employee.JobTitle.DOORS_DEPUTY,
        }

        if employee.job_title in supervisor_titles:
            return DoorAssignment.Role.SUPERVISOR

        if (
            employee.can_execute_maintenance
            or employee.job_title
            == Employee.JobTitle.TECHNICIAN
        ):
            return DoorAssignment.Role.TECHNICIAN

        if (
            employee.job_title
            == Employee.JobTitle.MONITOR
        ):
            return DoorAssignment.Role.MONITOR

        return DoorAssignment.Role.SUPPORT

    @classmethod
    def _door_loads(
        cls,
        shift_plan,
    ):
        """
        إرجاع الأبواب مع أعداد التوزيعات الحالية.
        """
        return list(
            cls.operational_doors()
            .annotate(
                total_count=Count(
                    "assignments",
                    filter=Q(
                        assignments__shift_plan=shift_plan,
                        assignments__is_active=True,
                    ),
                    distinct=True,
                ),
                supervisor_count=Count(
                    "assignments",
                    filter=Q(
                        assignments__shift_plan=shift_plan,
                        assignments__is_active=True,
                        assignments__is_supervisor=True,
                    ),
                    distinct=True,
                ),
                monitor_count=Count(
                    "assignments",
                    filter=Q(
                        assignments__shift_plan=shift_plan,
                        assignments__is_active=True,
                        assignments__role=(
                            DoorAssignment.Role.MONITOR
                        ),
                    ),
                    distinct=True,
                ),
            )
            .order_by(
                "door_number",
            )
        )

    @staticmethod
    def _door_supports_employee(
        *,
        door,
        employee,
    ) -> bool:
        """تقييد التوزيع الآلي بقسم الموظف وتصنيف الباب."""
        employee_section = str(
            getattr(employee, "operational_section", "")
            or ""
        ).strip().lower()

        if employee_section == DoorAssignment.AssignmentSection.MALE:
            return door.operational_section in {
                Door.OperationalSection.MALE,
                Door.OperationalSection.SHARED,
            }

        if employee_section == DoorAssignment.AssignmentSection.FEMALE:
            return door.operational_section in {
                Door.OperationalSection.FEMALE,
                Door.OperationalSection.SHARED,
            }

        return False

    @classmethod
    @transaction.atomic
    def auto_assign(
        cls,
        *,
        shift_plan,
        performed_by=None,
        limit=None,
        request=None,
    ):
        """
        توزيع الموظفين المتاحين تلقائيًا.
        """
        employees = cls.eligible_employees(
            shift_plan=shift_plan,
        )

        if limit:
            employees = employees[:limit]

        created = []
        skipped = []

        for employee in employees:
            role = cls.infer_role(
                employee,
            )

            doors = cls._door_loads(
                shift_plan,
            )

            if role == DoorAssignment.Role.SUPERVISOR:
                supervisor_door_ids = set(
                    DoorAssignment.objects.filter(
                        shift_plan=shift_plan,
                        section=employee.operational_section,
                        is_active=True,
                        is_supervisor=True,
                    ).values_list(
                        "door_id",
                        flat=True,
                    )
                )
                candidates = [
                    door
                    for door in doors
                    if door.pk not in supervisor_door_ids
                    and cls._door_supports_employee(
                        door=door,
                        employee=employee,
                    )
                ]

            elif role == DoorAssignment.Role.MONITOR:
                candidates = sorted(
                    [
                        door
                        for door in doors
                        if cls._door_supports_employee(
                            door=door,
                            employee=employee,
                        )
                    ],
                    key=lambda door: (
                        door.monitor_count > 0,
                        door.monitor_count,
                        door.total_count,
                        door.door_number,
                    ),
                )

            else:
                candidates = sorted(
                    [
                        door
                        for door in doors
                        if cls._door_supports_employee(
                            door=door,
                            employee=employee,
                        )
                    ],
                    key=lambda door: (
                        door.total_count,
                        door.door_number,
                    ),
                )

            if not candidates:
                skipped.append(
                    employee.full_name,
                )
                continue

            selected_door = candidates[0]

            try:
                assignment = cls.create_assignment(
                    shift_plan=shift_plan,
                    employee=employee,
                    door=selected_door,
                    role=role,
                    section=employee.operational_section,
                    assigned_by=performed_by,
                    history_reason=(
                        "تنفيذ محرك التوزيع التلقائي"
                    ),
                    request=request,
                )

                created.append(
                    assignment,
                )

            except ValidationError:
                skipped.append(
                    employee.full_name,
                )

        return {
            "created": created,
            "skipped": skipped,
        }

    @classmethod
    def report(
        cls,
        *,
        shift_plan,
    ):
        """
        إنشاء تقرير جودة وتغطية الوردية.
        """
        doors = cls._door_loads(
            shift_plan,
        )

        assignments = (
            DoorAssignment.objects
            .filter(
                shift_plan=shift_plan,
                is_active=True,
            )
        )

        total_doors = len(
            doors,
        )

        covered_doors = sum(
            1
            for door in doors
            if door.total_count > 0
        )

        doors_without_supervisor = [
            door
            for door in doors
            if door.supervisor_count == 0
        ]

        doors_without_monitor = [
            door
            for door in doors
            if door.monitor_count == 0
        ]

        active_employees = (
            Employee.objects
            .filter(
                is_active=True,
                work_status=Employee.WorkStatus.ACTIVE,
                can_work_on_doors=True,
            )
            .distinct()
        )

        employees_on_break = sum(
            1
            for employee in active_employees
            if cls.employee_is_on_break(
                employee=employee,
                shift_plan=shift_plan,
            )
        )

        available_employees = len(
            cls.eligible_employees(
                shift_plan=shift_plan,
            )
        )

        coverage_percent = (
            round(
                (
                    covered_doors
                    / total_doors
                )
                * 100
            )
            if total_doors
            else 0
        )

        supervisor_percent = (
            round(
                (
                    (
                        total_doors
                        - len(
                            doors_without_supervisor
                        )
                    )
                    / total_doors
                )
                * 100
            )
            if total_doors
            else 0
        )

        monitor_percent = (
            round(
                (
                    (
                        total_doors
                        - len(
                            doors_without_monitor
                        )
                    )
                    / total_doors
                )
                * 100
            )
            if total_doors
            else 0
        )

        quality_score = round(
            coverage_percent * 0.40
            + supervisor_percent * 0.35
            + monitor_percent * 0.25
        )

        if quality_score >= 90:
            quality_label = "ممتاز"

        elif quality_score >= 75:
            quality_label = "جيد جدًا"

        elif quality_score >= 60:
            quality_label = "جيد"

        else:
            quality_label = "يحتاج تحسين"

        warnings = []
        suggestions = []

        if doors_without_supervisor:
            warnings.append(
                f"{len(doors_without_supervisor)} بابًا بلا مشرف."
            )

            suggestions.append(
                "ابدأ بتوزيع المشرفين على الأبواب غير المغطاة إشرافيًا."
            )

        if doors_without_monitor:
            warnings.append(
                f"{len(doors_without_monitor)} بابًا بلا مراقب."
            )

            suggestions.append(
                "وزع المراقبين على الأبواب الأقل تغطية."
            )

        if covered_doors < total_doors:
            warnings.append(
                f"{total_doors - covered_doors} بابًا دون أي موظف."
            )

        if available_employees:
            suggestions.append(
                f"يوجد {available_employees} موظفًا متاحًا للتوزيع التلقائي."
            )

        return DistributionReport(
            total_doors=total_doors,
            covered_doors=covered_doors,
            uncovered_doors=max(
                total_doors - covered_doors,
                0,
            ),
            doors_without_supervisor=len(
                doors_without_supervisor,
            ),
            doors_without_monitor=len(
                doors_without_monitor,
            ),
            available_employees=available_employees,
            employees_on_break=employees_on_break,
            total_assignments=assignments.count(),
            coverage_percent=coverage_percent,
            quality_score=quality_score,
            quality_label=quality_label,
            warnings=warnings,
            suggestions=suggestions,
        )

    @classmethod
    def build_rebalance_plan(
        cls,
        *,
        shift_plan,
    ):
        """
        إنشاء معاينة لإعادة التوازن دون تعديل قاعدة البيانات.
        """
        assignments = list(
            DoorAssignment.objects
            .select_related(
                "employee",
                "door",
                "shift_plan",
            )
            .filter(
                shift_plan=shift_plan,
                is_active=True,
            )
            .order_by(
                "role",
                "employee__employee_number",
            )
        )

        doors = list(
            cls.operational_doors(),
        )

        if not assignments:
            return {
                "moves": [],
                "total_moves": 0,
                "target_doors": [],
                "before_covered": 0,
                "after_covered": 0,
                "message": (
                    "لا توجد توزيعات نشطة لإعادة توازنها."
                ),
            }

        if not doors:
            raise ValidationError(
                "لا توجد أبواب تشغيلية نشطة."
            )

        supervisors = [
            assignment
            for assignment in assignments
            if assignment.role
            == DoorAssignment.Role.SUPERVISOR
        ]

        monitors = [
            assignment
            for assignment in assignments
            if assignment.role
            == DoorAssignment.Role.MONITOR
        ]

        technicians = [
            assignment
            for assignment in assignments
            if assignment.role
            == DoorAssignment.Role.TECHNICIAN
        ]

        support = [
            assignment
            for assignment in assignments
            if assignment.role
            == DoorAssignment.Role.SUPPORT
        ]

        target_count = max(
            len(supervisors),
            len(monitors),
            1,
        )

        target_count = min(
            target_count,
            len(doors),
            len(assignments),
        )

        target_doors = doors[
            :target_count
        ]

        loads = {
            door.id: 0
            for door in target_doors
        }

        planned = {}

        for index, assignment in enumerate(
            supervisors,
        ):
            compatible_doors = [
                door
                for door in target_doors
                if cls._door_supports_employee(
                    door=door,
                    employee=assignment.employee,
                )
            ]

            if not compatible_doors:
                continue

            door = compatible_doors[
                index % len(compatible_doors)
            ]

            planned[
                assignment.id
            ] = door

            loads[
                door.id
            ] += 1

        supervisor_door_ids = {
            planned[assignment.id].id
            for assignment in supervisors
            if assignment.id in planned
        }

        for assignment in monitors:
            compatible_doors = [
                door
                for door in target_doors
                if cls._door_supports_employee(
                    door=door,
                    employee=assignment.employee,
                )
            ]

            if not compatible_doors:
                continue

            door = min(
                compatible_doors,
                key=lambda item: (
                    item.id
                    not in supervisor_door_ids,
                    loads[item.id],
                    item.door_number,
                ),
            )

            planned[
                assignment.id
            ] = door

            loads[
                door.id
            ] += 1

        for assignment in (
            technicians
            + support
        ):
            compatible_doors = [
                door
                for door in target_doors
                if cls._door_supports_employee(
                    door=door,
                    employee=assignment.employee,
                )
            ]

            if not compatible_doors:
                continue

            door = min(
                compatible_doors,
                key=lambda item: (
                    loads[item.id],
                    item.door_number,
                ),
            )

            planned[
                assignment.id
            ] = door

            loads[
                door.id
            ] += 1

        moves = []

        for assignment in assignments:
            target_door = planned.get(
                assignment.id,
            )

            if target_door is None:
                continue

            changed = (
                assignment.door_id
                != target_door.id
            )

            moves.append(
                {
                    "assignment_id": (
                        assignment.id
                    ),
                    "employee_id": (
                        assignment.employee_id
                    ),
                    "employee_number": (
                        assignment.employee.employee_number
                    ),
                    "employee_name": (
                        assignment.employee.full_name
                    ),
                    "role": (
                        assignment.role
                    ),
                    "role_label": (
                        assignment.get_role_display()
                    ),
                    "old_door_id": (
                        assignment.door_id
                    ),
                    "old_door_number": (
                        assignment.door.door_number
                    ),
                    "new_door_id": (
                        target_door.id
                    ),
                    "new_door_number": (
                        target_door.door_number
                    ),
                    "changed": (
                        changed
                    ),
                }
            )

        before_covered = len(
            {
                assignment.door_id
                for assignment in assignments
            }
        )

        after_covered = len(
            {
                move["new_door_id"]
                for move in moves
            }
        )

        return {
            "moves": moves,
            "total_moves": sum(
                1
                for move in moves
                if move["changed"]
            ),
            "target_doors": [
                door.door_number
                for door in target_doors
            ],
            "before_covered": (
                before_covered
            ),
            "after_covered": (
                after_covered
            ),
            "message": (
                "لا توجد عمليات نقل مطلوبة؛ التوزيع متوازن بالفعل."
                if not any(
                    move["changed"]
                    for move in moves
                )
                else (
                    "تم إعداد خطة إعادة التوازن بنجاح."
                )
            ),
        }

    @classmethod
    @transaction.atomic
    def apply_rebalance(
        cls,
        *,
        shift_plan,
        performed_by=None,
        reason="",
        request=None,
    ):
        """
        تنفيذ خطة إعادة التوازن وتسجيل كل عملية نقل
        في audit.AssignmentHistory.
        """
        from apps.audit.services import (
            record_assignment_history,
        )

        plan = cls.build_rebalance_plan(
            shift_plan=shift_plan,
        )

        changed_moves = [
            move
            for move in plan["moves"]
            if move["changed"]
        ]

        if not changed_moves:
            return {
                **plan,
                "updated": 0,
            }

        assignment_ids = [
            move["assignment_id"]
            for move in plan["moves"]
        ]

        assignments = {
            assignment.id: assignment
            for assignment in (
                DoorAssignment.objects
                .select_for_update()
                .filter(
                    id__in=assignment_ids,
                    shift_plan=shift_plan,
                    is_active=True,
                )
            )
        }

        old_snapshots = {
            assignment_id: assignment_snapshot(
                assignment,
            )
            for assignment_id, assignment
            in assignments.items()
        }

        DoorAssignment.objects.filter(
            id__in=assignment_ids,
            role=DoorAssignment.Role.SUPERVISOR,
        ).update(
            is_supervisor=False,
        )

        updated = 0

        for move in plan["moves"]:
            assignment = assignments.get(
                move["assignment_id"],
            )

            if assignment is None:
                continue

            if not move["changed"]:
                continue

            old_door = assignment.door

            DoorAssignment.objects.filter(
                pk=assignment.pk,
            ).update(
                door_id=move["new_door_id"],
            )

            assignment.refresh_from_db()

            record_assignment_history(
                assignment=assignment,
                employee=assignment.employee,
                door=assignment.door,
                shift_plan=shift_plan,
                old_value=old_snapshots[
                    assignment.id
                ],
                new_value=assignment_snapshot(
                    assignment,
                ),
                request=request,
                user=performed_by,
                reason=(
                    reason
                    or (
                        "إعادة توازن التوزيع: "
                        f"نقل من باب "
                        f"{old_door.door_number} "
                        f"إلى باب "
                        f"{assignment.door.door_number}"
                    )
                ),
            )

            updated += 1

        DoorAssignment.objects.filter(
            id__in=assignment_ids,
            role=DoorAssignment.Role.SUPERVISOR,
        ).update(
            is_supervisor=True,
        )

        return {
            **plan,
            "updated": updated,
        }

    @classmethod
    def rebalance(
        cls,
        *,
        shift_plan,
        performed_by=None,
        request=None,
    ):
        """
        اسم توافقي لخدمة إعادة التوازن.
        """
        return cls.apply_rebalance(
            shift_plan=shift_plan,
            performed_by=performed_by,
            request=request,
        )


def auto_assign_employee_to_door(
    *,
    shift_plan,
    employee,
    assigned_by=None,
    request=None,
):
    """
    دالة توافقية لتوزيع موظف واحد تلقائيًا.
    """
    role = DistributionService.infer_role(
        employee,
    )

    doors = DistributionService._door_loads(
        shift_plan,
    )

    if not doors:
        raise ValidationError(
            "لا توجد أبواب نشطة للتوزيع."
        )

    if role == DoorAssignment.Role.SUPERVISOR:
        candidates = [
            door
            for door in doors
            if door.supervisor_count == 0
            and DistributionService._door_supports_employee(
                door=door,
                employee=employee,
            )
        ]

    elif role == DoorAssignment.Role.MONITOR:
        candidates = sorted(
            [
                door
                for door in doors
                if DistributionService._door_supports_employee(
                    door=door,
                    employee=employee,
                )
            ],
            key=lambda door: (
                door.monitor_count > 0,
                door.monitor_count,
                door.total_count,
                door.door_number,
            ),
        )

    else:
        candidates = sorted(
            [
                door
                for door in doors
                if DistributionService._door_supports_employee(
                    door=door,
                    employee=employee,
                )
            ],
            key=lambda door: (
                door.total_count,
                door.door_number,
            ),
        )

    if not candidates:
        raise ValidationError(
            "لا يوجد باب مناسب للتوزيع."
        )

    return DistributionService.create_assignment(
        shift_plan=shift_plan,
        employee=employee,
        door=candidates[0],
        role=role,
        assigned_by=assigned_by,
        history_reason=(
            "توزيع تلقائي لموظف واحد"
        ),
        request=request,
    )