"""
Webhook Service for PriceScout
Handles outbound webhook notifications to external systems.
"""

import hmac
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional
import httpx
from datetime import datetime, UTC

logger = logging.getLogger(__name__)

class WebhookService:
    """
    Service for sending outbound webhooks.
    """

    @staticmethod
    async def send_webhook(
        url: str,
        payload: Dict[str, Any],
        secret: Optional[str] = None,
        event_type: str = "alert",
        company_id: Optional[int] = None
    ) -> bool:
        """
        Send a webhook notification.

        Args:
            url: Destination URL
            payload: Data to send
            secret: Optional secret for HMAC signature
            event_type: Type of event (e.g., 'price_alert', 'schedule_alert')
            company_id: ID of the company
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not url:
            return False

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PriceScout-Webhook/1.0",
            "X-PriceScout-Event": event_type,
            "X-PriceScout-Timestamp": str(int(time.time()))
        }

        # Prepare payload
        full_payload = {
            "version": "1.0",
            "event": event_type,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "company_id": company_id,
            "data": payload
        }
        
        body = json.dumps(full_payload)

        # Add HMAC signature if secret is provided
        if secret:
            signature = hmac.new(
                secret.encode('utf-8'),
                body.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            headers["X-PriceScout-Signature"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, content=body)
                
                if response.status_code >= 200 and response.status_code < 300:
                    logger.info(f"Webhook sent successfully to {url} (Event: {event_type})")
                    return True
                else:
                    logger.error(f"Webhook failed to {url} with status {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Error sending webhook to {url}: {e}")
            return False

    @classmethod
    async def notify_price_alert(cls, url: str, alert_data: Dict[str, Any], secret: Optional[str] = None, company_id: Optional[int] = None):
        return await cls.send_webhook(url, alert_data, secret, "price_alert", company_id)

    @classmethod
    async def notify_schedule_alert(cls, url: str, alert_data: Dict[str, Any], secret: Optional[str] = None, company_id: Optional[int] = None):
        return await cls.send_webhook(url, alert_data, secret, "schedule_alert", company_id)

webhook_service = WebhookService()
