season = models.OneToOneField(
    "scheduling.Season",
    on_delete=models.PROTECT,
    related_name="report",
)
