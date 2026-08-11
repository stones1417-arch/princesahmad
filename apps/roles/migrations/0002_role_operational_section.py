from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("roles", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="operational_section",
            field=models.CharField(
                choices=[
                    ("all", "الكل"),
                    ("male", "رجالي"),
                    ("female", "نسائي"),
                ],
                db_index=True,
                default="all",
                help_text=(
                    "يحدد القسم الذي يستطيع صاحب الدور "
                    "الوصول إلى بياناته."
                ),
                max_length=10,
                verbose_name="نطاق القسم التشغيلي",
            ),
        ),
    ]