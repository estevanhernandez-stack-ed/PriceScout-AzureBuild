"""
Schedule Monitor Service
Detects when movie theaters post new showtimes, films, or schedule changes.

This service:
1. Creates baseline snapshots of theater schedules
2. Compares current schedules against baselines
3. Generates alerts for detected changes
"""

import json
import logging
import os
import sqlite3
from datetime import datetime, date, timedelta, UTC
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

from app import config

logger = logging.getLogger(__name__)


@dataclass
class ScheduleChange:
    """Represents a detected schedule change"""
    theater_name: str
    film_title: Optional[str]
    play_date: str
    alert_type: str  # new_film, new_showtime, removed_showtime, removed_film, format_added, new_schedule, event_added, presale_started
    old_value: Optional[Dict]
    new_value: Optional[Dict]
    change_details: str

EVENT_KEYWORDS = ['Event', 'Early Access', 'Q&A', 'Special Screening', 'Fan Event', 'Premiere']

class ScheduleMonitorService:
    """
    Service for monitoring and detecting schedule changes.
    Compares current EntTelligence data against stored baselines.
    """

    def __init__(self, company_id: int):
        self.company_id = company_id
        self.db_path = getattr(config, 'DB_FILE', None) or os.path.join(config.PROJECT_DIR, 'pricescout.db')

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_or_create_config(self) -> Dict[str, Any]:
        """
        Get monitoring configuration for company, creating default if needed.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM schedule_monitor_config
                WHERE company_id = ?
            """, (self.company_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)

            # Create default config
            cursor.execute("""
                INSERT INTO schedule_monitor_config (company_id)
                VALUES (?)
            """, (self.company_id,))
            conn.commit()

            # Fetch the newly created config
            cursor.execute("""
                SELECT * FROM schedule_monitor_config
                WHERE company_id = ?
            """, (self.company_id,))
            return dict(cursor.fetchone())

        finally:
            conn.close()

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update monitoring configuration.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build update query dynamically
            allowed_fields = [
                'is_enabled', 'check_frequency_hours',
                'alert_on_new_film', 'alert_on_new_showtime',
                'alert_on_removed_showtime', 'alert_on_removed_film',
                'alert_on_format_added', 'alert_on_time_changed',
                'alert_on_new_schedule', 'alert_on_event', 'alert_on_presale',
                'theaters_filter', 'films_filter', 'circuits_filter',
                'days_ahead', 'notification_enabled',
                'webhook_url', 'notification_email'
            ]

            set_clauses = []
            values = []
            for field in allowed_fields:
                if field in updates:
                    set_clauses.append(f"{field} = ?")
                    value = updates[field]
                    # Convert lists to JSON strings
                    if isinstance(value, list):
                        value = json.dumps(value)
                    values.append(value)

            if set_clauses:
                set_clauses.append("updated_at = ?")
                values.append(datetime.now(UTC).isoformat())
                values.append(self.company_id)

                cursor.execute(f"""
                    UPDATE schedule_monitor_config
                    SET {', '.join(set_clauses)}
                    WHERE company_id = ?
                """, values)
                conn.commit()

            return self.get_or_create_config()

        finally:
            conn.close()

    def create_baseline_snapshot(
        self,
        theater_name: str,
        film_title: str,
        play_date: str,
        showtimes: List[Dict],
        source: str = 'enttelligence',
        user_id: Optional[int] = None
    ) -> int:
        """
        Create a baseline snapshot for a theater/film/date.
        Returns the baseline_id.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC).isoformat()

            # Mark any existing baseline as expired
            cursor.execute("""
                UPDATE schedule_baselines
                SET effective_to = ?
                WHERE company_id = ?
                  AND theater_name = ?
                  AND film_title = ?
                  AND play_date = ?
                  AND effective_to IS NULL
            """, (now, self.company_id, theater_name, film_title, play_date))

            # Insert new baseline
            cursor.execute("""
                INSERT INTO schedule_baselines
                (company_id, theater_name, film_title, play_date, showtimes,
                 snapshot_at, source, effective_from, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.company_id, theater_name, film_title, play_date,
                json.dumps(showtimes), now, source, now, user_id
            ))

            conn.commit()
            return cursor.lastrowid

        finally:
            conn.close()

    def get_current_baseline(
        self,
        theater_name: str,
        film_title: str,
        play_date: str
    ) -> Optional[Dict]:
        """
        Get the current (active) baseline for a theater/film/date.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM schedule_baselines
                WHERE company_id = ?
                  AND theater_name = ?
                  AND film_title = ?
                  AND play_date = ?
                  AND effective_to IS NULL
                ORDER BY effective_from DESC
                LIMIT 1
            """, (self.company_id, theater_name, film_title, play_date))

            row = cursor.fetchone()
            if row:
                result = dict(row)
                result['showtimes'] = json.loads(result['showtimes']) if result['showtimes'] else []
                return result
            return None

        finally:
            conn.close()

    def get_theater_baselines(self, theater_name: str, play_date: str) -> List[Dict]:
        """
        Get all current baselines for a theater on a date.
        Returns list of baselines (one per film).
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT * FROM schedule_baselines
                WHERE company_id = ?
                  AND theater_name = ?
                  AND play_date = ?
                  AND effective_to IS NULL
                ORDER BY film_title
            """, (self.company_id, theater_name, play_date))

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                result['showtimes'] = json.loads(result['showtimes']) if result['showtimes'] else []
                results.append(result)
            return results

        finally:
            conn.close()

    def create_baselines_from_cache(
        self,
        theater_names: Optional[List[str]] = None,
        play_dates: Optional[List[str]] = None,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Create baseline snapshots from current EntTelligence cache data.
        This is used to establish the initial baseline before monitoring.

        Returns:
            Dict with counts of baselines created
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build query to get current schedule from EntTelligence cache
            query = """
                SELECT DISTINCT theater_name, film_title, play_date, showtime, format
                FROM enttelligence_price_cache
                WHERE company_id = ?
            """
            params = [self.company_id]

            if theater_names:
                placeholders = ','.join(['?' for _ in theater_names])
                query += f" AND theater_name IN ({placeholders})"
                params.extend(theater_names)

            if play_dates:
                placeholders = ','.join(['?' for _ in play_dates])
                query += f" AND play_date IN ({placeholders})"
                params.extend(play_dates)

            query += " ORDER BY theater_name, film_title, play_date, showtime"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Group by theater/film/date
            schedules = {}
            for row in rows:
                key = (row['theater_name'], row['film_title'], row['play_date'])
                if key not in schedules:
                    schedules[key] = []
                schedules[key].append({
                    'time': row['showtime'],
                    'format': row['format']
                })

            # Create baselines
            baselines_created = 0
            theaters_processed = set()
            films_processed = set()

            for (theater, film, pdate), showtimes in schedules.items():
                self.create_baseline_snapshot(
                    theater_name=theater,
                    film_title=film,
                    play_date=pdate,
                    showtimes=showtimes,
                    source='enttelligence',
                    user_id=user_id
                )
                baselines_created += 1
                theaters_processed.add(theater)
                films_processed.add(film)

            return {
                'baselines_created': baselines_created,
                'theaters_processed': len(theaters_processed),
                'films_processed': len(films_processed)
            }

        finally:
            conn.close()

    def detect_changes(
        self,
        theater_name: str,
        play_date: str,
        current_schedule: Dict[str, List[Dict]]
    ) -> List[ScheduleChange]:
        """
        Compare current schedule against baselines and detect changes.

        Args:
            theater_name: Theater to check
            play_date: Date to check
            current_schedule: Dict mapping film_title -> list of showtime dicts

        Returns:
            List of ScheduleChange objects
        """
        changes = []

        # Get baselines for this theater/date
        baselines = self.get_theater_baselines(theater_name, play_date)
        baseline_films = {b['film_title']: b for b in baselines}

        # --- NEW: Check against configured operating hours ---
        from app.db_adapter import get_configured_operating_hours
        from app.utils import normalize_time_string
        config_hours = get_configured_operating_hours(theater_name)
        if config_hours:
            play_date_dt = datetime.fromisoformat(play_date)
            day_of_week = play_date_dt.weekday()
            day_config = next((h for h in config_hours if h['day_of_week'] == day_of_week), None)

            if day_config and day_config['first_showtime'] and day_config['last_showtime']:
                target_first = datetime.strptime(normalize_time_string(day_config['first_showtime']), "%I:%M%p").time()
                target_last = datetime.strptime(normalize_time_string(day_config['last_showtime']), "%I:%M%p").time()

                all_current_showtimes = []
                for f_title, f_showtimes in current_schedule.items():
                    for s in f_showtimes:
                        try:
                            s_time = datetime.strptime(normalize_time_string(s['time']), "%I:%M%p").time()
                            all_current_showtimes.append((f_title, s['time'], s_time))
                        except (ValueError, TypeError):
                            continue

                if all_current_showtimes:
                    # Check for showtimes before first start
                    earliest = min(all_current_showtimes, key=lambda x: x[2])
                    if earliest[2] < target_first:
                        changes.append(ScheduleChange(
                            theater_name=theater_name,
                            film_title=earliest[0],
                            play_date=play_date,
                            alert_type='out_of_hours',
                            old_value={'target_first': day_config['first_showtime']},
                            new_value={'actual_time': earliest[1]},
                            change_details=f"Showtime {earliest[1]} for '{earliest[0]}' is earlier than configured first start time {day_config['first_showtime']}"
                        ))

                    # Check for showtimes after last start
                    latest = max(all_current_showtimes, key=lambda x: x[2])
                    if latest[2] > target_last:
                        changes.append(ScheduleChange(
                            theater_name=theater_name,
                            film_title=latest[0],
                            play_date=play_date,
                            alert_type='out_of_hours',
                            old_value={'target_last': day_config['last_showtime']},
                            new_value={'actual_time': latest[1]},
                            change_details=f"Showtime {latest[1]} for '{latest[0]}' is later than configured last start time {day_config['last_showtime']}"
                        ))

        # --- Check for New Schedule Posting (First time showtimes appear for this date) ---
        if not baseline_films and current_schedule:
            total_showtimes = sum(len(s) for s in current_schedule.values())
            changes.append(ScheduleChange(
                theater_name=theater_name,
                film_title=None,
                play_date=play_date,
                alert_type='new_schedule',
                old_value=None,
                new_value={'films_count': len(current_schedule), 'showtimes_count': total_showtimes},
                change_details=f"New schedule posted for {play_date} with {len(current_schedule)} films and {total_showtimes} showtimes"
            ))

        # Check for new films
        for film_title, showtimes in current_schedule.items():
            # Event detection
            is_event = any(keyword.lower() in film_title.lower() for keyword in EVENT_KEYWORDS)

            if film_title not in baseline_films:
                alert_type = 'event_added' if is_event else 'new_film'
                details = f"New {'event' if is_event else 'film'} '{film_title}' added with {len(showtimes)} showtime(s)"
                
                changes.append(ScheduleChange(
                    theater_name=theater_name,
                    film_title=film_title,
                    play_date=play_date,
                    alert_type=alert_type,
                    old_value=None,
                    new_value={'showtimes': showtimes, 'is_event': is_event},
                    change_details=details
                ))
                
                # Check for presale (if this is for a future date)
                # In a real scenario, we would check the presale_buildup table or current sync data
                # For now, we'll flag it if it's an event or major release placeholder
                if is_event:
                    changes.append(ScheduleChange(
                        theater_name=theater_name,
                        film_title=film_title,
                        play_date=play_date,
                        alert_type='presale_started',
                        old_value=None,
                        new_value={'is_event': True},
                        change_details=f"Presale started for event '{film_title}' on {play_date}"
                    ))
            else:
                # Compare showtimes for existing film
                baseline = baseline_films[film_title]
                baseline_times = set(s.get('time', '') for s in baseline['showtimes'])
                current_times = set(s.get('time', '') for s in showtimes)

                # New showtimes
                new_times = current_times - baseline_times
                for time in new_times:
                    showtime_info = next((s for s in showtimes if s.get('time') == time), {})
                    changes.append(ScheduleChange(
                        theater_name=theater_name,
                        film_title=film_title,
                        play_date=play_date,
                        alert_type='new_showtime',
                        old_value=None,
                        new_value={'time': time, 'format': showtime_info.get('format')},
                        change_details=f"New showtime {time} added for '{film_title}'"
                    ))

                # Removed showtimes
                removed_times = baseline_times - current_times
                for time in removed_times:
                    showtime_info = next((s for s in baseline['showtimes'] if s.get('time') == time), {})
                    changes.append(ScheduleChange(
                        theater_name=theater_name,
                        film_title=film_title,
                        play_date=play_date,
                        alert_type='removed_showtime',
                        old_value={'time': time, 'format': showtime_info.get('format')},
                        new_value=None,
                        change_details=f"Showtime {time} removed for '{film_title}'"
                    ))

                # Check for new formats
                baseline_formats = set(s.get('format') for s in baseline['showtimes'] if s.get('format'))
                current_formats = set(s.get('format') for s in showtimes if s.get('format'))
                new_formats = current_formats - baseline_formats
                for fmt in new_formats:
                    changes.append(ScheduleChange(
                        theater_name=theater_name,
                        film_title=film_title,
                        play_date=play_date,
                        alert_type='format_added',
                        old_value=None,
                        new_value={'format': fmt},
                        change_details=f"New format '{fmt}' available for '{film_title}'"
                    ))

        # Check for removed films
        for film_title, baseline in baseline_films.items():
            if film_title not in current_schedule:
                changes.append(ScheduleChange(
                    theater_name=theater_name,
                    film_title=film_title,
                    play_date=play_date,
                    alert_type='removed_film',
                    old_value={'showtimes': baseline['showtimes']},
                    new_value=None,
                    change_details=f"Film '{film_title}' removed from schedule"
                ))

        return changes

    def save_alert(self, change: ScheduleChange, baseline_id: Optional[int] = None) -> int:
        """
        Save a schedule alert to the database.
        Returns the alert_id.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            now = datetime.now(UTC).isoformat()

            cursor.execute("""
                INSERT INTO schedule_alerts
                (company_id, theater_name, film_title, play_date, alert_type,
                 old_value, new_value, change_details, source, baseline_id,
                 triggered_at, detected_at, is_acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.company_id,
                change.theater_name,
                change.film_title,
                change.play_date,
                change.alert_type,
                json.dumps(change.old_value) if change.old_value else None,
                json.dumps(change.new_value) if change.new_value else None,
                change.change_details,
                'enttelligence',
                baseline_id,
                now,
                now,
                0
            ))

            conn.commit()
            return cursor.lastrowid

        finally:
            conn.close()

    def get_alerts(
        self,
        is_acknowledged: Optional[bool] = None,
        alert_type: Optional[str] = None,
        theater_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Get schedule alerts with optional filters.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            query = """
                SELECT * FROM schedule_alerts
                WHERE company_id = ?
            """
            params = [self.company_id]

            if is_acknowledged is not None:
                query += " AND is_acknowledged = ?"
                params.append(1 if is_acknowledged else 0)

            if alert_type:
                query += " AND alert_type = ?"
                params.append(alert_type)

            if theater_name:
                query += " AND theater_name LIKE ?"
                params.append(f"%{theater_name}%")

            query += " ORDER BY triggered_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                if result.get('old_value'):
                    result['old_value'] = json.loads(result['old_value'])
                if result.get('new_value'):
                    result['new_value'] = json.loads(result['new_value'])
                results.append(result)

            return results

        finally:
            conn.close()

    def get_alert_summary(self) -> Dict[str, Any]:
        """
        Get summary statistics for schedule alerts.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Total pending/acknowledged
            cursor.execute("""
                SELECT
                    SUM(CASE WHEN is_acknowledged = 1 THEN 0 ELSE 1 END) as pending,
                    SUM(CASE WHEN is_acknowledged = 1 THEN 1 ELSE 0 END) as acknowledged
                FROM schedule_alerts
                WHERE company_id = ?
            """, (self.company_id,))
            totals = cursor.fetchone()

            # By type
            cursor.execute("""
                SELECT alert_type, COUNT(*) as count
                FROM schedule_alerts
                WHERE company_id = ? AND (is_acknowledged = 0 OR is_acknowledged IS NULL)
                GROUP BY alert_type
            """, (self.company_id,))
            rows_type = cursor.fetchall()
            by_type = {row['alert_type']: row['count'] for row in rows_type}

            # By theater (top 5)
            cursor.execute("""
                SELECT theater_name, COUNT(*) as count
                FROM schedule_alerts
                WHERE company_id = ? AND (is_acknowledged = 0 OR is_acknowledged IS NULL)
                GROUP BY theater_name
                ORDER BY count DESC
                LIMIT 5
            """, (self.company_id,))
            rows_theater = cursor.fetchall()
            by_theater = {row['theater_name']: row['count'] for row in rows_theater}

            # Oldest/newest pending
            cursor.execute("""
                SELECT MIN(triggered_at) as oldest, MAX(triggered_at) as newest
                FROM schedule_alerts
                WHERE company_id = ? AND (is_acknowledged = 0 OR is_acknowledged IS NULL)
            """, (self.company_id,))
            timestamps = cursor.fetchone()

            return {
                'total_pending': totals['pending'] or 0,
                'total_acknowledged': totals['acknowledged'] or 0,
                'by_type': by_type,
                'by_theater': by_theater,
                'oldest_pending': timestamps['oldest'],
                'newest_pending': timestamps['newest']
            }

        finally:
            conn.close()

    def acknowledge_alert(
        self,
        alert_id: int,
        user_id: int,
        notes: Optional[str] = None
    ) -> bool:
        """
        Acknowledge a schedule alert.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE schedule_alerts
                SET is_acknowledged = 1,
                    acknowledged_by = ?,
                    acknowledged_at = ?,
                    acknowledgment_notes = ?
                WHERE alert_id = ? AND company_id = ?
            """, (user_id, datetime.now(UTC).isoformat(), notes, alert_id, self.company_id))

            conn.commit()
            return cursor.rowcount > 0

        finally:
            conn.close()

    def run_check(
        self,
        theater_names: Optional[List[str]] = None,
        play_dates: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a schedule check against baselines.
        Compares current EntTelligence cache data against stored baselines.

        Returns:
            Dict with check results and counts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        alerts_created = 0
        theaters_checked = set()
        changes_detected = []

        try:
            config = self.get_or_create_config()
            # Build query to get current schedule from EntTelligence cache
            query = """
                SELECT DISTINCT theater_name, film_title, play_date, showtime, format
                FROM enttelligence_price_cache
                WHERE company_id = ?
            """
            params = [self.company_id]

            if theater_names:
                placeholders = ','.join(['?' for _ in theater_names])
                query += f" AND theater_name IN ({placeholders})"
                params.extend(theater_names)

            if play_dates:
                placeholders = ','.join(['?' for _ in play_dates])
                query += f" AND play_date IN ({placeholders})"
                params.extend(play_dates)

            query += " ORDER BY theater_name, film_title, play_date, showtime"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # Group by theater/date
            theater_schedules = {}
            for row in rows:
                key = (row['theater_name'], row['play_date'])
                if key not in theater_schedules:
                    theater_schedules[key] = {}
                film = row['film_title']
                if film not in theater_schedules[key]:
                    theater_schedules[key][film] = []
                theater_schedules[key][film].append({
                    'time': row['showtime'],
                    'format': row['format']
                })

            # Check each theater/date for changes
            for (theater, pdate), schedule in theater_schedules.items():
                theaters_checked.add(theater)
                changes = self.detect_changes(theater, pdate, schedule)

                # Filter changes based on config
                for change in changes:
                    should_save = False
                    if change.alert_type == 'new_film' and config.get('alert_on_new_film', True):
                        should_save = True
                    elif change.alert_type == 'new_showtime' and config.get('alert_on_new_showtime', True):
                        should_save = True
                    elif change.alert_type == 'removed_showtime' and config.get('alert_on_removed_showtime', True):
                        should_save = True
                    elif change.alert_type == 'removed_film' and config.get('alert_on_removed_film', True):
                        should_save = True
                    elif change.alert_type == 'format_added' and config.get('alert_on_format_added', True):
                        should_save = True
                    elif change.alert_type == 'new_schedule' and config.get('alert_on_new_schedule', True):
                        should_save = True
                    elif change.alert_type == 'event_added' and config.get('alert_on_event', True):
                        should_save = True
                    elif change.alert_type == 'presale_started' and config.get('alert_on_presale', True):
                        should_save = True
                    elif change.alert_type == 'out_of_hours':
                        should_save = True

                    if should_save:
                        self.save_alert(change)
                        alerts_created += 1
                        changes_detected.append(asdict(change))

            # Update baselines with current data
            for (theater, pdate), schedule in theater_schedules.items():
                for film, showtimes in schedule.items():
                    self.create_baseline_snapshot(
                        theater_name=theater,
                        film_title=film,
                        play_date=pdate,
                        showtimes=showtimes,
                        source='enttelligence'
                    )

            # Dispatch notifications if alerts were created
            if alerts_created > 0 and config.get('notification_enabled'):
                try:
                    from app.notification_service import dispatch_schedule_alerts_sync
                    dispatch_schedule_alerts_sync(self.company_id, changes_detected)
                    logger.info(f"Dispatched notifications for {alerts_created} schedule alerts")
                except Exception as e:
                    logger.error(f"Failed to dispatch schedule notifications: {e}")

            # Update config with last check info
            try:
                cursor.execute("""
                    UPDATE schedule_monitor_config
                    SET last_check_at = ?,
                        last_check_status = 'success',
                        last_check_alerts_count = ?
                    WHERE company_id = ?
                """, (datetime.now(UTC).isoformat(), alerts_created, self.company_id))
                conn.commit()
            except Exception as e:
                logger.error(f"Failed to update config after successful check: {e}")

            return {
                'status': 'completed',
                'theaters_checked': len(theaters_checked),
                'alerts_created': alerts_created,
                'changes': changes_detected
            }

        except Exception as e:
            # Update config with failure
            try:
                cursor.execute("""
                    UPDATE schedule_monitor_config
                    SET last_check_at = ?,
                        last_check_status = 'failed'
                    WHERE company_id = ?
                """, (datetime.now(UTC).isoformat(), self.company_id))
                conn.commit()
            except Exception as inner_e:
                logger.error(f"Failed to update failure status in config: {inner_e}")

            return {
                'status': 'failed',
                'error': str(e),
                'theaters_checked': len(theaters_checked),
                'alerts_created': alerts_created
            }

        finally:
            conn.close()


def get_schedule_monitor_service(company_id: int) -> ScheduleMonitorService:
    """Factory function to get a ScheduleMonitorService instance"""
    return ScheduleMonitorService(company_id)
