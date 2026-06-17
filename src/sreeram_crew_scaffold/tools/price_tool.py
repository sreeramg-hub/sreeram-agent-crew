import json
import pathlib
from typing import Literal, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

STATE_DIR = pathlib.Path(__file__).parents[3] / "state"

YAHOO_TICKERS = {"gold": "GC%3DF", "silver": "SI%3DF"}
UNITS = {"gold": "oz", "silver": "oz"}


class PriceLookupInput(BaseModel):
    metal: Literal["gold", "silver"] = Field(
        ..., description="The metal to look up: 'gold' or 'silver'."
    )


class PriceLookupTool(BaseTool):
    name: str = "price_lookup"
    description: str = (
        "Fetches the current spot price for gold or silver (USD/oz) "
        "and calculates the percentage change from the previous close. "
        "Input: metal name ('gold' or 'silver')."
    )
    args_schema: Type[BaseModel] = PriceLookupInput

    def _run(self, metal: str) -> str:
        metal = metal.lower().strip()
        ticker = YAHOO_TICKERS.get(metal)
        if not ticker:
            return f"Unknown metal '{metal}'. Choose 'gold' or 'silver'."

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            meta = resp.json()["chart"]["result"][0]["meta"]
        except Exception as e:
            return f"Failed to fetch {metal} price: {e}"

        current = meta["regularMarketPrice"]
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

        if prev_close and prev_close != 0:
            pct_change = ((current - prev_close) / prev_close) * 100
            direction = "up" if pct_change >= 0 else "down"
            change_str = f"{direction} {abs(pct_change):.2f}% from previous close (${prev_close:.2f})"
        else:
            change_str = "change unavailable"

        return (
            f"{metal.capitalize()} spot price: ${current:.2f}/oz — {change_str}."
        )
