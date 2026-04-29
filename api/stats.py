import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()


DATA_API_HOST = os.getenv(
    "POLYMARKET_DATA_API_HOST",
    "https://data-api.polymarket.com",
).rstrip("/")
BUILDER_NAME = (
    os.getenv("POLY_BUILDER_NAME")
    or os.getenv("BUILDER_NAME")
    or "OpiPoliX"
).strip()


def to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def parse_api_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def api_get(path: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    url = f"{DATA_API_HOST}{path}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "OpiPoliX Builder Dashboard"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Unexpected Data API response for {path}: {type(payload).__name__}")
    return payload


def fetch_builder_volume(time_period: str) -> List[Dict[str, Any]]:
    rows = api_get("/v1/builders/volume", {"timePeriod": time_period})
    builder_key = BUILDER_NAME.lower()
    return [
        row for row in rows
        if str(row.get("builder", "")).strip().lower() == builder_key
    ]


def iso_week_key(value: str) -> str:
    dt = parse_api_time(value)
    if not dt:
        return value or "Unknown"
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def normalize_rank(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value)


def active_users(row: Dict[str, Any]) -> int:
    return int(to_decimal(row.get("activeUsers") or 0))


def volume(row: Dict[str, Any]) -> Decimal:
    return to_decimal(row.get("volume") or 0)


def daily_row(row: Dict[str, Any]) -> Dict[str, Any]:
    dt = parse_api_time(row.get("dt"))
    date = dt.date().isoformat() if dt else str(row.get("dt") or "")
    users = active_users(row)
    return {
        "date": date,
        "volume_usdc": money(volume(row)),
        "active_users": users,
        "rank": normalize_rank(row.get("rank")),
        "trades": users,
        "unique_users": users,
        "unique_txs": 0,
    }


def weekly_row(row: Dict[str, Any]) -> Dict[str, Any]:
    users = active_users(row)
    return {
        "week": iso_week_key(str(row.get("dt") or "")),
        "volume_usdc": money(volume(row)),
        "active_users": users,
        "rank": normalize_rank(row.get("rank")),
        "trades": users,
        "unique_users": users,
        "unique_txs": 0,
    }


def sum_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_volume = sum((volume(row) for row in rows), Decimal("0"))
    total_users = sum(active_users(row) for row in rows)
    best_rank = min(
        (int(row["rank"]) for row in rows if str(row.get("rank", "")).isdigit()),
        default=None,
    )
    return {
        "volume_usdc": money(total_volume),
        "active_users": total_users,
        "rank": normalize_rank(best_rank),
        "period_rows": len(rows),
        "trades": total_users,
        "unique_users": total_users,
        "unique_txs": 0,
    }


def compute_stats(
    daily_rows: List[Dict[str, Any]],
    weekly_rows: List[Dict[str, Any]],
    all_rows: List[Dict[str, Any]],
    window_hours: int,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=window_hours)

    window_rows = [
        row for row in daily_rows
        if (parse_api_time(row.get("dt")) or datetime.min.replace(tzinfo=timezone.utc)) >= start
    ]

    daily = sorted((daily_row(row) for row in daily_rows), key=lambda row: row["date"], reverse=True)
    weekly = sorted((weekly_row(row) for row in weekly_rows), key=lambda row: row["week"], reverse=True)

    return {
        "generated_at_utc": now.isoformat(),
        "window_hours": window_hours,
        "window_start_utc": start.isoformat(),
        "window_end_utc": now.isoformat(),
        "builder_name": BUILDER_NAME,
        "data_source": "Polymarket Data API /v1/builders/volume",
        "debug_info": {
            "total_rows": len(daily_rows) + len(weekly_rows) + len(all_rows),
            "daily_buckets": len(daily),
            "weekly_buckets": len(weekly),
            "all_time_buckets": len(all_rows),
            "total_trades_fetched": len(daily_rows),
            "trades_with_timestamp": len(daily_rows),
            "trades_without_timestamp": 0,
        },
        "all_time": sum_rows(all_rows or daily_rows),
        "window": sum_rows(window_rows),
        "daily": daily,
        "weekly": weekly,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)
            hours = int(query_params.get("hours", ["24"])[0])

            daily_rows = fetch_builder_volume("DAY")
            weekly_rows = fetch_builder_volume("WEEK")
            all_rows = fetch_builder_volume("ALL")

            data = compute_stats(
                daily_rows=daily_rows,
                weekly_rows=weekly_rows,
                all_rows=all_rows,
                window_hours=hours,
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            import traceback

            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e),
                "detail": traceback.format_exc(),
            }, indent=2).encode())
