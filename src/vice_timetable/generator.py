import argparse
import ast
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from timezonefinder import TimezoneFinder


BASE_DIR = Path(__file__).resolve().parents[2]
AIRPORT_REFERENCE_FILE = BASE_DIR / "reference" / "airports.csv"
AIRPORT_OVERRIDES_FILE = BASE_DIR / "airport_overrides.json"
CARGO_RULES_FILE = BASE_DIR / "cargo_rules.json"
OUTPUT_DIR = BASE_DIR / "output"
TIMEZONE_FINDER = TimezoneFinder()


# ---------------------------------------------------------
# CLI
# ---------------------------------------------------------

def add_generate_arguments(parser):
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

    parser.add_argument(
        "--show-cargo",
        action="store_true",
        help="Print the full cargo-flight audit list.",
    )

    return parser


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate VICE-compatible timetables from historical flight data."
    )

    add_generate_arguments(parser)

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


# ---------------------------------------------------------
# CONFIG / REFERENCE DATA
# ---------------------------------------------------------

def load_json_config(path, description):
    if not path.exists():
        raise SystemExit(
            f'Error: {description} file not found: "{path}"'
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f'Error: invalid JSON in {description} file "{path}": {exc}'
        ) from exc


def load_airport_overrides(path=AIRPORT_OVERRIDES_FILE):
    config = load_json_config(path, "airport overrides")

    reidentifications = {
        str(old).strip().upper(): str(new).strip().upper()
        for old, new in config.get("reidentifications", {}).items()
    }

    excluded_airports = {
        str(code).strip().upper()
        for code in config.get("excluded_airports", [])
    }

    return reidentifications, excluded_airports


def load_airport_reference(path=AIRPORT_REFERENCE_FILE):
    if not path.exists():
        raise SystemExit(
            f'Error: airport reference file not found: "{path}"'
        )

    return pd.read_csv(
        path,
        low_memory=False,
    )


def build_known_airports(airports):
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


def get_airport_metadata(airports, airport_code):
    airport_code = airport_code.upper()

    ident = airports["ident"].fillna("").astype(str).str.upper()
    gps_code = airports["gps_code"].fillna("").astype(str).str.upper()

    match = airports[
        (ident == airport_code)
        | (gps_code == airport_code)
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

    timezone = TIMEZONE_FINDER.timezone_at(
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


def load_cargo_rules(path=CARGO_RULES_FILE):
    config = load_json_config(path, "cargo rules")

    dedicated_cargo_airlines = {
        str(code).strip().upper()
        for code in config.get("dedicated_cargo_airlines", [])
    }

    freighter_keywords = {
        str(keyword).strip().lower()
        for keyword in config.get("freighter_keywords", [])
    }

    return dedicated_cargo_airlines, freighter_keywords


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def classify_cargo(
    row,
    dedicated_cargo_airlines,
    freighter_keywords,
):
    airline = str(row["Airline"]).strip().upper()
    detailed = str(row["AC_Type_Detailed"]).strip().lower()

    if airline in dedicated_cargo_airlines:
        return True, "dedicated cargo carrier"

    if any(keyword in detailed for keyword in freighter_keywords):
        return True, "freighter aircraft type"

    return False, "passenger/default"


def parse_airports(value):
    """
    Convert ApplicableAirports into a normal Python list.

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
    """Reject obviously missing values."""

    if pd.isna(value):
        return False

    value = str(value).strip()

    return value not in ("", "-", "nan", "None")


# ---------------------------------------------------------
# GENERATION
# ---------------------------------------------------------

def generate_timetable(
    input_file,
    airport,
    target_date,
    timezone_name,
    timetable_name,
    airports,
    known_airports,
    airport_reidentifications,
    excluded_airports,
    dedicated_cargo_airlines,
    freighter_keywords,
    show_cargo=False,
):
    output_file = OUTPUT_DIR / f"{airport} {timetable_name}.csv"

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
        input_file,
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
        origin_text.str.contains(airport, na=False, regex=False)
        | destination_text.str.contains(airport, na=False, regex=False)
    )

    df = df[airport_mask].copy()

    print(
        f"Flights mentioning {airport}: {len(df):,}"
    )

    print("Parsing airport information...")

    df["origin_airports"] = (
        df["Track_Origin_ApplicableAirports"]
        .apply(parse_airports)
    )

    df["destination_airports"] = (
        df["Track_Destination_ApplicableAirports"]
        .apply(parse_airports)
    )

    departure_mask = (
        df["origin_airports"].apply(
            lambda x: x == [airport]
        )
        & df["destination_airports"].apply(
            lambda x: len(x) == 1
        )
    )

    arrival_mask = (
        df["destination_airports"].apply(
            lambda x: x == [airport]
        )
        & df["origin_airports"].apply(
            lambda x: len(x) == 1
        )
    )

    departures = df[departure_mask].copy()
    arrivals = df[arrival_mask].copy()

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

    timezone = ZoneInfo(timezone_name)

    departures["event_time_local"] = (
        departures["event_time_utc"]
        .dt.tz_convert(timezone)
    )

    arrivals["event_time_local"] = (
        arrivals["event_time_utc"]
        .dt.tz_convert(timezone)
    )

    departures = departures[
        departures["event_time_local"]
        .dt.strftime("%Y-%m-%d")
        == target_date
    ].copy()

    arrivals = arrivals[
        arrivals["event_time_local"]
        .dt.strftime("%Y-%m-%d")
        == target_date
    ].copy()

    print(
        f"\nRaw usable traffic for {target_date}:"
    )
    print(
        f"Departures: {len(departures):,}"
    )
    print(
        f"Arrivals:   {len(arrivals):,}"
    )

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

    # -----------------------------------------------------
    # AIRPORT CLEANUP
    # -----------------------------------------------------

    reidentified_count = (
        combined["origin"].isin(airport_reidentifications).sum()
        + combined["destination"].isin(airport_reidentifications).sum()
    )

    reidentification_counts = {}

    for old, new in airport_reidentifications.items():
        count = (
            (combined["origin"] == old).sum()
            + (combined["destination"] == old).sum()
        )

        if count:
            reidentification_counts[(old, new)] = count

    combined["origin"] = combined["origin"].replace(
        airport_reidentifications
    )

    combined["destination"] = combined["destination"].replace(
        airport_reidentifications
    )

    excluded_matches = pd.concat([
        combined.loc[
            combined["origin"].isin(excluded_airports),
            "origin",
        ],
        combined.loc[
            combined["destination"].isin(excluded_airports),
            "destination",
        ],
    ])

    excluded_breakdown = excluded_matches.value_counts()

    excluded_mask = (
        combined["origin"].isin(excluded_airports)
        | combined["destination"].isin(excluded_airports)
    )

    excluded_count = excluded_mask.sum()

    combined = combined[
        ~excluded_mask
    ].copy()

    print(
        f"Reidentified airport references: {reidentified_count:,}"
    )
    print(
        f"Removed excluded-airport flights: {excluded_count:,}"
    )

    if not excluded_breakdown.empty:
        print("\nExcluded airport breakdown:")

        for airport_code, count in excluded_breakdown.items():
            print(f"  {airport_code}: {count}")

    if reidentification_counts:
        print("\nAirport reidentifications:")

        for (old, new), count in reidentification_counts.items():
            print(f"  {old} -> {new}: {count}")

    unknown_origin_mask = ~combined["origin"].isin(known_airports)
    unknown_destination_mask = ~combined["destination"].isin(known_airports)

    unknown_matches = pd.concat([
        combined.loc[
            unknown_origin_mask,
            "origin",
        ],
        combined.loc[
            unknown_destination_mask,
            "destination",
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

        for airport_code, count in unknown_breakdown.items():
            print(f"  {airport_code}: {count}")

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

    before_cleanup = len(combined)

    combined = combined[
        combined["Callsign"].apply(is_valid_text)
        & combined["AC_Type"].apply(is_valid_text)
        & combined["origin"].apply(is_valid_text)
        & combined["destination"].apply(is_valid_text)
    ].copy()

    removed = before_cleanup - len(combined)

    print(
        f"Removed invalid records: {removed:,}"
    )

    # -----------------------------------------------------
    # VICE FIELDS
    # -----------------------------------------------------

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
        lambda row: classify_cargo(
            row,
            dedicated_cargo_airlines,
            freighter_keywords,
        ),
        axis=1,
        result_type="expand",
    )

    combined["cargo"] = cargo_results[0]
    combined["cargo_reason"] = cargo_results[1]

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

    if show_cargo:
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

    vice = vice.sort_values(
        ["time", "callsign"]
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    vice.to_csv(
        output_file,
        index=False,
    )

    print("\n" + "=" * 50)
    print("VICE TIMETABLE CREATED")
    print("=" * 50)
    print(
        f"Airport:      {airport}"
    )
    print(
        f"Source date:  {target_date}"
    )
    print(
        f"Flights:      {len(vice):,}"
    )
    print(
        f"Departures:   "
        f"{(vice['origin'] == airport).sum():,}"
    )
    print(
        f"Arrivals:     "
        f"{(vice['destination'] == airport).sum():,}"
    )
    print(
        f"Cargo:        "
        f"{(vice['cargo'] == 'true').sum():,}"
    )
    print("\nOutput:")
    print(
        output_file.resolve()
    )
    print("\nFirst 20 timetable entries:\n")
    print(
        vice.head(20).to_string(
            index=False
        )
    )

    return vice


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def run_generate(args):
    validate_args(args)

    airport = args.airport.upper()
    target_date = args.date

    airports = load_airport_reference()
    known_airports = build_known_airports(airports)

    airport_reidentifications, excluded_airports = (
        load_airport_overrides()
    )

    dedicated_cargo_airlines, freighter_keywords = (
        load_cargo_rules()
    )

    airport_metadata = get_airport_metadata(
        airports,
        airport,
    )

    timezone_name = determine_timezone(
        airport_metadata,
        args.timezone,
    )

    print("\nAirport configuration:")
    print(f"Airport:  {airport}")
    print(f"Name:     {airport_metadata['name']}")
    print(f"Timezone: {timezone_name}")

    if args.timezone:
        print("Source:   CLI override")
    else:
        print("Source:   Automatically detected")

    return generate_timetable(
        input_file=args.input,
        airport=airport,
        target_date=target_date,
        timezone_name=timezone_name,
        timetable_name=args.name,
        airports=airports,
        known_airports=known_airports,
        airport_reidentifications=airport_reidentifications,
        excluded_airports=excluded_airports,
        dedicated_cargo_airlines=dedicated_cargo_airlines,
        freighter_keywords=freighter_keywords,
        show_cargo=args.show_cargo,
    )


def main():
    args = parse_args()
    run_generate(args)

