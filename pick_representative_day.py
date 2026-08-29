import argparse
import ast
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import pandas as pd
from timezonefinder import TimezoneFinder


BASE_DIR = Path(__file__).resolve().parent
AIRPORT_REFERENCE_FILE = BASE_DIR / "reference" / "airports.csv"
TIMEZONE_FINDER = TimezoneFinder()
AIRPORT_OVERRIDES_FILE = BASE_DIR / "airport_overrides.json"


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Find a representative weekday for a VICE timetable "
            "from historical flight data."
        )
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
        "--timezone",
        required=False,
        help=(
            "Optional IANA timezone override. "
            "If omitted, the timezone is detected automatically."
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Number of candidate dates to display. Default: 10.",
    )

    parser.add_argument(
    "--month",
    type=int,
    choices=range(1, 13),
    help=(
        "Optional calendar month to analyze, e.g. 6 for June. "
        "If omitted, all dates in the dataset are considered."
    ),
    )

    return parser.parse_args()


def parse_airports(value):
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


def load_airport_reference():
    if not AIRPORT_REFERENCE_FILE.exists():
        raise SystemExit(
            f'Error: airport reference file not found: '
            f'"{AIRPORT_REFERENCE_FILE}"'
        )

    return pd.read_csv(
        AIRPORT_REFERENCE_FILE,
        low_memory=False,
    )


def get_airport_metadata(airports, airport_code):
    airport_code = airport_code.upper()

    ident = (
        airports["ident"]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    gps_code = (
        airports["gps_code"]
        .fillna("")
        .astype(str)
        .str.upper()
    )

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
        "name": str(airport.get("name", "")),
        "latitude": airport.get("latitude_deg"),
        "longitude": airport.get("longitude_deg"),
    }


def determine_timezone(metadata, override=None):
    if override:
        return override

    latitude = metadata["latitude"]
    longitude = metadata["longitude"]

    if pd.isna(latitude) or pd.isna(longitude):
        raise SystemExit(
            "Error: airport coordinates are missing. "
            "Use --timezone to specify the timezone manually."
        )

    timezone = TIMEZONE_FINDER.timezone_at(
        lat=float(latitude),
        lng=float(longitude),
    )

    if not timezone:
        raise SystemExit(
            "Error: timezone could not be determined. "
            "Use --timezone to specify it manually."
        )

    return timezone

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
    config = load_json_config(
        path,
        "airport overrides",
    )

    reidentifications = {
        str(old).strip().upper(): str(new).strip().upper()
        for old, new in config.get(
            "reidentifications",
            {},
        ).items()
    }

    excluded_airports = {
        str(code).strip().upper()
        for code in config.get(
            "excluded_airports",
            [],
        )
    }

    return reidentifications, excluded_airports

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


def is_valid_text(value):
    if pd.isna(value):
        return False

    value = str(value).strip()

    return value not in (
        "",
        "-",
        "nan",
        "None",
    )
    
def main():
    args = parse_args()

    input_file = Path(args.input)

    if not input_file.exists():
        raise SystemExit(
            f'Error: input file not found: "{args.input}"'
        )

    airport = args.airport.upper()

    if len(airport) != 4 or not airport.isalpha():
        raise SystemExit(
            "Error: airport must be a 4-letter ICAO identifier."
        )

    airports = load_airport_reference()
    known_airports = build_known_airports(
    airports
    )
    airport_reidentifications, excluded_airports = (
        load_airport_overrides()
    )
    metadata = get_airport_metadata(
        airports,
        airport,
    )

    timezone_name = determine_timezone(
        metadata,
        args.timezone,
    )

    timezone = ZoneInfo(timezone_name)

    print("\nAirport configuration:")
    print(f"Airport:  {airport}")
    print(f"Name:     {metadata['name']}")
    print(f"Timezone: {timezone_name}")

    print("\nLoading flight dataset...")

    columns = [
    "Callsign",
    "AC_Type",
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
        origin_text.str.contains(
            airport,
            na=False,
            regex=False,
        )
        |
        destination_text.str.contains(
            airport,
            na=False,
            regex=False,
        )
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
        &
        df["destination_airports"].apply(
            lambda x: len(x) == 1
        )
    )

    arrival_mask = (
        df["destination_airports"].apply(
            lambda x: x == [airport]
        )
        &
        df["origin_airports"].apply(
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

    departures["event_time_local"] = (
        departures["event_time_utc"]
        .dt.tz_convert(timezone)
    )

    arrivals["event_time_local"] = (
        arrivals["event_time_utc"]
        .dt.tz_convert(timezone)
    )

    # ---------------------------------------------------------
    # PREPARE ROUTES
    # ---------------------------------------------------------

    departures["origin"] = departures[
        "origin_airports"
    ].apply(lambda x: x[0])

    departures["destination"] = departures[
        "destination_airports"
    ].apply(lambda x: x[0])

    departures["direction"] = "departure"


    arrivals["origin"] = arrivals[
        "origin_airports"
    ].apply(lambda x: x[0])

    arrivals["destination"] = arrivals[
        "destination_airports"
    ].apply(lambda x: x[0])

    arrivals["direction"] = "arrival"


    combined = pd.concat(
        [
            departures,
            arrivals,
        ],
        ignore_index=True,
    )


    print(
        f"\nUsable operations before cleanup: "
        f"{len(combined):,}"
    )


    # ---------------------------------------------------------
    # APPLY AIRPORT REIDENTIFICATIONS
    # ---------------------------------------------------------

    combined["origin"] = (
        combined["origin"]
        .replace(
            airport_reidentifications
        )
    )

    combined["destination"] = (
        combined["destination"]
        .replace(
            airport_reidentifications
        )
    )


    # ---------------------------------------------------------
    # REMOVE MANUALLY EXCLUDED AIRPORTS
    # ---------------------------------------------------------

    excluded_mask = (
        combined["origin"].isin(
            excluded_airports
        )
        |
        combined["destination"].isin(
            excluded_airports
        )
    )

    excluded_count = excluded_mask.sum()

    combined = combined[
        ~excluded_mask
    ].copy()

    print(
        f"Removed excluded-airport operations: "
        f"{excluded_count:,}"
    )


    # ---------------------------------------------------------
    # REMOVE UNKNOWN AIRPORTS
    # ---------------------------------------------------------

    unknown_origin = (
        ~combined["origin"].isin(
            known_airports
        )
    )

    unknown_destination = (
        ~combined["destination"].isin(
            known_airports
        )
    )

    unknown_mask = (
        unknown_origin
        | unknown_destination
    )

    unknown_count = unknown_mask.sum()

    combined = combined[
        ~unknown_mask
    ].copy()

    print(
        f"Removed unknown-airport operations: "
        f"{unknown_count:,}"
    )


    # ---------------------------------------------------------
    # REMOVE SAME-AIRPORT FLIGHTS
    # ---------------------------------------------------------

    same_airport_mask = (
        combined["origin"]
        == combined["destination"]
    )

    same_airport_count = (
        same_airport_mask.sum()
    )

    combined = combined[
        ~same_airport_mask
    ].copy()

    print(
        f"Removed same-airport operations: "
        f"{same_airport_count:,}"
    )


    # ---------------------------------------------------------
    # REMOVE INVALID RECORDS
    # ---------------------------------------------------------

    before_invalid_cleanup = len(
        combined
    )

    combined = combined[
        combined["Callsign"].apply(
            is_valid_text
        )
        &
        combined["AC_Type"].apply(
            is_valid_text
        )
        &
        combined["origin"].apply(
            is_valid_text
        )
        &
        combined["destination"].apply(
            is_valid_text
        )
    ].copy()

    invalid_count = (
        before_invalid_cleanup
        - len(combined)
    )

    print(
        f"Removed invalid operations: "
        f"{invalid_count:,}"
    )


    # ---------------------------------------------------------
    # BUILD LOCAL DATES
    # ---------------------------------------------------------

    combined["local_date"] = (
        combined["event_time_local"]
        .dt.date
    )


    # ---------------------------------------------------------
    # COUNT OPERATIONS BY DATE
    # ---------------------------------------------------------

    departure_counts = (
        combined[
            combined["direction"]
            == "departure"
        ]
        .groupby("local_date")
        .size()
    )

    arrival_counts = (
        combined[
            combined["direction"]
            == "arrival"
        ]
        .groupby("local_date")
        .size()
    )

    daily = pd.DataFrame(
        {
            "departures": departure_counts,
            "arrivals": arrival_counts,
        }
    ).fillna(0)

    daily["departures"] = (
        daily["departures"]
        .astype(int)
    )

    daily["arrivals"] = (
        daily["arrivals"]
        .astype(int)
    )

    daily["total"] = (
        daily["departures"]
        + daily["arrivals"]
    )

    daily.index = pd.to_datetime(
        daily.index
    )

    daily["weekday"] = (
        daily.index.day_name()
    )

    weekdays = daily[
        daily["weekday"].isin(
            [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
            ]
        )
    ].copy()

    if args.month:
        weekdays = weekdays[
            weekdays.index.month == args.month
        ].copy()

        if weekdays.empty:
            raise SystemExit(
                f"Error: no weekday traffic found for month {args.month}."
            )

    median_departures = weekdays["departures"].median()
    median_arrivals = weekdays["arrivals"].median()
    median_total = weekdays["total"].median()

    weekdays["departure_difference"] = (
        weekdays["departures"] - median_departures
    ).abs()

    weekdays["arrival_difference"] = (
        weekdays["arrivals"] - median_arrivals
    ).abs()

    weekdays["total_difference"] = (
        weekdays["total"] - median_total
    ).abs()

    weekdays["score"] = (
        weekdays["departure_difference"]
        + weekdays["arrival_difference"]
        + weekdays["total_difference"]
    )

    ranked = weekdays.sort_values(
        [
            "score",
            "total_difference",
            "departure_difference",
            "arrival_difference",
        ],
        ascending=True,
    )

    print("\n" + "=" * 72)

    analysis_label = airport

    if args.month:
        month_name = pd.Timestamp(
            year=2000,
            month=args.month,
            day=1,
        ).month_name()

        analysis_label += f" — {month_name}"

    print(
        f"REPRESENTATIVE WEEKDAY ANALYSIS — {analysis_label}"
    )

    print("=" * 72)

    print(
        f"\nMedian weekday departures: "
        f"{median_departures:,.0f}"
    )

    print(
        f"Median weekday arrivals:   "
        f"{median_arrivals:,.0f}"
    )

    print(
        f"Median weekday operations: "
        f"{median_total:,.0f}"
    )

    print(
        f"\nTop {args.top} representative candidates:\n"
    )

    display = ranked.head(args.top).copy()

    display.index = (
        display.index
        .strftime("%Y-%m-%d")
    )

    print(
        display[
            [
                "weekday",
                "departures",
                "arrivals",
                "total",
                "score",
            ]
        ].to_string()
    )

    recommended = ranked.iloc[0]

    recommended_date = (
        ranked.index[0]
        .strftime("%Y-%m-%d")
    )

    print("\nRecommended date:")
    print(
        f"  {recommended_date} "
        f"({recommended['weekday']})"
    )

    print(
        f"  Departures: "
        f"{int(recommended['departures']):,}"
    )

    print(
        f"  Arrivals:   "
        f"{int(recommended['arrivals']):,}"
    )

    print(
        f"  Total:      "
        f"{int(recommended['total']):,}"
    )

    print(
        f"  Representative score: "
        f"{recommended['score']:,.0f}"
    )


if __name__ == "__main__":
    main()