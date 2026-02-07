"""
Settings Router

Company-level configuration endpoints: tax estimation, market scope,
name mapping diagnostics, and system health.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import sqlite3
import os

from api.routers.auth import require_operator, require_read_admin
from api.services.tax_estimation import get_tax_config, save_tax_config
from app import config

router = APIRouter(prefix="/settings", tags=["Settings"])


# ============================================================================
# Request/Response Models
# ============================================================================

class TaxConfigResponse(BaseModel):
    """Tax configuration for EntTelligence price adjustment"""
    enabled: bool = False
    default_rate: float = Field(0.075, ge=0, le=0.25, description="Default tax rate (e.g., 0.075 for 7.5%)")
    per_state: Dict[str, float] = Field(default_factory=dict, description="Per-state tax rate overrides (e.g., {'WI': 0.055})")


class TaxConfigUpdateRequest(BaseModel):
    """Update tax configuration"""
    enabled: Optional[bool] = None
    default_rate: Optional[float] = Field(None, ge=0, le=0.25)
    per_state: Optional[Dict[str, float]] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/tax-config", response_model=TaxConfigResponse)
async def get_tax_configuration(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get the current tax estimation configuration.

    Tax estimation is used to adjust EntTelligence prices (tax-exclusive)
    for comparison with Fandango prices (tax-inclusive).
    """
    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1
    config = get_tax_config(company_id)
    return TaxConfigResponse(
        enabled=config["enabled"],
        default_rate=config["default_rate"],
        per_state=config["per_state"],
    )


@router.put("/tax-config", response_model=TaxConfigResponse)
async def update_tax_configuration(
    request: TaxConfigUpdateRequest,
    current_user: dict = Depends(require_operator)
):
    """
    Update tax estimation configuration.

    Requires operator or admin role. Partial updates supported —
    only fields included in the request body will be changed.
    """
    company_id = current_user.get("company_id") or current_user.get("default_company_id") or 1

    # Load existing config
    current = get_tax_config(company_id)

    # Merge updates
    if request.enabled is not None:
        current["enabled"] = request.enabled
    if request.default_rate is not None:
        current["default_rate"] = request.default_rate
    if request.per_state is not None:
        current["per_state"] = request.per_state

    try:
        saved = save_tax_config(company_id, current)
        return TaxConfigResponse(
            enabled=saved["enabled"],
            default_rate=saved["default_rate"],
            per_state=saved["per_state"],
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save tax config: {e}")


# ============================================================================
# Market Scope
# ============================================================================

@router.get("/market-scope")
async def get_market_scope(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get market scope summary and name matching diagnostics.

    Shows how markets.json theaters are resolved against theater_metadata
    and EntTelligence price cache.
    """
    from api.services.market_scope_service import (
        get_market_scope_summary,
        get_match_diagnostics,
        get_in_market_enttelligence_names,
        _load_markets_json,
    )

    summary = get_market_scope_summary()
    diagnostics = get_match_diagnostics()

    # Get per-director breakdown from markets.json
    json_theaters = _load_markets_json()
    directors: Dict[str, Dict] = {}
    for t in json_theaters:
        d = t['director']
        if d not in directors:
            directors[d] = {'markets': set(), 'theaters': 0, 'marcus': 0}
        directors[d]['markets'].add(t['market'])
        directors[d]['theaters'] += 1
        if t['is_marcus']:
            directors[d]['marcus'] += 1

    director_breakdown = [
        {
            'director': d,
            'market_count': len(info['markets']),
            'theater_count': info['theaters'],
            'marcus_count': info['marcus'],
            'competitor_count': info['theaters'] - info['marcus'],
        }
        for d, info in sorted(directors.items())
    ]

    # EntTelligence resolution
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    ent_matched = 0
    try:
        conn = sqlite3.connect(db_path)
        ent_names = get_in_market_enttelligence_names(conn)
        ent_matched = len(ent_names)
        conn.close()
    except Exception:
        pass

    return {
        **summary,
        'enttelligence_matched': ent_matched,
        'enttelligence_unmatched': summary['total_in_market_theaters'] - ent_matched,
        'directors': director_breakdown,
        'match_diagnostics': diagnostics,
    }


# ============================================================================
# Name Mapping
# ============================================================================

@router.get("/name-mapping")
async def get_name_mapping(
    current_user: dict = Depends(require_read_admin)
):
    """
    Get theater name mapping status: known aliases, match log, and unmatched theaters.
    """
    from api.services.market_scope_service import (
        get_in_market_enttelligence_names,
        get_match_diagnostics,
    )

    diagnostics = get_match_diagnostics()

    # Get EntTelligence aliases from DB
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    aliases = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT enttelligence_name, fandango_name, match_confidence, is_verified
            FROM theater_name_mapping
            ORDER BY enttelligence_name
        """)
        aliases = [dict(r) for r in cur.fetchall()]

        # Also get EntTelligence match count
        ent_names = get_in_market_enttelligence_names(conn)
        conn.close()
    except Exception:
        ent_names = set()

    return {
        'total_market_theaters': diagnostics['total_json_theaters'],
        'metadata_matched': diagnostics['matched_count'],
        'enttelligence_matched': len(ent_names),
        'unmatched_theaters': diagnostics['unmatched'],
        'non_trivial_matches': diagnostics['match_log'],
        'aliases': aliases,
    }


# ============================================================================
# System Diagnostics
# ============================================================================

@router.get("/system-diagnostics")
async def get_system_diagnostics(
    current_user: dict = Depends(require_read_admin)
):
    """
    Read-only system diagnostics: data source health, table row counts,
    baseline status, and configuration summary.
    """
    db_path = config.DB_FILE or os.path.join(config.PROJECT_DIR, 'pricescout.db')
    diag: Dict = {
        'data_sources': {},
        'table_counts': {},
        'baseline_summary': {},
        'config_summary': {},
    }

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Table row counts for key tables
        for table in [
            'enttelligence_price_cache', 'showings', 'prices',
            'price_baselines', 'circuit_benchmarks', 'price_alerts',
            'theater_metadata', 'theater_name_mapping', 'company_profiles',
            'discount_day_programs', 'alert_configurations',
        ]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM [{table}]")
                diag['table_counts'][table] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                diag['table_counts'][table] = None

        # EntTelligence freshness
        try:
            cur.execute("""
                SELECT MIN(play_date) as min_date, MAX(play_date) as max_date,
                       MAX(fetched_at) as last_fetch,
                       COUNT(DISTINCT theater_name) as theaters,
                       COUNT(DISTINCT circuit_name) as circuits
                FROM enttelligence_price_cache
            """)
            row = cur.fetchone()
            diag['data_sources']['enttelligence'] = {
                'date_range': f"{row['min_date']} to {row['max_date']}" if row['min_date'] else 'No data',
                'last_fetch': row['last_fetch'],
                'theaters': row['theaters'],
                'circuits': row['circuits'],
                'total_rows': diag['table_counts'].get('enttelligence_price_cache', 0),
            }
        except Exception:
            diag['data_sources']['enttelligence'] = {'status': 'unavailable'}

        # Fandango freshness
        try:
            cur.execute("""
                SELECT MIN(play_date) as min_date, MAX(play_date) as max_date,
                       MAX(created_at) as last_scrape,
                       COUNT(DISTINCT theater_name) as theaters
                FROM showings
            """)
            row = cur.fetchone()
            diag['data_sources']['fandango'] = {
                'date_range': f"{row['min_date']} to {row['max_date']}" if row['min_date'] else 'No data',
                'last_scrape': row['last_scrape'],
                'theaters': row['theaters'],
                'total_showings': diag['table_counts'].get('showings', 0),
                'total_prices': diag['table_counts'].get('prices', 0),
            }
        except Exception:
            diag['data_sources']['fandango'] = {'status': 'unavailable'}

        # Baseline summary by source
        try:
            cur.execute("""
                SELECT source, COUNT(*) as count,
                       MIN(effective_from) as earliest,
                       MAX(last_discovery_at) as latest_discovery
                FROM price_baselines
                WHERE effective_to IS NULL
                GROUP BY source
            """)
            for row in cur.fetchall():
                diag['baseline_summary'][row['source']] = {
                    'active_count': row['count'],
                    'earliest': row['earliest'],
                    'latest_discovery': row['latest_discovery'],
                }
        except Exception:
            pass

        # Config summary
        company_id = current_user.get("company_id") or 1
        tax = get_tax_config(company_id)
        diag['config_summary'] = {
            'tax_enabled': tax['enabled'],
            'tax_default_rate': tax['default_rate'],
            'tax_state_overrides': len(tax.get('per_state', {})),
            'enttelligence_enabled': getattr(config, 'ENTTELLIGENCE_ENABLED', False),
        }

        conn.close()
    except Exception as e:
        diag['error'] = str(e)

    return diag
