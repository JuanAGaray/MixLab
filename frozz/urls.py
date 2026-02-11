from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
    path('accounts/', include('accounts.urls')),
    path('rentals/', include('rentals.urls')),
    path('api/', include('store.api_urls')),
]

# En producción (Vercel) no hay DEBUG; servir estáticos desde STATICFILES_DIRS
# para que /static/css/, /static/img/, etc. respondan sin depender de collectstatic.
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

# Media solo en desarrollo (en Vercel los uploads suelen ir a un storage externo)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
