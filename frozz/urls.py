from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from store.sitemap import ProductSitemap, CategorySitemap, StaticSitemap

sitemaps = {
    'products': ProductSitemap,
    'categories': CategorySitemap,
    'static': StaticSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('store.urls')),
    path('accounts/', include('accounts.urls')),
    path('rentals/', include('rentals.urls')),
    path('api/', include('store.api_urls')),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path('robots.txt', TemplateView.as_view(template_name='robots.txt', content_type='text/plain'), name='robots'),
]

# En producción (Vercel) no hay DEBUG; servir estáticos desde STATICFILES_DIRS
# para que /static/css/, /static/img/, etc. respondan sin depender de collectstatic.
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])

# Media solo en desarrollo (en Vercel los uploads suelen ir a un storage externo)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
