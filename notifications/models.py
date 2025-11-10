from djongo import models
from django.core.validators import EmailValidator
import uuid

class Notification(models.Model):
    """Notification model using MongoDB via Djongo"""
    
    NOTIFICATION_TYPES = [
        ('EMAIL', 'Email'),
        ('SMS', 'SMS'),
        ('PUSH', 'Push Notification'),
    ]
    
    NOTIFICATION_STATUS = [
        ('PENDING', 'Pending'),
        ('SENT', 'Sent'),
        ('FAILED', 'Failed'),
        ('DELIVERED', 'Delivered'),
    ]
    
    EVENT_TYPES = [
        ('order.confirmed', 'Order Confirmed'),
        ('order.cancelled', 'Order Cancelled'),
        ('order.delivered', 'Order Delivered'),
        ('payment.succeeded', 'Payment Succeeded'),
        ('payment.failed', 'Payment Failed'),
        ('payment.refunded', 'Payment Refunded'),
        ('shipment.shipped', 'Shipment Shipped'),
        ('shipment.delivered', 'Shipment Delivered'),
    ]
    
    _id = models.ObjectIdField(primary_key=True)
    notification_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    # Recipient info
    recipient_email = models.EmailField(validators=[EmailValidator()], null=True, blank=True)
    recipient_phone = models.CharField(max_length=15, null=True, blank=True)
    recipient_name = models.CharField(max_length=255)
    
    # Notification details
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES)
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    subject = models.CharField(max_length=500)
    message = models.TextField()
    
    # Status tracking
    status = models.CharField(max_length=20, choices=NOTIFICATION_STATUS, default='PENDING')
    error_message = models.TextField(null=True, blank=True)
    
    # Metadata
    order_id = models.IntegerField(null=True, blank=True, db_index=True)
    payment_id = models.IntegerField(null=True, blank=True)
    shipment_id = models.IntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    # Retry tracking
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['event_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.notification_type} - {self.event_type} - {self.status}"
    
    def can_retry(self):
        """Check if notification can be retried"""
        return self.status == 'FAILED' and self.retry_count < self.max_retries