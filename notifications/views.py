from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
import logging

from .models import Notification
from .serializers import (
    NotificationSerializer,
    SendNotificationSerializer,
    NotificationListSerializer
)
from .services import send_email, send_sms

logger = logging.getLogger(__name__)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['POST'])
def send_notification(request):
    """
    POST /v1/notifications/send
    Send a notification (email or SMS)
    """
    serializer = SendNotificationSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response({
            'error': 'validation_error',
            'details': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    try:
        # Create notification record
        notification = Notification.objects.create(
            recipient_name=data['recipient_name'],
            recipient_email=data.get('recipient_email'),
            recipient_phone=data.get('recipient_phone'),
            notification_type=data['notification_type'],
            event_type=data['event_type'],
            subject=data['subject'],
            message=data['message'],
            order_id=data.get('order_id'),
            payment_id=data.get('payment_id'),
            shipment_id=data.get('shipment_id'),
            metadata=data.get('metadata', {})
        )
        
        # Send notification based on type
        if data['notification_type'] == 'EMAIL':
            success, error = send_email(
                to_email=data['recipient_email'],
                subject=data['subject'],
                message=data['message']
            )
        elif data['notification_type'] == 'SMS':
            success, error = send_sms(
                to_phone=data['recipient_phone'],
                message=data['message']
            )
        else:
            success, error = False, "Unsupported notification type"
        
        if success:
            notification.status = 'SENT'
            notification.sent_at = timezone.now()
            notification.save()
            
            logger.info(f"Notification {notification.notification_id} sent successfully")
            
            return Response({
                'message': 'Notification sent successfully',
                'notification': NotificationSerializer(notification).data
            }, status=status.HTTP_201_CREATED)
        else:
            notification.status = 'FAILED'
            notification.error_message = error
            notification.save()
            
            logger.error(f"Failed to send notification {notification.notification_id}: {error}")
            
            return Response({
                'error': 'send_failed',
                'message': error,
                'notification': NotificationSerializer(notification).data
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        return Response({
            'error': 'processing_error',
            'message': 'Failed to process notification'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_notification(request, notification_id):
    """
    GET /v1/notifications/{notification_id}
    Retrieve notification details
    """
    try:
        notification = Notification.objects.get(notification_id=notification_id)
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Notification.DoesNotExist:
        return Response({
            'error': 'not_found',
            'message': 'Notification not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def list_notifications(request):
    """
    GET /v1/notifications
    List all notifications with pagination and filters
    """
    queryset = Notification.objects.all()
    
    # Apply filters
    notification_type = request.query_params.get('type')
    event_type = request.query_params.get('event')
    status_filter = request.query_params.get('status')
    order_id = request.query_params.get('order_id')
    
    if notification_type:
        queryset = queryset.filter(notification_type=notification_type)
    if event_type:
        queryset = queryset.filter(event_type=event_type)
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if order_id:
        queryset = queryset.filter(order_id=order_id)
    
    # Pagination
    paginator = NotificationPagination()
    page = paginator.paginate_queryset(queryset, request)
    
    if page is not None:
        serializer = NotificationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
    
    serializer = NotificationListSerializer(queryset, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
def retry_notification(request, notification_id):
    """
    POST /v1/notifications/{notification_id}/retry
    Retry a failed notification
    """
    try:
        notification = Notification.objects.get(notification_id=notification_id)
        
        if not notification.can_retry():
            return Response({
                'error': 'cannot_retry',
                'message': 'Notification cannot be retried (max retries reached or not failed)'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Attempt to resend
        if notification.notification_type == 'EMAIL':
            success, error = send_email(
                to_email=notification.recipient_email,
                subject=notification.subject,
                message=notification.message
            )
        elif notification.notification_type == 'SMS':
            success, error = send_sms(
                to_phone=notification.recipient_phone,
                message=notification.message
            )
        else:
            success, error = False, "Unsupported notification type"
        
        notification.retry_count += 1
        
        if success:
            notification.status = 'SENT'
            notification.sent_at = timezone.now()
            notification.error_message = None
        else:
            notification.error_message = error
        
        notification.save()
        
        return Response({
            'message': 'Retry completed',
            'notification': NotificationSerializer(notification).data
        }, status=status.HTTP_200_OK)
        
    except Notification.DoesNotExist:
        return Response({
            'error': 'not_found',
            'message': 'Notification not found'
        }, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def notification_stats(request):
    """
    GET /v1/notifications/stats
    Get notification statistics
    """
    total = Notification.objects.count()
    sent = Notification.objects.filter(status='SENT').count()
    failed = Notification.objects.filter(status='FAILED').count()
    pending = Notification.objects.filter(status='PENDING').count()
    
    by_type = {}
    for notif_type, _ in Notification.NOTIFICATION_TYPES:
        by_type[notif_type] = Notification.objects.filter(notification_type=notif_type).count()
    
    by_event = {}
    for event_type, _ in Notification.EVENT_TYPES:
        by_event[event_type] = Notification.objects.filter(event_type=event_type).count()
    
    return Response({
        'total': total,
        'sent': sent,
        'failed': failed,
        'pending': pending,
        'by_type': by_type,
        'by_event': by_event
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'service': 'notification-service',
        'version': 'v1.0.0'
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def ready_check(request):
    """Readiness check endpoint"""
    from django.db import connection
    try:
        # Check MongoDB connection
        Notification.objects.count()
        return Response({
            'status': 'ready',
            'database': 'connected'
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'status': 'not_ready',
            'error': str(e)
        }, status=status.HTTP_503_SERVICE_UNAVAILABLE)