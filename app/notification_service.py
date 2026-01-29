"""
Notification Service for PriceScout
Handles webhook and email notifications for price alerts.

Usage:
    from app.notification_service import dispatch_alert_notifications

    # After generating alerts
    await dispatch_alert_notifications(company_id=1, alerts=alert_list)
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, UTC
from typing import List, Optional

from app.db_session import get_session
from app.db_models import PriceAlert, AlertConfiguration, Company
from app.audit_service import audit_service

logger = logging.getLogger(__name__)

# Try to import httpx for async HTTP requests
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    logger.warning("httpx not installed - webhook notifications will use synchronous requests")

# Try to import telemetry
try:
    from api.telemetry import track_event
except ImportError:
    def track_event(name, properties=None):
        pass


class NotificationService:
    """Service for dispatching alert notifications."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    async def dispatch_notifications(self, alerts: List[PriceAlert]):
        """
        Dispatch notifications for a batch of alerts.
        Called as a background task after alert generation.

        Args:
            alerts: List of PriceAlert objects to notify about
        """
        if not alerts:
            return

        with get_session() as session:
            config = session.query(AlertConfiguration).filter(
                AlertConfiguration.company_id == self.company_id
            ).first()

            if not config or not config.notification_enabled:
                logger.debug(f"Notifications disabled for company {self.company_id}")
                return

            # Dispatch webhook
            if config.webhook_url:
                await self._send_webhook(config, alerts)

            # Queue email (if immediate)
            if config.notification_email and config.email_frequency == 'immediate':
                await self._send_email(config, alerts)

    async def dispatch_system_notification(self, title: str, message: str, severity: str = "warning"):
        """
        Dispatch a system-level notification (e.g., circuit breaker open).
        Sends to all configured admin recipients or company webhooks.
        """
        with get_session() as session:
            # For system alerts, we either send to a global config or all active company admins
            # Here we'll send to all companies that have notifications enabled
            configs = session.query(AlertConfiguration).filter(
                AlertConfiguration.notification_enabled == True
            ).all()

            tasks = []
            for config in configs:
                # Send webhook
                if config.webhook_url:
                    tasks.append(self._send_system_webhook(config, title, message, severity))
                
                # Send email
                if config.notification_email:
                    tasks.append(self._send_system_email(config, title, message, severity))
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_system_webhook(self, config: AlertConfiguration, title: str, message: str, severity: str):
        """Send a system-level webhook."""
        try:
            payload = {
                "event": "system_alert",
                "timestamp": datetime.now(UTC).isoformat(),
                "title": title,
                "message": message,
                "severity": severity
            }
            payload_json = json.dumps(payload, sort_keys=True, default=str)
            
            headers = {"Content-Type": "application/json"}
            if config.webhook_secret:
                signature = hmac.new(
                    config.webhook_secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-PriceScout-Signature"] = f"sha256={signature}"

            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(config.webhook_url, content=payload_json, headers=headers)
            else:
                import requests
                requests.post(config.webhook_url, data=payload_json, headers=headers, timeout=10)
                
            logger.info(f"System webhook '{title}' sent to {config.webhook_url}")
        except Exception as e:
            logger.error(f"Failed to send system webhook: {e}")

    async def _send_system_email(self, config: AlertConfiguration, title: str, message: str, severity: str):
        """Send a system-level email."""
        subject = f"PriceScout SYSTEM {severity.upper()}: {title}"
        body = f"Event: {title}\nSeverity: {severity}\nTime: {datetime.now(UTC)}\n\nDetails:\n{message}\n\n-- PriceScout System Monitor"
        
        # In placeholder mode, we just log
        logger.warning(f"System Email to {config.notification_email}: {subject}")
        logger.debug(f"Body: {body}")

        track_event("PriceScout.Notification.SystemEmailQueued", {
            "Title": title,
            "Severity": severity,
            "Recipient": config.notification_email
        })

    async def _send_webhook(self, config: AlertConfiguration, alerts: List[PriceAlert]):
        """Send webhook notification with HMAC signature."""
        try:
            payload = self._build_webhook_payload(alerts)
            payload_json = json.dumps(payload, sort_keys=True, default=str)

            headers = {"Content-Type": "application/json"}

            # Add HMAC signature if secret configured
            if config.webhook_secret:
                signature = hmac.new(
                    config.webhook_secret.encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-PriceScout-Signature"] = f"sha256={signature}"

            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        config.webhook_url,
                        content=payload_json,
                        headers=headers
                    )
                    response.raise_for_status()
            else:
                # Fallback to synchronous requests
                import requests
                response = requests.post(
                    config.webhook_url,
                    data=payload_json,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()

            # Mark alerts as notified
            self._mark_alerts_notified(alerts)

            track_event("PriceScout.Notification.WebhookSent", {
                "AlertCount": str(len(alerts)),
                "CompanyId": str(self.company_id)
            })

            logger.info(f"Webhook sent successfully for {len(alerts)} alerts to {config.webhook_url}")

        except Exception as e:
            logger.error(f"Webhook failed for company {self.company_id}: {e}")

            # Record error on alerts
            self._mark_alerts_error(alerts, str(e))

            track_event("PriceScout.Notification.WebhookFailed", {
                "Error": str(e),
                "CompanyId": str(self.company_id)
            })

            # Audit webhook failure
            audit_service.system_event(
                event_type="webhook_failed",
                severity="error",
                company_id=self.company_id,
                details={"error": str(e), "url": config.webhook_url, "alert_count": len(alerts)}
            )

    def _build_webhook_payload(self, alerts: List[PriceAlert]) -> dict:
        """Build the webhook payload from alerts."""
        return {
            "event": "price_alerts",
            "timestamp": datetime.now(UTC).isoformat(),
            "company_id": self.company_id,
            "alert_count": len(alerts),
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "alert_type": a.alert_type,
                    "theater_name": a.theater_name,
                    "film_title": a.film_title,
                    "ticket_type": a.ticket_type,
                    "format": a.format,
                    "old_price": float(a.old_price) if a.old_price else None,
                    "new_price": float(a.new_price) if a.new_price else None,
                    "price_change_percent": float(a.price_change_percent) if a.price_change_percent else None,
                    "baseline_price": float(a.baseline_price) if a.baseline_price else None,
                    "surge_multiplier": float(a.surge_multiplier) if a.surge_multiplier else None,
                    "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
                    "play_date": str(a.play_date) if a.play_date else None
                }
                for a in alerts
            ]
        }

    def _mark_alerts_notified(self, alerts: List[PriceAlert]):
        """Mark alerts as having been notified."""
        try:
            with get_session() as session:
                alert_ids = [a.alert_id for a in alerts if a.alert_id]
                if alert_ids:
                    session.query(PriceAlert).filter(
                        PriceAlert.alert_id.in_(alert_ids)
                    ).update({
                        'notification_sent': True,
                        'notification_sent_at': datetime.now(UTC)
                    }, synchronize_session=False)
        except Exception as e:
            logger.warning(f"Failed to mark alerts as notified: {e}")

    def _mark_alerts_error(self, alerts: List[PriceAlert], error_message: str):
        """Mark alerts with notification error."""
        try:
            with get_session() as session:
                alert_ids = [a.alert_id for a in alerts if a.alert_id]
                if alert_ids:
                    session.query(PriceAlert).filter(
                        PriceAlert.alert_id.in_(alert_ids)
                    ).update({
                        'notification_error': error_message[:500]  # Truncate long errors
                    }, synchronize_session=False)
        except Exception as e:
            logger.warning(f"Failed to mark alerts with error: {e}")

    async def _send_email(self, config: AlertConfiguration, alerts: List[PriceAlert]):
        """
        Send email notification.

        This is a placeholder implementation. In production, integrate with:
        - SendGrid
        - AWS SES
        - SMTP server
        """
        # Build email content
        subject = f"PriceScout Alert: {len(alerts)} price change(s) detected"

        body_lines = [
            f"PriceScout detected {len(alerts)} price alert(s):",
            ""
        ]

        for alert in alerts[:10]:  # Limit to first 10 alerts in email
            if alert.alert_type == 'surge_detected':
                body_lines.append(
                    f"  - SURGE: {alert.theater_name} {alert.ticket_type} "
                    f"${alert.new_price} ({alert.price_change_percent:+.1f}% above baseline)"
                )
            else:
                body_lines.append(
                    f"  - {alert.alert_type.upper()}: {alert.theater_name} {alert.ticket_type} "
                    f"${alert.old_price} -> ${alert.new_price} ({alert.price_change_percent:+.1f}%)"
                )

        if len(alerts) > 10:
            body_lines.append(f"  ... and {len(alerts) - 10} more alerts")

        body_lines.extend([
            "",
            "Log in to PriceScout to view and acknowledge these alerts.",
            "",
            "-- PriceScout Alert System"
        ])

        body = "\n".join(body_lines)

        # Log intent (actual email sending would go here)
        logger.info(f"Email notification queued to {config.notification_email}: {subject}")
        logger.debug(f"Email body:\n{body}")

        track_event("PriceScout.Notification.EmailQueued", {
            "AlertCount": str(len(alerts)),
            "Email": config.notification_email,
            "CompanyId": str(self.company_id)
        })

        # TODO: Implement actual email sending
        # Example with SendGrid:
        # from sendgrid import SendGridAPIClient
        # from sendgrid.helpers.mail import Mail
        # message = Mail(
        #     from_email='alerts@pricescout.com',
        #     to_emails=config.notification_email,
        #     subject=subject,
        #     plain_text_content=body
        # )
        # sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        # sg.send(message)


async def dispatch_alert_notifications(company_id: int, alerts: List[PriceAlert]):
    """
    Convenience function for dispatching notifications.
    Called as a FastAPI background task.

    Args:
        company_id: Company ID for multi-tenancy
        alerts: List of PriceAlert objects to notify about
    """
    try:
        service = NotificationService(company_id)
        await service.dispatch_notifications(alerts)
    except Exception as e:
        logger.exception(f"Error dispatching notifications for company {company_id}: {e}")


def dispatch_alerts_sync(company_id: int, alerts: List[PriceAlert]):
    """
    Synchronous wrapper for notification dispatch.
    Use when asyncio event loop is not available.

    Args:
        company_id: Company ID for multi-tenancy
        alerts: List of PriceAlert objects to notify about
    """
    try:
        asyncio.run(dispatch_alert_notifications(company_id, alerts))
    except RuntimeError:
        # Event loop already running - schedule as task
        asyncio.create_task(dispatch_alert_notifications(company_id, alerts))
    except Exception as e:
        logger.exception(f"Error in sync notification dispatch: {e}")


# ============================================================================
# Schedule Alert Notifications
# ============================================================================

class ScheduleNotificationService:
    """Service for dispatching schedule change alert notifications."""

    def __init__(self, company_id: int):
        self.company_id = company_id

    def _get_config(self):
        """Get schedule monitor config for this company."""
        import sqlite3
        import os
        from app import config as app_config

        db_path = os.path.join(app_config.PROJECT_DIR, 'pricescout.db')
        if not os.path.exists(db_path):
            return None

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM schedule_monitor_config
                WHERE company_id = ?
            """, (self.company_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    async def dispatch_notifications(self, alerts: List[dict]):
        """
        Dispatch notifications for schedule alerts.

        Args:
            alerts: List of schedule alert dictionaries
        """
        if not alerts:
            return

        config = self._get_config()
        if not config or not config.get('notification_enabled'):
            logger.debug(f"Schedule notifications disabled for company {self.company_id}")
            return

        # Dispatch webhook
        if config.get('webhook_url'):
            await self._send_webhook(config, alerts)

        # Queue email
        if config.get('notification_email'):
            await self._send_email(config, alerts)

    async def _send_webhook(self, config: dict, alerts: List[dict]):
        """Send webhook notification for schedule alerts."""
        try:
            payload = self._build_webhook_payload(alerts)
            payload_json = json.dumps(payload, sort_keys=True, default=str)

            headers = {"Content-Type": "application/json"}

            # Add HMAC signature if secret configured
            if config.get('webhook_secret'):
                signature = hmac.new(
                    config['webhook_secret'].encode(),
                    payload_json.encode(),
                    hashlib.sha256
                ).hexdigest()
                headers["X-PriceScout-Signature"] = f"sha256={signature}"

            if HAS_HTTPX:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        config['webhook_url'],
                        content=payload_json,
                        headers=headers
                    )
                    response.raise_for_status()
            else:
                import requests
                response = requests.post(
                    config['webhook_url'],
                    data=payload_json,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()

            track_event("PriceScout.Notification.ScheduleWebhookSent", {
                "AlertCount": str(len(alerts)),
                "CompanyId": str(self.company_id)
            })

            logger.info(f"Schedule webhook sent for {len(alerts)} alerts to {config['webhook_url']}")

        except Exception as e:
            logger.error(f"Schedule webhook failed for company {self.company_id}: {e}")
            track_event("PriceScout.Notification.ScheduleWebhookFailed", {
                "Error": str(e),
                "CompanyId": str(self.company_id)
            })

            # Audit schedule webhook failure
            audit_service.system_event(
                event_type="schedule_webhook_failed",
                severity="error",
                company_id=self.company_id,
                details={"error": str(e), "url": config.get('webhook_url'), "alert_count": len(alerts)}
            )

    def _build_webhook_payload(self, alerts: List[dict]) -> dict:
        """Build webhook payload for schedule alerts."""
        return {
            "event": "schedule_alerts",
            "timestamp": datetime.now(UTC).isoformat(),
            "company_id": self.company_id,
            "alert_count": len(alerts),
            "alerts": [
                {
                    "alert_type": a.get('alert_type'),
                    "theater_name": a.get('theater_name'),
                    "film_title": a.get('film_title'),
                    "play_date": a.get('play_date'),
                    "change_details": a.get('change_details'),
                    "old_value": a.get('old_value'),
                    "new_value": a.get('new_value')
                }
                for a in alerts
            ]
        }

    async def _send_email(self, config: dict, alerts: List[dict]):
        """Send email notification for schedule alerts."""
        subject = f"PriceScout: {len(alerts)} schedule change(s) detected"

        # Group alerts by type
        alert_types = {}
        for alert in alerts:
            alert_type = alert.get('alert_type', 'unknown')
            if alert_type not in alert_types:
                alert_types[alert_type] = []
            alert_types[alert_type].append(alert)

        body_lines = [
            f"PriceScout detected {len(alerts)} schedule change(s):",
            ""
        ]

        type_descriptions = {
            'new_film': 'New Films Added',
            'new_showtime': 'New Showtimes Added',
            'removed_showtime': 'Showtimes Removed',
            'removed_film': 'Films Removed',
            'format_added': 'New Formats Available'
        }

        for alert_type, type_alerts in alert_types.items():
            body_lines.append(f"\n{type_descriptions.get(alert_type, alert_type).upper()} ({len(type_alerts)}):")
            for alert in type_alerts[:5]:  # Limit per type
                body_lines.append(
                    f"  - {alert.get('theater_name')}: {alert.get('film_title', 'N/A')} "
                    f"({alert.get('play_date', 'N/A')})"
                )
            if len(type_alerts) > 5:
                body_lines.append(f"  ... and {len(type_alerts) - 5} more")

        body_lines.extend([
            "",
            "Log in to PriceScout to view and acknowledge these alerts.",
            "",
            "-- PriceScout Schedule Monitor"
        ])

        body = "\n".join(body_lines)

        logger.info(f"Schedule email notification queued to {config['notification_email']}: {subject}")
        logger.debug(f"Email body:\n{body}")

        track_event("PriceScout.Notification.ScheduleEmailQueued", {
            "AlertCount": str(len(alerts)),
            "Email": config['notification_email'],
            "CompanyId": str(self.company_id)
        })

async def dispatch_system_notification(title: str, message: str, severity: str = "warning"):
    """Global convenience function for system notifications."""
    try:
        # Default to company 1 or generic service
        service = NotificationService(1)
        await service.dispatch_system_notification(title, message, severity)
    except Exception as e:
        logger.error(f"Error in global system notification: {e}")

def dispatch_system_notification_sync(title: str, message: str, severity: str = "warning"):
    """Synchronous global convenience function for system notifications."""
    try:
        # Try to get existing event loop
        loop = asyncio.get_running_loop()
        # If we're in an async context, schedule the task
        loop.create_task(dispatch_system_notification(title, message, severity))
    except RuntimeError:
        # No running loop - create a new one
        try:
            asyncio.run(dispatch_system_notification(title, message, severity))
        except RuntimeError:
            # Nested event loop or other issue - log and skip
            logger.debug(f"Could not dispatch system notification: {title}")
    except Exception as e:
        logger.error(f"Error in sync global system notification: {e}")


async def dispatch_schedule_alert_notifications(company_id: int, alerts: List[dict]):
    """
    Dispatch notifications for schedule alerts.

    Args:
        company_id: Company ID for multi-tenancy
        alerts: List of schedule alert dictionaries
    """
    try:
        service = ScheduleNotificationService(company_id)
        await service.dispatch_notifications(alerts)
    except Exception as e:
        logger.exception(f"Error dispatching schedule notifications for company {company_id}: {e}")


def dispatch_schedule_alerts_sync(company_id: int, alerts: List[dict]):
    """
    Synchronous wrapper for schedule notification dispatch.

    Args:
        company_id: Company ID for multi-tenancy
        alerts: List of schedule alert dictionaries
    """
    try:
        asyncio.run(dispatch_schedule_alert_notifications(company_id, alerts))
    except RuntimeError:
        asyncio.create_task(dispatch_schedule_alert_notifications(company_id, alerts))
    except Exception as e:
        logger.exception(f"Error in sync schedule notification dispatch: {e}")
