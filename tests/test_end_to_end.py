from pathlib import Path

import pandas as pd

from vice_timetable.generator import (
    build_known_airports,
    generate_timetable,
    load_airport_overrides,
    load_airport_reference,
    load_cargo_rules,
)


BASE_DIR = Path(__file__).resolve().parent.parent


def test_generate_timetable_end_to_end(tmp_path, monkeypatch):
    airports = load_airport_reference()
    known_airports = build_known_airports(airports)

    airport_reidentifications, excluded_airports = (
        load_airport_overrides()
    )

    dedicated_cargo_airlines, freighter_keywords = (
        load_cargo_rules()
    )

    # Redirect generated output so tests don't touch the normal output folder.
    monkeypatch.setattr(
        "vice_timetable.generator.OUTPUT_DIR",
        tmp_path,
    )

    result = generate_timetable(
        input_file=BASE_DIR / "tests" / "fixtures" / "sample_flights.parquet",
        airport="KCLT",
        target_date="2026-06-18",
        timezone_name="America/New_York",
        timetable_name="Test",
        known_airports=known_airports,
        airport_reidentifications=airport_reidentifications,
        excluded_airports=excluded_airports,
        dedicated_cargo_airlines=dedicated_cargo_airlines,
        freighter_keywords=freighter_keywords,
        show_cargo=False,
    )

    expected = pd.read_csv(
        BASE_DIR / "tests" / "expected" / "KCLT Test.csv",
        dtype=str,
    )

    result = result.astype(str)

    pd.testing.assert_frame_equal(
        result.reset_index(drop=True),
        expected.reset_index(drop=True),
        check_dtype=False,
    )
