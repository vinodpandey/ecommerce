from django.conf import settings


def core(request):
    return {
        'lms_base_url': request.site.siteconfiguration.build_lms_url(),
        'lms_dashboard_url': request.site.siteconfiguration.student_dashboard_url,
        'platform_name': request.site.name,
        'support_url': settings.SUPPORT_URL,
    }
