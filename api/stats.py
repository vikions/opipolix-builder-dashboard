import os
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_builder_signing_sdk.config import BuilderConfig, BuilderApiKeyCreds

load_dotenv()


def to_decimal(x: Any) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def parse_match_time(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Попробуем разные форматы
        if s.endswith('Z'):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)
    except Exception:
        try:
            # Попробуем timestamp
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except Exception:
            return None


def init_client_builder_only() -> ClobClient:
    key = os.getenv("BUILDER_API_KEY")
    secret = os.getenv("BUILDER_SECRET")
    passphrase = os.getenv("BUILDER_PASS_PHRASE")
    if not (key and secret and passphrase):
        raise RuntimeError("Missing BUILDER_API_KEY / BUILDER_SECRET / BUILDER_PASS_PHRASE")

    builder_config = BuilderConfig(
        local_builder_creds=BuilderApiKeyCreds(
            key=key,
            secret=secret,
            passphrase=passphrase,
        )
    )

    return ClobClient(
        host="https://clob.polymarket.com",
        chain_id=137,
        builder_config=builder_config,
    )


def normalize_builder_trades_response(resp: Any) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if isinstance(resp, list):
        return resp, None

    if isinstance(resp, dict):
        trades = resp.get("trades")
        if trades is None and "data" in resp and isinstance(resp["data"], list):
            trades = resp["data"]
        if trades is None:
            trades = []
        next_cursor = resp.get("next_cursor") or resp.get("nextCursor")
        return trades, next_cursor

    trades = getattr(resp, "trades", None) or []
    next_cursor = getattr(resp, "next_cursor", None) or getattr(resp, "nextCursor", None)
    return list(trades), next_cursor


def get_builder_trades_call(client: ClobClient, params: Optional[Dict[str, Any]]) -> Any:
    if hasattr(client, "get_builder_trades"):
        return client.get_builder_trades(params if params else None)
    if hasattr(client, "getBuilderTrades"):
        return client.getBuilderTrades(params if params else None)
    raise RuntimeError("No get_builder_trades/getBuilderTrades on this client")


def fetch_all_builder_trades(
    client: ClobClient, 
    after: Optional[str] = None, 
    before: Optional[str] = None,
    max_iterations: int = 100
) -> List[Dict[str, Any]]:
    """
    Fetches all builder trades with optional time filtering.
    
    Args:
        client: ClobClient instance
        after: ISO timestamp or Unix timestamp (trades after this time)
        before: ISO timestamp or Unix timestamp (trades before this time)
        max_iterations: Maximum number of pagination iterations
    """
    all_trades: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        params: Dict[str, Any] = {}
        
        if cursor:
            params["id"] = cursor
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        resp = get_builder_trades_call(client, params if params else None)
        trades, next_cursor = normalize_builder_trades_response(resp)
        
        if not trades:
            break
            
        all_trades.extend(trades)

        if not next_cursor:
            break
        cursor = next_cursor

    return all_trades


def iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def compute_stats(trades: List[Dict[str, Any]], window_hours: int) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=window_hours)

    vol_all = Decimal("0")
    n_all = 0
    tx_all: Set[str] = set()
    users_all: Set[str] = set()

    daily: Dict[str, Dict[str, Any]] = {}
    weekly: Dict[str, Dict[str, Any]] = {}

    # Для отладки
    trades_with_time = 0
    trades_without_time = 0

    for t in trades:
        n_all += 1
        size_usdc = to_decimal(t.get("sizeUsdc") or t.get("size_usdc") or "0")
        vol_all += size_usdc

        txh = (t.get("transactionHash") or t.get("transaction_hash") or "").strip()
        if txh:
            tx_all.add(txh)

        owner = (t.get("owner") or "").strip().lower()
        if owner:
            users_all.add(owner)

        # Парсим время
        mt = parse_match_time(t.get("matchTime") or t.get("match_time"))
        if not mt:
            trades_without_time += 1
            continue
        
        trades_with_time += 1

        # Daily aggregation
        day = mt.date().isoformat()
        if day not in daily:
            daily[day] = {
                "date": day, 
                "volume_usdc": Decimal("0"), 
                "trades": 0, 
                "unique_users": set(), 
                "unique_txs": set()
            }
        daily[day]["volume_usdc"] += size_usdc
        daily[day]["trades"] += 1
        if owner:
            daily[day]["unique_users"].add(owner)
        if txh:
            daily[day]["unique_txs"].add(txh)

        # Weekly aggregation
        wk = iso_week_key(mt)
        if wk not in weekly:
            weekly[wk] = {
                "week": wk, 
                "volume_usdc": Decimal("0"), 
                "trades": 0, 
                "unique_users": set(), 
                "unique_txs": set()
            }
        weekly[wk]["volume_usdc"] += size_usdc
        weekly[wk]["trades"] += 1
        if owner:
            weekly[wk]["unique_users"].add(owner)
        if txh:
            weekly[wk]["unique_txs"].add(txh)

    # Window stats (last N hours)
    vol_win = Decimal("0")
    n_win = 0
    tx_win: Set[str] = set()
    users_win: Set[str] = set()
    
    for t in trades:
        mt = parse_match_time(t.get("matchTime") or t.get("match_time"))
        if not mt or mt < start:
            continue
        n_win += 1
        vol_win += to_decimal(t.get("sizeUsdc") or t.get("size_usdc") or "0")
        txh = (t.get("transactionHash") or t.get("transaction_hash") or "").strip()
        if txh:
            tx_win.add(txh)
        owner = (t.get("owner") or "").strip().lower()
        if owner:
            users_win.add(owner)

    def money(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    # Sort by date (newest first)
    daily_list = sorted(daily.values(), key=lambda x: x["date"], reverse=True)
    weekly_list = sorted(weekly.values(), key=lambda x: x["week"], reverse=True)

    # Convert sets to counts
    for row in daily_list:
        row["unique_users"] = len(row["unique_users"])
        row["unique_txs"] = len(row["unique_txs"])
        row["volume_usdc"] = money(row["volume_usdc"])
    for row in weekly_list:
        row["unique_users"] = len(row["unique_users"])
        row["unique_txs"] = len(row["unique_txs"])
        row["volume_usdc"] = money(row["volume_usdc"])

    return {
        "generated_at_utc": now.isoformat(),
        "window_hours": window_hours,
        "window_start_utc": start.isoformat(),
        "window_end_utc": now.isoformat(),
        "debug_info": {
            "total_trades_fetched": len(trades),
            "trades_with_timestamp": trades_with_time,
            "trades_without_timestamp": trades_without_time,
            "daily_buckets": len(daily_list),
            "weekly_buckets": len(weekly_list),
        },
        "all_time": {
            "volume_usdc": money(vol_all),
            "trades": n_all,
            "unique_txs": len(tx_all),
            "unique_users": len(users_all),
        },
        "window": {
            "volume_usdc": money(vol_win),
            "trades": n_win,
            "unique_txs": len(tx_win),
            "unique_users": len(users_win),
        },
        "daily": daily_list,
        "weekly": weekly_list,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Parse query parameters
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)
            hours = int(query_params.get('hours', ['24'])[0])
            
            # Опционально: можем запросить трейды только за определенный период
            # Но API может не поддерживать фильтрацию по времени, поэтому получаем все
            client = init_client_builder_only()
            
            # Получаем все трейды (API может не поддерживать after/before для matchTime)
            trades = fetch_all_builder_trades(client)
            
            data = compute_stats(trades, window_hours=hours)
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e),
                "detail": error_detail
            }, indent=2).encode())