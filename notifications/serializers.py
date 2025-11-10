from rest_framework import serializers
from .models import Notification

class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for Notification model"""
    
    class Meta:
        model = Notification
        fields = [
            'notification_id', 'recipient_email', 'recipient_phone', 'recipient_name',
            'notification_type', 'event_type', 'subject', 'message', 'status',
            'order_id', 'payment_id', 'shipment_id', 'created_at', 'sent_at',
            'delivered_at', 'error_message', 'retry_count'
        ]
        read_only_fields = ['notification_id', 'created_at', 'sent_at', 'delivered_at']


class SendNotificationSerializer(serializers.Serializer):
    """Serializer for sending notifications"""
    
    notification_type = serializers.ChoiceField(choices=Notification.NOTIFICATION_TYPES)
    event_type = serializers.ChoiceField(choices=Notification.EVENT_TYPES)
    recipient_name = serializers.CharField(max_length=255)
    recipient_email = serializers.EmailField(required=False, allow_blank=True)
    recipient_phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    subject = serializers.CharField(max_length=500)
    message = serializers.CharField()
    order_id = serializers.IntegerField(required=False, allow_null=True)
    payment_id = serializers.IntegerField(required=False, allow_null=True)
    shipment_id = serializers.IntegerField(required=False, allow_null=True)
    metadata = serializers.JSONField(required=False, default=dict)
    
    def validate(self, data):
        """Validate that at least one recipient contact is provided"""
        notification_type = data.get('notification_type')
        recipient_email = data.get('recipient_email')
        recipient_phone = data.get('recipient_phone')
        
        if notification_type == 'EMAIL' and not recipient_email:
            raise serializers.ValidationError("Email is required for EMAIL notifications")
        
        if notification_type == 'SMS' and not recipient_phone:
            raise serializers.ValidationError("Phone is required for SMS notifications")
        
        return data


class NotificationListSerializer(serializers.ModelSerializer):
    """Serializer for listing notifications"""
    
    class Meta:
        model = Notification
        fields = [
            'notification_id', 'recipient_name', 'notification_type',
            'event_type', 'status', 'created_at', 'order_id'
        ]