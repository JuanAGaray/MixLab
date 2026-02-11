from django.urls import path
from . import views

app_name = 'rentals'

urlpatterns = [
    path('', views.rental_list, name='rental_list'),
    path('product/<int:product_id>/', views.rental_detail, name='rental_detail'),
    path('create/<int:product_id>/', views.create_rental, name='create_rental'),
    path('<int:rental_id>/', views.rental_detail_view, name='rental_detail_view'),
    path('history/', views.rental_history, name='rental_history'),
]

