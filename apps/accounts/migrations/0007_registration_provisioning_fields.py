from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("roles", "0004_alter_role_options"), ("accounts", "0006_alter_accountregistrationrequest_status")]

    operations = [
        migrations.AlterField(
            model_name="accountregistrationrequest", name="status",
            field=models.CharField(choices=[("pending", "قيد المراجعة"), ("needs_edit", "تحتاج مراجعة"), ("approved", "موافق عليه"), ("activated", "مفعّل"), ("rejected", "مرفوض"), ("cancelled", "ملغي")], db_index=True, default="pending", max_length=20, verbose_name="حالة الطلب"),
        ),
        migrations.AddField(model_name="accountregistrationrequest", name="activated_at", field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ التفعيل")),
        migrations.AddField(model_name="accountregistrationrequest", name="activation_email_error", field=models.TextField(blank=True, verbose_name="خطأ إرسال رابط التفعيل")),
        migrations.AddField(model_name="accountregistrationrequest", name="activation_email_sent_at", field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ إرسال رابط التفعيل")),
        migrations.AddField(model_name="accountregistrationrequest", name="operational_section", field=models.CharField(blank=True, choices=[("male", "رجالي"), ("female", "نسائي")], max_length=10, verbose_name="القسم التشغيلي")),
        migrations.AddField(model_name="accountregistrationrequest", name="rejection_reason", field=models.TextField(blank=True, verbose_name="سبب الرفض")),
        migrations.AddField(model_name="accountregistrationrequest", name="approved_role", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_account_requests", to="roles.role", verbose_name="الدور المعتمد")),
    ]
