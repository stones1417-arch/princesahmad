تحديث إعادة التوازن الحقيقية

استبدل الملفات:
apps/distribution/services.py
apps/distribution/views.py
apps/distribution/urls.py
templates/distribution/dashboard.html

لا يوجد تعديل على models.py ولا Migration جديد في هذه المرحلة.

بعد الاستبدال نفذ:
python manage.py check
python manage.py runserver

الاختبار:
1. افتح لوحة التوزيع.
2. اضغط معاينة إعادة التوازن.
3. راجع الموظف والباب الحالي والباب المقترح.
4. اضغط اعتماد وتنفيذ.
5. تحقق من AssignmentHistory.

الخطة لا تغير أدوار الموظفين، بل تنقلهم بين الأبواب لتجميع التغطية.
