# VICE Timetable Generator

VICE Timetable Generator converts historical flight records stored in Parquet files into VICE-compatible timetable CSV files. It can also rank representative weekdays for an airport before a timetable is generated.

The project is functionally complete and in maintenance/stabilization status. Generated timetables should still be reviewed because historical ADS-B-derived records can contain ambiguous airports, missing aircraft details, and outdated identifiers.

## Requirements and installation

- Python 3.11 or newer
- `pandas`
- `pyarrow`
- `timezonefinder`
- `pytest` for tests

Create and activate a virtual environment, then install the project in editable mode:

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

This installs the `vice-timetable` command. Runtime configuration and the airport reference are packaged with `vice_timetable`, so the installed CLI does not depend on the repository root for those files.

## CLI

The CLI has two commands:

```text
vice-timetable generate
vice-timetable pick-day
```

Use `vice-timetable --help` or append `--help` to either command for the complete option reference.

### Generate a timetable

```bash
vice-timetable generate \
  --input ./data/2026_Q2_detailed_github.parquet \
  --airport KCLT \
  --date 2026-06-18 \
  --name "Summer Weekday"
```

Generation options are:

- `--input`: source Parquet dataset (required)
- `--airport`: four-letter ICAO identifier, such as `KCLT` (required)
- `--date`: local calendar date in `YYYY-MM-DD` format (required)
- `--timezone`: optional IANA timezone override; otherwise it is detected from airport coordinates
- `--name`: timetable name, defaulting to `Timetable`
- `--show-cargo`: print the detailed cargo-flight audit

The command writes `output/<ICAO> <name>.csv` beneath the current working directory. The CSV columns are:

```text
callsign,origin,destination,aircraft_type,time,cargo
```

Rows are sorted by local time and callsign. Cargo is written as `true` or `false`. To use a result in VICE, place it under `resources/traffic/timetables/<ICAO>/` in the VICE installation.

### Pick a representative day

```bash
vice-timetable pick-day \
  --input ./data/2026_Q2_detailed_github.parquet \
  --airport KCLT \
  --month 6 \
  --top 10
```

Representative-day options are:

- `--input`: source Parquet dataset (required)
- `--airport`: four-letter ICAO identifier (required)
- `--timezone`: optional IANA timezone override
- `--month`: optional month from 1 through 12
- `--top`: number of ranked dates to display, defaulting to `10`

The picker applies the same airport parsing, identifier reidentification, manual exclusion, known-airport validation, same-airport removal, and invalid-record cleanup used by generation. It considers Monday through Friday, calculates median departures, arrivals, and total operations, and scores every candidate by its combined absolute distance from those medians. Lower scores are more representative.

## Data and configuration

Large historical datasets are intentionally not tracked. Put local source files under `data/`; all Parquet files are ignored except intentionally tracked fixtures under `tests/fixtures/`.

Runtime data lives under `src/vice_timetable/data/` and is included in installed packages:

- `airports.csv`: OurAirports reference used for airport validation, coordinates, and automatic timezone detection
- `airport_overrides.json`: historical identifier replacements and manual airport exclusions
- `cargo_rules.json`: dedicated cargo airline codes and freighter-description keywords

The airport reference builds its known-identifier set from the `ident` and `gps_code` columns. Flights involving unknown, excluded, invalid, or identical origin/destination airports are removed before output.

## Compatibility scripts

The original root commands remain as lightweight wrappers around package code:

```bash
python generate_timetable.py --help
python pick_representative_day.py --help
```

They accept the same command-specific options as `vice-timetable generate` and `vice-timetable pick-day`. New automation should prefer the installed CLI.

The root-level `analyze_day.py`, `analyze_clt_dates.py`, `find_clt.py`, and `inspect_dataset.py` files are historical dataset-inspection utilities with hard-coded local examples. They are not part of the installed package or supported CLI.

## Project structure

```text
.
├── pyproject.toml
├── requirements.txt
├── generate_timetable.py
├── pick_representative_day.py
├── src/vice_timetable/
│   ├── __init__.py
│   ├── cli.py
│   ├── generator.py
│   ├── representative_day.py
│   └── data/
│       ├── airports.csv
│       ├── airport_overrides.json
│       └── cargo_rules.json
├── tests/
│   ├── test_generator.py
│   ├── test_end_to_end.py
│   ├── fixtures/sample_flights.parquet
│   └── expected/KCLT Test.csv
└── .github/workflows/tests.yml
```

## Tests and CI

Run all tests with:

```bash
python -m pytest
```

The suite contains focused helper tests and an end-to-end regression test that generates a timetable from the small deterministic Parquet fixture and compares it with the expected VICE CSV. GitHub Actions checks out the repository, sets up Python, installs dependencies and the editable project, and runs the same pytest command on pushes and pull requests.

## Generation pipeline

Generation loads the requested Parquet columns, pre-filters records mentioning the selected airport, retains unambiguous origin/destination pairs, converts UTC event timestamps to local time, and filters the selected local date. It then applies configured airport cleanup, classifies cargo traffic, reports a summary, and writes the VICE CSV.

The historical data format used during development comes from the [MrAirspace aircraft flight schedules project](https://github.com/MrAirspace/aircraft-flight-schedules).
