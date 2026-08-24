from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.distribution.models import DoorAssignment
from apps.locations.door_directions import get_door_sort_order, normalize_door_code
from apps.locations.models import Door
from apps.scheduling.models import ShiftPlan


def _validate_operational_context(
    *,
    door_shift,
    assignment,
    section,
    errors,
):
    """Resolve and validate the section for a door operation record."""
    normalized_section = str(section or "").strip().lower()

    if assignment:
        if not door_shift:
            errors["assignment"] = (
                "لا يمكن ربط التسكين دون تحديد حالة الباب."
            )
        elif (
            assignment.shift_plan_id
            != door_shift.shift_plan_id
            or assignment.door.door_number
            != door_shift.door_number
        ):
            errors["assignment"] = (
                "التسكين لا يطابق الباب أو الوردية المحددة."
            )

        expected_section = assignment.section
    else:
        expected_section = getattr(
            door_shift,
            "section",
            "",
        ) if door_shift else ""

        if not expected_section and door_shift:
            door = (
                Door.objects
                .filter(
                    door_number=door_shift.door_number,
                )
                .first()
            )

            if door and door.operational_section != (
                Door.OperationalSection.SHARED
            ):
                expected_section = (
                    door.operational_section
                )

    if normalized_section and expected_section:
        if normalized_section != expected_section:
            errors["section"] = (
                "القسم المحدد لا يطابق قسم التسكين أو الباب."
            )

    if not normalized_section and expected_section:
        normalized_section = expected_section

    if not door_shift and not assignment:
        return normalized_section

    if normalized_section not in {
        "male",
        "female",
    }:
        errors["section"] = (
            "يجب تحديد القسم صراحةً للباب المشترك."
        )

    return normalized_section


class DoorShift(models.Model):
    class DoorState(models.TextChoices):
        OPEN = "open", "مفتوح"
        CLOSED = "closed", "مغلق"
        MAINTENANCE = "maintenance", "تحت صيانة"
        SECURED = "secured", "مؤمّن"

    door_number = models.CharField(
        max_length=10,
        db_index=True,
        verbose_name="رقم الباب",
    )

    sort_order = models.PositiveSmallIntegerField(
        default=0,
        db_index=True,
        editable=False,
        verbose_name="ترتيب الباب الرسمي",
    )

    section = models.CharField(
        max_length=10,
        choices=(
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
        blank=True,
        default="",
        db_index=True,
        verbose_name="القسم التشغيلي",
    )

    shift_plan = models.ForeignKey(
        ShiftPlan,
        on_delete=models.CASCADE,
        related_name="door_shifts",
        verbose_name="الوردية",
        db_index=True,
    )

    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_doors",
        verbose_name="مشرف الباب المناوب",
    )

    state = models.CharField(
        max_length=20,
        choices=DoorState.choices,
        default=DoorState.OPEN,
        verbose_name="حالة الباب",
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="نشط",
        db_index=True,
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخر تحديث",
    )


    class Meta:
        ordering = ["sort_order", "door_number"]
        unique_together = ("door_number", "shift_plan")

        verbose_name = "حالة باب"
        verbose_name_plural = "حالات الأبواب"

        indexes = [
            models.Index(fields=["door_number"]),
            models.Index(fields=["state"]),
            models.Index(fields=["shift_plan"]),
            models.Index(fields=["is_active"]),
        ]

        permissions = [
            (
                "can_update_door_state",
                "يمكن تحديث حالة الباب",
            ),
            (
                "can_assign_door_supervisor",
                "يمكن تعيين مشرف الباب",
            ),
        ]

    def __str__(self):
        return (
            f"باب {self.door_number} - "
            f"{self.get_state_display()}"
        )

    def clean(self):
        super().clean()

        if self.door_number:
            self.door_number = normalize_door_code(self.door_number)
            self.sort_order = get_door_sort_order(self.door_number)

        door = (
            Door.objects
            .filter(door_number=self.door_number)
            .first()
        )

        door_section = (
            door.operational_section
            if door
            else Door.get_section_for_door_number(
                self.door_number,
            )
        )

        if door_section in {
            Door.OperationalSection.MALE,
            Door.OperationalSection.FEMALE,
        }:
            self.section = door_section

        if (
            self.shift_plan_id
            and not self.shift_plan.is_active
        ):
            raise ValidationError(
                "لا يمكن تعديل باب لوردية غير نشطة."
            )

    def save(self, *args, **kwargs):
        if self.door_number:
            self.door_number = normalize_door_code(self.door_number)
            self.sort_order = get_door_sort_order(self.door_number)

        door = (
            Door.objects
            .filter(door_number=self.door_number)
            .first()
        )
        door_section = (
            door.operational_section
            if door
            else Door.get_section_for_door_number(
                self.door_number,
            )
        )

        if door_section != Door.OperationalSection.SHARED:
            self.section = door_section

        super().save(*args, **kwargs)



class DoorCurrentState(models.Model):
    """
    المصدر الرسمي للحالة الحالية لكل باب.

    يبقى DoorShift مرتبطًا بالوردية، بينما يحتفظ هذا النموذج
    بالحالة الحالية للباب بصورة مستقلة عن تبدل الورديات.
    """

    class UpdateSource(models.TextChoices):
        OPERATIONS = "operations", "العمليات"
        MAINTENANCE = "maintenance", "الصيانة"
        SYSTEM = "system", "النظام"

    door = models.OneToOneField(
        "locations.Door",
        on_delete=models.CASCADE,
        related_name="current_state",
        verbose_name="الباب",
    )

    state = models.CharField(
        max_length=20,
        choices=DoorShift.DoorState.choices,
        default=DoorShift.DoorState.OPEN,
        db_index=True,
        verbose_name="الحالة الحالية",
    )

    notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات الحالة",
    )

    current_shift = models.ForeignKey(
        DoorShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_state_snapshots",
        verbose_name="سجل الباب في الوردية الحالية",
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_door_current_states",
        verbose_name="آخر تحديث بواسطة",
    )

    update_source = models.CharField(
        max_length=20,
        choices=UpdateSource.choices,
        default=UpdateSource.OPERATIONS,
        db_index=True,
        verbose_name="مصدر التحديث",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
        verbose_name="آخر تحديث",
    )

    class Meta:
        ordering = ["door__door_number"]
        verbose_name = "الحالة الحالية للباب"
        verbose_name_plural = "الحالات الحالية للأبواب"

        indexes = [
            models.Index(
                fields=["state"],
                name="door_current_state_idx",
            ),
            models.Index(
                fields=["update_source"],
                name="door_current_source_idx",
            ),
            models.Index(
                fields=["updated_at"],
                name="door_current_updated_idx",
            ),
        ]

        permissions = [
            (
                "can_view_all_current_door_states",
                "يمكن عرض جميع الحالات الحالية للأبواب",
            ),
        ]

    def __str__(self):
        return (
            f"{self.door} - "
            f"{self.get_state_display()}"
        )


class MaintenanceRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "جديد"
        APPROVED = "approved", "معتمد"
        ASSIGNED = "assigned", "محول للفريق الفني"
        IN_PROGRESS = "in_progress", "قيد التنفيذ"
        FIXED = "fixed", "تم الإصلاح"
        OPEN = "open", "مفتوح"
        DONE = "done", "منجز"
        CLOSED = "closed", "مغلق"

    class Priority(models.TextChoices):
        LOW = "low", "منخفضة"
        MEDIUM = "medium", "متوسطة"
        HIGH = "high", "عالية"
        URGENT = "urgent", "عاجلة"

    request_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        db_index=True,
        verbose_name="رقم الطلب",
    )

    door_shift = models.ForeignKey(
        DoorShift,
        on_delete=models.CASCADE,
        related_name="maintenance_requests",
        verbose_name="الباب",
        db_index=True,
    )

    assignment = models.ForeignKey(
        DoorAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests",
        verbose_name="التسكين المرتبط",
    )

    section = models.CharField(
        max_length=10,
        choices=(
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
        blank=True,
        default="",
        db_index=True,
        verbose_name="القسم التشغيلي",
    )

    description = models.TextField(
        verbose_name="وصف المشكلة",
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True,
        verbose_name="درجة الخطورة",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
        verbose_name="حالة الطلب",
    )

    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_maintenance_requests",
        verbose_name="الفني المكلف",
    )

    technician_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="اسم الفني المنفذ",
    )

    technician_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="رقم جوال الفني",
    )

    image = models.ImageField(
        upload_to="maintenance/",
        null=True,
        blank=True,
        verbose_name="صورة المشكلة",
    )

    before_image = models.ImageField(
        upload_to="maintenance/before/",
        null=True,
        blank=True,
        verbose_name="صورة قبل الإصلاح",
    )

    after_image = models.ImageField(
        upload_to="maintenance/after/",
        null=True,
        blank=True,
        verbose_name="صورة بعد الإصلاح",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_requests",
        verbose_name="المستخدم المنفذ للطلب",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_maintenance_requests",
        verbose_name="اعتمد بواسطة",
    )

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_by_maintenance_requests",
        verbose_name="حوّل بواسطة",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="تاريخ الإنشاء",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الاعتماد",
    )

    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ التحويل للفريق الفني",
    )

    planned_start_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت البدء المخطط",
    )

    source_incident = models.OneToOneField(
        "ops.Incident",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maintenance_request",
        verbose_name="البلاغ التشغيلي المصدر",
    )

    planned_end_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="وقت الانتهاء المخطط",
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ بدء التنفيذ",
    )

    fixed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإصلاح",
    )

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ الإغلاق",
    )

    estimated_minutes = models.PositiveIntegerField(
        default=120,
        verbose_name="المدة المتوقعة بالدقائق",
    )

    rating = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="تقييم الإصلاح",
    )

    closing_notes = models.TextField(
        blank=True,
        verbose_name="ملاحظات الإغلاق",
    ) 

    
    class Meta:
        ordering = ["-created_at"]

        verbose_name = "طلب صيانة"
        verbose_name_plural = "طلبات الصيانة"

        indexes = [
            models.Index(fields=["request_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["door_shift"]),
            models.Index(fields=["technician"]),
        ]

        permissions = [
            ("can_create_maintenance", "يمكن إنشاء طلب صيانة"),
            ("can_approve_maintenance", "يمكن اعتماد طلب صيانة"),
            ("can_assign_maintenance", "يمكن تحويل الطلب للفريق الفني"),
            ("can_update_maintenance_status", "يمكن تحديث حالة الطلب"),
            ("can_close_maintenance", "يمكن إغلاق طلب الصيانة"),
        ]

    def __str__(self):
        return (
            self.request_number
            or f"طلب صيانة #{self.pk}"
        )

    @property
    def processing_duration(self):
        end_time = self.closed_at or self.fixed_at

        if not end_time:
            return None

        return end_time - self.created_at

    @property
    def is_open_request(self):
        return self.status not in (
            self.Status.CLOSED,
            self.Status.DONE,
        )

    @property
    def planned_duration(self):
        if not self.planned_start_at or not self.planned_end_at:
            return None
        return self.planned_end_at - self.planned_start_at

    @property
    def planned_duration_minutes(self):
        duration = self.planned_duration
        return int(duration.total_seconds() // 60) if duration else None

    @property
    def actual_duration(self):
        end_time = self.closed_at or self.fixed_at
        if not self.started_at or not end_time:
            return None
        return end_time - self.started_at

    @property
    def is_schedule_overdue(self):
        if not self.planned_end_at or self.is_final_status:
            return False
        return timezone.now() > self.planned_end_at

    @property
    def is_final_status(self):
        return self.status in (
            self.Status.CLOSED,
            self.Status.DONE,
        )

    @property
    def elapsed_minutes(self):
        end = self.closed_at or timezone.now()

        return int(
            (end - self.created_at).total_seconds() / 60
        )

    @property
    def elapsed_text(self):

        minutes = self.elapsed_minutes

        if minutes < 60:
            return f"{minutes} دقيقة"

        hours = minutes // 60

        if hours < 24:
            return f"{hours} ساعة"

        return f"{hours // 24} يوم"

    @property
    def progress_percentage(self):

        mapping = {
            self.Status.NEW: 5,
            self.Status.APPROVED: 20,
            self.Status.ASSIGNED: 40,
            self.Status.IN_PROGRESS: 70,
            self.Status.FIXED: 90,
            self.Status.DONE: 100,
            self.Status.CLOSED: 100,
        }

        return mapping.get(self.status, 0)

    @property
    def status_color(self):

        colors = {
            self.Status.NEW: "primary",
            self.Status.APPROVED: "info",
            self.Status.ASSIGNED: "warning",
            self.Status.IN_PROGRESS: "warning",
            self.Status.FIXED: "success",
            self.Status.DONE: "success",
            self.Status.CLOSED: "secondary",
        }

        return colors.get(
            self.status,
            "secondary",
        )

    def clean(self):
        super().clean()

        errors = {}

        if bool(self.planned_start_at) != bool(self.planned_end_at):
            errors["planned_end_at"] = "يجب تحديد وقتي البدء والانتهاء المخططين معًا."
        elif (
            self.planned_start_at
            and self.planned_end_at
            and self.planned_end_at <= self.planned_start_at
        ):
            errors["planned_end_at"] = "يجب أن يكون وقت الانتهاء المخطط بعد وقت البدء المخطط."

        self.section = _validate_operational_context(
            door_shift=self.door_shift,
            assignment=self.assignment,
            section=self.section,
            errors=errors,
        )

        if errors:
            raise ValidationError(errors)

        if not self.door_shift.is_active:
            raise ValidationError(
                "الباب غير نشط."
            )

        if not self.door_shift.shift_plan.is_active:
            raise ValidationError(
                "الوردية غير نشطة."
            )

        if (
            self.status == self.Status.ASSIGNED
            and not self.technician
            and not self.technician_name
        ):
            raise ValidationError(
                "يجب تحديد الفني."
            )

        if (
            self.status == self.Status.CLOSED
            and not self.closing_notes
        ):
            raise ValidationError(
                "ملاحظات الإغلاق مطلوبة."
            )

        if not 0 <= self.rating <= 5:
            raise ValidationError(
                "التقييم يجب أن يكون بين 0 و 5."
            )

    def _generate_request_number(self):

        today = timezone.now().strftime("%Y%m%d")
        prefix = f"MR-{today}-"

        last = (
            MaintenanceRequest.objects
            .filter(
                request_number__startswith=prefix
            )
            .order_by("-request_number")
            .first()
        )

        if not last:
            return f"{prefix}001"

        try:
            number = int(
                last.request_number.split("-")[-1]
            )
            return f"{prefix}{number + 1:03d}"

        except Exception:
            return (
                f"{prefix}"
                f"{timezone.now().strftime('%H%M%S')}"
            )

    def save(self, *args, **kwargs):

        is_new = self.pk is None

        previous_status = None

        if not is_new:
            previous_status = (
                MaintenanceRequest.objects
                .only("status")
                .get(pk=self.pk)
                .status
            )

        if not self.request_number:
            self.request_number = (
                self._generate_request_number()
            )

        now = timezone.now()

        if previous_status != self.status:

            if (
                self.status == self.Status.APPROVED
                and not self.approved_at
            ):
                self.approved_at = now

            elif (
                self.status == self.Status.ASSIGNED
                and not self.assigned_at
            ):
                self.assigned_at = now

            elif (
                self.status == self.Status.IN_PROGRESS
                and not self.started_at
            ):
                self.started_at = now

            elif (
                self.status in (
                    self.Status.FIXED,
                    self.Status.DONE,
                )
                and not self.fixed_at
            ):
                self.fixed_at = now

            elif (
                self.status == self.Status.CLOSED
                and not self.closed_at
            ):
                self.closed_at = now

        super().save(*args, **kwargs)


class Incident(models.Model):

    class EscalationLevel(models.TextChoices):
        NONE = "none", "غير مصعّد"
        DEPARTMENT_HEAD = "department_head", "رئيس قسم الأبواب"
        GENERAL_MANAGER = "general_manager", "المدير العام"

    class IncidentType(models.TextChoices):
        DOOR_FAULT = "door_fault", "عطل باب"
        CROWDING = "crowding", "ازدحام"
        OPERATIONAL_VIOLATION = "operational_violation", "مخالفة تشغيلية"
        SECURITY = "security", "بلاغ أمني"
        CLEANING = "cleaning", "بلاغ نظافة"
        TECHNICAL = "technical", "بلاغ تقني"
        MAINTENANCE = "maintenance", "بلاغ صيانة"
        GENERAL = "general", "بلاغ عام"

    class Priority(models.TextChoices):
        LOW = "low", "منخفضة"
        MEDIUM = "medium", "متوسطة"
        HIGH = "high", "عالية"
        CRITICAL = "critical", "حرجة"

    class Status(models.TextChoices):
        NEW = "new", "جديد"
        IN_PROGRESS = "in_progress", "قيد المعالجة"
        FORWARDED = "forwarded", "تم التوجيه"
        RESOLVED = "resolved", "تم الحل"
        CLOSED = "closed", "مغلق"

    incident_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        db_index=True,
        verbose_name="رقم البلاغ",
    )

    shift_plan = models.ForeignKey(
        ShiftPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
    )

    door = models.ForeignKey(
        Door,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incidents",
        verbose_name="الباب المرتبط",
    )

    door_shift = models.ForeignKey(
        DoorShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
    )

    assignment = models.ForeignKey(
        DoorAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidents",
        verbose_name="التسكين المرتبط",
    )

    section = models.CharField(
        max_length=10,
        choices=(
            ("male", "رجالي"),
            ("female", "نسائي"),
        ),
        blank=True,
        default="",
        db_index=True,
        verbose_name="القسم التشغيلي",
    )

    incident_type = models.CharField(
        max_length=40,
        choices=IncidentType.choices,
        default=IncidentType.GENERAL,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    description = models.TextField()

    reported_by_name = models.CharField(
        max_length=150,
        blank=True,
    )

    assigned_to_name = models.CharField(
        max_length=150,
        blank=True,
    )

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_operational_incidents",
        verbose_name="محول إلى",
    )

    escalation_level = models.CharField(
        max_length=30,
        choices=EscalationLevel.choices,
        default=EscalationLevel.NONE,
        db_index=True,
        verbose_name="مستوى التصعيد",
    )

    escalated_at = models.DateTimeField(null=True, blank=True)

    escalated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="escalated_operational_incidents",
    )

    escalation_note = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_incidents",
    )

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_incidents",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    closing_notes = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "بلاغ تشغيلي"
        verbose_name_plural = "البلاغات التشغيلية"

        indexes = [
            models.Index(fields=["incident_number"]),
            models.Index(fields=["incident_type"]),
            models.Index(fields=["priority"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.incident_number or "بلاغ"

    @property
    def is_open(self):
        return self.status not in (
            self.Status.RESOLVED,
            self.Status.CLOSED,
        )

    @property
    def processing_duration(self):
        if not self.closed_at:
            return None
        return self.closed_at - self.created_at

    def _generate_incident_number(self):
        today = timezone.now().strftime("%Y%m%d")
        prefix = f"INC-{today}-"

        last = (
            Incident.objects
            .filter(
                incident_number__startswith=prefix
            )
            .order_by("-incident_number")
            .first()
        )

        if not last or not last.incident_number:
            return f"{prefix}001"

        try:
            number = int(
                last.incident_number.split("-")[-1]
            )
            return f"{prefix}{number + 1:03d}"

        except (ValueError, IndexError):
            return (
                f"{prefix}"
                f"{timezone.now().strftime('%H%M%S')}"
            )

    def clean(self):
        super().clean()

        errors = {}

        self.section = _validate_operational_context(
            door_shift=self.door_shift,
            assignment=self.assignment,
            section=self.section,
            errors=errors,
        )

        if self.door_id:
            if not self.door.is_active:
                errors["door"] = "لا يمكن ربط البلاغ بباب غير نشط."

            door_section = self.door.operational_section
            if door_section != Door.OperationalSection.SHARED:
                if self.section and self.section != door_section:
                    errors["section"] = "قسم البلاغ لا يطابق قسم الباب المحدد."
                self.section = door_section

            if (
                self.door_shift_id
                and self.door_shift.door_number != self.door.door_number
            ):
                errors["door"] = "الباب المحدد لا يطابق حالة الباب في الوردية."

        if not self.description.strip():
            raise ValidationError(
                "وصف البلاغ مطلوب."
            )

        if (
            self.status == self.Status.CLOSED
            and not self.closing_notes.strip()
        ):
            errors["closing_notes"] = (
                "ملاحظات الإغلاق مطلوبة."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):

        if not self.incident_number:
            self.incident_number = (
                self._generate_incident_number()
            )

        if (
            self.door_shift_id
            and not self.shift_plan_id
        ):
            self.shift_plan = (
                self.door_shift.shift_plan
            )

        if (
            self.status == self.Status.CLOSED
            and not self.closed_at
        ):
            self.closed_at = timezone.now()

        elif self.status != self.Status.CLOSED:
            self.closed_at = None

        super().save(*args, **kwargs)


class IncidentRoutingEvent(models.Model):
    class EventType(models.TextChoices):
        CREATED = "created", "إنشاء البلاغ"
        ASSIGNED = "assigned", "إسناد البلاغ"
        PROCESSING_STARTED = "processing_started", "بدء المعالجة"
        ESCALATED = "escalated", "تصعيد البلاغ"
        CONVERTED_TO_MAINTENANCE = "converted_to_maintenance", "تحويل إلى الصيانة"
        MAINTENANCE_APPROVED = "maintenance_approved", "اعتماد الصيانة"
        MAINTENANCE_STARTED = "maintenance_started", "بدء الصيانة"
        MAINTENANCE_COMPLETED = "maintenance_completed", "اكتمال الصيانة"
        CLOSED = "closed", "إغلاق البلاغ"

    incident = models.ForeignKey(
        Incident,
        on_delete=models.CASCADE,
        related_name="routing_events",
    )
    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incident_routing_events",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="targeted_incident_routing_events",
    )
    target_level = models.CharField(
        max_length=30,
        choices=Incident.EscalationLevel.choices,
        blank=True,
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "pk"]
