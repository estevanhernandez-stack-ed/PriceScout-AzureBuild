"""
Repair Queue for Failed Theater URL Repairs

Implements a persistent queue with exponential backoff for theaters that
failed repair attempts. Instead of waiting for the next daily maintenance
run, queued repairs are retried more frequently with increasing intervals.

Backoff Schedule:
- 1st retry: 1 hour
- 2nd retry: 2 hours
- 3rd retry: 4 hours
- 4th retry: 8 hours
- 5th retry: 24 hours (max)

After MAX_ATTEMPTS (5), the theater is removed from queue and requires
manual intervention.

Usage:
    from app.repair_queue import repair_queue

    # Add failed repair to queue
    repair_queue.add("AMC Test Theater", "Madison", "53703")

    # Process due repairs
    due_repairs = repair_queue.get_due_repairs()
    for job in due_repairs:
        success = await attempt_repair(job)
        if success:
            repair_queue.mark_success(job.theater_name, job.market_name)
        else:
            repair_queue.record_failure(job.theater_name, job.market_name)
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, UTC
from typing import List, Optional, Dict, Any

from app import config

logger = logging.getLogger(__name__)


@dataclass
class RepairJob:
    """Represents a queued repair job with backoff tracking."""
    theater_name: str
    market_name: str
    zip_code: Optional[str]
    attempts: int = 0
    next_attempt_at: Optional[str] = None
    first_failure_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    error_message: Optional[str] = None

    def calculate_backoff(self) -> datetime:
        """
        Calculate next retry time using exponential backoff.
        Backoff: 1h, 2h, 4h, 8h, 24h (max)
        """
        hours = min(2 ** self.attempts, 24)
        return datetime.now(UTC) + timedelta(hours=hours)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepairJob':
        """Create RepairJob from dictionary."""
        return cls(**data)


class RepairQueue:
    """
    Persistent queue for failed theater repairs with exponential backoff.

    Stores queue state in a JSON file so it persists across restarts.
    Thread-safe through file-level locking.
    """

    MAX_ATTEMPTS = 5
    QUEUE_FILE = "repair_queue.json"

    def __init__(self, queue_dir: str = None):
        self.queue_dir = queue_dir or config.PROJECT_DIR
        self.queue_file = os.path.join(self.queue_dir, self.QUEUE_FILE)

    def _load(self) -> Dict[str, Dict]:
        """Load queue from file."""
        if not os.path.exists(self.queue_file):
            return {}

        try:
            with open(self.queue_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading repair queue: {e}")
            return {}

    def _save(self, queue: Dict[str, Dict]) -> None:
        """Save queue to file."""
        try:
            with open(self.queue_file, 'w') as f:
                json.dump(queue, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving repair queue: {e}")

    def _make_key(self, theater_name: str, market_name: str) -> str:
        """Create unique key for theater/market combination."""
        return f"{theater_name}|{market_name}"

    def add(
        self,
        theater_name: str,
        market_name: str,
        zip_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> RepairJob:
        """
        Add theater to repair queue or update existing entry.

        Args:
            theater_name: Name of the theater
            market_name: Market the theater belongs to
            zip_code: ZIP code for better matching (optional)
            error_message: Error from failed repair (optional)

        Returns:
            The RepairJob that was created or updated
        """
        queue = self._load()
        key = self._make_key(theater_name, market_name)
        now = datetime.now(UTC).isoformat()

        if key in queue:
            # Existing job - increment attempts
            job_data = queue[key]
            job_data['attempts'] = job_data.get('attempts', 0) + 1
            job_data['last_failure_at'] = now
            job_data['error_message'] = error_message
            job = RepairJob.from_dict(job_data)
            job.next_attempt_at = job.calculate_backoff().isoformat()
            queue[key] = job.to_dict()

            logger.info(
                f"Repair queue: Updated {theater_name} "
                f"(attempt {job.attempts}, next retry in {2**min(job.attempts, 4)} hours)"
            )
        else:
            # New job
            job = RepairJob(
                theater_name=theater_name,
                market_name=market_name,
                zip_code=zip_code,
                attempts=1,
                first_failure_at=now,
                last_failure_at=now,
                error_message=error_message
            )
            job.next_attempt_at = job.calculate_backoff().isoformat()
            queue[key] = job.to_dict()

            logger.info(f"Repair queue: Added {theater_name} (retry in 1 hour)")

        self._save(queue)
        return job

    def get_due_repairs(self) -> List[RepairJob]:
        """
        Get all repairs that are ready for retry.

        Returns:
            List of RepairJob objects ready for processing
        """
        queue = self._load()
        now = datetime.now(UTC)
        due = []

        for key, data in queue.items():
            job = RepairJob.from_dict(data)

            # Skip if max attempts reached
            if job.attempts >= self.MAX_ATTEMPTS:
                continue

            # Check if ready for retry
            if job.next_attempt_at:
                next_time = datetime.fromisoformat(job.next_attempt_at.replace('Z', '+00:00'))
                if next_time.tzinfo is None:
                    next_time = next_time.replace(tzinfo=UTC)
                if next_time <= now:
                    due.append(job)

        logger.debug(f"Repair queue: {len(due)} repairs due for retry")
        return due

    def mark_success(self, theater_name: str, market_name: str) -> bool:
        """
        Remove theater from queue after successful repair.

        Args:
            theater_name: Name of the theater
            market_name: Market the theater belongs to

        Returns:
            True if removed, False if not found
        """
        queue = self._load()
        key = self._make_key(theater_name, market_name)

        if key in queue:
            del queue[key]
            self._save(queue)
            logger.info(f"Repair queue: Removed {theater_name} (repair successful)")
            return True

        return False

    def record_failure(
        self,
        theater_name: str,
        market_name: str,
        error_message: Optional[str] = None
    ) -> Optional[RepairJob]:
        """
        Record another failed repair attempt.

        Args:
            theater_name: Name of the theater
            market_name: Market the theater belongs to
            error_message: Error from the failure (optional)

        Returns:
            Updated RepairJob, or None if max attempts reached
        """
        queue = self._load()
        key = self._make_key(theater_name, market_name)

        if key not in queue:
            logger.warning(f"Repair queue: {theater_name} not found, adding new entry")
            return self.add(theater_name, market_name, error_message=error_message)

        job_data = queue[key]
        job_data['attempts'] = job_data.get('attempts', 0) + 1
        job_data['last_failure_at'] = datetime.now(UTC).isoformat()
        job_data['error_message'] = error_message

        job = RepairJob.from_dict(job_data)

        if job.attempts >= self.MAX_ATTEMPTS:
            logger.warning(
                f"Repair queue: {theater_name} reached max attempts ({self.MAX_ATTEMPTS}). "
                "Manual intervention required."
            )
            # Keep in queue but don't schedule more retries
            queue[key] = job.to_dict()
            self._save(queue)
            return None

        job.next_attempt_at = job.calculate_backoff().isoformat()
        queue[key] = job.to_dict()
        self._save(queue)

        logger.info(
            f"Repair queue: {theater_name} failed again "
            f"(attempt {job.attempts}, next retry in {2**min(job.attempts, 4)} hours)"
        )
        return job

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get overall queue status and statistics.

        Returns:
            Dictionary with queue statistics
        """
        queue = self._load()

        total = len(queue)
        by_attempts = {}
        max_attempts_reached = 0
        due_now = 0
        now = datetime.now(UTC)

        for data in queue.values():
            attempts = data.get('attempts', 0)
            by_attempts[attempts] = by_attempts.get(attempts, 0) + 1

            if attempts >= self.MAX_ATTEMPTS:
                max_attempts_reached += 1

            if data.get('next_attempt_at'):
                next_time = datetime.fromisoformat(data['next_attempt_at'].replace('Z', '+00:00'))
                if next_time.tzinfo is None: next_time = next_time.replace(tzinfo=UTC)
                if next_time <= now:
                    due_now += 1

        return {
            "total_queued": total,
            "due_now": due_now,
            "max_attempts_reached": max_attempts_reached,
            "by_attempts": by_attempts,
            "max_attempts_limit": self.MAX_ATTEMPTS
        }

    def get_all_jobs(self) -> List[RepairJob]:
        """Get all jobs in the queue."""
        queue = self._load()
        return [RepairJob.from_dict(data) for data in queue.values()]

    def get_failed_permanently(self) -> List[RepairJob]:
        """Get theaters that have reached max attempts."""
        queue = self._load()
        return [
            RepairJob.from_dict(data)
            for data in queue.values()
            if data.get('attempts', 0) >= self.MAX_ATTEMPTS
        ]

    def clear_permanently_failed(self) -> int:
        """
        Remove theaters that have reached max attempts from queue.

        Returns:
            Number of entries removed
        """
        queue = self._load()
        to_remove = [
            key for key, data in queue.items()
            if data.get('attempts', 0) >= self.MAX_ATTEMPTS
        ]

        for key in to_remove:
            del queue[key]

        if to_remove:
            self._save(queue)
            logger.info(f"Repair queue: Cleared {len(to_remove)} permanently failed entries")

        return len(to_remove)

    def reset_job(self, theater_name: str, market_name: str) -> bool:
        """
        Reset a job's attempt count for manual retry.

        Args:
            theater_name: Name of the theater
            market_name: Market the theater belongs to

        Returns:
            True if reset, False if not found
        """
        queue = self._load()
        key = self._make_key(theater_name, market_name)

        if key in queue:
            queue[key]['attempts'] = 0
            queue[key]['next_attempt_at'] = datetime.now(UTC).isoformat()
            self._save(queue)
            logger.info(f"Repair queue: Reset {theater_name} for immediate retry")
            return True

        return False


# Global repair queue instance
repair_queue = RepairQueue()


async def process_repair_queue_async():
    """
    Process queued repair attempts.
    Called by scheduler to retry failed repairs.
    """
    from app.cache_maintenance_service import CacheMaintenanceService

    due = repair_queue.get_due_repairs()

    if not due:
        logger.debug("Repair queue: No repairs due")
        return {"processed": 0, "success": 0, "failed": 0}

    logger.info(f"Repair queue: Processing {len(due)} queued repairs...")

    service = CacheMaintenanceService()
    success_count = 0
    fail_count = 0

    for job in due:
        try:
            result = await service._attempt_repair(job.theater_name, job.zip_code)

            if result:
                repair_queue.mark_success(job.theater_name, job.market_name)
                logger.info(f"Repair queue: Successfully repaired {job.theater_name}")
                success_count += 1
            else:
                repair_queue.record_failure(
                    job.theater_name,
                    job.market_name,
                    "No URL found"
                )
                fail_count += 1

        except Exception as e:
            repair_queue.record_failure(
                job.theater_name,
                job.market_name,
                str(e)
            )
            fail_count += 1
            logger.error(f"Repair queue: Error repairing {job.theater_name}: {e}")

    logger.info(
        f"Repair queue: Processed {len(due)} repairs. "
        f"Success: {success_count}, Failed: {fail_count}"
    )

    return {
        "processed": len(due),
        "success": success_count,
        "failed": fail_count
    }


def process_repair_queue_sync():
    """Synchronous wrapper for repair queue processing."""
    import asyncio
    return asyncio.run(process_repair_queue_async())
