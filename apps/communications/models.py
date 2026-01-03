from django.db import models
from apps.locations.models import Door


class Announcement(models.Model):
    """
    تعميم تشغيلي
    """
    title = models.CharField(max_length=200)
    content = models.TextField()
    door = models.ForeignKey(Door, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
