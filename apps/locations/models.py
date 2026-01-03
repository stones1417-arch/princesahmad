from django.db import models


class Zone(models.Model):
    """
    منطقة أو قطاع داخل المسجد
    """
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Door(models.Model):
    """
    باب من أبواب المسجد
    """
    name = models.CharField(max_length=50)
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
