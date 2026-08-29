# VICE Timetable Generator

A Python utility for generating VICE-compatible airport timetables from historical flight schedule data and identifying representative traffic days.

The project reads large quarterly Parquet datasets, filters traffic for a selected airport and date, converts event times to local airport time, validates airport identifiers, performs cleanup, classifies cargo traffic, exports VICE-compatible CSV files, and can analyze weekday traffic to recommend a representative source date.

## Current Features

- Reads quarterly historical flight data from Parquet files
- Filters traffic for a selected airport
- Selects flights from a specific local calendar date
- Automatically detects the airport's IANA timezone from airport coordinates
- Supports an optional manual timezone override
- Converts UTC timestamps to the airport's local timezone
- Generates VICE-compatible timetable CSV files
- Provides an installable `vice-timetable` CLI
- Supports `generate` and `pick-day` subcommands
- Keeps legacy direct-script entry points for compatibility
- Removes ambiguous airport records
- Removes same-airport flights
- Removes records with invalid or missing callsigns and aircraft types
- Applies historical airport identifier reidentifications
- Validates airport identifiers against an OurAirports reference dataset
- Automatically removes flights involving unknown airports
- Supports manual airport exclusions
- Uses configurable cargo-classification rules
- Reports cargo-classification reasons and an optional detailed cargo audit
- Reports cleanup actions during generation
- Pre-filters large datasets before parsing to improve performance
- Includes a representative-day picker that scores weekdays using departure, arrival, and total-operation medians
- Includes automated unit and end-to-end tests
- Runs tests automatically in GitHub Actions CI

## Output Format

VICE timetable CSV files use:

```text
callsign,origin,destination,aircraft_type,time,cargo
```

Example:

```csv
AAL1234,KCLT,KDFW,A321,08:14,false
UPS1284,KPHL,KCLT,B752,05:02,true
```

Times are expressed in local time at the timetable airport.

## Requirements

Python 3.11 or newer is recommended.

Install the project in editable mode:

```bash
python -m pip install -e .
```

This installs the project dependencies and exposes the `vice-timetable` command.

Current runtime dependencies include:

```text
pandas
pyarrow
timezonefinder
```

Development/testing also uses:

```text
pytest
```

## Project Structure

```text
vice-timetable-generator/
├── pyproject.toml
├── generate_timetable.py
├── pick_representative_day.py
├── airport_overrides.json
├── cargo_rules.json
├── requirements.txt
├── README.md
├── src/
│   └── vice_timetable/
│       ├── __init__.py
│       ├── cli.py
│       ├── generator.py
│       └── representative_day.py
├── tests/
│   ├── test_generator.py
│   ├── test_end_to_end.py
│   ├── fixtures/
│   │   └── sample_flights.parquet
│   └── expected/
│       └── KCLT Test.csv
├── reference/
│   └── airports.csv
├── data/
└── output/
```

The `data/` and `output/` directories are ignored by Git. Large Parquet source files belong in `data/`, while the small Parquet fixture under `tests/fixtures/` is intentionally tracked for automated testing.

The root-level `generate_timetable.py` and `pick_representative_day.py` files are compatibility wrappers. The primary implementation now lives under `src/vice_timetable/`.

## Data Source

The generator was developed for use with the historical aircraft flight schedule datasets published by MrAirspace:

https://github.com/MrAirspace/aircraft-flight-schedules

These datasets contain historical ADS-B-derived flight records including callsign, airline, aircraft type, origin/destination airport candidates, and approximate runway departure and arrival timestamps.

Source timestamps are stored in UTC.

## Airport Reference Data

Airport validation and automatic timezone detection use the OurAirports dataset stored at:

```text
reference/airports.csv
```

The project builds a set of known airport identifiers from the `ident` and `gps_code` fields.

Flights involving airports not found in the reference dataset are automatically removed before export.

Example:

```text
Removed unknown-airport flights: 3

Unknown airport breakdown:
  MUPR: 2
  LGHL: 1
```

## Automatic Timezone Detection

The project automatically determines the selected airport's IANA timezone using latitude and longitude from the OurAirports reference dataset.

Example:

```text
Airport configuration:
Airport:  KCLT
Name:     Charlotte Douglas International Airport
Timezone: America/New_York
Source:   Automatically detected
```

The `--timezone` argument is optional and can still be used as a manual override.

Example:

```bash
vice-timetable generate   --input "./data/2026_Q2_detailed_github.parquet"   --airport KCLT   --date 2026-06-18   --timezone America/New_York   --name "Summer Weekday"
```

If automatic timezone detection fails because airport coordinate data is unavailable, use `--timezone` to specify it manually.

## Airport Overrides

Historical flight data may contain airport identifiers that have changed since the flight occurred or may require a manual exclusion.

These cases are handled through:

```text
airport_overrides.json
```

Example:

```json
{
  "reidentifications": {
    "KPBI": "KDJT"
  },
  "excluded_airports": []
}
```

### Reidentifications

Reidentifications replace an older airport identifier with the identifier currently recognized by VICE.

Example:

```text
KPBI -> KDJT
```

The generator reports how many references were changed:

```text
Airport reidentifications:
  KPBI -> KDJT: 9
```

### Manual Exclusions

The `excluded_airports` list can be used for airports that should always be removed manually.

Flights involving excluded airports are removed before export and reported in the cleanup summary.

## Cargo Classification

Cargo classification rules are stored in:

```text
cargo_rules.json
```

Example:

```json
{
  "dedicated_cargo_airlines": [
    "UPS",
    "FDX",
    "GTI",
    "ABX",
    "CKS",
    "CLX",
    "CAO",
    "CKK"
  ],
  "freighter_keywords": [
    "freighter",
    "cargo"
  ]
}
```

Flights are marked as cargo when either:

- the airline code is listed as a dedicated cargo carrier, or
- the detailed aircraft description contains a configured freighter keyword.

The generator keeps cargo-classification rules outside the Python source so they can be adjusted without modifying code.

During generation, it prints a summary of how cargo traffic was classified:

```text
Cargo classification summary:
  passenger/default: 1,143
  dedicated cargo carrier: 9
```

The generator always reports cargo classification totals. Use `--show-cargo` to print the detailed cargo-flight audit list.

## CLI Usage

After installation:

```bash
python -m pip install -e .
```

the project exposes:

```text
vice-timetable
├── generate
└── pick-day
```

Use:

```bash
vice-timetable --help
```

to view available subcommands.

### Generate a Timetable

```bash
vice-timetable generate   --input "./data/2026_Q2_detailed_github.parquet"   --airport KCLT   --date 2026-06-18   --name "Summer Weekday"
```

This produces:

```text
output/KCLT Summer Weekday.csv
```

Generator arguments:

`--input` — Path to the source Parquet dataset.  
`--airport` — Four-letter ICAO identifier, e.g. `KCLT`.  
`--date` — Local calendar date in `YYYY-MM-DD` format.  
`--timezone` — Optional IANA timezone override.  
`--name` — Output timetable name. Defaults to `Timetable`.  
`--show-cargo` — Prints the full cargo-flight audit list.

### Representative Day Picker

Use `pick-day` to identify a weekday that best represents typical traffic for a selected airport and optional month.

```bash
vice-timetable pick-day   --input "./data/2026_Q2_detailed_github.parquet"   --airport KCLT   --month 6
```

Representative-day arguments:

`--input` — Path to the source Parquet dataset.  
`--airport` — Four-letter ICAO identifier, e.g. `KCLT`.  
`--timezone` — Optional IANA timezone override.  
`--month` — Optional calendar month from 1 through 12.  
`--top` — Number of candidate dates to display. Defaults to `10`.

The representative-day picker applies the same major airport cleanup rules used by timetable generation, then calculates weekday medians for departures, arrivals, and total operations. Each candidate date receives a representative score based on its distance from those medians. Lower scores indicate a more representative day.

Example:

```text
REPRESENTATIVE WEEKDAY ANALYSIS — KCLT — June

Median weekday departures: 693
Median weekday arrivals:   674
Median weekday operations: 1,374

Recommended date:
  2026-06-03 (Wednesday)
  Departures: 697
  Arrivals:   681
  Total:      1,378
  Representative score: 14.5
```

## Legacy Direct-Script Usage

The original entry points remain available as compatibility wrappers.

```bash
python generate_timetable.py   --input "./data/2026_Q2_detailed_github.parquet"   --airport KCLT   --date 2026-06-18   --name "Summer Weekday"
```

```bash
python pick_representative_day.py   --input "./data/2026_Q2_detailed_github.parquet"   --airport KCLT   --month 6
```

For new usage, the `vice-timetable` CLI is preferred.

## Example Generator Output

```text
Airport configuration:
Airport:  KCLT
Name:     Charlotte Douglas International Airport
Timezone: America/New_York
Source:   Automatically detected

Loading flight dataset...
Loaded 14,040,611 flights.
Pre-filtering airport traffic...
Flights mentioning KCLT: 147,008
Parsing airport information...

Raw usable traffic for 2026-06-18:
Departures: 576
Arrivals:   615

Reidentified airport references: 9

Airport reidentifications:
  KPBI -> KDJT: 9

Removed unknown-airport flights: 3

Unknown airport breakdown:
  MUPR: 2
  LGHL: 1

Removed same-airport flights: 18
Removed invalid records: 18

Cargo classification summary:
  passenger/default: 1,143
  dedicated cargo carrier: 9

==================================================
VICE TIMETABLE CREATED
==================================================

Airport:      KCLT
Source date:  2026-06-18
Flights:      1,152
Departures:   558
Arrivals:     594
Cargo:        9
```

## Timetable Generation Process

```text
Read airport metadata
        ↓
Automatically determine timezone
        ↓
Load quarterly flight dataset
        ↓
Pre-filter flights mentioning selected airport
        ↓
Parse origin and destination airport candidates
        ↓
Keep unambiguous airport pairs
        ↓
Convert event times from UTC to local time
        ↓
Filter to selected local calendar date
        ↓
Apply airport identifier reidentifications
        ↓
Apply manual airport exclusions
        ↓
Validate airports against OurAirports
        ↓
Remove unknown airports
        ↓
Remove same-airport flights
        ↓
Remove invalid records
        ↓
Classify cargo traffic
        ↓
Report cargo summary / optional audit
        ↓
Export VICE-compatible CSV
```

## Testing and CI

Run the automated test suite with:

```bash
python -m pytest
```

The project includes unit tests for core helper behavior, an end-to-end timetable-generation regression test, a small deterministic Parquet fixture under `tests/fixtures/`, an expected VICE CSV output fixture, and GitHub Actions CI that runs tests automatically on pushes and pull requests.

The current automated suite contains 9 passing tests.

## VICE Integration

Place generated timetable files under:

```text
resources/traffic/timetables/<ICAO>/
```

Example:

```text
resources/traffic/timetables/KCLT/KCLT Summer Weekday.csv
```

VICE automatically discovers timetable CSV files in the airport directory and makes them available as a timetable traffic source.

## Development Status

This project is under active development.

Completed foundations include:

- representative-day selection
- automated tests and GitHub Actions CI
- installable Python packaging
- unified `vice-timetable` CLI
- generator and representative-day package modules
- legacy compatibility wrappers
- airport validation and cleanup
- configurable cargo classification
- automatic timezone detection

Potential future work includes:

- automatic airport reference updates
- additional timetable analysis tools
- multi-airport generation
- multi-date or batch timetable generation
- additional CLI ergonomics and packaging polish

## Disclaimer

Historical ADS-B-derived flight data may contain ambiguous airport assignments, missing aircraft information, outdated identifiers, or other imperfect records.

The generator attempts to identify and remove these records before producing a timetable, but generated files should still be reviewed and tested in VICE before use.
