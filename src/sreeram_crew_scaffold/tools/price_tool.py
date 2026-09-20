import requests

# Front-month COMEX futures — close to, but not exactly, the spot price.
YAHOO_TICKERS = {"gold": "GC%3DF", "silver": "SI%3DF"}


def fetch_price(metal: str) -> dict:
    """Latest futures price (USD/oz) and % change vs previous close. Raises on any failure."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{YAHOO_TICKERS[metal]}?interval=1d&range=2d"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    resp.raise_for_status()
    meta = resp.json()["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
    pct_change = ((price - prev_close) / prev_close) * 100 if prev_close else None
    return {"metal": metal, "price": price, "prev_close": prev_close, "pct_change": pct_change}
