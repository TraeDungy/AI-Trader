"""Merge Alpha Vantage JSON payloads into a consolidated JSONL file."""
from __future__ import annotations

import argparse
import glob
import json
import os
from typing import Iterable

from alpha_vantage_utils import (
    DEFAULT_TIMEZONE,
    get_interval_config,
    iter_symbols_from_filenames,
    normalize_alpha_vantage_payload,
    normalize_interval,
    trim_latest_bar_to_buy,
)

all_nasdaq_100_symbols = [
    "NVDA", "MSFT", "AAPL", "GOOG", "GOOGL", "AMZN", "META", "AVGO", "TSLA",
    "NFLX", "PLTR", "COST", "ASML", "AMD", "CSCO", "AZN", "TMUS", "MU", "LIN",
    "PEP", "SHOP", "APP", "INTU", "AMAT", "LRCX", "PDD", "QCOM", "ARM", "INTC",
    "BKNG", "AMGN", "TXN", "ISRG", "GILD", "KLAC", "PANW", "ADBE", "HON",
    "CRWD", "CEG", "ADI", "ADP", "DASH", "CMCSA", "VRTX", "MELI", "SBUX",
    "CDNS", "ORLY", "SNPS", "MSTR", "MDLZ", "ABNB", "MRVL", "CTAS", "TRI",
    "MAR", "MNST", "CSX", "ADSK", "PYPL", "FTNT", "AEP", "WDAY", "REGN", "ROP",
    "NXPI", "DDOG", "AXON", "ROST", "IDXX", "EA", "PCAR", "FAST", "EXC", "TTWO",
    "XEL", "ZS", "PAYX", "WBD", "BKR", "CPRT", "CCEP", "FANG", "TEAM", "CHTR",
    "KDP", "MCHP", "GEHC", "VRSK", "CTSH", "CSGP", "KHC", "ODFL", "DXCM", "TTD",
    "ON", "BIIB", "LULU", "CDW", "GFS",
]


def _iter_price_files(pattern: str) -> Iterable[str]:
    for filepath in sorted(glob.glob(pattern)):
        yield filepath


def merge_price_files(interval: str, tz_name: str = DEFAULT_TIMEZONE) -> str:
    """Merge individual JSON payloads into a JSONL file for the interval."""
    canonical_interval = normalize_interval(interval)
    config = get_interval_config(canonical_interval)

    current_dir = os.path.dirname(__file__)
    pattern = os.path.join(current_dir, f"{config['file_prefix']}*.json")
    output_path = os.path.join(current_dir, config["merged_filename"])

    files = list(_iter_price_files(pattern))
    if not files:
        raise FileNotFoundError(f"No price files found for pattern: {pattern}")

    with open(output_path, "w", encoding="utf-8") as fout:
        for filepath, symbol in iter_symbols_from_filenames(files):
            if symbol not in all_nasdaq_100_symbols and symbol != "QQQ":
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            normalized_payload, series_key = normalize_alpha_vantage_payload(
                data, canonical_interval, tz_name=tz_name
            )
            series = normalized_payload.get(series_key)
            if isinstance(series, dict) and config.get("trim_latest_to_buy"):
                trim_latest_bar_to_buy(series)
            fout.write(json.dumps(normalized_payload, ensure_ascii=False) + "\n")

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge Alpha Vantage JSON payloads")
    parser.add_argument("--interval", default="daily", help="Interval to merge: daily, 60min/hourly, or 15min")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="IANA timezone for localization")
    args = parser.parse_args()

    output_path = merge_price_files(args.interval, tz_name=args.timezone)
    print(f"✅ Wrote merged data to {output_path}")


if __name__ == "__main__":
    main()
