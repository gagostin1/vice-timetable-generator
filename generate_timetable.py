import pandas as pd
import ast
from zoneinfo import ZoneInfo
from pathlib import Path


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

FILE = "data/2026_Q2_detailed_github.parquet"

AIRPORT = "KCLT"
TARGET_DATE = "2026-06-18"

TIMEZONE = "America/New_York"

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "KCLT Summer Weekday.csv"


# Dedicated cargo airline ICAO codes.
# We can expand this after auditing the generated timetable.
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

# Airport identifiers that have changed since the historical data
AIRPORT_REIDENTIFICATIONS = {
    "KPBI": "KDJT",
}

EXCLUDED_AIRPORTS = {
    "MUPR", 
    "LGHL",
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

combined["origin"] = combined["origin"].replace(
    AIRPORT_REIDENTIFICATIONS
)

combined["destination"] = combined["destination"].replace(
    AIRPORT_REIDENTIFICATIONS
)

# Remove airports known to be invalid for VICE / bad historical matches

bad_airport_mask = (
    combined["origin"].isin(EXCLUDED_AIRPORTS)
    | combined["destination"].isin(EXCLUDED_AIRPORTS)
)

bad_airport_count = bad_airport_mask.sum()

combined = combined[
    ~bad_airport_mask
].copy()

print(
    f"Removed excluded-airport flights: {bad_airport_count:,}"
)

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