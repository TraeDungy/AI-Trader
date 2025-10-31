"""Alpha Vantage price ingestion utilities.

Historically this script only downloaded daily bars for the backtester.
It now exposes interval-aware helpers so the same schema can back both
live and historical pipelines (daily, hourly, 15-minute).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable, List

import requests
from dotenv import load_dotenv

from alpha_vantage_utils import (
    DEFAULT_TIMEZONE,
    get_interval_config,
    normalize_alpha_vantage_payload,
    normalize_interval,
)

load_dotenv()

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
DEFAULT_OUTPUTSIZE = "compact"

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
    "ON", "BIIB", "LULU", "CDW", "GFS"
]


def _build_request_params(symbol: str, interval: str, outputsize: str, apikey: str) -> dict:
    config = get_interval_config(interval)
    params = {
        "function": config["function"],
        "symbol": symbol,
        "apikey": apikey,
        "datatype": "json",
        "outputsize": outputsize,
    }
    params.update(config.get("api_params", {}))
    return params


def _write_payload(data: dict, symbol: str, interval: str, output_dir: Path, tz_name: str) -> Path:
    config = get_interval_config(interval)
    normalized_payload, series_key = normalize_alpha_vantage_payload(data, interval, tz_name=tz_name)
    if not series_key:
        raise ValueError("Alpha Vantage response did not contain a time series block")

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{config['file_prefix']}_{symbol}.json"
    output_path = output_dir / filename
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(normalized_payload, f, ensure_ascii=False, indent=4)

    # Maintain legacy duplicate file for QQQ daily bars expected by dashboards
    if symbol == "QQQ" and config["file_prefix"] == "daily_prices":
        alt_path = output_dir / f"A{filename}"
        with alt_path.open("w", encoding="utf-8") as f:
            json.dump(normalized_payload, f, ensure_ascii=False, indent=4)

    return output_path


def fetch_prices(
    symbol: str,
    interval: str = "daily",
    output_dir: Path | str = Path("."),
    tz_name: str = DEFAULT_TIMEZONE,
    outputsize: str = DEFAULT_OUTPUTSIZE,
    session: requests.Session | None = None,
) -> Path:
    """Fetch Alpha Vantage prices for the requested symbol/interval."""
    canonical_interval = normalize_interval(interval)
    apikey = os.getenv("ALPHAADVANTAGE_API_KEY")
    if not apikey:
        raise RuntimeError("ALPHAADVANTAGE_API_KEY environment variable is not set")

    params = _build_request_params(symbol, canonical_interval, outputsize, apikey)
    requester = session if session is not None else requests
    try:
        response = requester.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch data for {symbol}: {exc}") from exc

    data = response.json()
    if data.get("Note") or data.get("Information"):
        raise RuntimeError(f"Alpha Vantage returned an error for {symbol}: {data.get('Note') or data.get('Information')}")

    return _write_payload(data, symbol, canonical_interval, Path(output_dir), tz_name)


def get_daily_price(symbol: str, **kwargs) -> Path:
    """Fetch daily price data for a symbol."""
    return fetch_prices(symbol, interval="daily", **kwargs)


def get_hourly_price(symbol: str, **kwargs) -> Path:
    """Fetch hourly (60 minute) price data for a symbol."""
    return fetch_prices(symbol, interval="60min", **kwargs)


def get_15min_price(symbol: str, **kwargs) -> Path:
    """Fetch 15-minute price data for a symbol."""
    return fetch_prices(symbol, interval="15min", **kwargs)


def _parse_symbols(cli_symbols: Iterable[str] | None) -> List[str]:
    if cli_symbols:
        symbols = [sym.upper() for sym in cli_symbols]
    else:
        symbols = list(all_nasdaq_100_symbols)
    if "QQQ" not in symbols:
        symbols.append("QQQ")
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Alpha Vantage price data")
    parser.add_argument("--interval", default="daily", help="Data interval: daily, hourly/60min, or 15min")
    parser.add_argument("--symbols", nargs="*", help="Specific ticker symbols to download")
    parser.add_argument("--output-dir", default=".", help="Directory for the JSON output files")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="IANA timezone name for timestamp localization")
    parser.add_argument(
        "--outputsize",
        default=DEFAULT_OUTPUTSIZE,
        choices=["compact", "full"],
        help="Alpha Vantage outputsize parameter",
    )
    args = parser.parse_args()

    symbols = _parse_symbols(args.symbols)
    interval = args.interval

    successes = 0
    for symbol in symbols:
        try:
            path = fetch_prices(
                symbol,
                interval=interval,
                output_dir=args.output_dir,
                tz_name=args.timezone,
                outputsize=args.outputsize,
            )
            print(f"✅ Saved {symbol} {normalize_interval(interval)} data to {path}")
            successes += 1
        except Exception as exc:  # pylint: disable=broad-except
            print(f"❌ Failed to fetch {symbol}: {exc}")

    if successes == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
