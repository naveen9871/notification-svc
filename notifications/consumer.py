import pika
import json
import logging
import os
import django
from urllib.parse import urlparse

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'notification_service.settings')
django.setup()

from notifications.models import Notification
from notifications.services import (
    send_email, send_sms,
    format_order_confirmation_email,
    format_payment_success_email,
    format_shipment_notification,
    format_order_cancellation_email
)
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_rabbitmq_connection():
    """Create RabbitMQ connection with support for URL or separate parameters"""
    try:
        # Check if RABBITMQ_URL is provided
        rabbitmq_url = os.environ.get('RABBITMQ_URL')
        
        if rabbitmq_url:
            # Parse the URL (format: amqp://user:pass@host:port/vhost)
            parsed_url = urlparse(rabbitmq_url)
            
            # Extract credentials from URL
            username = parsed_url.username or 'guest'
            password = parsed_url.password or 'guest'
            host = parsed_url.hostname or 'localhost'
            port = parsed_url.port or 5672
            virtual_host = parsed_url.path[1:] if parsed_url.path else '/'  # Remove leading slash
            
            credentials = pika.PlainCredentials(username, password)
            parameters = pika.ConnectionParameters(
                host=host,
                port=port,
                virtual_host=virtual_host,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            logger.info(f"Connecting to RabbitMQ via URL: {host}:{port}{virtual_host}")
        else:
            # Fall back to separate environment variables
            credentials = pika.PlainCredentials(
                os.environ.get('RABBITMQ_USER', 'guest'),
                os.environ.get('RABBITMQ_PASSWORD', 'guest')
            )
            
            # Handle port conversion safely
            port_str = os.environ.get('RABBITMQ_PORT', '5672')
            try:
                port = int(port_str)
            except ValueError:
                logger.warning(f"Invalid port {port_str}, using default 5672")
                port = 5672
                
            parameters = pika.ConnectionParameters(
                host=os.environ.get('RABBITMQ_HOST', 'localhost'),
                port=port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            logger.info(f"Connecting to RabbitMQ via separate parameters: {parameters.host}:{parameters.port}")
        
        connection = pika.BlockingConnection(parameters)
        logger.info("Successfully connected to RabbitMQ")
        return connection
        
    except Exception as e:
        logger.error(f"Failed to connect to RabbitMQ: {str(e)}")
        return None


def consume_events():
    """
    Consume events from RabbitMQ exchanges:
    - order_events (order.confirmed, order.cancelled, order.delivered)
    - payment_events (payment.succeeded, payment.failed, payment.refunded)
    - shipping_events (shipment.shipped, shipment.delivered)
    """
    connection = None
    max_retries = 3
    retry_count = 0
    retry_delay = 5  # seconds
    
    while retry_count < max_retries:
        try:
            connection = get_rabbitmq_connection()
            if not connection:
                logger.error(f"Cannot connect to RabbitMQ. Retry {retry_count + 1}/{max_retries}")
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                continue
            
            channel = connection.channel()
            
            # Setup exchanges and queues
            exchanges = ['order_events', 'payment_events', 'shipping_events']
            queue_name = 'notification_service_events'
            
            # Declare queue
            channel.queue_declare(queue=queue_name, durable=True)
            
            # Bind to all relevant exchanges
            event_bindings = {
                'order_events': ['order.confirmed', 'order.cancelled', 'order.delivered'],
                'payment_events': ['payment.succeeded', 'payment.failed', 'payment.refunded'],
                'shipping_events': ['shipment.shipped', 'shipment.delivered']
            }
            
            for exchange, routing_keys in event_bindings.items():
                channel.exchange_declare(exchange=exchange, exchange_type='topic', durable=True)
                for routing_key in routing_keys:
                    channel.queue_bind(
                        exchange=exchange,
                        queue=queue_name,
                        routing_key=routing_key
                    )
                    logger.info(f"Bound to {exchange} with routing key {routing_key}")
            
            def callback(ch, method, properties, body):
                try:
                    message = json.loads(body)
                    event_type = message.get('event_type')
                    data = message.get('data', {})
                    
                    logger.info(f"Received event: {event_type}")
                    
                    # Process event
                    handle_event(event_type, data)
                    
                    # Acknowledge message
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON message: {str(e)}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                except Exception as e:
                    logger.error(f"Error processing event: {str(e)}")
                    # Reject and don't requeue if processing fails
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            # Set QoS
            channel.basic_qos(prefetch_count=1)
            
            # Start consuming
            channel.basic_consume(queue=queue_name, on_message_callback=callback)
            
            logger.info("Started consuming events. Waiting for messages...")
            retry_count = 0  # Reset retry count on successful connection
            channel.start_consuming()
            
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"Retrying connection in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("Max retries exceeded. Exiting.")
                break
        except KeyboardInterrupt:
            logger.info("Consumer stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in event consumer: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error("Max retries exceeded. Exiting.")
                break
        finally:
            if connection and not connection.is_closed:
                connection.close()
                logger.info("RabbitMQ connection closed")


def handle_event(event_type, data):
    """Handle different event types and send notifications"""
    
    try:
        if event_type == 'order.confirmed':
            handle_order_confirmed(data)
        elif event_type == 'order.cancelled':
            handle_order_cancelled(data)
        elif event_type == 'order.delivered':
            handle_order_delivered(data)
        elif event_type == 'payment.succeeded':
            handle_payment_succeeded(data)
        elif event_type == 'payment.failed':
            handle_payment_failed(data)
        elif event_type == 'payment.refunded':
            handle_payment_refunded(data)
        elif event_type == 'shipment.shipped':
            handle_shipment_shipped(data)
        elif event_type == 'shipment.delivered':
            handle_shipment_delivered(data)
        else:
            logger.warning(f"Unhandled event type: {event_type}")
            
    except Exception as e:
        logger.error(f"Error handling event {event_type}: {str(e)}")


def handle_order_confirmed(data):
    """Handle order confirmation event"""
    try:
        subject, message = format_order_confirmation_email(data)
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            notification_type='EMAIL',
            event_type='order.confirmed',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Order confirmation email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send order confirmation email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for order confirmation")
            
    except Exception as e:
        logger.error(f"Error in handle_order_confirmed: {str(e)}")


def handle_order_cancelled(data):
    """Handle order cancellation event"""
    try:
        subject, message = format_order_cancellation_email(data)
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            notification_type='EMAIL',
            event_type='order.cancelled',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Order cancellation email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send order cancellation email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for order cancellation")
            
    except Exception as e:
        logger.error(f"Error in handle_order_cancelled: {str(e)}")


def handle_order_delivered(data):
    """Handle order delivered event"""
    try:
        subject = f"Order Delivered - Order #{data.get('order_id')}"
        message = f"""
Dear Customer,

Your order has been successfully delivered!

Order ID: {data.get('order_id')}
Delivered At: {data.get('delivered_at', 'Today')}

Thank you for shopping with us!

Best regards,
ECI E-commerce Team
    """
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            recipient_phone=data.get('customer_phone'),
            notification_type='EMAIL',
            event_type='order.delivered',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Order delivered email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send order delivered email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for order delivered")
            
    except Exception as e:
        logger.error(f"Error in handle_order_delivered: {str(e)}")


def handle_payment_succeeded(data):
    """Handle payment success event"""
    try:
        subject, message = format_payment_success_email(data)
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            notification_type='EMAIL',
            event_type='payment.succeeded',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            payment_id=data.get('payment_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Payment success email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send payment success email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for payment success")
            
    except Exception as e:
        logger.error(f"Error in handle_payment_succeeded: {str(e)}")


def handle_payment_failed(data):
    """Handle payment failure event"""
    try:
        subject = f"Payment Failed - Order #{data.get('order_id')}"
        message = f"""
Dear Customer,

Your payment could not be processed.

Order ID: {data.get('order_id')}
Amount: ₹{data.get('amount')}
Reason: {data.get('reason', 'Unknown error')}

Please try again or use a different payment method.

Best regards,
ECI E-commerce Team
    """
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            notification_type='EMAIL',
            event_type='payment.failed',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            payment_id=data.get('payment_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Payment failure email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send payment failure email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for payment failure")
            
    except Exception as e:
        logger.error(f"Error in handle_payment_failed: {str(e)}")


def handle_payment_refunded(data):
    """Handle payment refund event"""
    try:
        subject = f"Refund Processed - Order #{data.get('order_id')}"
        message = f"""
Dear Customer,

Your refund has been processed successfully!

Order ID: {data.get('order_id')}
Refund Amount: ₹{data.get('refund_amount')}
Reason: {data.get('reason', 'Order cancellation')}

The amount will be credited to your original payment method within 5-7 business days.

Best regards,
ECI E-commerce Team
    """
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            notification_type='EMAIL',
            event_type='payment.refunded',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            payment_id=data.get('payment_id'),
            metadata=data
        )
        
        if notification.recipient_email:
            success, error = send_email(notification.recipient_email, subject, message)
            if success:
                notification.status = 'SENT'
                notification.sent_at = timezone.now()
                logger.info(f"Refund processed email sent for order {data.get('order_id')}")
            else:
                notification.status = 'FAILED'
                notification.error_message = error
                logger.error(f"Failed to send refund email: {error}")
            notification.save()
        else:
            logger.warning("No recipient email provided for refund")
            
    except Exception as e:
        logger.error(f"Error in handle_payment_refunded: {str(e)}")


def handle_shipment_shipped(data):
    """Handle shipment shipped event"""
    try:
        subject, message = format_shipment_notification(data)
        
        notification = Notification.objects.create(
            recipient_name=data.get('customer_name', 'Customer'),
            recipient_email=data.get('customer_email'),
            recipient_phone=data.get('customer_phone'),
            notification_type='EMAIL',
            event_type='shipment.shipped',
            subject=subject,
            message=message,
            order_id=data.get('order_id'),
            shipment_id=data.get('shipment_id'),
            metadata=data
        )
        
        email_sent = False
        sms_sent = False
        
        # Send email
        if notification.recipient_email:
            email_success, email_error = send_email(notification.recipient_email, subject, message)
            if email_success:
                email_sent = True
                logger.info(f"Shipment notification email sent for order {data.get('order_id')}")
            else:
                logger.error(f"Failed to send shipment email: {email_error}")
        
        # Also send SMS
        if notification.recipient_phone:
            sms_message = f"Your order #{data.get('order_id')} has been shipped via {data.get('carrier')}. Track: {data.get('tracking_no')}"
            sms_success, sms_error = send_sms(notification.recipient_phone, sms_message)
            if sms_success:
                sms_sent = True
                logger.info(f"Shipment notification SMS sent for order {data.get('order_id')}")
            else:
                logger.error(f"Failed to send shipment SMS: {sms_error}")
        
        if email_sent or sms_sent:
            notification.status = 'SENT'
            notification.sent_at = timezone.now()
        else:
            notification.status = 'FAILED'
            notification.error_message = "Both email and SMS failed"
            
        notification.save()
        
    except Exception as e:
        logger.error(f"Error in handle_shipment_shipped: {str(e)}")


def handle_shipment_delivered(data):
    """Handle shipment delivered event"""
    # This is same as order delivered, so reuse that handler
    handle_order_delivered(data)


if __name__ == '__main__':
    import time
    logger.info("Starting Notification Service Event Consumer...")
    consume_events()