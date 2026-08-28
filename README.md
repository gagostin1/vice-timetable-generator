# VICE Timetable Generator

A Python utility for generating VICE-compatible airport timetables from historical flight schedule data.

The generator reads large quarterly Parquet datasets, filters traffic for a selected airport and date, converts event times to local airport time, validates airport identifiers, performs cleanup, classifies cargo traffic, and exports a CSV compatible with VICE timetable traffic.

## Current Features

- Reads quarterly historical flight data from Parquet files
- Filters traffic for a selected airport
- Selects flights from a specific local calendar date
- Automatically detects the airport's IANA timezone from airport coordinates
- Supports an optional manual timezone override
- Converts UTC timestamps to the airport's local timezone
- Generates VICE-compatible timetable CSV files
- Supports command-line arguments for airport, date, input file, timetable name, and optional timezone
- Removes ambiguous airport records
- Removes same-airport flights
- Removes records with invalid or missing callsigns and aircraft types
- Applies historical airport identifier reidentifications
- Validates airport identifiers against an OurAirports reference dataset
- Automatically removes flights involving unknown airports
- Supports manual airport exclusions
- Uses configurable cargo-classification rules
- Reports cargo-classification reasons and an audit list of cargo flights
- Reports cleanup actions during generation
- Pre-filters large datasets before parsing to improve performance

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

Install dependencies with:

```bash
pip install -r requirements.txt
```

Current dependencies:

```text
pandas
pyarrow
timezonefinder
```

## Project Structure

```text
vice-timetable-generator/
├── generate_timetable.py
├── analyze_day.py
├── analyze_clt_dates.py
├── find_clt.py
├── inspect_dataset.py
├── airport_overrides.json
├── cargo_rules.json
├── requirements.txt
├── README.md
├── reference/
│   └── airports.csv
├── data/
└── output/
```

The `data/` and `output/` directories are ignored by Git. Large Parquet source files belong in `data/`, and generated VICE timetables are written to `output/`.

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

The generator builds a set of known airport identifiers from the `ident` and `gps_code` fields.

Flights involving airports not found in the reference dataset are automatically removed before export.

Example:

```text
Removed unknown-airport flights: 3

Unknown airport breakdown:
  MUPR: 2
  LGHL: 1
```

## Automatic Timezone Detection

The generator automatically determines the timetable airport's IANA timezone using latitude and longitude from the OurAirports reference dataset.

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
python generate_timetable.py \
  --input "./data/2026_Q2_detailed_github.parquet" \
  --airport KCLT \
  --date 2026-06-18 \
  --timezone America/New_York \
  --name "Summer Weekday"
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

The generator always reports cargo classification totals. Use `--show-cargo` to print the detailed cargo-flight audit list

Example:

```text
Cargo flights:
Callsign Airline AC_Type origin destination cargo_reason
FDX1635  FDX     B763    KCLT   KIND        dedicated cargo carrier
UPS1283  UPS     A306    KCLT   KPHL        dedicated cargo carrier
```

The VICE timetable output schema remains unchanged; only the final `cargo` boolean is written to the CSV.

## Usage

Example:

```bash
python generate_timetable.py \
  --input "./data/2026_Q2_detailed_github.parquet" \
  --airport KCLT \
  --date 2026-06-18 \
  --name "Summer Weekday"
```

This produces:

```text
output/KCLT Summer Weekday.csv
```

### Arguments

`--input`  
Path to the source Parquet dataset.

`--airport`  
Four-letter ICAO identifier for the timetable airport, e.g. `KCLT`.

`--date`  
Local calendar date in `YYYY-MM-DD` format.

`--timezone`  
Optional IANA timezone override. If omitted, the timezone is detected automatically from airport reference data.

`--name`  
Name used for the generated timetable file, e.g. `Summer Weekday`.

`--show-cargo`  
Optional flag that prints the full cargo-flight audit list. By default, only the cargo classification summary is shown.

## Example Output

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
Departures:     558
Arrivals:       594
Cargo:            9
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
Report cargo audit
        ↓
Export VICE-compatible CSV
```

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

Current priorities include:

- Representative-day selection
- Automatic airport reference updates
- Additional timetable analysis tools
- Multi-airport and multi-date generation
- Automated tests and CI
- Packaging as an installable CLI

## Disclaimer

Historical ADS-B-derived flight data may contain ambiguous airport assignments, missing aircraft information, outdated identifiers, or other imperfect records.

The generator attempts to identify and remove these records before producing a timetable, but generated files should still be reviewed and tested in VICE before use.
