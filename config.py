"""
config.py - All model assumptions in one place.

Cargo size, voyage length, costs (freight, other costs, financing),
freight period estimates, start date and excluded outlier days.
Every other script imports from here, so changing an assumption
means editing this file only.
"""

# --- Period ---
START_DATE = "2016-01-01"        # US crude export ban lifted Dec 2015 - trade not possible before

# Days excluded as unrealistic for a physical trade (see notes.md)
EXCLUDE_DATES = ["2020-04-20"]   # WTI -$37: one-day Cushing storage squeeze at futures expiry

# --- Cargo ---
CARGO_BBL = 600_000              # barrels per cargo (typical Aframax tanker size)

# --- Voyage timing ---
VOYAGE_CALENDAR_DAYS = 20        # US Gulf Coast -> Rotterdam, incl. loading/discharge (used for financing)
VOYAGE_TRADING_DAYS = 14         # ~20 calendar days excluding weekends/holidays (used for .shift)

# --- Freight ($/bbl): published estimates, not real TD25 data ---
FREIGHT_BASE = 3.00                       # normal market conditions
FREIGHT_PERIODS = {
    ("2022-10-01", "2022-12-31"): 9.00,   # Argus: record $10.18/bl on 18 Nov 2022 (EU ban on Russian crude)
    ("2026-01-01", "2026-12-31"): 15.00,  # Kpler: TD25 $20.75 -> $11.71/bbl in early Nov 2026
}

# --- Other costs ($/bbl) ---
OTHER_COSTS_PER_BBL = 0.30       # insurance, port fees, small oil losses

# --- Financing ---
FINANCING_RATE = 0.05            # 5% per year: interest on money tied up in the cargo during the voyage

# --- Sensitivity analysis ---
FREIGHT_RANGE = list(range(1, 11))   # flat freight levels tested: $1 to $10/bbl
