from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Product, Category


class ProductSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8
    
    def items(self):
        return Product.objects.filter(available=True)
    
    def lastmod(self, obj):
        return obj.updated_at
    
    def location(self, obj):
        return reverse('store:product_detail', args=[obj.slug])


class CategorySitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.7
    
    def items(self):
        return Category.objects.all()
    
    def lastmod(self, obj):
        return obj.updated_at
    
    def location(self, obj):
        return f"{reverse('store:product_list')}?category={obj.slug}"


class StaticSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.6
    
    def items(self):
        return [
            'store:home',
            'store:product_list',
            'store:about',
            'store:privacy_policy',
            'store:normatividad',
        ]
    
    def location(self, item):
        return reverse(item)
