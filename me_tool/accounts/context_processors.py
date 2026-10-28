from django.conf import settings

from .models import access_for


def access(request):
    """`access` (what the user may do) and the wellness app address in every template."""
    return {"access": access_for(request.user), "wellness_url": settings.WELLNESS_API_URL}
