"""
Audit Service for PriceScout
Standardizes logging of security, data, and system events.

This service records events to the `audit_log` table and optionally
integrates with external telemetry systems like Azure Application Insights.
"""

import json
import logging
from datetime import datetime, UTC
from typing import Optional, Any, Dict
from fastapi import Request

from app.db_session import get_session
from app.db_models import AuditLog
from app.config import ENABLE_APP_INSIGHTS

logger = logging.getLogger(__name__)

class AuditService:
    """
    Service for recording audit trail events.
    """

    @staticmethod
    def log_event(
        event_type: str,
        event_category: str,
        severity: str = "info",
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        company_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        session_id: Optional[str] = None
    ) -> None:
        """
        Record an audit log entry.

        Args:
            event_type: Specific event name (e.g., 'login_success', 'price_baseline_updated')
            event_category: Grouping (e.g., 'authentication', 'data_change', 'system')
            severity: Importance level ('info', 'warning', 'error', 'critical')
            user_id: ID of the user who performed the action
            username: Username of the user
            company_id: ID of the company context
            details: Dictionary of additional information to be stored as JSON
            request: Optional FastAPI Request object to extract IP and User-Agent
            session_id: Optional session identifier
        """
        ip_address = None
        user_agent = None

        if request:
            # Try to get real IP from proxy headers
            ip_address = request.headers.get("X-Forwarded-For")
            if ip_address:
                ip_address = ip_address.split(",")[0].strip()
            else:
                ip_address = request.client.host if request.client else None
            
            user_agent = request.headers.get("User-Agent")

        # Prepare details JSON
        details_json = json.dumps(details) if details else "{}"

        try:
            with get_session() as session:
                log_entry = AuditLog(
                    timestamp=datetime.now(UTC),
                    user_id=user_id,
                    username=username,
                    company_id=company_id,
                    event_type=event_type,
                    event_category=event_category,
                    severity=severity,
                    details=details_json,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    session_id=session_id
                )
                session.add(log_entry)
                # Commit is handled by the get_session context manager
            
            # Also log to standard logger
            log_msg = f"[AUDIT] {event_category.upper()} | {event_type} | User: {username or 'System'} | {details_json}"
            if severity == "critical":
                logger.critical(log_msg)
            elif severity == "error":
                logger.error(log_msg)
            elif severity == "warning":
                logger.warning(log_msg)
            else:
                logger.info(log_msg)

            # Integration with App Insights could go here if needed
            if ENABLE_APP_INSIGHTS:
                # Add custom event to telemetry
                pass

        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
            # Fallback to standard logging if DB fails
            logger.info(f"[AUDIT-FALLBACK] {event_type} by {username}: {details_json}")

    # Convenience methods
    @classmethod
    def security_event(cls, event_type: str, severity: str = "info", **kwargs):
        cls.log_event(event_type, "security", severity, **kwargs)

    @classmethod
    def data_event(cls, event_type: str, severity: str = "info", **kwargs):
        cls.log_event(event_type, "data_change", severity, **kwargs)

    @classmethod
    def system_event(cls, event_type: str, severity: str = "info", **kwargs):
        cls.log_event(event_type, "system", severity, **kwargs)

audit_service = AuditService()
