from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    CategoryViewSet, ProductViewSet, OrderViewSet, 
    CartViewSet, CartItemViewSet
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet)
router.register(r'products', ProductViewSet)
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'cart', CartViewSet, basename='cart')
router.register(r'cart-items', CartItemViewSet, basename='cart-item')

urlpatterns = [
    path('', include(router.urls)),
]

