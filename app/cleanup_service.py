"""
Data Retention and Cleanup Service

Automatically cleans up old data based on configured retention periods:
- Acknowledged alerts (price and schedule) after 90 days
- Expired baselines after 180 days
- Old scrape runs after 365 days
- Audit logs after 365 days
- Expired cache entries immediately
- Log file rotation

Usage:
    from app.cleanup_service import CleanupService

    service = CleanupService()
    result = service.run_cleanup()
"""

import os
import json
import glob
import logging
from datetime import datetime, timedelta, UTC
from typing import Dict, Any, List
import sqlite3

from app import config

logger = logging.getLogger(__name__)


class CleanupService:
    """Data retention and cleanup service."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(config.PROJECT_DIR, 'pricescout.db')

        # Load retention periods from config
        self.retention = {
            'acknowledged_alerts': config.RETENTION_ACKNOWLEDGED_ALERTS,
            'expired_baselines': config.RETENTION_EXPIRED_BASELINES,
            'scrape_runs': config.RETENTION_SCRAPE_RUNS,
            'audit_logs': config.RETENTION_AUDIT_LOGS,
            'log_files': config.RETENTION_LOG_FILES,
        }

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_exists(self, cursor, table_name: str) -> bool:
        """Check if a table exists."""
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table_name,))
        return cursor.fetchone() is not None

    def run_cleanup(self) -> Dict[str, Any]:
        """
        Run full cleanup cycle.

        Returns:
            Dict with counts of records deleted per category
        """
        logger.info("Starting data cleanup cycle...")
        start_time = datetime.now(UTC)

        results = {
            'timestamp': start_time.isoformat(),
            'retention_config': self.retention,
            'deleted': {}
        }

        try:
            results['deleted']['price_alerts'] = self._cleanup_price_alerts()
            results['deleted']['schedule_alerts'] = self._cleanup_schedule_alerts()
            results['deleted']['price_baselines'] = self._cleanup_price_baselines()
            results['deleted']['schedule_baselines'] = self._cleanup_schedule_baselines()
            results['deleted']['expired_cache'] = self._cleanup_expired_cache()
            results['deleted']['scrape_runs'] = self._cleanup_old_scrapes()
            results['deleted']['audit_logs'] = self._cleanup_audit_logs()
            results['deleted']['log_files'] = self._rotate_log_files()

            results['status'] = 'completed'
            results['duration_seconds'] = (datetime.now(UTC) - start_time).total_seconds()

            total_deleted = sum(v for v in results['deleted'].values() if isinstance(v, int))
            logger.info(f"Cleanup complete. {total_deleted} total records deleted in {results['duration_seconds']:.1f}s")

        except Exception as e:
            results['status'] = 'error'
            results['error'] = str(e)
            logger.error(f"Cleanup failed: {e}", exc_info=True)

        return results

    def _cleanup_price_alerts(self) -> int:
        """Delete acknowledged price alerts older than retention period."""
        if self.retention['acknowledged_alerts'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'price_alerts'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['acknowledged_alerts'])

            cursor.execute("""
                DELETE FROM price_alerts
                WHERE is_acknowledged = 1 AND acknowledged_at < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} acknowledged price alerts older than {self.retention['acknowledged_alerts']} days")

            return deleted

        finally:
            conn.close()

    def _cleanup_schedule_alerts(self) -> int:
        """Delete acknowledged schedule alerts older than retention period."""
        if self.retention['acknowledged_alerts'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'schedule_alerts'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['acknowledged_alerts'])

            cursor.execute("""
                DELETE FROM schedule_alerts
                WHERE is_acknowledged = 1 AND acknowledged_at < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} acknowledged schedule alerts older than {self.retention['acknowledged_alerts']} days")

            return deleted

        finally:
            conn.close()

    def _cleanup_price_baselines(self) -> int:
        """Delete expired price baselines older than retention period."""
        if self.retention['expired_baselines'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'price_baselines'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['expired_baselines'])

            # Only delete baselines that have been superseded (effective_to is set)
            cursor.execute("""
                DELETE FROM price_baselines
                WHERE effective_to IS NOT NULL AND effective_to < ?
            """, (cutoff.date().isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} expired price baselines older than {self.retention['expired_baselines']} days")

            return deleted

        finally:
            conn.close()

    def _cleanup_schedule_baselines(self) -> int:
        """Delete expired schedule baselines older than retention period."""
        if self.retention['expired_baselines'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'schedule_baselines'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['expired_baselines'])

            # Only delete baselines that have been superseded (effective_to is set)
            cursor.execute("""
                DELETE FROM schedule_baselines
                WHERE effective_to IS NOT NULL AND effective_to < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} expired schedule baselines older than {self.retention['expired_baselines']} days")

            return deleted

        finally:
            conn.close()

    def _cleanup_expired_cache(self) -> int:
        """Delete expired EntTelligence cache entries."""
        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'enttelligence_price_cache'):
                return 0

            now = datetime.now(UTC).isoformat()

            cursor.execute("""
                DELETE FROM enttelligence_price_cache
                WHERE expires_at IS NOT NULL AND expires_at < ?
            """, (now,))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} expired cache entries")

            return deleted

        finally:
            conn.close()

    def _cleanup_old_scrapes(self) -> int:
        """Delete old scrape runs and cascade to prices/showtimes."""
        if self.retention['scrape_runs'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'scrape_runs'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['scrape_runs'])

            # Get count of runs to delete
            cursor.execute("""
                SELECT COUNT(*) FROM scrape_runs
                WHERE run_timestamp < ?
            """, (cutoff.isoformat(),))
            count = cursor.fetchone()[0]

            if count == 0:
                return 0

            # Delete associated prices first (if foreign key constraints don't cascade)
            if self._table_exists(cursor, 'prices'):
                cursor.execute("""
                    DELETE FROM prices
                    WHERE run_id IN (
                        SELECT run_id FROM scrape_runs WHERE run_timestamp < ?
                    )
                """, (cutoff.isoformat(),))

            # Delete associated operating_hours
            if self._table_exists(cursor, 'operating_hours'):
                cursor.execute("""
                    DELETE FROM operating_hours
                    WHERE run_id IN (
                        SELECT run_id FROM scrape_runs WHERE run_timestamp < ?
                    )
                """, (cutoff.isoformat(),))

            # Delete the scrape runs
            cursor.execute("""
                DELETE FROM scrape_runs
                WHERE run_timestamp < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} scrape runs (and associated data) older than {self.retention['scrape_runs']} days")

            return deleted

        finally:
            conn.close()

    def _cleanup_audit_logs(self) -> int:
        """Delete old audit log entries."""
        if self.retention['audit_logs'] <= 0:
            return 0

        if not os.path.exists(self.db_path):
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if not self._table_exists(cursor, 'audit_log'):
                return 0

            cutoff = datetime.now(UTC) - timedelta(days=self.retention['audit_logs'])

            cursor.execute("""
                DELETE FROM audit_log
                WHERE timestamp < ?
            """, (cutoff.isoformat(),))

            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info(f"Deleted {deleted} audit log entries older than {self.retention['audit_logs']} days")

            return deleted

        finally:
            conn.close()

    def _rotate_log_files(self) -> int:
        """Rotate and clean up old log files."""
        if self.retention['log_files'] <= 0:
            return 0

        rotated = 0
        cutoff = datetime.now(UTC) - timedelta(days=self.retention['log_files'])

        # Log files to check
        log_patterns = [
            os.path.join(config.PROJECT_DIR, '*.log'),
            os.path.join(config.PROJECT_DIR, 'logs', '*.log'),
        ]

        for pattern in log_patterns:
            for log_file in glob.glob(pattern):
                try:
                    # Check file modification time
                    mtime = datetime.fromtimestamp(os.path.getmtime(log_file))

                    if mtime < cutoff:
                        # Archive old log files by truncating them
                        file_size = os.path.getsize(log_file)
                        if file_size > 0:
                            # Keep last 1000 lines
                            with open(log_file, 'r') as f:
                                lines = f.readlines()

                            if len(lines) > 1000:
                                with open(log_file, 'w') as f:
                                    f.writelines(lines[-1000:])
                                rotated += 1
                                logger.info(f"Rotated log file: {log_file}")

                except Exception as e:
                    logger.warning(f"Failed to rotate log file {log_file}: {e}")

        # Clean up cache_maintenance.log (JSONL format)
        maintenance_log = os.path.join(config.PROJECT_DIR, 'cache_maintenance.log')
        if os.path.exists(maintenance_log):
            try:
                with open(maintenance_log, 'r') as f:
                    lines = f.readlines()

                # Keep only entries from last retention period
                kept_lines = []
                for line in lines:
                    try:
                        entry = json.loads(line.strip())
                        ts = entry.get('timestamp', '')
                        entry_time = datetime.fromisoformat(ts.replace('Z', '+00:00')) if ts else None
                        if entry_time and entry_time.tzinfo is None: entry_time = entry_time.replace(tzinfo=UTC)
                        if entry_time > cutoff:
                            kept_lines.append(line)
                    except (json.JSONDecodeError, ValueError):
                        pass  # Skip invalid lines

                if len(kept_lines) < len(lines):
                    with open(maintenance_log, 'w') as f:
                        f.writelines(kept_lines)
                    rotated += 1
                    logger.info(f"Cleaned cache_maintenance.log: kept {len(kept_lines)} of {len(lines)} entries")

            except Exception as e:
                logger.warning(f"Failed to clean maintenance log: {e}")

        return rotated

    def get_cleanup_summary(self) -> Dict[str, Any]:
        """
        Get summary of data that would be cleaned up without actually deleting.

        Returns:
            Dict with counts of records that would be deleted
        """
        summary = {
            'retention_config': self.retention,
            'would_delete': {}
        }

        if not os.path.exists(self.db_path):
            return summary

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Price alerts
            if self._table_exists(cursor, 'price_alerts'):
                cutoff = datetime.now(UTC) - timedelta(days=self.retention['acknowledged_alerts'])
                cursor.execute("""
                    SELECT COUNT(*) FROM price_alerts
                    WHERE is_acknowledged = 1 AND acknowledged_at < ?
                """, (cutoff.isoformat(),))
                summary['would_delete']['price_alerts'] = cursor.fetchone()[0]

            # Schedule alerts
            if self._table_exists(cursor, 'schedule_alerts'):
                cutoff = datetime.now(UTC) - timedelta(days=self.retention['acknowledged_alerts'])
                cursor.execute("""
                    SELECT COUNT(*) FROM schedule_alerts
                    WHERE is_acknowledged = 1 AND acknowledged_at < ?
                """, (cutoff.isoformat(),))
                summary['would_delete']['schedule_alerts'] = cursor.fetchone()[0]

            # Scrape runs
            if self._table_exists(cursor, 'scrape_runs'):
                cutoff = datetime.now(UTC) - timedelta(days=self.retention['scrape_runs'])
                cursor.execute("""
                    SELECT COUNT(*) FROM scrape_runs
                    WHERE run_timestamp < ?
                """, (cutoff.isoformat(),))
                summary['would_delete']['scrape_runs'] = cursor.fetchone()[0]

            # Expired cache
            if self._table_exists(cursor, 'enttelligence_price_cache'):
                cursor.execute("""
                    SELECT COUNT(*) FROM enttelligence_price_cache
                    WHERE expires_at IS NOT NULL AND expires_at < ?
                """, (datetime.now(UTC).isoformat(),))
                summary['would_delete']['expired_cache'] = cursor.fetchone()[0]

        finally:
            conn.close()

        return summary


def run_cleanup() -> Dict[str, Any]:
    """Convenience function to run cleanup."""
    service = CleanupService()
    return service.run_cleanup()
