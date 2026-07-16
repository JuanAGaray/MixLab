from django.urls import path
from . import views

app_name = 'rentals'

urlpatterns = [
    path('', views.rental_list, name='rental_list'),
    path('product/<int:product_id>/', views.rental_detail, name='rental_detail'),
    path('create/<int:product_id>/', views.create_rental, name='create_rental'),
    path('history/', views.rental_history, name='rental_history'),
    # Manager — solicitudes
    path('solicitudes/', views.rental_requests, name='rental_requests'),
    path('solicitudes/<int:rental_id>/', views.rental_request_detail, name='rental_request_detail'),
    path('solicitudes/<int:rental_id>/estado/', views.rental_request_set_status, name='rental_request_set_status'),
    path('<int:rental_id>/', views.rental_detail_view, name='rental_detail_view'),
]

