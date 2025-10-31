"""Utility helpers for Alpha Vantage time series normalization.

This module centralizes schema conversions and timezone handling so that
all ingestion scripts produce identical output regardless of interval.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Tuple
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/New_York"

INTERVAL_ALIASES = {
    "daily": "daily",
    "1d": "daily",
    "d": "daily",
    "60min": "60min",
    "1h": "60min",
    "hourly": "60min",
    "h": "60min",
    "15min": "15min",
    "15m": "15min",
    "quarter-hour": "15min",
}

INTERVAL_CONFIG: Dict[str, Dict[str, Any]] = {
    "daily": {
        "function": "TIME_SERIES_DAILY",
        "api_params": {},
        "file_prefix": "daily_prices",
        "merged_filename": "merged.jsonl",
        "series_hint": "Daily",
        "keep_date_only": True,
        "trim_latest_to_buy": True,
    },
    "60min": {
        "function": "TIME_SERIES_INTRADAY",
        "api_params": {"interval": "60min", "entitlement": "delayed"},
        "file_prefix": "hourly_prices",
        "merged_filename": "merged_60min.jsonl",
        "series_hint": "60min",
        "keep_date_only": False,
        "trim_latest_to_buy": False,
    },
    "15min": {
        "function": "TIME_SERIES_INTRADAY",
        "api_params": {"interval": "15min", "entitlement": "delayed"},
        "file_prefix": "fifteen_min_prices",
        "merged_filename": "merged_15min.jsonl",
        "series_hint": "15min",
        "keep_date_only": False,
        "trim_latest_to_buy": False,
    },
}

_SCHEMA_FIELD_RENAMES = {
    "1. open": "1. buy price",
    "4. close": "4. sell price",
}


def normalize_interval(interval: str) -> str:
    """Return the canonical interval key."""
    key = interval.lower()
    return INTERVAL_ALIASES.get(key, key)


def get_interval_config(interval: str) -> Dict[str, Any]:
    """Fetch configuration for the provided interval."""
    canonical = normalize_interval(interval)
    if canonical not in INTERVAL_CONFIG:
        supported = ", ".join(sorted(INTERVAL_CONFIG))
        raise ValueError(f"Unsupported interval '{interval}'. Supported intervals: {supported}")
    return INTERVAL_CONFIG[canonical]


def _extract_time_series(payload: Dict[str, Any], hint: str | None = None) -> Tuple[str, Dict[str, Any]]:
    """Locate the Alpha Vantage time series block and return its key and value."""
    if hint:
        suffix = f"({hint})"
        for key, value in payload.items():
            if key.startswith("Time Series") and key.endswith(suffix):
                if isinstance(value, dict):
                    return key, value
                break
    for key, value in payload.items():
        if key.startswith("Time Series") and isinstance(value, dict):
            return key, value
    return "", {}


def _rename_bar_schema(bar: Dict[str, Any]) -> Dict[str, Any]:
    """Rename Alpha Vantage OHLC fields to the internal schema."""
    renamed = {}
    for field, value in bar.items():
        renamed[_SCHEMA_FIELD_RENAMES.get(field, field)] = value
    return renamed


def _localize_timestamp(timestamp: str, tz: ZoneInfo, keep_date_only: bool) -> str:
    """Attach timezone information to a timestamp string."""
    if keep_date_only:
        return timestamp
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return timestamp
    return dt.replace(tzinfo=tz).isoformat()


def _localize_last_refreshed(meta: Dict[str, Any], tz: ZoneInfo, keep_date_only: bool) -> None:
    last_refreshed = meta.get("3. Last Refreshed")
    if not isinstance(last_refreshed, str):
        return
    fmt = "%Y-%m-%d"
    if not keep_date_only and len(last_refreshed) > 10:
        fmt = "%Y-%m-%d %H:%M:%S"
    try:
        dt = datetime.strptime(last_refreshed, fmt)
    except ValueError:
        return
    meta["3. Last Refreshed"] = dt.replace(tzinfo=tz).isoformat()


def normalize_alpha_vantage_payload(
    payload: Dict[str, Any],
    interval: str,
    tz_name: str = DEFAULT_TIMEZONE,
) -> Tuple[Dict[str, Any], str]:
    """Normalize schema and timezone fields for an Alpha Vantage payload."""
    config = get_interval_config(interval)
    tz = ZoneInfo(tz_name)
    normalized_payload = dict(payload)

    series_key, series = _extract_time_series(normalized_payload, hint=config.get("series_hint"))
    if series_key and isinstance(series, dict):
        keep_date_only = config.get("keep_date_only", False)
        localized_series = {}
        for timestamp, bar in series.items():
            if isinstance(bar, dict):
                renamed_bar = _rename_bar_schema(bar)
            else:
                renamed_bar = {}
            localized_key = _localize_timestamp(timestamp, tz, keep_date_only)
            localized_series[localized_key] = renamed_bar
        normalized_payload[series_key] = localized_series

    meta = normalized_payload.get("Meta Data")
    if isinstance(meta, dict):
        meta = dict(meta)
        _localize_last_refreshed(meta, tz, config.get("keep_date_only", False))
        tz_key = "5. Time Zone" if "5. Time Zone" in meta else "6. Time Zone"
        meta[tz_key] = tz.key
        normalized_payload["Meta Data"] = meta

    return normalized_payload, series_key


def trim_latest_bar_to_buy(series: Dict[str, Dict[str, Any]]) -> None:
    """Reduce the latest bar to only include the buy price field."""
    if not series:
        return
    try:
        latest_timestamp = max(series.keys())
    except TypeError:
        return
    latest_bar = series.get(latest_timestamp)
    if not isinstance(latest_bar, dict):
        return
    buy_price = latest_bar.get("1. buy price")
    series[latest_timestamp] = {"1. buy price": buy_price} if buy_price is not None else {}


def iter_symbols_from_filenames(files: Iterable[str]) -> Iterable[Tuple[str, str]]:
    """Yield (filepath, symbol) pairs for matching NASDAQ-100 files."""
    for filepath in files:
        parts = filepath.split("_")
        if not parts:
            continue
        symbol_part = parts[-1]
        if symbol_part.endswith(".json"):
            symbol = symbol_part[:-5]
            yield filepath, symbol
