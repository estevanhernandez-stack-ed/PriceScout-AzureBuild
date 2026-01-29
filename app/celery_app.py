"""
Celery Configuration for PriceScout
Enables distributed task processing using Redis or Azure Service Bus.
"""

import os
from celery import Celery
from app import config

# Initialize Celery
# If REDIS_HOST is set, use Redis as broker and backend
if config.REDIS_HOST:
    redis_url = f"redis{'s' if config.REDIS_SSL else ''}://:{config.REDIS_PASSWORD}@{config.REDIS_HOST}:{config.REDIS_PORT}/0"
    broker_url = redis_url
    result_backend = redis_url
else:
    # Fallback to local RPC/Memory for development (not persistent)
    broker_url = 'rpc://'
    result_backend = 'rpc://'

app = Celery(
    'pricescout',
    broker=broker_url,
    backend=result_backend,
    include=[
        'app.tasks.scrapes',
        'app.tasks.alerts',
        'app.tasks.sync',
        'app.tasks.system'
    ]
)

# Optional configuration
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1, # One task at a time per worker for long scrapes
)

# Automated Schedules (Celery Beat)
from celery.schedules import crontab

app.conf.beat_schedule = {
    'run-schedule-monitor-every-6-hours': {
        'task': 'app.tasks.alerts.run_schedule_monitor_task',
        'schedule': crontab(minute=0, hour='*/6'),
        'args': (1,)  # Default company_id
    },
    'sync-enttelligence-daily': {
        'task': 'app.tasks.sync.sync_enttelligence_task',
        'schedule': crontab(minute=0, hour=4),  # Run at 4 AM daily
        'args': (1, None)  # company_id, current date will be used if None
    },
    'data-retention-daily': {
        'task': 'app.tasks.system.data_retention_task',
        'schedule': crontab(minute=0, hour=3),  # Run at 3 AM daily
    },
    'system-health-alert': {
        'task': 'app.tasks.system.monitor_circuit_breakers_task',
        'schedule': crontab(minute=0, hour=2),  # Run at 2 AM daily
        'args': (1,)
    }
}

if __name__ == '__main__':
    app.start()
