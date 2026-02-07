"""
Progress Journal Module - File-based crash recovery
PriceScout Database Adapter Layer

Provides file-based progress tracking that survives database failures:
- start_scrape_journal: Initialize tracking for a scrape
- update_theater_progress: Update individual theater progress
- get_resumable_theaters: Get theaters that need resuming
- complete_scrape_journal: Mark job as done
- list_incomplete_jobs: Find jobs that can be resumed
- cleanup_old_journals: Maintenance
"""

import os
import json
import datetime as dt

# Progress journal directory - relative to app/ folder
PROGRESS_JOURNAL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'progress_journals')


def _ensure_journal_dir():
    """Ensure the progress journal directory exists."""
    os.makedirs(PROGRESS_JOURNAL_DIR, exist_ok=True)


def get_journal_path(job_id: str) -> str:
    """Get the path to a progress journal file."""
    _ensure_journal_dir()
    return os.path.join(PROGRESS_JOURNAL_DIR, f"{job_id}.json")


def write_progress_journal(job_id: str, data: dict):
    """Write or update progress journal for a job.

    This is a file-based backup that survives database failures.
    The file is updated atomically to prevent corruption.

    Args:
        job_id: Unique identifier for this scrape job
        data: Dict with job progress data
    """
    _ensure_journal_dir()
    journal_path = get_journal_path(job_id)
    temp_path = journal_path + '.tmp'

    # Add timestamp
    data['last_updated'] = dt.datetime.now(dt.timezone.utc).isoformat()

    try:
        # Write to temp file first (atomic write pattern)
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)

        # Atomically replace the old file
        if os.path.exists(journal_path):
            os.remove(journal_path)
        os.rename(temp_path, journal_path)

    except Exception as e:
        print(f"  [JOURNAL] Error writing progress journal: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def read_progress_journal(job_id: str) -> dict:
    """Read a progress journal file.

    Args:
        job_id: Unique identifier for this scrape job

    Returns:
        Dict with job progress data, or empty dict if not found
    """
    journal_path = get_journal_path(job_id)

    if not os.path.exists(journal_path):
        return {}

    try:
        with open(journal_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"  [JOURNAL] Error reading progress journal: {e}")
        return {}


def update_theater_progress(job_id: str, theater_name: str, phase: str, status: str,
                           showings: int = 0, prices: int = 0, error: str = None):
    """Update progress for a specific theater in the journal.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        phase: 'showings' or 'prices'
        status: 'started', 'completed', 'failed'
        showings: Number of showings (for showings phase)
        prices: Number of prices (for prices phase)
        error: Error message if failed
    """
    journal = read_progress_journal(job_id)

    if 'theaters' not in journal:
        journal['theaters'] = {}

    if theater_name not in journal['theaters']:
        journal['theaters'][theater_name] = {
            'showings_status': 'pending',
            'prices_status': 'pending',
            'showings_count': 0,
            'prices_count': 0
        }

    theater_data = journal['theaters'][theater_name]
    theater_data[f'{phase}_status'] = status
    theater_data[f'{phase}_at'] = dt.datetime.now(dt.timezone.utc).isoformat()

    if phase == 'showings':
        theater_data['showings_count'] = showings
    elif phase == 'prices':
        theater_data['prices_count'] = prices

    if error:
        theater_data['error'] = error

    # Update summary counts
    theaters = journal['theaters']
    journal['summary'] = {
        'total_theaters': len(theaters),
        'showings_completed': sum(1 for t in theaters.values() if t.get('showings_status') == 'completed'),
        'prices_completed': sum(1 for t in theaters.values() if t.get('prices_status') == 'completed'),
        'failed': sum(1 for t in theaters.values() if t.get('showings_status') == 'failed' or t.get('prices_status') == 'failed'),
        'total_showings': sum(t.get('showings_count', 0) for t in theaters.values()),
        'total_prices': sum(t.get('prices_count', 0) for t in theaters.values())
    }

    write_progress_journal(job_id, journal)


def get_resumable_theaters(job_id: str, all_theaters: list, phase: str = 'prices') -> list:
    """Get list of theaters that need to be resumed (not completed).

    Args:
        job_id: Unique identifier for this scrape job
        all_theaters: Full list of theater names to scrape
        phase: 'showings' or 'prices'

    Returns:
        List of theater names that haven't completed the phase
    """
    journal = read_progress_journal(job_id)

    if not journal or 'theaters' not in journal:
        return all_theaters

    completed = set()
    for theater_name, data in journal['theaters'].items():
        if data.get(f'{phase}_status') == 'completed':
            completed.add(theater_name)

    remaining = [t for t in all_theaters if t not in completed]

    if len(remaining) < len(all_theaters):
        print(f"  [JOURNAL] Resuming: {len(all_theaters) - len(remaining)} theaters already completed, {len(remaining)} remaining")

    return remaining


def start_scrape_journal(job_id: str, theaters: list, play_date, market: str = None,
                        company_id: int = None, run_id: int = None):
    """Initialize a progress journal for a new scrape.

    Args:
        job_id: Unique identifier for this scrape job
        theaters: List of theater names to scrape
        play_date: Date being scraped
        market: Optional market name
        company_id: Company ID
        run_id: Scrape run ID
    """
    journal = {
        'job_id': job_id,
        'run_id': run_id,
        'company_id': company_id,
        'market': market,
        'play_date': str(play_date),
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'theaters': {t: {'showings_status': 'pending', 'prices_status': 'pending'} for t in theaters},
        'summary': {
            'total_theaters': len(theaters),
            'showings_completed': 0,
            'prices_completed': 0,
            'failed': 0,
            'total_showings': 0,
            'total_prices': 0
        }
    }

    write_progress_journal(job_id, journal)
    print(f"  [JOURNAL] Started progress journal for job {job_id} with {len(theaters)} theaters")


def complete_scrape_journal(job_id: str, status: str = 'completed'):
    """Mark a scrape job as completed in the journal.

    Args:
        job_id: Unique identifier for this scrape job
        status: 'completed', 'failed', or 'cancelled'
    """
    journal = read_progress_journal(job_id)
    if journal:
        journal['status'] = status
        journal['completed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write_progress_journal(job_id, journal)
        print(f"  [JOURNAL] Job {job_id} marked as {status}")


def list_incomplete_jobs() -> list:
    """List all jobs that haven't been marked as completed.

    Returns:
        List of job_id strings for incomplete jobs
    """
    _ensure_journal_dir()
    incomplete = []

    try:
        for filename in os.listdir(PROGRESS_JOURNAL_DIR):
            if filename.endswith('.json'):
                job_id = filename[:-5]
                journal = read_progress_journal(job_id)
                if journal and journal.get('status') not in ('completed', 'failed', 'cancelled'):
                    incomplete.append(job_id)
    except Exception as e:
        print(f"  [JOURNAL] Error listing incomplete jobs: {e}")

    return incomplete


def cleanup_old_journals(days_old: int = 7):
    """Clean up journal files older than specified days.

    Args:
        days_old: Delete journals older than this many days
    """
    _ensure_journal_dir()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)
    deleted = 0

    try:
        for filename in os.listdir(PROGRESS_JOURNAL_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(PROGRESS_JOURNAL_DIR, filename)
                mtime = dt.datetime.fromtimestamp(os.path.getmtime(filepath), tz=dt.timezone.utc)
                if mtime < cutoff:
                    os.remove(filepath)
                    deleted += 1
    except Exception as e:
        print(f"  [JOURNAL] Error cleaning up journals: {e}")

    if deleted > 0:
        print(f"  [JOURNAL] Cleaned up {deleted} old journal files")
