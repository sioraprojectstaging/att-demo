"""
URL configuration for Siora One.

/api/          REST API used by the web app and the mobile app
/api/docs/     interactive API docs (Swagger UI) for app developers
/api/schema/   OpenAPI 3 schema (import into Postman / generate clients)
/api/health/   liveness check
/admin/        Django admin
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView


def health(request):
    """Liveness + database check. Unauthenticated; returns no data."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        database = 'ok'
        status = 200
    except Exception:
        database = 'unavailable'
        status = 503
    return JsonResponse({'status': 'ok' if status == 200 else 'degraded', 'database': database}, status=status)


urlpatterns = [
    path('', RedirectView.as_view(url='/api/docs/', permanent=False)),
    path('admin/', admin.site.urls),
    re_path(r'^api/health/?$', health, name='health'),
    re_path(r'^api/schema/?$', SpectacularAPIView.as_view(), name='schema'),
    re_path(r'^api/docs/?$', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    re_path(r'^api/redoc/?$', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('api/', include('api.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
