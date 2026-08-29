from pathlib import Path

import pandas as pd
import pytest

from generate_timetable import (
    parse_airports,
    is_valid_text,
    classify_cargo,
    determine_timezone,
)


def test_parse_airports_single():
    assert parse_airports("['KCLT']") == ["KCLT"]


def test_parse_airports_multiple():
    assert parse_airports("['KCRE', 'KMYR']") == ["KCRE", "KMYR"]


def test_parse_airports_missing():
    assert parse_airports("-") == []
    assert parse_airports(None) == []


def test_is_valid_text():
    assert is_valid_text("AAL123")
    assert not is_valid_text("-")
    assert not is_valid_text("")
    assert not is_valid_text(None)


def test_cargo_dedicated_carrier():
    row = pd.Series(
        {
            "Airline": "FDX",
            "AC_Type_Detailed": "767 300F",
        }
    )

    cargo, reason = classify_cargo(
        row,
        {"FDX", "UPS"},
        {"freighter", "cargo"},
    )

    assert cargo is True
    assert reason == "dedicated cargo carrier"


def test_cargo_freighter_keyword():
    row = pd.Series(
        {
            "Airline": "ABC",
            "AC_Type_Detailed": "Boeing 747 Freighter",
        }
    )

    cargo, reason = classify_cargo(
        row,
        {"FDX", "UPS"},
        {"freighter", "cargo"},
    )

    assert cargo is True
    assert reason == "freighter aircraft type"


def test_cargo_passenger():
    row = pd.Series(
        {
            "Airline": "AAL",
            "AC_Type_Detailed": "A321-231",
        }
    )

    cargo, reason = classify_cargo(
        row,
        {"FDX", "UPS"},
        {"freighter", "cargo"},
    )

    assert cargo is False
    assert reason == "passenger/default"


def test_timezone_override():
    metadata = {
        "latitude": 35.2,
        "longitude": -80.9,
    }

    assert determine_timezone(
        metadata,
        "America/New_York",
    ) == "America/New_York"