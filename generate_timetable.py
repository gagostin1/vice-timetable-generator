import pandas as pd
import ast
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json

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
        required=True,
        help="IANA timezone, e.g. America/New_York.",
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

    try:
        ZoneInfo(args.timezone)
    except ZoneInfoNotFoundError:
        raise SystemExit(
            f'Error: unknown timezone "{args.timezone}".'
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

args = parse_args()
validate_args(args)

AIRPORT_REIDENTIFICATIONS, EXCLUDED_AIRPORTS = load_airport_overrides()
KNOWN_AIRPORTS = load_known_airports()

FILE = args.input
AIRPORT = args.airport.upper()
TARGET_DATE = args.date
TIMEZONE = args.timezone

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / f"{AIRPORT} {args.name}.csv"

# Dedicated cargo airline ICAO codes.

CARGO_AIRLINES = {
    "UPS",  # UPS
    "FDX",  # FedEx
    "GTI",  # Atlas Air
    "ABX",  # ABX Air
    "CKS",  # Kalitta Air
    "CLX",  # Cargolux
    "CAO",  # Air China Cargo
    "CKK",  # China Cargo Airlines
}

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


def determine_cargo(row):
    """
    First-pass cargo classifier.

    Dedicated cargo carriers are marked true.

    We can improve mixed passenger/cargo carrier detection
    after inspecting the results.
    """

    airline = str(row["Airline"]).strip().upper()

    if airline in CARGO_AIRLINES:
        return True

    detailed = str(row["AC_Type_Detailed"]).lower()

    if "freighter" in detailed:
        return True

    return False


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

# CLT must be the single known origin,
# and destination must also resolve to exactly one airport.

departure_mask = (
    df["origin_airports"].apply(
        lambda x: x == [AIRPORT]
    )
    &
    df["destination_airports"].apply(
        lambda x: len(x) == 1
    )
)


# CLT must be the single known destination,
# and origin must also resolve to exactly one airport.

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


combined["cargo"] = combined.apply(
    determine_cargo,
    axis=1,
)


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