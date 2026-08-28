from html import parser
import pandas as pd
import ast
from pathlib import Path
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
from timezonefinder import TimezoneFinder

# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate VICE-compatible timetables from historical flight data."
    )

    parser.add_argument(
        "--input",
        required=True,
        help="Path to the source Parquet flight dataset.",
    )

    parser.add_argument(
        "--airport",
        required=True,
        help="Airport ICAO identifier, e.g. KCLT.",
    )

    parser.add_argument(
        "--date",
        required=True,
        help="Local calendar date in YYYY-MM-DD format.",
    )

    parser.add_argument(
    "--timezone",
    required=False,
    help=(
        "Optional IANA timezone override, e.g. America/New_York. "
        "If omitted, the timezone is determined automatically "
        "from the airport reference data."
    ),
    )

    parser.add_argument(
        "--name",
        default="Timetable",
        help='Timetable name, e.g. "Summer Weekday".',
    )

    return parser.parse_args()

def validate_args(args):
    input_path = Path(args.input)

    if not input_path.exists():
        raise SystemExit(
            f'Error: input file not found: "{args.input}"'
        )

    if input_path.suffix.lower() != ".parquet":
        raise SystemExit(
            "Error: input file must be a .parquet file."
        )

    airport = args.airport.upper()

    if len(airport) != 4 or not airport.isalpha():
        raise SystemExit(
            "Error: airport must be a 4-letter ICAO identifier, e.g. KCLT."
        )

    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        raise SystemExit(
            "Error: date must use YYYY-MM-DD format."
        )

def load_airport_overrides(path="airport_overrides.json"):
    config_path = Path(path)

    if not config_path.exists():
        return {}, set()

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    reidentifications = config.get("reidentifications", {})
    excluded_airports = set(config.get("excluded_airports", []))

    return reidentifications, excluded_airports

def load_known_airports(path="reference/airports.csv"):
    airports = pd.read_csv(
        path,
        low_memory=False,
    )

    known_airports = set()

    for column in ["ident", "gps_code"]:
        if column in airports.columns:
            values = (
                airports[column]
                .dropna()
                .astype(str)
                .str.strip()
                .str.upper()
            )

            known_airports.update(values)

    return known_airports

def get_airport_metadata(
    airport_code,
    path="reference/airports.csv",
):
    airports = pd.read_csv(
        path,
        low_memory=False,
    )

    airport_code = airport_code.upper()

    match = airports[
        (airports["ident"].astype(str).str.upper() == airport_code)
        |
        (
            airports["gps_code"]
            .fillna("")
            .astype(str)
            .str.upper()
            == airport_code
        )
    ]

    if match.empty:
        raise SystemExit(
            f'Error: airport "{airport_code}" was not found '
            "in the airport reference dataset."
        )

    airport = match.iloc[0]

    return {
        "ident": str(airport.get("ident", airport_code)),
        "name": str(airport.get("name", "")),
        "latitude": airport.get("latitude_deg"),
        "longitude": airport.get("longitude_deg"),
    }

def determine_timezone(airport_metadata, override=None):
    if override:
        try:
            ZoneInfo(override)
        except ZoneInfoNotFoundError:
            raise SystemExit(
                f'Error: unknown timezone "{override}".'
            )

        return override

    latitude = airport_metadata["latitude"]
    longitude = airport_metadata["longitude"]

    if pd.isna(latitude) or pd.isna(longitude):
        raise SystemExit(
            "Error: airport coordinates are missing and "
            "timezone could not be determined automatically. "
            "Use --timezone to specify it manually."
        )

    finder = TimezoneFinder()

    timezone = finder.timezone_at(
        lat=float(latitude),
        lng=float(longitude),
    )

    if not timezone:
        raise SystemExit(
            "Error: timezone could not be determined "
            "for the selected airport. "
            "Use --timezone to specify it manually."
        )

    return timezone

def load_cargo_rules(path="cargo_rules.json"):
    config_path = Path(path)

    if not config_path.exists():
        raise SystemExit(
            f'Error: cargo rules file not found: "{path}"'
        )

    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    dedicated_cargo_airlines = {
        str(code).strip().upper()
        for code in config.get("dedicated_cargo_airlines", [])
    }

    freighter_keywords = {
        str(keyword).strip().lower()
        for keyword in config.get("freighter_keywords", [])
    }

    return dedicated_cargo_airlines, freighter_keywords

args = parse_args()
validate_args(args)

AIRPORT_REIDENTIFICATIONS, EXCLUDED_AIRPORTS = load_airport_overrides()
KNOWN_AIRPORTS = load_known_airports()
DEDICATED_CARGO_AIRLINES, FREIGHTER_KEYWORDS = load_cargo_rules()

FILE = args.input
AIRPORT = args.airport.upper()
TARGET_DATE = args.date

airport_metadata = get_airport_metadata(AIRPORT)

TIMEZONE = determine_timezone(
    airport_metadata,
    args.timezone,
)

print("\nAirport configuration:")
print(f"Airport:  {AIRPORT}")
print(f"Name:     {airport_metadata['name']}")
print(f"Timezone: {TIMEZONE}")

if args.timezone:
    print("Source:   CLI override")
else:
    print("Source:   Automatically detected")

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / f"{AIRPORT} {args.name}.csv"

def classify_cargo(row):
    airline = str(row["Airline"]).strip().upper()
    detailed = str(row["AC_Type_Detailed"]).strip().lower()

    if airline in DEDICATED_CARGO_AIRLINES:
        return True, "dedicated cargo carrier"

    if any(keyword in detailed for keyword in FREIGHTER_KEYWORDS):
        return True, "freighter aircraft type"

    return False, "passenger/default"

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def parse_airports(value):
    """
    Converts ApplicableAirports into a normal Python list.

    Example:
        "['KCLT']" -> ['KCLT']
        "['KCRE', 'KMYR']" -> ['KCRE', 'KMYR']
    """

    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        return list(value)

    text = str(value).strip()

    if text in ("", "-", "nan", "None"):
        return []

    try:
        parsed = ast.literal_eval(text)

        if isinstance(parsed, list):
            return parsed

        return [str(parsed)]

    except (ValueError, SyntaxError):
        return [text]

def is_valid_text(value):
    """
    Reject obviously missing values.
    """

    if pd.isna(value):
        return False

    value = str(value).strip()

    return value not in ("", "-", "nan", "None")

# ---------------------------------------------------------
# LOAD DATA
# ---------------------------------------------------------

print("Loading flight dataset...")

columns = [
    "Callsign",
    "Airline",
    "AC_Type",
    "AC_Type_Detailed",
    "Track_Origin_DateTime_UTC",
    "Track_Origin_ApplicableAirports",
    "Track_Destination_DateTime_UTC",
    "Track_Destination_ApplicableAirports",
]

df = pd.read_parquet(
    FILE,
    columns=columns,
)

print(f"Loaded {len(df):,} flights.")

print("Pre-filtering airport traffic...")

origin_text = (
    df["Track_Origin_ApplicableAirports"]
    .astype(str)
)

destination_text = (
    df["Track_Destination_ApplicableAirports"]
    .astype(str)
)

airport_mask = (
    origin_text.str.contains(AIRPORT, na=False)
    | destination_text.str.contains(AIRPORT, na=False)
)

df = df[airport_mask].copy()

print(
    f"Flights mentioning {AIRPORT}: {len(df):,}"
)

# ---------------------------------------------------------
# PARSE AIRPORT DATA
# ---------------------------------------------------------

print("Parsing airport information...")

df["origin_airports"] = (
    df["Track_Origin_ApplicableAirports"]
    .apply(parse_airports)
)

df["destination_airports"] = (
    df["Track_Destination_ApplicableAirports"]
    .apply(parse_airports)
)

# ---------------------------------------------------------
# REQUIRE UNAMBIGUOUS ROUTES
# ---------------------------------------------------------

departure_mask = (
    df["origin_airports"].apply(
        lambda x: x == [AIRPORT]
    )
    &
    df["destination_airports"].apply(
        lambda x: len(x) == 1
    )
)

arrival_mask = (
    df["destination_airports"].apply(
        lambda x: x == [AIRPORT]
    )
    &
    df["origin_airports"].apply(
        lambda x: len(x) == 1
    )
)

departures = df[departure_mask].copy()
arrivals = df[arrival_mask].copy()

# ---------------------------------------------------------
# EVENT TIMES
# ---------------------------------------------------------

departures["event_time_utc"] = pd.to_datetime(
    departures["Track_Origin_DateTime_UTC"],
    utc=True,
    errors="coerce",
)

arrivals["event_time_utc"] = pd.to_datetime(
    arrivals["Track_Destination_DateTime_UTC"],
    utc=True,
    errors="coerce",
)

timezone = ZoneInfo(TIMEZONE)

departures["event_time_local"] = (
    departures["event_time_utc"]
    .dt.tz_convert(timezone)
)

arrivals["event_time_local"] = (
    arrivals["event_time_utc"]
    .dt.tz_convert(timezone)
)

# ---------------------------------------------------------
# FILTER TARGET DATE
# ---------------------------------------------------------

departures = departures[
    departures["event_time_local"]
    .dt.strftime("%Y-%m-%d")
    == TARGET_DATE
].copy()

arrivals = arrivals[
    arrivals["event_time_local"]
    .dt.strftime("%Y-%m-%d")
    == TARGET_DATE
].copy()

print(
    f"\nRaw usable traffic for {TARGET_DATE}:"
)

print(
    f"Departures: {len(departures):,}"
)

print(
    f"Arrivals:   {len(arrivals):,}"
)

# ---------------------------------------------------------
# COMBINE FLIGHTS
# ---------------------------------------------------------

departures["origin"] = departures[
    "origin_airports"
].apply(lambda x: x[0])

departures["destination"] = departures[
    "destination_airports"
].apply(lambda x: x[0])

arrivals["origin"] = arrivals[
    "origin_airports"
].apply(lambda x: x[0])

arrivals["destination"] = arrivals[
    "destination_airports"
].apply(lambda x: x[0])

combined = pd.concat(
    [departures, arrivals],
    ignore_index=True,
)

# ---------------------------------------------------------
# UPDATE HISTORICAL AIRPORT IDENTIFIERS
# ---------------------------------------------------------

reidentified_origin_mask = combined["origin"].isin(AIRPORT_REIDENTIFICATIONS)
reidentified_destination_mask = combined["destination"].isin(AIRPORT_REIDENTIFICATIONS)

reidentified_count = (
    reidentified_origin_mask.sum()
    + reidentified_destination_mask.sum()
)

reidentification_counts = {}

for old, new in AIRPORT_REIDENTIFICATIONS.items():
    count = (
        (combined["origin"] == old).sum()
        + (combined["destination"] == old).sum()
    )

    if count:
        reidentification_counts[(old, new)] = count

combined["origin"] = combined["origin"].replace(
    AIRPORT_REIDENTIFICATIONS
)

combined["destination"] = combined["destination"].replace(
    AIRPORT_REIDENTIFICATIONS
)

# Remove airports known to be invalid for VICE / bad historical matches

excluded_matches = pd.concat([
    combined.loc[
        combined["origin"].isin(EXCLUDED_AIRPORTS),
        "origin"
    ],
    combined.loc[
        combined["destination"].isin(EXCLUDED_AIRPORTS),
        "destination"
    ],
])

excluded_breakdown = excluded_matches.value_counts()

bad_airport_mask = (
    combined["origin"].isin(EXCLUDED_AIRPORTS)
    | combined["destination"].isin(EXCLUDED_AIRPORTS)
)

bad_airport_count = bad_airport_mask.sum()

combined = combined[
    ~bad_airport_mask
].copy()

print(
    f"Reidentified airport references: {reidentified_count:,}"
)

print(
    f"Removed excluded-airport flights: {bad_airport_count:,}"
)

if not excluded_breakdown.empty:
    print("\nExcluded airport breakdown:")

    for airport, count in excluded_breakdown.items():
        print(f"  {airport}: {count}")

if reidentification_counts:
    print("\nAirport reidentifications:")

    for (old, new), count in reidentification_counts.items():
        print(f"  {old} -> {new}: {count}")      

# ---------------------------------------------------------
# REMOVE UNKNOWN AIRPORTS
# ---------------------------------------------------------

unknown_origin_mask = ~combined["origin"].isin(KNOWN_AIRPORTS)
unknown_destination_mask = ~combined["destination"].isin(KNOWN_AIRPORTS)

unknown_matches = pd.concat([
    combined.loc[
        unknown_origin_mask,
        "origin"
    ],
    combined.loc[
        unknown_destination_mask,
        "destination"
    ],
])

unknown_breakdown = unknown_matches.value_counts()

unknown_airport_mask = (
    unknown_origin_mask
    | unknown_destination_mask
)

unknown_airport_count = unknown_airport_mask.sum()

combined = combined[
    ~unknown_airport_mask
].copy()

print(
    f"Removed unknown-airport flights: {unknown_airport_count:,}"
)

if not unknown_breakdown.empty:
    print("\nUnknown airport breakdown:")

    for airport, count in unknown_breakdown.items():
        print(f"  {airport}: {count}")

# Remove same-airport/local flights.
# VICE needs a valid city pair for route matching.

same_airport = (
    combined["origin"] == combined["destination"]
)

same_airport_count = same_airport.sum()

combined = combined[
    ~same_airport
].copy()

print(
    f"Removed same-airport flights: {same_airport_count:,}"
)

# ---------------------------------------------------------
# REMOVE BAD RECORDS
# ---------------------------------------------------------

before_cleanup = len(combined)

combined = combined[
    combined["Callsign"].apply(is_valid_text)
    &
    combined["AC_Type"].apply(is_valid_text)
    &
    combined["origin"].apply(is_valid_text)
    &
    combined["destination"].apply(is_valid_text)
].copy()


removed = before_cleanup - len(combined)

print(
    f"Removed invalid records: {removed:,}"
)

# ---------------------------------------------------------
# BUILD VICE FIELDS
# ---------------------------------------------------------

combined["callsign"] = (
    combined["Callsign"]
    .astype(str)
    .str.strip()
    .str.upper()
)

combined["aircraft_type"] = (
    combined["AC_Type"]
    .astype(str)
    .str.strip()
    .str.upper()
)

combined["time"] = (
    combined["event_time_local"]
    .dt.strftime("%H:%M")
)

cargo_results = combined.apply(
    classify_cargo,
    axis=1,
    result_type="expand",
)

combined["cargo"] = cargo_results[0]
combined["cargo_reason"] = cargo_results[1]

# ---------------------------------------------------------
# BUILD FINAL VICE TABLE
# ---------------------------------------------------------

vice = combined[
    [
        "callsign",
        "origin",
        "destination",
        "aircraft_type",
        "time",
        "cargo",
    ]
].copy()

# VICE examples use lowercase true/false rather than
# Python's True/False representation.

vice["cargo"] = vice["cargo"].map(
    {
        True: "true",
        False: "false",
    }
)

cargo_summary = (
    combined["cargo_reason"]
    .value_counts()
)

print("\nCargo classification summary:")

for reason, count in cargo_summary.items():
    print(f"  {reason}: {count:,}")

cargo_flights = combined[
    combined["cargo"]
][
    [
        "Callsign",
        "Airline",
        "AC_Type",
        "AC_Type_Detailed",
        "origin",
        "destination",
        "cargo_reason",
    ]
]

if not cargo_flights.empty:
    print("\nCargo flights:")

    print(
        cargo_flights.to_string(
            index=False
        )
    )
# Sort chronologically.

vice = vice.sort_values(
    ["time", "callsign"]
).reset_index(drop=True)

# ---------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

vice.to_csv(
    OUTPUT_FILE,
    index=False,
)

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

print("\n" + "=" * 50)

print("VICE TIMETABLE CREATED")

print("=" * 50)

print(
    f"Airport:      {AIRPORT}"
)

print(
    f"Source date:  {TARGET_DATE}"
)

print(
    f"Flights:      {len(vice):,}"
)

print(
    f"Departures:   "
    f"{(vice['origin'] == AIRPORT).sum():,}"
)

print(
    f"Arrivals:     "
    f"{(vice['destination'] == AIRPORT).sum():,}"
)

print(
    f"Cargo:        "
    f"{(vice['cargo'] == 'true').sum():,}"
)

print(
    f"\nOutput:"
)

print(
    OUTPUT_FILE.resolve()
)

print("\nFirst 20 timetable entries:\n")

print(
    vice.head(20).to_string(
        index=False
    )
)