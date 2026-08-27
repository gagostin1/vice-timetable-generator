import pandas as pd

FILE = "data/2026_Q2_detailed_github.parquet"

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

origins = df["Track_Origin_ApplicableAirports"].astype(str)
destinations = df["Track_Destination_ApplicableAirports"].astype(str)

clt = df[
    origins.str.contains("KCLT", na=False)
    | destinations.str.contains("KCLT", na=False)
].copy()

print(f"\nFlights involving KCLT: {len(clt):,}")

print("\nFirst 30 KCLT flights:\n")

print(
    clt[
        [
            "Callsign",
            "Airline",
            "AC_Type",
            "AC_Type_Detailed",
            "Track_Origin_ApplicableAirports",
            "Track_Destination_ApplicableAirports",
            "Track_Origin_DateTime_UTC",
            "Track_Destination_DateTime_UTC",
        ]
    ]
    .head(30)
    .to_string(index=False)
)