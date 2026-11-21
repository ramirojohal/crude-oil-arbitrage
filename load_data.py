"""
load_data.py - Load and clean daily WTI and Brent spot prices.

Reads EIA spot prices (downloaded from FRED: DCOILWTICO, DCOILBRENTEU),
aligns them by date, removes missing days, adds the Brent-WTI spread
and a freight column (base rate + higher-freight periods from config.py),
then saves data/clean_prices.csv for the rest of the project.
"""

import os

import matplotlib.pyplot as plt
import pandas as pd

import config

# --- 1. Load raw spot prices (dates as the index) ---
wti = pd.read_csv("data/DCOILWTICO.csv", index_col=0, parse_dates=True)
brent = pd.read_csv("data/DCOILBRENTEU.csv", index_col=0, parse_dates=True)

# --- 2. Combine side by side, matched on date, in date order ---
df = pd.concat([wti, brent], axis=1, sort=True)
df.columns = ["WTI", "Brent"]

# --- 3. Clean: holiday blanks / "." become NaN, then drop them ---
df = df.apply(pd.to_numeric, errors="coerce")
df = df.dropna()

# --- 4. Spread ---
df["Spread"] = df["Brent"] - df["WTI"]

# --- 5. Freight: base rate everywhere, then overwrite high-freight periods ---
df["Freight"] = config.FREIGHT_BASE
for (start, end), rate in config.FREIGHT_PERIODS.items():
    df.loc[start:end, "Freight"] = rate

# --- 6. Data checks ---
print("Rows:", len(df), "| from", df.index.min().date(), "to", df.index.max().date())
print(f"Average spread since 2016: ${df.loc['2016':, 'Spread'].mean():.1f}/bbl")
print("\nNov 2022 freight check (should be 9.0):")
print(df.loc["2022-11", ["Spread", "Freight"]].head())
print("\nBiggest spread days:")
print(df["Spread"].nlargest(5))

# --- 7. Save clean data for the rest of the project ---
df.index.name = "Date"
df.to_csv("data/clean_prices.csv")
print("\nSaved clean data:", len(df), "rows")

# --- 8. Chart: prices and spread ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
df[["WTI", "Brent"]].plot(ax=ax1, title="WTI vs Brent spot ($/bbl)")
df["Spread"].plot(ax=ax2, title="Brent - WTI spread ($/bbl)", color="green")
ax2.axhline(0, color="black", linewidth=0.8)   # zero line
plt.tight_layout()
os.makedirs("charts", exist_ok=True)
plt.savefig("charts/prices_and_spread.png", dpi=150)
plt.close()
