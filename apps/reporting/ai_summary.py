def build_executive_summary(report):
    summary = []

    if report.open_doors >= report.closed_doors:
        summary.append(
            "شهدت الوردية استقرارًا في تشغيل الأبواب مع جاهزية تشغيلية جيدة."
        )
    else:
        summary.append(
            "تم تسجيل انخفاض في جاهزية الأبواب ويتطلب ذلك متابعة تشغيلية."
        )

    if report.total_maintenance_requests:
        summary.append(
            f"تم تسجيل {report.total_maintenance_requests} طلب صيانة خلال الوردية."
        )

    if report.completed_maintenance_requests:
        summary.append(
            f"تم إنجاز {report.completed_maintenance_requests} طلب صيانة."
        )

    if report.total_employees:
        summary.append(
            f"شارك في تشغيل الوردية {report.total_employees} موظفًا."
        )

    return " ".join(summary)
def build_recommendations(report):

    recommendations = []

    if report.open_doors < report.total_doors:
        recommendations.append(
            "رفع نسبة جاهزية الأبواب قبل بداية الوردية القادمة."
        )

    if report.total_maintenance_requests > report.completed_maintenance_requests:
        recommendations.append(
            "تسريع إغلاق طلبات الصيانة المفتوحة."
        )

    if report.closed_doors > 0:
        recommendations.append(
            "مراجعة أسباب إغلاق الأبواب وتحليلها."
        )

    if report.total_employees < report.total_doors:
        recommendations.append(
            "دراسة تعزيز توزيع القوى البشرية على الأبواب."
        )

    if not recommendations:
        recommendations.append(
            "الاستمرار في المحافظة على مستوى الأداء الحالي."
        )

    return recommendations