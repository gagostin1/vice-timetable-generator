import pandas as pd
import ast
from zoneinfo import ZoneInfo

FILE = "data/2026_Q2_detailed_github.parquet"
AIRPORT = "KCLT"
TARGET_DATE = "2026-06-18"

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

print("Loading dataset...")
df = pd.read_parquet(FILE, columns=columns)


def parse_airports(value):
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


print("Parsing airport fields...")

df["origin_airports"] = (
    df["Track_Origin_ApplicableAirports"]
    .apply(parse_airports)
)

df["destination_airports"] = (
    df["Track_Destination_ApplicableAirports"]
    .apply(parse_airports)
)

departures = df[
    (df["origin_airports"].apply(lambda x: x == [AIRPORT])) &
    (df["destination_airports"].apply(lambda x: len(x) == 1))
].copy()

arrivals = df[
    (df["destination_airports"].apply(lambda x: x == [AIRPORT])) &
    (df["origin_airports"].apply(lambda x: len(x) == 1))
].copy()


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


tz = ZoneInfo("America/New_York")

departures["event_time_local"] = (
    departures["event_time_utc"].dt.tz_convert(tz)
)

arrivals["event_time_local"] = (
    arrivals["event_time_utc"].dt.tz_convert(tz)
)


departures["local_date"] = (
    departures["event_time_local"]
    .dt.strftime("%Y-%m-%d")
)

arrivals["local_date"] = (
    arrivals["event_time_local"]
    .dt.strftime("%Y-%m-%d")
)


departures = departures[
    departures["local_date"] == TARGET_DATE
].copy()

arrivals = arrivals[
    arrivals["local_date"] == TARGET_DATE
].copy()


departures["hour"] = (
    departures["event_time_local"].dt.hour
)

arrivals["hour"] = (
    arrivals["event_time_local"].dt.hour
)


print(f"\nKCLT traffic for {TARGET_DATE}")
print("=" * 40)

print(f"Departures: {len(departures):,}")
print(f"Arrivals:   {len(arrivals):,}")
print(f"Total:      {len(departures) + len(arrivals):,}")


hourly_departures = departures.groupby("hour").size()
hourly_arrivals = arrivals.groupby("hour").size()

hourly = pd.DataFrame({
    "departures": hourly_departures,
    "arrivals": hourly_arrivals,
}).fillna(0)

hourly["departures"] = hourly["departures"].astype(int)
hourly["arrivals"] = hourly["arrivals"].astype(int)

hourly["total"] = (
    hourly["departures"]
    + hourly["arrivals"]
)

hourly = hourly.reindex(range(24), fill_value=0)


print("\nTraffic by hour:")
print(hourly.to_string())


print("\nTop airlines by flights:")

combined = pd.concat([departures, arrivals])

print(
    combined["Airline"]
    .value_counts()
    .head(20)
    .to_string()
)


print("\nTop aircraft types:")

print(
    combined["AC_Type"]
    .value_counts()
    .head(20)
    .to_string()
)