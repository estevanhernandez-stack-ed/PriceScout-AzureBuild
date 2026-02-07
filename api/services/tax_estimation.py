"""
Tax Estimation Service

Provides estimated tax adjustment for EntTelligence prices (tax-exclusive)
so they can be compared on equal footing with Fandango prices (tax-inclusive).

Tax rates are stored in Company.settings_dict under the "tax_config" key:
{
    "tax_config": {
        "enabled": true,
        "default_rate": 0.075,
        "per_theater": {
            "Marcus Ridge Cinema": 0.0503,
            "AMC Rosedale 14": 0.0,
            ...
        },
        "per_state": {
            "WI": 0.055,
            "TX": 0.0625,
            ...
        }
    }
}

Rate lookup priority:
1. per_theater (exact theater name match) -- derived from Fandango verification
2. per_state (theater's state) -- fallback for unverified theaters
3. default_rate -- last resort

A rate of 0.0 means EntTelligence prices are already tax-inclusive (e.g., AMC).
"""

import json
import logging
from typing import Optional, Dict, Any

from app.db_session import get_session
from app.db_models import Company, TheaterMetadata

logger = logging.getLogger(__name__)

# ── DMA-to-state mapping ────────────────────────────────────────────
# Maps EntTelligence DMA names to 2-letter US state / CA province codes.
# Used to auto-populate theater_metadata.state during sync.
DMA_TO_STATE: Dict[str, str] = {
    # Major US DMAs
    'Los Angeles': 'CA', 'Los Angeles Metro': 'CA', 'New York': 'NY',
    'San Francisco': 'CA', 'Chicago': 'IL', 'Dallas/Ft. Worth': 'TX',
    'Washington DC': 'DC', 'Philadelphia': 'PA', 'Boston': 'MA',
    'Seattle': 'WA', 'Seattle Metro': 'WA', 'Puget Sound South': 'WA',
    'Minneapolis/St Paul': 'MN', 'Phoenix': 'AZ', 'Salt Lake City': 'UT',
    'Denver': 'CO', 'Miami': 'FL', 'Detroit': 'MI',
    'Sacramento Stockton': 'CA', 'Sacramento Metro': 'CA',
    'Austin': 'TX', 'Orlando/Daytona': 'FL', 'Tampa/St.Pete': 'FL',
    'San Antonio': 'TX', 'Indianapolis': 'IN', 'Cleveland/Akron': 'OH',
    'San Diego': 'CA', 'San Diego Metro': 'CA', 'Kansas City': 'MO',
    'Raleigh/Durham': 'NC', 'Grand Rapids/Kalamazoo': 'MI',
    'Las Vegas': 'NV', 'Charlotte': 'NC', 'Albuquerque/Sante Fe': 'NM',
    'Milwaukee': 'WI', 'Greenville/Spartanburg': 'SC',
    'Des Moines/Ames': 'IA', 'Nashville': 'TN', 'Pittsburgh': 'PA',
    'Oklahoma City': 'OK', 'Cincinnati': 'OH', 'Baltimore': 'MD',
    'Norfolk/Portsmouth': 'VA', 'Hartford/New Haven': 'CT',
    'Memphis': 'TN', 'West Palm Beach': 'FL', 'Tulsa': 'OK',
    'Tucson': 'AZ', 'Omaha': 'NE', 'Mobile Pensacola': 'AL',
    'Little Rock/P.B.': 'AR', 'Jacksonville': 'FL', 'Honolulu': 'HI',
    'Greensboro/W. Salem': 'NC', 'Buffalo': 'NY',
    'Albany/Schenectady': 'NY', 'El Paso': 'TX', 'Syracuse': 'NY',
    'Roanoke': 'VA', 'Richmond': 'VA', 'Knoxville': 'TN',
    'Birmingham': 'AL', 'Wichita/Hutchinson': 'KS', 'Wichita': 'KS',
    'Santa Barbara': 'CA', 'New Orleans': 'LA', 'Lincoln/Hastings': 'NE',
    'Harlingen': 'TX', 'Ft. Myers/Naples': 'FL', 'Fresno Visalia': 'CA',
    'Evansville': 'IN', 'Davenport/Rock Island': 'IA',
    'Chattanooga': 'TN', 'Savannah': 'GA', 'Portland/Auburn': 'ME',
    'Portland OR': 'OR', 'Portland Metro': 'OR', 'Fort Smith': 'AR',
    'Duluth': 'MN', 'Charleston/Huntington': 'WV',
    'Cedar Rapids/Waterloo': 'IA', 'Wilkes Barre/Scranton': 'PA',
    'Spokane': 'WA', 'Reno': 'NV', 'Lexington': 'KY', 'Dayton': 'OH',
    'Columbia/Jefferson': 'MO', 'Colorado Springs/Pueblo': 'CO',
    'Tyler/Longview': 'TX', 'Topeka': 'KS', 'Sioux Falls': 'SD',
    'Paducah/Cape Gir': 'KY', 'Louisville': 'KY',
    'Greenville/New Bern': 'NC', 'Ft. Wayne': 'IN', 'Eugene': 'OR',
    'Huntsville/Decatur': 'AL', 'Flint/Saginaw': 'MI',
    'Baton Rouge': 'LA', 'Tri-Cities': 'WA', 'Toledo': 'OH',
    'Sioux City': 'IA', 'Shreveport': 'LA', 'Providence': 'RI',
    'Peoria/Bloomington': 'IL', 'Idaho Falls': 'ID',
    'Champaign/Springfield': 'IL', 'Boise': 'ID', 'Bakersfield': 'CA',
    'Amarillo': 'TX', 'Waco Temple': 'TX',
    'Tallahasse Thomasville': 'FL', 'Springfield/Holyoke': 'MA',
    'Palm Springs': 'CA', 'Orange County': 'CA', 'Montgomery': 'AL',
    'Green Bay/Appleton': 'WI', 'Florence/Myrtle Beach': 'SC',
    'Columbus/Tupelo': 'MS', 'Clarksburg/West': 'WV',
    'Charlottesville': 'VA', 'Casper/Riverton': 'WY',
    'Burlington/Plattsburgh': 'VT', 'Anchorage': 'AK',
    'Traverse City': 'MI', 'Odessa/Midland': 'TX', 'Macon': 'GA',
    'Lubbock': 'TX', 'Johnstown/Altoona': 'PA', 'Corpus Christi': 'TX',
    'Beckley/Bluefield': 'WV', 'Augusta': 'GA', 'Yuma': 'AZ',
    'Youngstown': 'OH', 'Yakima/Pasco': 'WA', 'South Bend': 'IN',
    'Panama City': 'FL', 'Monroe El Dorado': 'LA', 'Marquette': 'MI',
    'Hattiesburg/Laurel': 'MS', 'Gainesville': 'FL', 'Erie': 'PA',
    'Dothan': 'AL', 'Chico/Redding': 'CA', 'Cheyenne/Scotts': 'WY',
    'Bowling Green': 'KY', 'Binghamton': 'NY', 'Biloxi/Gulfport': 'MS',
    'Abilene/Sweetwater': 'TX', 'Wilmington': 'NC', 'Terre Haute': 'IN',
    'Sherman/Ada': 'TX', 'Salisbury': 'MD', 'Rapid City': 'SD',
    'Quincy/Hannibal': 'IL', 'Minot/Bismarck': 'ND', 'Meridian': 'MS',
    'Medford/Klamath': 'OR', 'Lima': 'OH', 'Laredo': 'TX',
    'Joplin/Pittsburg': 'MO', 'Greenwood/Greenville': 'MS',
    'Grand Junction': 'CO', 'Fargo/V.C.': 'ND', 'Elmira': 'NY',
    'Central Valley': 'CA', 'Billings': 'MT', 'Bangor': 'ME',
    'Zanesville': 'OH', 'Wheeling/Steubenville': 'WV',
    'Wausau/Rhinelander': 'WI', 'Utica': 'NY', 'Twin Falls': 'ID',
    'Rockford': 'IL', 'Parkersburg': 'WV', 'Ottumwa/Kirksville': 'IA',
    'North Platte': 'NE', 'Monterey': 'CA', 'Jonesboro': 'AR',
    'Helena': 'MT', 'Harrisonburg': 'VA', 'Great Falls': 'MT',
    'Fort Lauderdale': 'FL', 'Fairbanks': 'AK', 'Eureka': 'CA',
    'Eau Claire/La Crosse': 'WI', 'Butte': 'MT', 'Beaumont': 'TX',
    'Lansing': 'MI', 'Rochester Mason City Austin': 'MN',
    'Missoula MT': 'MT', 'Bend OR': 'OR',
    'Springfield MO': 'MO', 'Madison WI': 'WI',
    'Columbia SC': 'SC', 'Charleston SC': 'SC',
    'Jackson MS': 'MS', 'Jackson TN': 'TN',
    'Lafayette LA': 'LA', 'Lafayette IN': 'IN',
    'Rochester NY': 'NY', 'San Angelo TX': 'TX',
    'Lake Charles': 'LA', 'Atlanta GA': 'GA',
    'Houston TX': 'TX', 'St Louis MO': 'MO',
    'Columbus OH': 'OH', 'Harrisburg PA': 'PA',
    'Alexandria LA': 'LA',
    # Explicit state-in-name DMAs
    'Syracuse 13204': 'NY', 'Collegeville 19426': 'PA',
    'Flourtown 19031': 'PA', 'Aurora 80013': 'CO',
    # US Territories
    'Puerto Rico': 'PR', 'Virgin Islands': 'VI',
    'American Samoa': 'AS', 'Pacific Islands': 'GU',
    # Canada
    'Toronto ON': 'ON', 'Vancouver': 'BC', 'Montreal': 'QC',
    'Edmonton': 'AB', 'Calgary': 'AB', 'Ottawa': 'ON',
    'Winnipeg/Brandon': 'MB', 'Kelowna/Kamloops': 'BC',
    'Barrie ON': 'ON', 'Quebec City': 'QC', 'Halifax NS': 'NS',
    'Saint John/Moncton': 'NB', 'Regina': 'SK', 'Kitchener': 'ON',
    'Saskatoon SK': 'SK', 'Windsor ON': 'ON', 'Sudbury/Timmons': 'ON',
    'Trois-Rivi\xe8res': 'QC', 'Rouyn-Noranda': 'QC',
    'Kingston': 'ON', 'Charlottetown': 'PE', 'Victoria': 'BC',
    'Thunder Bay': 'ON', 'Sydney/Glace Bay': 'NS',
    'Prince George': 'BC', 'Dawson Creek': 'BC',
}


def state_from_dma(dma: Optional[str]) -> Optional[str]:
    """Derive 2-letter state/province code from an EntTelligence DMA name."""
    if not dma:
        return None
    return DMA_TO_STATE.get(dma)


# Default tax config when none is set
DEFAULT_TAX_CONFIG = {
    "enabled": False,
    "default_rate": 0.075,
    "per_theater": {},
    "per_state": {},
}


def get_tax_config(company_id: int) -> Dict[str, Any]:
    """
    Load tax configuration from Company.settings_dict.

    Returns the tax_config dict, or DEFAULT_TAX_CONFIG if not configured.
    """
    with get_session() as session:
        company = session.query(Company).filter_by(company_id=company_id).first()
        if not company:
            return DEFAULT_TAX_CONFIG.copy()

        settings = {}
        try:
            raw = company.settings
            settings = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            pass

        config = settings.get("tax_config")
        if not config or not isinstance(config, dict):
            return DEFAULT_TAX_CONFIG.copy()

        return {
            "enabled": config.get("enabled", False),
            "default_rate": float(config.get("default_rate", 0.075)),
            "per_theater": config.get("per_theater", {}),
            "per_state": config.get("per_state", {}),
        }


def save_tax_config(company_id: int, tax_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Save tax configuration to Company.settings_dict.

    Merges into existing settings without overwriting other keys.
    """
    with get_session() as session:
        company = session.query(Company).filter_by(company_id=company_id).first()
        if not company:
            raise ValueError(f"Company {company_id} not found")

        settings = {}
        try:
            raw = company.settings
            settings = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            settings = {}

        # Validate and normalize
        normalized = {
            "enabled": bool(tax_config.get("enabled", False)),
            "default_rate": max(0, min(0.25, float(tax_config.get("default_rate", 0.075)))),
            "per_theater": {},
            "per_state": {},
        }

        per_theater = tax_config.get("per_theater", {})
        if isinstance(per_theater, dict):
            for theater, rate in per_theater.items():
                theater = str(theater).strip()
                if theater:
                    normalized["per_theater"][theater] = max(0, min(0.25, float(rate)))

        per_state = tax_config.get("per_state", {})
        if isinstance(per_state, dict):
            for state, rate in per_state.items():
                state_upper = str(state).upper().strip()
                if state_upper and len(state_upper) == 2:
                    normalized["per_state"][state_upper] = max(0, min(0.25, float(rate)))

        settings["tax_config"] = normalized
        company.settings = json.dumps(settings)
        session.flush()

        return normalized


def get_theater_state(company_id: int, theater_name: str) -> Optional[str]:
    """
    Look up the state for a theater from theater_metadata.

    Returns 2-letter state code (e.g., 'WI') or None if not found.
    """
    with get_session() as session:
        meta = session.query(TheaterMetadata.state).filter_by(
            company_id=company_id,
            theater_name=theater_name,
        ).first()
        if meta and meta.state:
            return meta.state.upper().strip()
        return None


def get_tax_rate_for_theater(
    tax_config: Dict[str, Any],
    theater_state: Optional[str],
    theater_name: Optional[str] = None,
) -> float:
    """
    Determine the tax rate for a theater.

    Priority:
    1. per_theater exact match (derived from Fandango verification)
       - Returns 0.0 for tax-inclusive circuits (AMC, Regal, etc.)
       - Returns exact local rate for tax-exclusive circuits (Marcus, etc.)
    2. per_state fallback for unverified theaters
    3. default_rate as last resort
    """
    if not tax_config.get("enabled", False):
        return 0.0

    # 1. Per-theater rate (most precise, derived from data)
    per_theater = tax_config.get("per_theater", {})
    if theater_name and theater_name in per_theater:
        return float(per_theater[theater_name])

    # 2. Per-state fallback
    per_state = tax_config.get("per_state", {})
    if theater_state and theater_state in per_state:
        return float(per_state[theater_state])

    # 3. Default rate
    return float(tax_config.get("default_rate", 0.075))


def apply_estimated_tax(price: float, tax_rate: float) -> float:
    """Apply estimated tax to a price. Returns rounded to 2 decimals."""
    if tax_rate <= 0:
        return round(price, 2)
    return round(price * (1 + tax_rate), 2)


def bulk_get_theater_states(company_id: int, theater_names: list) -> Dict[str, Optional[str]]:
    """
    Batch lookup states for multiple theaters.

    Returns dict mapping theater_name -> state (or None).
    More efficient than individual lookups for compare-sources.
    """
    if not theater_names:
        return {}

    with get_session() as session:
        rows = session.query(
            TheaterMetadata.theater_name,
            TheaterMetadata.state,
        ).filter(
            TheaterMetadata.company_id == company_id,
            TheaterMetadata.theater_name.in_(theater_names),
        ).all()

        result = {name: None for name in theater_names}
        for row in rows:
            if row.state:
                result[row.theater_name] = row.state.upper().strip()
        return result
