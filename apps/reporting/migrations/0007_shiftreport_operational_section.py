from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("reporting", "0006_alter_shiftreport_options_and_more")]

    operations = [
        migrations.AddField(
            model_name="shiftreport",
            name="operational_section",
            field=models.CharField(
                choices=[("all", "الكل"), ("male", "رجالي"), ("female", "نسائي")],
                db_index=True,
                default="all",
                max_length=10,
                verbose_name="نطاق القسم التشغيلي",
            ),
        ),
    ]