from .models import Incident, MaintenanceRequest


def maintenance_badge(request):
    """
    عدادات البلاغات التشغيلية وطلبات الصيانة
    المستخدمة في القائمة العلوية.
    """

    if not request.user.is_authenticated:
        return {}

    maintenance_count = (
        MaintenanceRequest.objects.filter(
            status__in=[
                MaintenanceRequest.Status.NEW,
                MaintenanceRequest.Status.APPROVED,
                MaintenanceRequest.Status.ASSIGNED,
                MaintenanceRequest.Status.IN_PROGRESS,
                MaintenanceRequest.Status.OPEN,
            ]
        ).count()
    )

    incidents_count = (
        Incident.objects.filter(
            status__in=[
                Incident.Status.NEW,
                Incident.Status.IN_PROGRESS,
                Incident.Status.FORWARDED,
            ]
        ).count()
    )

    critical_incidents_count = (
        Incident.objects.filter(
            priority=Incident.Priority.CRITICAL,
            status__in=[
                Incident.Status.NEW,
                Incident.Status.IN_PROGRESS,
                Incident.Status.FORWARDED,
            ]
        ).count()
    )

    return {
        "maintenance_badge_count": maintenance_count,
        "incidents_badge_count": incidents_count,
        "critical_incidents_badge_count": critical_incidents_count,
    }