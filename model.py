"""
model.py - Profit model for the WTI (US Gulf) -> Brent (Rotterdam) crude arbitrage.

For every loading day since 2016, calculates:
  - unhedged profit (sell Brent on arrival, 14 trading days after loading)
  - hedged profit (short Brent futures at loading, bought back on arrival)
  - the "arb open" rule: ship only when the hedged margin at loading is positive
  - freight sensitivity and break-even freight
Saves results to data/model_results.csv for risk.py.
"""

import os

import matplotlib.pyplot as plt
import pandas as pd

import config

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


# ============ DATA ============
# Clean spot prices from load_data.py, from the date the trade became legal
df = pd.read_csv("data/clean_prices.csv", index_col=0, parse_dates=True)
df = df.loc[config.START_DATE:]

# Brent futures (for the hedge), matched on date. Spot and futures come from
# different sources with slightly different holiday calendars, so drop unmatched days
fut = pd.read_csv("data/brent_futures.csv", index_col=0, parse_dates=True)
df = df.join(fut, how="left")
print("Days with no futures price:", df["Brent_fut"].isna().sum())
df = df.dropna(subset=["Brent_fut"])
print("Rows:", len(df), "| from", df.index.min().date(), "to", df.index.max().date())


# ============ PRICES ON ARRIVAL ============
# shift(-N) pulls the value from N rows (trading days) later into today's row
df["Brent_arrival"] = df["Brent"].shift(-config.VOYAGE_TRADING_DAYS)
df["Brent_fut_arrival"] = df["Brent_fut"].shift(-config.VOYAGE_TRADING_DAYS)


# ============ COSTS PER BARREL ============
# Freight: already a column (base rate + high-freight periods, set in load_data.py)
df["Other_costs"] = config.OTHER_COSTS_PER_BBL          # insurance, port fees, losses

# Financing: interest on the money paid for the oil, for the length of the voyage
# = price paid x annual rate x (voyage calendar days / 365)
df["Financing"] = df["WTI"] * config.FINANCING_RATE * config.VOYAGE_CALENDAR_DAYS / 365

df["Total_costs"] = df["Freight"] + df["Other_costs"] + df["Financing"]


# ============ PROFIT ============
# Unhedged: sell Brent on arrival - buy WTI at loading - all costs
df["Profit_per_bbl"] = df["Brent_arrival"] - df["WTI"] - df["Total_costs"]
df["Profit_per_cargo"] = df["Profit_per_bbl"] * config.CARGO_BBL

# Hedge: SELL Brent futures at loading, BUY them back on arrival.
# Gains if Brent falls during the voyage, loses if it rises - opposite to the physical cargo
df["Futures_profit"] = df["Brent_fut"] - df["Brent_fut_arrival"]
df["Hedged_profit_per_bbl"] = df["Profit_per_bbl"] + df["Futures_profit"]
df["Hedged_profit_per_cargo"] = df["Hedged_profit_per_bbl"] * config.CARGO_BBL

# Drop the final loading days: their ships haven't "arrived" yet in our data,
# so there's no arrival price (spot or futures) and no profit can be calculated
df = df.dropna(subset=["Brent_arrival", "Brent_fut_arrival"])

# Remove unrealistic outlier days (see config.EXCLUDE_DATES), keeping a full copy to compare
df_all = df.copy()
df = df.drop(pd.to_datetime(config.EXCLUDE_DATES))

print("\n===== OUTLIER CHECK =====")
print(f"With 20 Apr 2020:  avg ${df_all['Profit_per_bbl'].mean():.2f}/bbl, "
      f"std ${df_all['Profit_per_bbl'].std():.2f}, best ${df_all['Profit_per_bbl'].max():.2f}")
print(f"Without it:        avg ${df['Profit_per_bbl'].mean():.2f}/bbl, "
      f"std ${df['Profit_per_bbl'].std():.2f}, best ${df['Profit_per_bbl'].max():.2f}")


# ============ UNHEDGED RESULTS ============
p = df["Profit_per_bbl"]
c = df["Profit_per_cargo"]

print("\n===== UNHEDGED TRADE RESULTS (2016 onwards) =====")
print(f"Number of trades:  {len(df)}")
print(f"Share profitable:  {(p > 0).mean():.1%}")
print(f"Average profit:    ${p.mean():.2f}/bbl  =  ${c.mean() / 1e6:.2f}m per cargo")
print(f"Median profit:     ${p.median():.2f}/bbl")
print(f"Std deviation:     ${p.std():.2f}/bbl")
print(f"Best trade:        ${p.max():.2f}/bbl on {p.idxmax().date()}")
print(f"Worst trade:       ${p.min():.2f}/bbl on {p.idxmin().date()}")

yearly = df.groupby(df.index.year)["Profit_per_bbl"].agg(["mean", "std", "count"])
yearly["share_profitable"] = df.groupby(df.index.year)["Profit_per_bbl"].apply(lambda x: (x > 0).mean())
print("\n===== BY YEAR =====")
print(yearly.round(2))

# Trades checked by hand against the raw CSV (see notes.md)
print("\n===== HAND-CHECK TRADES =====")
for d in ["2019-03-01", "2022-03-01", "2026-06-03"]:
    print(d, df.loc[d, ["WTI", "Brent_arrival", "Total_costs", "Profit_per_bbl"]].round(2).to_dict())


# ============ HEDGED vs UNHEDGED ============
def summarise(profit):
    """Key statistics for a column of profits ($/bbl)."""
    return {
        "Avg $/bbl":     profit.mean(),
        "Median $/bbl":  profit.median(),
        "Std $/bbl":     profit.std(),
        "% profitable":  (profit > 0).mean() * 100,
        "Worst $/bbl":   profit.min(),
        "Best $/bbl":    profit.max(),
    }


comparison = pd.DataFrame({
    "Unhedged": summarise(df["Profit_per_bbl"]),
    "Hedged":   summarise(df["Hedged_profit_per_bbl"]),
})
print("\n===== HEDGED vs UNHEDGED =====")
print(comparison.round(2))

risk_cut = 1 - df["Hedged_profit_per_bbl"].std() / df["Profit_per_bbl"].std()
print(f"\nHedging cuts the standard deviation of profit by {risk_cut:.0%}")


# ============ SELECTIVE TRADING: only ship when the arb is open ============
# Locked-in margin at loading, using only prices known ON the loading day (no look-ahead)
df["Expected_margin"] = df["Brent_fut"] - df["WTI"] - df["Total_costs"]
df["Arb_open"] = df["Expected_margin"] > 0
open_days = df[df["Arb_open"]]

print(f"\nArb open on {df['Arb_open'].mean():.0%} of loading days ({len(open_days)} of {len(df)})")

comparison_sel = pd.DataFrame({
    "Every day - unhedged": summarise(df["Profit_per_bbl"]),
    "Every day - hedged":   summarise(df["Hedged_profit_per_bbl"]),
    "Arb open - unhedged":  summarise(open_days["Profit_per_bbl"]),
    "Arb open - hedged":    summarise(open_days["Hedged_profit_per_bbl"]),
})
print("\n===== SELECTIVE vs EVERY DAY =====")
print(comparison_sel.round(2))

print("\n===== ARB OPEN BY YEAR (% of days) =====")
print((df.groupby(df.index.year)["Arb_open"].mean() * 100).round(0))


# ============ FREIGHT SENSITIVITY & BREAK-EVEN ============
# Profit before freight: add the actual freight back on, then subtract test levels
pre_freight = df["Profit_per_bbl"] + df["Freight"]
pre_freight_hedged = df["Hedged_profit_per_bbl"] + df["Freight"]

print(f"\nBreak-even freight (every day, unhedged): ${pre_freight.mean():.2f}/bbl")
print(f"Break-even freight (every day, hedged):   ${pre_freight_hedged.mean():.2f}/bbl")

# What if freight were a flat $f/bbl on every day?
rows = []
for f in config.FREIGHT_RANGE:
    unhedged = pre_freight - f
    hedged = pre_freight_hedged - f
    open_mask = (df["Expected_margin"] + df["Freight"] - f) > 0   # arb open at this freight
    rows.append({
        "Freight $/bbl":          f,
        "Unhedged avg":           unhedged.mean(),
        "Unhedged % profitable":  (unhedged > 0).mean() * 100,
        "Arb open % of days":     open_mask.mean() * 100,
        "Arb-open hedged avg":    hedged[open_mask].mean(),
    })

sensitivity = pd.DataFrame(rows).set_index("Freight $/bbl")
print("\n===== FREIGHT SENSITIVITY (flat freight every day) =====")
print(sensitivity.round(2))


# ============ SAVE RESULTS (used by risk.py) ============
df.to_csv("data/model_results.csv")
print("\nSaved model results:", len(df), "rows")


# ============ CHARTS ============
os.makedirs("charts", exist_ok=True)

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 10))

# Chart 1: how often each profit level happened
ax1.hist(df["Profit_per_bbl"], bins=100, color="steelblue", edgecolor="white")
ax1.axvline(0, color="black", linewidth=1, label="Break-even")
ax1.axvline(df["Profit_per_bbl"].mean(), color="red", linestyle="--",
            label=f"Average (${df['Profit_per_bbl'].mean():.2f})")
ax1.set_title("Unhedged profit per barrel, every loading day since 2016")
ax1.set_xlabel("Profit ($/bbl)")
ax1.set_ylabel("Number of trades")
ax1.legend()

# Chart 2: profit over time
ax2.plot(df.index, df["Profit_per_bbl"], color="lightgray", linewidth=0.7, label="Each trade")
ax2.plot(df.index, df["Profit_per_bbl"].rolling(60).mean(), color="darkblue",
         linewidth=1.8, label="60-day rolling average")
ax2.axhline(0, color="black", linewidth=1)
ax2.set_title("Unhedged profit per barrel over time")
ax2.set_ylabel("Profit ($/bbl)")
ax2.legend()

plt.tight_layout(h_pad=3)
plt.savefig("charts/unhedged_profit.png", dpi=150)
plt.close()
