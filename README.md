# VICE Timetable Generator

A Python utility for generating VICE-compatible airport timetables from historical flight schedule data.

The generator reads large quarterly Parquet datasets, filters traffic for a selected airport and date, converts event times to local airport time, validates airport identifiers, performs cleanup, and exports a CSV compatible with VICE timetable traffic.

## Current Features

- Reads quarterly historical flight data from Parquet files
- Filters traffic for a selected airport
- Selects flights from a specific local calendar date
- Converts UTC timestamps to the airport's local timezone
- Generates VICE-compatible timetable CSV files
- Supports command-line arguments for airport, date, timezone, input file, and timetable name
- Removes ambiguous airport records
- Removes same-airport flights
- Removes records with invalid or missing callsigns and aircraft types
- Applies historical airport identifier reidentifications
- Validates airport identifiers against an OurAirports reference dataset
- Automatically removes flights involving unknown airports
- Supports manual airport exclusions
- Reports all cleanup actions during generation
- Performs basic cargo classification
- Pre-filters large datasets before parsing to improve performance

## Output Format

VICE timetable CSV files use the following columns:

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
├── requirements.txt
├── README.md
├── reference/
│   └── airports.csv
├── data/
└── output/
```

The `data/` and `output/` directories are ignored by Git.

Large source Parquet datasets should be placed in `data/`.

Generated VICE timetables are written to `output/`.

## Data Source

The generator was developed for use with the historical aircraft flight schedule datasets published by MrAirspace:

https://github.com/MrAirspace/aircraft-flight-schedules

These datasets contain historical ADS-B-derived flight records including:

- Callsign
- Airline
- Aircraft type
- Origin airport candidates
- Destination airport candidates
- Approximate runway departure time
- Approximate runway arrival time

The source timestamps are stored in UTC.

## Airport Reference Data

Airport validation uses the OurAirports airport dataset stored at:

```text
reference/airports.csv
```

OurAirports is also used as an airport data source by VICE.

The generator builds a set of known airport identifiers from the `ident` and `gps_code` fields in this file.

Flights involving airports that are not found in the reference dataset are automatically removed before the timetable is exported.

Example cleanup output:

```text
Removed unknown-airport flights: 3

Unknown airport breakdown:
  MUPR: 2
  LGHL: 1
```

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

The generator reports how many airport references were changed:

```text
Airport reidentifications:
  KPBI -> KDJT: 9
```

### Manual Exclusions

The `excluded_airports` list can be used for airports that should always be removed manually.

Example:

```json
{
  "reidentifications": {
    "KPBI": "KDJT"
  },
  "excluded_airports": [
    "XXXX"
  ]
}
```

Flights involving excluded airports are removed before export and reported in the cleanup summary.

## Usage

The generator is run from the command line.

Example:

```bash
python generate_timetable.py --input "./data/2026_Q2_detailed_github.parquet" --airport KCLT --date 2026-06-18 --timezone America/New_York --name "Summer Weekday"
```

This produces:

```text
output/KCLT Summer Weekday.csv
```

### Arguments

`--input`

Path to the source Parquet dataset.

`--airport`

Four-letter ICAO identifier for the timetable airport.

Example:

```text
KCLT
```

`--date`

Local calendar date to use for the timetable.

Format:

```text
YYYY-MM-DD
```

Example:

```text
2026-06-18
```

`--timezone`

IANA timezone for the airport.

Example:

```text
America/New_York
```

`--name`

Name used for the generated timetable file.

Example:

```text
Summer Weekday
```

## Example

Command:

```bash
python generate_timetable.py --input "./data/2026_Q2_detailed_github.parquet" --airport KCLT --date 2026-06-18 --timezone America/New_York --name "Summer Weekday"
```

Example output:

```text
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

The generator processes traffic in the following order:

```text
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
Export VICE-compatible CSV
```

## VICE Integration

Generated timetable files should be placed in the VICE repository under:

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

Current development priorities include:

- Improved cargo classification
- Stronger airport validation
- Automatic airport reference updates
- Better cleanup reporting
- Additional timetable analysis tools
- Improved support for generating timetables for multiple airports and dates

## Disclaimer

Historical ADS-B-derived flight data may contain ambiguous airport assignments, missing aircraft information, outdated identifiers, or other imperfect records.

The generator attempts to identify and remove these records before producing a timetable, but generated files should still be reviewed and tested in VICE before use.
