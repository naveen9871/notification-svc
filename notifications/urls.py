from django.urls import path
from . import views

urlpatterns = [
    # Notification endpoints
    path('send/', views.send_notification, name='send-notification'),
    path('', views.list_notifications, name='list-notifications'),
    path('stats/', views.notification_stats, name='notification-stats'),
    path('<uuid:notification_id>/', views.get_notification, name='get-notification'),
    path('<uuid:notification_id>/retry/', views.retry_notification, name='retry-notification'),
    
    # Health checks
    path('health/', views.health_check, name='health-check'),
    path('ready/', views.ready_check, name='ready-check'),
]