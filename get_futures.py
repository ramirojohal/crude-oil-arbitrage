"""
get_futures.py - Download Brent front-month futures prices (Yahoo: BZ=F).

Used for the hedge: the trader sells Brent futures at loading and buys
them back on arrival. Run once; saves data/brent_futures.csv.
Note: this is a continuous series that jumps when contracts roll.
"""


import yfinance as yf

fut = yf.download("BZ=F", start="2016-01-01")["Close"].squeeze()

fut.name = "Brent_fut"    # naming the column
fut.index.name = "Date"   # name index to match clean_prices.csv

fut.to_csv("data/brent_futures.csv")
print("Saved", len(fut), "rows from", fut.index.min().date(), "to" , fut.index.max().date())
print(fut.head())