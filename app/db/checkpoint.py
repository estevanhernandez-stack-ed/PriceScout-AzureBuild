"""
Checkpoint Tracking Module - Crash-resilient scrape tracking
PriceScout Database Adapter Layer

Provides checkpoint management for long-running scrapes:
- create_checkpoint: Start tracking a theater scrape
- complete_checkpoint: Mark as done
- fail_checkpoint: Mark as failed
- get_completed_theaters: Query completed theaters
- get_job_progress: Get progress summary
- cleanup_old_checkpoints: Maintenance
"""

import datetime as dt
from sqlalchemy import and_
from app.db_session import get_session
from app.db_models import ScrapeCheckpoint
from app import config


def create_checkpoint(job_id: str, run_id: int, theater_name: str, play_date, phase: str,
                     company_id: int = None, market: str = None) -> int:
    """Create or update a checkpoint for a theater scrape.

    Args:
        job_id: Unique identifier for this scrape job
        run_id: The scrape run ID
        theater_name: Name of the theater being scraped
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        company_id: Company ID (defaults to config or 1)
        market: Optional market name

    Returns:
        checkpoint_id
    """
    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        if company_id is None:
            company_id = getattr(config, 'CURRENT_COMPANY_ID', None) or 1

        # Check if checkpoint exists
        existing = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if existing:
            existing.status = 'in_progress'
            existing.started_at = dt.datetime.now(dt.timezone.utc)
            existing.completed_at = None
            session.commit()
            return existing.checkpoint_id
        else:
            checkpoint = ScrapeCheckpoint(
                job_id=job_id,
                run_id=run_id,
                company_id=company_id,
                theater_name=theater_name,
                market=market,
                play_date=play_date,
                phase=phase,
                status='in_progress'
            )
            session.add(checkpoint)
            session.commit()
            return checkpoint.checkpoint_id


def complete_checkpoint(job_id: str, theater_name: str, play_date, phase: str,
                       showings_count: int = 0, prices_count: int = 0):
    """Mark a checkpoint as completed.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        showings_count: Number of showings scraped (for showings phase)
        prices_count: Number of prices scraped (for prices phase)
    """
    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoint = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if checkpoint:
            checkpoint.status = 'completed'
            checkpoint.completed_at = dt.datetime.now(dt.timezone.utc)
            checkpoint.showings_count = showings_count
            checkpoint.prices_count = prices_count
            session.commit()
            print(f"  [CHECKPOINT] Completed: {theater_name} ({phase}) - {showings_count} showings, {prices_count} prices")


def fail_checkpoint(job_id: str, theater_name: str, play_date, phase: str, error_message: str):
    """Mark a checkpoint as failed.

    Args:
        job_id: Unique identifier for this scrape job
        theater_name: Name of the theater
        play_date: Date being scraped
        phase: 'showings' or 'prices'
        error_message: Error that caused the failure
    """
    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoint = session.query(ScrapeCheckpoint).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.theater_name == theater_name,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase
            )
        ).first()

        if checkpoint:
            checkpoint.status = 'failed'
            checkpoint.completed_at = dt.datetime.now(dt.timezone.utc)
            checkpoint.error_message = error_message[:500] if error_message else None
            session.commit()
            print(f"  [CHECKPOINT] Failed: {theater_name} ({phase}) - {error_message[:100] if error_message else 'Unknown'}")


def get_completed_theaters(job_id: str, play_date, phase: str = 'prices') -> set:
    """Get set of theater names that have completed a given phase.

    Args:
        job_id: Unique identifier for this scrape job
        play_date: Date being scraped
        phase: 'showings' or 'prices'

    Returns:
        Set of theater names that are complete
    """
    if isinstance(play_date, str):
        play_date = dt.datetime.strptime(play_date, '%Y-%m-%d').date()
    elif isinstance(play_date, dt.datetime):
        play_date = play_date.date()

    with get_session() as session:
        checkpoints = session.query(ScrapeCheckpoint.theater_name).filter(
            and_(
                ScrapeCheckpoint.job_id == job_id,
                ScrapeCheckpoint.play_date == play_date,
                ScrapeCheckpoint.phase == phase,
                ScrapeCheckpoint.status == 'completed'
            )
        ).all()

        return {cp.theater_name for cp in checkpoints}


def get_job_progress(job_id: str) -> dict:
    """Get progress summary for a scrape job.

    Args:
        job_id: Unique identifier for this scrape job

    Returns:
        Dict with progress info: total_theaters, completed, in_progress, failed, showings_total, prices_total
    """
    with get_session() as session:
        checkpoints = session.query(ScrapeCheckpoint).filter(
            ScrapeCheckpoint.job_id == job_id
        ).all()

        completed = sum(1 for cp in checkpoints if cp.status == 'completed')
        in_progress = sum(1 for cp in checkpoints if cp.status == 'in_progress')
        failed = sum(1 for cp in checkpoints if cp.status == 'failed')
        showings_total = sum(cp.showings_count or 0 for cp in checkpoints)
        prices_total = sum(cp.prices_count or 0 for cp in checkpoints)

        return {
            'job_id': job_id,
            'total_checkpoints': len(checkpoints),
            'completed': completed,
            'in_progress': in_progress,
            'failed': failed,
            'showings_total': showings_total,
            'prices_total': prices_total,
            'theaters': [
                {
                    'theater': cp.theater_name,
                    'market': cp.market,
                    'phase': cp.phase,
                    'status': cp.status,
                    'showings': cp.showings_count,
                    'prices': cp.prices_count
                }
                for cp in checkpoints
            ]
        }


def cleanup_old_checkpoints(days_old: int = 7):
    """Clean up checkpoints older than specified days.

    Args:
        days_old: Delete checkpoints older than this many days
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_old)

    with get_session() as session:
        deleted = session.query(ScrapeCheckpoint).filter(
            ScrapeCheckpoint.started_at < cutoff
        ).delete(synchronize_session=False)
        session.commit()
        if deleted > 0:
            print(f"  [CHECKPOINT] Cleaned up {deleted} old checkpoints")
