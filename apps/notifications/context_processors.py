from .models import Notification


def notifications_badge(request):
    if not request.user.is_authenticated:
        return {
            "unread_notifications_count": 0,
            "latest_notifications": [],
        }

    notifications = (
        Notification.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    return {
        "unread_notifications_count": notifications.filter(is_read=False).count(),
        "latest_notifications": notifications[:5],
    }