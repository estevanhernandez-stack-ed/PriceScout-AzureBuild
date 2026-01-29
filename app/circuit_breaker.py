"""
Circuit Breaker Pattern Implementation for PriceScout

Prevents cascading failures when external services (like Fandango) are unavailable.
When too many failures occur, the circuit "opens" and rejects requests until
a reset timeout passes, then allows a test request through.

States:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests are rejected
- HALF_OPEN: Testing recovery, one request allowed through

Usage:
    from app.circuit_breaker import fandango_breaker

    if fandango_breaker.can_execute():
        try:
            result = scrape_url(url)
            fandango_breaker.record_success()
        except Exception:
            fandango_breaker.record_failure()
    else:
        # Circuit is open, skip this request
        logger.warning("Circuit breaker open, skipping request")
"""

import os
import time
import logging
from enum import Enum
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional, Dict, Any

from app import config
from app.notification_service import dispatch_system_notification_sync

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Implements the circuit breaker pattern to prevent cascading failures
    when external services are unavailable or degraded.

    Attributes:
        name: Identifier for this circuit breaker
        failure_threshold: Number of failures before opening circuit
        reset_timeout: Seconds to wait before testing recovery
        half_open_max_calls: Max calls allowed in half-open state
    """

    name: str
    failure_threshold: int = 5
    reset_timeout: int = 3600  # 1 hour
    half_open_max_calls: int = 1

    # Internal state (not exposed in __init__)
    _failures: int = field(default=0, init=False, repr=False)
    _successes_in_half_open: int = field(default=0, init=False, repr=False)
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False, repr=False)
    _last_failure_time: float = field(default=0.0, init=False, repr=False)
    _last_state_change: float = field(default_factory=time.time, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def can_execute(self) -> bool:
        """
        Check if a request should proceed.

        Returns:
            True if request should proceed, False if circuit is open
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            elif self._state == CircuitState.OPEN:
                # Check if reset timeout has passed
                if time.time() - self._last_failure_time > self.reset_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
                    logger.info(f"Circuit breaker '{self.name}' transitioning to HALF_OPEN")
                    return True
                return False

            else:  # HALF_OPEN
                # Allow limited requests through to test recovery
                return True

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._successes_in_half_open += 1
                if self._successes_in_half_open >= self.half_open_max_calls:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"Circuit breaker '{self.name}' recovered, transitioning to CLOSED")
            else:
                # Reset failures on success in closed state
                self._failures = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Failed during recovery test, go back to open
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"Circuit breaker '{self.name}' failed recovery test, back to OPEN")

            elif self._state == CircuitState.CLOSED:
                if self._failures >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit breaker '{self.name}' opened after {self._failures} failures"
                    )
                    
                    # Notify admins
                    dispatch_system_notification_sync(
                        title=f"Circuit Breaker '{self.name}' OPEN",
                        message=f"The circuit breaker for '{self.name}' has opened automatically after {self._failures} consecutive failures. External service requests will be rejected for {self.reset_timeout} seconds.",
                        severity="critical"
                    )

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state (must be called with lock held)."""
        self._state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self._failures = 0
            self._successes_in_half_open = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._successes_in_half_open = 0

    def force_open(self) -> None:
        """Manually open the circuit breaker."""
        with self._lock:
            self._transition_to(CircuitState.OPEN)
            self._last_failure_time = time.time()
            logger.warning(f"Circuit breaker '{self.name}' manually opened")
            
            # Notify admins
            dispatch_system_notification_sync(
                title=f"Circuit Breaker '{self.name}' OPEN (Manual)",
                message=f"The circuit breaker for '{self.name}' was manually opened. Requests to this service will be rejected.",
                severity="critical"
            )

    def force_close(self) -> None:
        """Manually close the circuit breaker (reset)."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            logger.info(f"Circuit breaker '{self.name}' manually closed/reset")

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        with self._lock:
            time_since_last_failure = (
                time.time() - self._last_failure_time
                if self._last_failure_time > 0
                else None
            )
            time_until_retry = None
            if self._state == CircuitState.OPEN and self._last_failure_time > 0:
                remaining = self.reset_timeout - (time.time() - self._last_failure_time)
                time_until_retry = max(0, remaining)

            return {
                "name": self.name,
                "state": self._state.value,
                "failures": self._failures,
                "failure_threshold": self.failure_threshold,
                "reset_timeout_seconds": self.reset_timeout,
                "reset_timeout": self.reset_timeout,  # Alias for Pydantic compatibility
                "last_failure_time": self._last_failure_time if self._last_failure_time > 0 else None,
                "last_state_change": self._last_state_change,
                "time_since_last_failure_seconds": (
                    round(time_since_last_failure, 1) if time_since_last_failure else None
                ),
                "time_until_retry_seconds": (
                    round(time_until_retry, 1) if time_until_retry is not None else None
                ),
                "state_duration_seconds": round(time.time() - self._last_state_change, 1)
            }

    @property
    def state(self) -> CircuitState:
        """Get current state (read-only)."""
        return self._state

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self._state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED


# =============================================================================
# Global Circuit Breakers
# =============================================================================

# Fandango scraper circuit breaker
# Opens after 5 consecutive failures, retries after 1 hour
fandango_breaker = CircuitBreaker(
    name="fandango",
    failure_threshold=int(os.getenv('FANDANGO_CIRCUIT_FAILURE_THRESHOLD', '5')),
    reset_timeout=int(os.getenv('FANDANGO_CIRCUIT_RESET_TIMEOUT', '3600'))
)

# EntTelligence API circuit breaker
# Opens after 3 consecutive failures, retries after 5 minutes
enttelligence_breaker = CircuitBreaker(
    name="enttelligence",
    failure_threshold=int(os.getenv('ENTTELLIGENCE_CIRCUIT_FAILURE_THRESHOLD', '3')),
    reset_timeout=int(os.getenv('ENTTELLIGENCE_CIRCUIT_RESET_TIMEOUT', '300'))
)


def get_all_circuit_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all circuit breakers."""
    return {
        "fandango": fandango_breaker.get_status(),
        "enttelligence": enttelligence_breaker.get_status()
    }


def reset_all_circuits() -> None:
    """Reset all circuit breakers to closed state."""
    fandango_breaker.force_close()
    enttelligence_breaker.force_close()
    logger.info("All circuit breakers reset to CLOSED")
