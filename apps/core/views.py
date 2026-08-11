from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.roles.services.section_context import set_current_section


@login_required
@require_POST
def set_operational_section(request):
    """Persist the platform-wide operational section selected from the header."""
    set_current_section(request, request.POST.get("section"))

    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("dashboard:index")
