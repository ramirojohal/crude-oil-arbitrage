"""
risk.py - Tail risk for one cargo: probability of loss, 95% VaR and Expected Shortfall.

1. Historical version from the model's results (overlapping trades - first estimate).
2. Block bootstrap: 10,000 simulated voyages built from random 7-day blocks of real
   daily Brent spot and futures moves, applied to today's Brent price.
Compares unhedged vs hedged risk, with an optional check excluding the 2020 COVID crash.
"""

import numpy as np
import pandas as pd

import config

# --- Simulation settings ---
N_SIMS = 10_000                  # number of simulated voyages
BLOCK = 7                        # consecutive real days per block
SEED = 42                        # fixed random seed -> reproducible results
EXCLUDE_COVID = False            # True = rerun without Mar-May 2020 (robustness check)

df = pd.read_csv("data/model_results.csv", index_col=0, parse_dates=True)
open_days = df[df["Arb_open"]]


def risk_stats(cargo_profit, level=0.95):
    """Probability of loss, VaR and Expected Shortfall for a column of cargo profits ($)."""
    cutoff = cargo_profit.quantile(1 - level)          # the 5th percentile outcome
    worst = cargo_profit[cargo_profit <= cutoff]       # the worst 5% of outcomes
    return {
        "Prob. of loss":  (cargo_profit < 0).mean() * 100,
        "Avg profit $m":  cargo_profit.mean() / 1e6,
        "95% VaR $m":     -cutoff / 1e6,               # shown as a positive loss
        "95% ES $m":      -worst.mean() / 1e6,
    }


# ============ 1. HISTORICAL RISK (first estimate) ============
hist = pd.DataFrame({
    "Every day - unhedged": risk_stats(df["Profit_per_cargo"]),
    "Every day - hedged":   risk_stats(df["Hedged_profit_per_cargo"]),
    "Arb open - hedged":    risk_stats(open_days["Hedged_profit_per_cargo"]),
})
print("===== HISTORICAL RISK PER CARGO (600,000 bbl) =====")
print(hist.round(2))


# ============ 2. DAILY % MOVES (raw material for the simulation) ============
# Daily % change in Brent spot and futures, taken from the SAME days so they stay paired
rets = df[["Brent", "Brent_fut"]].pct_change().dropna()
rets.columns = ["spot_ret", "fut_ret"]

if EXCLUDE_COVID:
    rets = rets.drop(rets.loc["2020-03-01":"2020-05-31"].index)
    print("\nNOTE: Mar-May 2020 excluded from simulation")

print("\n===== DAILY % MOVES =====")
print(f"Days of history: {len(rets)}")
print((rets * 100).describe().round(2))
print("\nBiggest daily falls in Brent spot (%):")
print((rets["spot_ret"].nsmallest(5) * 100).round(1))


# ============ 3. BLOCK BOOTSTRAP: simulate voyages ============
VOYAGE = config.VOYAGE_TRADING_DAYS          # 14 trading days
n_blocks = -(-VOYAGE // BLOCK)               # blocks needed, rounded up

spot = rets["spot_ret"].to_numpy()
fut = rets["fut_ret"].to_numpy()
rng = np.random.default_rng(SEED)

spot_voyage = np.zeros(N_SIMS)
fut_voyage = np.zeros(N_SIMS)

for i in range(N_SIMS):
    path_spot, path_fut = [], []
    for _ in range(n_blocks):
        start = rng.integers(0, len(spot) - BLOCK + 1)     # random starting day
        path_spot.extend(spot[start:start + BLOCK])        # consecutive real days
        path_fut.extend(fut[start:start + BLOCK])          # SAME days for futures
    path_spot = np.array(path_spot[:VOYAGE])               # trim to exactly the voyage length
    path_fut = np.array(path_fut[:VOYAGE])
    spot_voyage[i] = np.prod(1 + path_spot) - 1            # total % move over the voyage
    fut_voyage[i] = np.prod(1 + path_fut) - 1

print(f"\n===== SIMULATED {VOYAGE}-DAY VOYAGE MOVES =====")
print(f"Spot:    mean {spot_voyage.mean():.2%}, std {spot_voyage.std():.2%}, "
      f"worst {spot_voyage.min():.1%}, best {spot_voyage.max():.1%}")
print(f"Futures: mean {fut_voyage.mean():.2%}, std {fut_voyage.std():.2%}")

# Sanity check: simulated spread of moves should be close to real history
real_moves = df["Brent"].pct_change(VOYAGE).dropna()
print(f"Real {VOYAGE}-day spot moves: std {real_moves.std():.2%}")


# ============ 4. SIMULATED CARGO PROFITS & RISK ============
# Typical arb-open cargo, priced at the latest Brent (not the last loading day)
latest = pd.read_csv("data/clean_prices.csv", index_col=0, parse_dates=True)
P = latest["Brent"].iloc[-1]
M = open_days["Expected_margin"].mean()      # typical locked margin when the arb is open
print(f"\nSimulating a cargo at Brent ${P:.2f} ({latest.index[-1].date()}) "
      f"with locked margin ${M:.2f}/bbl")

# Unhedged: margin + full Brent move. Hedged: futures cancel most of it, leaving basis
sim_unhedged = (M + P * spot_voyage) * config.CARGO_BBL
sim_hedged = (M + P * (spot_voyage - fut_voyage)) * config.CARGO_BBL

sim = pd.DataFrame({
    "Simulated - unhedged": risk_stats(pd.Series(sim_unhedged)),
    "Simulated - hedged":   risk_stats(pd.Series(sim_hedged)),
})
print(f"\n===== SIMULATED RISK PER CARGO ({N_SIMS:,} block-bootstrap voyages) =====")
print(sim.round(2))

cut_var = 1 - sim.loc["95% VaR $m", "Simulated - hedged"] / sim.loc["95% VaR $m", "Simulated - unhedged"]
cut_es = 1 - sim.loc["95% ES $m", "Simulated - hedged"] / sim.loc["95% ES $m", "Simulated - unhedged"]
print(f"\nHedging cuts 95% VaR by {cut_var:.0%} and Expected Shortfall by {cut_es:.0%}")
