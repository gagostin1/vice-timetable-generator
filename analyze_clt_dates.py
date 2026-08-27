import pandas as pd
import ast
from zoneinfo import ZoneInfo

FILE = "data/2026_Q2_detailed_github.parquet"
AIRPORT = "KCLT"

print("Loading dataset...")

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

df = pd.read_parquet(FILE, columns=columns)

print(f"Total flights loaded: {len(df):,}")


def parse_airports(value):
    """
    Convert the ApplicableAirports value into a normal Python list.
    Handles values such as:
        ['KCLT']
        ['KCRE', 'KMYR']
    """

    if value is None:
        return []

    if isinstance(value, (list, tuple)):
        return list(value)

    text = str(value)

    if text in ("-", "nan", "None", ""):
        return []

    try:
        parsed = ast.literal_eval(text)

        if isinstance(parsed, list):
            return parsed

        return [str(parsed)]

    except (ValueError, SyntaxError):
        return [text]


print("Parsing airport data...")

df["origin_airports"] = df[
    "Track_Origin_ApplicableAirports"
].apply(parse_airports)

df["destination_airports"] = df[
    "Track_Destination_ApplicableAirports"
].apply(parse_airports)


# Confident CLT departure:
# origin airport list contains ONLY KCLT
is_clt_departure = df["origin_airports"].apply(
    lambda airports: airports == [AIRPORT]
)

# Confident CLT arrival:
# destination airport list contains ONLY KCLT
is_clt_arrival = df["destination_airports"].apply(
    lambda airports: airports == [AIRPORT]
)


departures = df[is_clt_departure].copy()
arrivals = df[is_clt_arrival].copy()

print(f"\nClean KCLT departures in quarter: {len(departures):,}")
print(f"Clean KCLT arrivals in quarter:   {len(arrivals):,}")
print(
    f"Clean KCLT operations total:      "
    f"{len(departures) + len(arrivals):,}"
)


# Convert timestamp columns into UTC-aware datetimes

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


# Charlotte local timezone
charlotte_tz = ZoneInfo("America/New_York")

departures["event_time_local"] = (
    departures["event_time_utc"]
    .dt.tz_convert(charlotte_tz)
)

arrivals["event_time_local"] = (
    arrivals["event_time_utc"]
    .dt.tz_convert(charlotte_tz)
)


# Determine local calendar date

departures["local_date"] = (
    departures["event_time_local"].dt.date
)

arrivals["local_date"] = (
    arrivals["event_time_local"].dt.date
)


# Count operations by date

departure_counts = departures.groupby("local_date").size()
arrival_counts = arrivals.groupby("local_date").size()

daily = pd.DataFrame({
    "departures": departure_counts,
    "arrivals": arrival_counts,
}).fillna(0)

daily["departures"] = daily["departures"].astype(int)
daily["arrivals"] = daily["arrivals"].astype(int)

daily["total"] = (
    daily["departures"]
    + daily["arrivals"]
)

daily.index = pd.to_datetime(daily.index)

daily["weekday"] = daily.index.day_name()


print("\nTop 20 busiest clean KCLT days:\n")

print(
    daily
    .sort_values("total", ascending=False)
    .head(20)
    .to_string()
)


print("\nTypical Tuesday-Thursday days:\n")

weekdays = daily[
    daily["weekday"].isin(
        ["Tuesday", "Wednesday", "Thursday"]
    )
]

print(
    weekdays
    .sort_values("total", ascending=False)
    .head(30)
    .to_string()
)