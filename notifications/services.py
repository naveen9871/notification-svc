import logging
import time
import random

logger = logging.getLogger(__name__)


def send_email(to_email, subject, message):
    """
    Simulate email sending
    In production, integrate with services like:
    - SendGrid
    - AWS SES
    - Mailgun
    - SMTP
    """
    try:
        logger.info(f"Sending email to {to_email}: {subject}")
        
        # Simulate email sending delay
        time.sleep(0.5)
        
        # Simulate 95% success rate
        if random.random() < 0.95:
            logger.info(f"Email sent successfully to {to_email}")
            return True, None
        else:
            error = "Email delivery failed - recipient inbox full"
            logger.error(f"Failed to send email to {to_email}: {error}")
            return False, error
            
    except Exception as e:
        error = f"Email service error: {str(e)}"
        logger.error(error)
        return False, error


def send_sms(to_phone, message):
    """
    Simulate SMS sending
    In production, integrate with services like:
    - Twilio
    - AWS SNS
    - MSG91
    - Vonage
    """
    try:
        logger.info(f"Sending SMS to {to_phone}")
        
        # Simulate SMS sending delay
        time.sleep(0.3)
        
        # Simulate 90% success rate
        if random.random() < 0.90:
            logger.info(f"SMS sent successfully to {to_phone}")
            return True, None
        else:
            error = "SMS delivery failed - invalid phone number"
            logger.error(f"Failed to send SMS to {to_phone}: {error}")
            return False, error
            
    except Exception as e:
        error = f"SMS service error: {str(e)}"
        logger.error(error)
        return False, error


def format_order_confirmation_email(order_data):
    """Format order confirmation email"""
    subject = f"Order Confirmation - Order #{order_data['order_id']}"
    message = f"""
Dear {order_data['customer_name']},

Thank you for your order!

Order Details:
- Order ID: {order_data['order_id']}
- Order Total: ₹{order_data['order_total']}
- Items: {order_data['item_count']} item(s)

Your order is being processed and you will receive a shipping confirmation soon.

Track your order: {order_data.get('tracking_url', 'N/A')}

Thank you for shopping with us!

Best regards,
ECI E-commerce Team
    """
    return subject, message


def format_payment_success_email(payment_data):
    """Format payment success email"""
    subject = f"Payment Successful - Order #{payment_data['order_id']}"
    message = f"""
Dear Customer,

Your payment has been processed successfully!

Payment Details:
- Payment ID: {payment_data['payment_id']}
- Order ID: {payment_data['order_id']}
- Amount: ₹{payment_data['amount']}
- Method: {payment_data['method']}
- Reference: {payment_data['reference']}

Your order will be shipped soon.

Thank you!

Best regards,
ECI E-commerce Team
    """
    return subject, message


def format_shipment_notification(shipment_data):
    """Format shipment notification"""
    subject = f"Your Order has been Shipped - Order #{shipment_data['order_id']}"
    message = f"""
Dear Customer,

Good news! Your order has been shipped.

Shipment Details:
- Order ID: {shipment_data['order_id']}
- Carrier: {shipment_data['carrier']}
- Tracking Number: {shipment_data['tracking_no']}
- Expected Delivery: {shipment_data.get('expected_delivery', '2-3 business days')}

Track your shipment: {shipment_data.get('tracking_url', 'N/A')}

Thank you for your patience!

Best regards,
ECI E-commerce Team
    """
    return subject, message


def format_order_cancellation_email(order_data):
    """Format order cancellation email"""
    subject = f"Order Cancelled - Order #{order_data['order_id']}"
    message = f"""
Dear {order_data['customer_name']},

Your order has been cancelled as requested.

Order Details:
- Order ID: {order_data['order_id']}
- Cancellation Reason: {order_data.get('reason', 'Customer request')}

If you paid for this order, a refund will be processed within 5-7 business days.

If you have any questions, please contact our support team.

Best regards,
ECI E-commerce Team
    """
    return subject, message


def mask_sensitive_data(data):
    """Mask PII in logs"""
    if 'email' in data:
        email = data['email']
        if '@' in email:
            parts = email.split('@')
            data['email'] = f"{parts[0][:2]}***@{parts[1]}"
    
    if 'phone' in data:
        phone = data['phone']
        data['phone'] = f"***{phone[-4:]}"
    
    return data