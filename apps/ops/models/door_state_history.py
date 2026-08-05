class DoorStateHistory(models.Model):
    door_shift = models.ForeignKey(
        "ops.DoorShift",
        on_delete=models.PROTECT,
        related_name="state_history",
    )

    previous_state = models.CharField(
        max_length=20,
        choices=DoorShift.DoorState.choices,
        blank=True,
    )

    new_state = models.CharField(
        max_length=20,
        choices=DoorShift.DoorState.choices,
    )

    reason = models.TextField(
        blank=True,
    )

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="door_state_changes",
    )

    changed_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-changed_at"]