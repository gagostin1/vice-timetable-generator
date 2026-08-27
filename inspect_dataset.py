import pandas as pd

FILE = "data/2026_Q2_detailed_github.parquet"

print("Loading dataset...")
df = pd.read_parquet(FILE)

print("\nRows:")
print(len(df))

print("\nColumns:")
for column in df.columns:
    print(column)

print("\nFirst 5 flights:")
print(df.head().to_string())