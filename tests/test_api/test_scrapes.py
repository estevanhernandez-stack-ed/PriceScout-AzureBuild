"""
Tests for scrape API functionality.

These tests verify the contract between frontend and backend for showtime key formats
and scrape filtering logic.
"""
import pytest


# Define the canonical key format - this is the contract between frontend and backend
# Frontend: makeShowtimeKey(date, theater, film, time, format) in MarketModePage.tsx
# Backend: key construction in api/routers/scrapes.py run_scrape_job()
SHOWTIME_KEY_SEPARATOR = "|"
SHOWTIME_KEY_COMPONENTS = ["date", "theater", "film", "time", "format"]


def make_showtime_key(date: str, theater: str, film: str, time: str, format: str = "Standard") -> str:
    """
    Build a showtime key in the canonical format.

    This function mirrors the frontend's makeShowtimeKey() function.
    Any changes here must be reflected in:
    - frontend/src/pages/MarketModePage.tsx (makeShowtimeKey)
    - frontend/src/pages/CompSnipeModePage.tsx (if applicable)
    - api/routers/scrapes.py (run_scrape_job key construction)
    """
    return f"{date}{SHOWTIME_KEY_SEPARATOR}{theater}{SHOWTIME_KEY_SEPARATOR}{film}{SHOWTIME_KEY_SEPARATOR}{time}{SHOWTIME_KEY_SEPARATOR}{format}"


class TestShowtimeKeyFormat:
    """Tests for showtime key format consistency."""

    def test_key_has_five_components(self):
        """Showtime keys must have exactly 5 components: date|theater|film|time|format"""
        key = make_showtime_key("2026-01-23", "AMC Theater", "Mercy", "12:30pm", "Standard")
        components = key.split(SHOWTIME_KEY_SEPARATOR)

        assert len(components) == 5, f"Key should have 5 components, got {len(components)}: {key}"
        assert components == ["2026-01-23", "AMC Theater", "Mercy", "12:30pm", "Standard"]

    def test_key_format_includes_format_field(self):
        """
        Regression test: Keys MUST include format as the 5th component.

        Bug history: The backend originally built keys with only 4 components
        (date|theater|film|time) while frontend sent 5 components including format.
        This caused all showtime filtering to fail silently (0 matches).
        """
        key = make_showtime_key("2026-01-23", "AMC", "Mercy", "12:30pm", "IMAX")

        assert "IMAX" in key, "Format must be included in key"
        assert key.endswith("|IMAX"), f"Format should be the last component: {key}"

    def test_key_with_special_characters_in_theater_name(self):
        """Theater names can contain special characters like & and commas."""
        key = make_showtime_key(
            "2026-01-23",
            "Regal Hamburg Pavilion IMAX & RPX",
            "Gladiator",
            "7:00pm",
            "Standard"
        )

        assert "Regal Hamburg Pavilion IMAX & RPX" in key

    def test_key_with_year_in_film_title(self):
        """Film titles often include the year in parentheses."""
        key = make_showtime_key(
            "2026-01-23",
            "AMC",
            "Mercy (2026)",
            "12:30pm",
            "Premium Format"
        )

        assert "Mercy (2026)" in key


class TestShowtimeFiltering:
    """Tests for the showtime filtering logic in run_scrape_job."""

    def test_filter_matches_exact_key(self):
        """Selected keys should match exactly with generated keys."""
        # Simulate frontend selection
        selected_keys = {
            "2026-01-23|AMC Center Valley 16|Mercy (2026)|12:30pm|Standard",
            "2026-01-23|AMC Center Valley 16|Gladiator|7:00pm|IMAX",
        }

        # Simulate backend showtime data from scraper
        showtime_data = [
            {"film_title": "Mercy (2026)", "showtime": "12:30pm", "format": "Standard"},
            {"film_title": "Mercy (2026)", "showtime": "3:00pm", "format": "Standard"},
            {"film_title": "Gladiator", "showtime": "7:00pm", "format": "IMAX"},
            {"film_title": "Gladiator", "showtime": "10:00pm", "format": "Standard"},
        ]

        theater_name = "AMC Center Valley 16"
        date_str = "2026-01-23"

        # Simulate backend filtering logic (from scrapes.py)
        filtered = []
        for showing in showtime_data:
            film = showing.get("film_title", "Unknown")
            showtime_str = showing.get("showtime", "")
            fmt = showing.get("format", "Standard")
            key = f"{date_str}|{theater_name}|{film}|{showtime_str}|{fmt}"

            if key in selected_keys:
                filtered.append(showing)

        assert len(filtered) == 2, f"Expected 2 matches, got {len(filtered)}"
        assert filtered[0]["showtime"] == "12:30pm"
        assert filtered[1]["showtime"] == "7:00pm"

    def test_filter_no_match_when_format_differs(self):
        """Keys must match on all 5 components including format."""
        # Frontend selected Standard format
        selected_keys = {
            "2026-01-23|AMC|Mercy|12:30pm|Standard",
        }

        # Backend has IMAX format
        showtime_data = [
            {"film_title": "Mercy", "showtime": "12:30pm", "format": "IMAX"},
        ]

        filtered = []
        for showing in showtime_data:
            key = f"2026-01-23|AMC|{showing['film_title']}|{showing['showtime']}|{showing['format']}"
            if key in selected_keys:
                filtered.append(showing)

        assert len(filtered) == 0, "Different formats should not match"

    def test_filter_with_empty_selection_returns_all(self):
        """When no selection is provided (None), all showtimes should be included."""
        selected_keys_set = None  # No filter

        showtime_data = [
            {"film_title": "Mercy", "showtime": "12:30pm", "format": "Standard"},
            {"film_title": "Gladiator", "showtime": "7:00pm", "format": "IMAX"},
        ]

        # Backend logic: if selected_keys_set is None, don't filter
        if selected_keys_set:
            filtered = [s for s in showtime_data if make_showtime_key(
                "2026-01-23", "AMC", s["film_title"], s["showtime"], s["format"]
            ) in selected_keys_set]
        else:
            filtered = showtime_data

        assert len(filtered) == 2, "All showtimes should be included when no filter"


class TestKeyFormatDocumentation:
    """Meta-tests to ensure key format is documented."""

    def test_key_format_constant_exists(self):
        """Verify the key format is defined as a constant for documentation."""
        assert SHOWTIME_KEY_SEPARATOR == "|"
        assert len(SHOWTIME_KEY_COMPONENTS) == 5
        assert SHOWTIME_KEY_COMPONENTS == ["date", "theater", "film", "time", "format"]
