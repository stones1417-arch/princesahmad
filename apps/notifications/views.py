from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .models import Notification


@login_required
def notifications_list_view(request):

    notifications = (
        Notification.objects
        .filter(user=request.user)
        .order_by("-created_at")
    )

    return render(
        request,
        "notifications/list.html",
        {
            "notifications": notifications,
        },
    )


@login_required
def mark_notification_read_view(request, pk):

    notification = get_object_or_404(
        Notification,
        pk=pk,
        user=request.user,
    )

    notification.mark_as_read()

    if notification.url:
        return redirect(notification.url)

    return redirect("notifications:list")


@login_required
def mark_all_notifications_read_view(request):

    notifications = Notification.objects.filter(
        user=request.user,
        is_read=False,
    )

    for notification in notifications:
        notification.mark_as_read()

    return redirect("notifications:list")