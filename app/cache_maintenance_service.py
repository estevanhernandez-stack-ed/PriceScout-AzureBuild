"""
Theater Cache Maintenance Service

Automated background service that:
1. Fixes failed/broken theater URLs
2. Randomly samples theaters to detect major Fandango changes
3. Alerts when significant failures occur (site restructure detection)

Usage:
    from app.cache_maintenance_service import CacheMaintenanceService

    service = CacheMaintenanceService()
    result = await service.run_maintenance()
"""

import os
import json
import random
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.config import CACHE_FILE, PROJECT_DIR
from app.scraper import Scraper
from app.circuit_breaker import fandango_breaker
from app.repair_queue import repair_queue

logger = logging.getLogger(__name__)

# Maintenance configuration
RANDOM_SAMPLE_SIZE = 10  # Number of random theaters to check
FAILURE_THRESHOLD_PERCENT = 30  # Alert if > 30% of sample fails
MAX_REPAIR_ATTEMPTS = 20  # Max theaters to attempt repair per run


class CacheMaintenanceService:
    """Automated theater cache maintenance and health monitoring."""

    def __init__(self, cache_file: str = None):
        self.cache_file = cache_file or CACHE_FILE
        self.scraper = Scraper()
        self.maintenance_log_file = os.path.join(PROJECT_DIR, 'cache_maintenance.log')

    def _load_cache(self) -> Optional[Dict]:
        """Load the theater cache file."""
        if not os.path.exists(self.cache_file):
            logger.warning(f"Cache file not found: {self.cache_file}")
            return None
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            return None

    def _save_cache(self, cache: Dict) -> bool:
        """Save the theater cache with backup."""
        try:
            # Create backup
            backup_path = self.cache_file + ".maintenance_bak"
            if os.path.exists(self.cache_file):
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                os.rename(self.cache_file, backup_path)

            # Save updated cache
            with open(self.cache_file, 'w') as f:
                json.dump(cache, f, indent=2)

            logger.info(f"Cache saved. Backup at: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            return False

    def _load_markets_data(self) -> Dict:
        """Load all markets data from disk for ZIP code lookups."""
        all_markets = {}
        data_dir = os.path.join(PROJECT_DIR, 'data')

        if not os.path.exists(data_dir):
            return all_markets

        for company_dir in os.listdir(data_dir):
            markets_file = os.path.join(data_dir, company_dir, 'markets.json')
            if os.path.exists(markets_file):
                try:
                    with open(markets_file, 'r') as f:
                        company_markets = json.load(f)
                        # Merge into all_markets
                        for parent, regions in company_markets.items():
                            if parent not in all_markets:
                                all_markets[parent] = {}
                            for region, markets in regions.items():
                                if region not in all_markets[parent]:
                                    all_markets[parent][region] = {}
                                all_markets[parent][region].update(markets)
                except Exception as e:
                    logger.warning(f"Error loading markets from {markets_file}: {e}")

        return all_markets

    def _find_zip_for_theater(self, theater_name: str, market_name: str, markets_data: Dict) -> Optional[str]:
        """Find the ZIP code for a theater from markets data."""
        for parent, regions in markets_data.items():
            for region, markets in regions.items():
                if market_name in markets:
                    for theater in markets[market_name].get('theaters', []):
                        if theater.get('name') == theater_name:
                            return theater.get('zip')
        return None

    def _get_failed_theaters(self, cache: Dict) -> List[Dict]:
        """Get list of theaters with broken/missing URLs."""
        failed = []
        for market_name, market_info in cache.get('markets', {}).items():
            for theater in market_info.get('theaters', []):
                url = theater.get('url', '')
                # Consider failed if: no URL, URL is N/A, or marked as not on Fandango
                if not url or url == 'N/A' or theater.get('not_on_fandango'):
                    failed.append({
                        'market': market_name,
                        'name': theater.get('name'),
                        'theater': theater
                    })
        return failed

    def _get_random_sample(self, cache: Dict, sample_size: int = RANDOM_SAMPLE_SIZE) -> List[Dict]:
        """Get random sample of theaters with valid URLs for health check."""
        valid_theaters = []
        for market_name, market_info in cache.get('markets', {}).items():
            for theater in market_info.get('theaters', []):
                url = theater.get('url', '')
                if url and url != 'N/A' and not theater.get('not_on_fandango'):
                    valid_theaters.append({
                        'market': market_name,
                        'name': theater.get('name'),
                        'url': url,
                        'theater': theater
                    })

        # Random sample
        if len(valid_theaters) <= sample_size:
            return valid_theaters
        return random.sample(valid_theaters, sample_size)

    async def _check_url_health(self, url: str) -> bool:
        """Check if a theater URL is still valid."""
        # Check circuit breaker before making request
        if not fandango_breaker.can_execute():
            logger.warning("Fandango circuit breaker OPEN - skipping URL health check")
            return False  # Assume unhealthy when circuit is open

        try:
            result = await self.scraper.check_url_status(url)
            if result:
                fandango_breaker.record_success()
            else:
                fandango_breaker.record_failure()
            return result
        except Exception as e:
            fandango_breaker.record_failure()
            logger.error(f"URL health check failed: {e}")
            return False

    async def _attempt_repair(self, theater_name: str, zip_code: Optional[str]) -> Optional[Dict]:
        """Attempt to find a new URL for a failed theater."""
        # Check circuit breaker before making request
        if not fandango_breaker.can_execute():
            logger.warning("Fandango circuit breaker OPEN - skipping repair attempt")
            return None

        try:
            result = await self.scraper.discover_theater_url(theater_name)
            if result.get('found'):
                fandango_breaker.record_success()
                return {
                    'name': result['theater_name'],
                    'url': result['url'],
                    'code': result.get('theater_code')
                }
            else:
                fandango_breaker.record_failure()
        except Exception as e:
            fandango_breaker.record_failure()
            logger.warning(f"Error discovering URL for {theater_name}: {e}")
        return None

    def _log_maintenance(self, result: Dict):
        """Append maintenance result to log file."""
        try:
            log_entry = {
                'timestamp': datetime.now().isoformat(),
                **result
            }

            # Append to log file
            with open(self.maintenance_log_file, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Error writing maintenance log: {e}")

    async def run_health_check(self) -> Dict:
        """
        Run random health check on theater URLs.
        Returns dict with health status and any alerts.
        """
        cache = self._load_cache()
        if not cache:
            return {'status': 'error', 'message': 'Cache not found'}

        sample = self._get_random_sample(cache)
        if not sample:
            return {'status': 'ok', 'message': 'No theaters to check', 'checked': 0}

        logger.info(f"Running health check on {len(sample)} random theaters...")

        # Check each URL in the sample
        results = []
        for item in sample:
            is_healthy = await self._check_url_health(item['url'])
            results.append({
                'name': item['name'],
                'market': item['market'],
                'url': item['url'],
                'healthy': is_healthy
            })
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.5)

        # Calculate failure rate
        failed = [r for r in results if not r['healthy']]
        failure_rate = (len(failed) / len(results)) * 100 if results else 0

        health_result = {
            'status': 'ok' if failure_rate < FAILURE_THRESHOLD_PERCENT else 'alert',
            'checked': len(results),
            'failed': len(failed),
            'failure_rate_percent': round(failure_rate, 1),
            'failed_theaters': [f['name'] for f in failed],
            'threshold_percent': FAILURE_THRESHOLD_PERCENT
        }

        if failure_rate >= FAILURE_THRESHOLD_PERCENT:
            health_result['alert'] = (
                f"High failure rate detected ({failure_rate:.1f}%). "
                "Fandango may have changed their site structure. Manual review recommended."
            )
            logger.warning(health_result['alert'])

        return health_result

    async def run_repair(self, max_repairs: int = MAX_REPAIR_ATTEMPTS) -> Dict:
        """
        Attempt to repair failed theater URLs.
        Returns dict with repair results.
        """
        cache = self._load_cache()
        if not cache:
            return {'status': 'error', 'message': 'Cache not found'}

        markets_data = self._load_markets_data()
        failed_theaters = self._get_failed_theaters(cache)

        if not failed_theaters:
            return {'status': 'ok', 'message': 'No failed theaters to repair', 'repaired': 0}

        # Limit repairs per run
        to_repair = failed_theaters[:max_repairs]
        logger.info(f"Attempting to repair {len(to_repair)} failed theaters...")

        repaired = []
        still_failed = []

        for item in to_repair:
            theater_name = item['name']
            market_name = item['market']
            theater = item['theater']

            # Get ZIP code for better matching
            zip_code = self._find_zip_for_theater(theater_name, market_name, markets_data)

            # Attempt repair
            new_data = await self._attempt_repair(theater_name, zip_code)

            if new_data:
                # Update theater in cache
                theater['name'] = new_data['name']
                theater['url'] = new_data['url']
                if 'not_on_fandango' in theater:
                    del theater['not_on_fandango']
                repaired.append({
                    'original_name': theater_name,
                    'new_name': new_data['name'],
                    'market': market_name,
                    'url': new_data['url']
                })
                logger.info(f"Repaired: {theater_name} -> {new_data['name']}")
            else:
                still_failed.append({
                    'name': theater_name,
                    'market': market_name
                })
                # Add to repair queue for retry with exponential backoff
                repair_queue.add(theater_name, market_name, zip_code)
                logger.warning(f"Could not repair: {theater_name} (added to retry queue)")

            # Delay between repairs
            await asyncio.sleep(1)

        # Save updated cache if repairs were made
        if repaired:
            cache['metadata'] = cache.get('metadata', {})
            cache['metadata']['last_maintenance'] = datetime.now().isoformat()
            cache['metadata']['last_repair_count'] = len(repaired)
            self._save_cache(cache)

        return {
            'status': 'ok',
            'total_failed': len(failed_theaters),
            'attempted': len(to_repair),
            'repaired': len(repaired),
            'still_failed': len(still_failed),
            'repaired_theaters': repaired,
            'still_failed_theaters': still_failed
        }

    async def run_maintenance(self) -> Dict:
        """
        Run full maintenance cycle:
        1. Health check (random sample)
        2. Repair failed theaters

        Returns comprehensive maintenance result.
        """
        logger.info("Starting cache maintenance...")
        start_time = datetime.now()

        # Run health check
        health_result = await self.run_health_check()

        # Run repairs
        repair_result = await self.run_repair()

        # Compile results
        duration = (datetime.now() - start_time).total_seconds()

        result = {
            'timestamp': start_time.isoformat(),
            'duration_seconds': round(duration, 1),
            'health_check': health_result,
            'repairs': repair_result,
            'circuit_breaker': fandango_breaker.get_status(),
            'overall_status': 'ok'
        }

        # Determine overall status
        if health_result.get('status') == 'alert':
            result['overall_status'] = 'alert'
            result['alert_message'] = health_result.get('alert')
        elif health_result.get('status') == 'error' or repair_result.get('status') == 'error':
            result['overall_status'] = 'error'

        # Log the maintenance run
        self._log_maintenance(result)

        logger.info(f"Maintenance complete in {duration:.1f}s. "
                   f"Health: {health_result.get('status')}, "
                   f"Repaired: {repair_result.get('repaired', 0)}")

        return result

    def get_maintenance_history(self, limit: int = 10) -> List[Dict]:
        """Get recent maintenance run history from log."""
        if not os.path.exists(self.maintenance_log_file):
            return []

        try:
            entries = []
            with open(self.maintenance_log_file, 'r') as f:
                for line in f:
                    try:
                        entries.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue

            # Return most recent entries
            return entries[-limit:][::-1]  # Newest first
        except Exception as e:
            logger.error(f"Error reading maintenance log: {e}")
            return []


# Convenience function for running maintenance
async def run_cache_maintenance() -> Dict:
    """Run cache maintenance (convenience function for scheduler)."""
    service = CacheMaintenanceService()
    return await service.run_maintenance()


def run_cache_maintenance_sync() -> Dict:
    """Synchronous wrapper for cache maintenance."""
    return asyncio.run(run_cache_maintenance())
