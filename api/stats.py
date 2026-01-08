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
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
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


def get_builder_trades_call(client: ClobClient, params: Optional[Dict[str, str]]) -> Any:
    if hasattr(client, "get_builder_trades"):
        return client.get_builder_trades(params if params else None)
    if hasattr(client, "getBuilderTrades"):
        return client.getBuilderTrades(params if params else None)
    raise RuntimeError("No get_builder_trades/getBuilderTrades on this client")


def fetch_all_builder_trades(
    client: ClobClient,
    after: Optional[str] = None,
    before: Optional[str] = None,
    max_iterations: int = 2000,
) -> List[Dict[str, Any]]:
    """
    Pagination per docs:
      - response has next_cursor
      - pass it back as params['id']
    Time filters:
      - after / before (strings per API docs)
    """
    all_trades: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        params: Dict[str, str] = {}

        if cursor:
            params["id"] = cursor
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        resp = get_builder_trades_call(client, params if params else None)
        trades, next_cursor = normalize_builder_trades_response(resp)

        # ВАЖНО: не выходим просто потому что trades пустой — ориентируемся на next_cursor
        if trades:
            all_trades.extend(trades)

        if not next_cursor:
            break
        cursor = next_cursor

    return all_trades


def iso_week_key(dt: datetime) -> str:
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def compute_all_time(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    vol_all = Decimal("0")
    n_all = 0
    tx_all: Set[str] = set()
    users_all: Set[str] = set()

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

    def money(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    return {
        "volume_usdc": money(vol_all),
        "trades": n_all,
        "unique_txs": len(tx_all),
        "unique_users": len(users_all),
    }


def compute_window(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Тут уже trades приходят ОТФИЛЬТРОВАННЫЕ по after/before
    vol = Decimal("0")
    n = 0
    txs: Set[str] = set()
    users: Set[str] = set()

    for t in trades:
        n += 1
        vol += to_decimal(t.get("sizeUsdc") or t.get("size_usdc") or "0")

        txh = (t.get("transactionHash") or t.get("transaction_hash") or "").strip()
        if txh:
            txs.add(txh)

        owner = (t.get("owner") or "").strip().lower()
        if owner:
            users.add(owner)

    def money(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    return {
        "volume_usdc": money(vol),
        "trades": n,
        "unique_txs": len(txs),
        "unique_users": len(users),
        "total_trades_fetched": len(trades),
    }


def compute_daily_weekly_from_trades(trades: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Делает daily/weekly по matchTime. Эти trades мы будем брать за последние 7 дней через after.
    """
    daily: Dict[str, Dict[str, Any]] = {}
    weekly: Dict[str, Dict[str, Any]] = {}

    for t in trades:
        size_usdc = to_decimal(t.get("sizeUsdc") or t.get("size_usdc") or "0")
        txh = (t.get("transactionHash") or t.get("transaction_hash") or "").strip()
        owner = (t.get("owner") or "").strip().lower()

        mt = parse_match_time(t.get("matchTime") or t.get("match_time"))
        if not mt:
            # если matchTime вдруг отсутствует — пропускаем в разбиении (но окно/общее уже посчитаны)
            continue

        day = mt.date().isoformat()
        wk = iso_week_key(mt)

        if day not in daily:
            daily[day] = {"date": day, "volume_usdc": Decimal("0"), "trades": 0, "unique_users": set(), "unique_txs": set()}
        daily[day]["volume_usdc"] += size_usdc
        daily[day]["trades"] += 1
        if owner:
            daily[day]["unique_users"].add(owner)
        if txh:
            daily[day]["unique_txs"].add(txh)

        if wk not in weekly:
            weekly[wk] = {"week": wk, "volume_usdc": Decimal("0"), "trades": 0, "unique_users": set(), "unique_txs": set()}
        weekly[wk]["volume_usdc"] += size_usdc
        weekly[wk]["trades"] += 1
        if owner:
            weekly[wk]["unique_users"].add(owner)
        if txh:
            weekly[wk]["unique_txs"].add(txh)

    def money(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    daily_list = sorted(daily.values(), key=lambda x: x["date"], reverse=True)
    weekly_list = sorted(weekly.values(), key=lambda x: x["week"], reverse=True)

    for row in daily_list:
        row["unique_users"] = len(row["unique_users"])
        row["unique_txs"] = len(row["unique_txs"])
        row["volume_usdc"] = money(row["volume_usdc"])
    for row in weekly_list:
        row["unique_users"] = len(row["unique_users"])
        row["unique_txs"] = len(row["unique_txs"])
        row["volume_usdc"] = money(row["volume_usdc"])

    return daily_list, weekly_list


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)

            hours = int(query_params.get("hours", ["24"])[0])

            now = datetime.now(timezone.utc)

            # ✅ строго по докам: after/before — строки
            after_24h = (now - timedelta(hours=hours)).isoformat()
            after_7d = (now - timedelta(days=7)).isoformat()

            client = init_client_builder_only()

            # 1) ALL TIME — как было, без after/before
            trades_all = fetch_all_builder_trades(client)
            all_time = compute_all_time(trades_all)

            # 2) WINDOW (24h или сколько указал) — только через after
            trades_24h = fetch_all_builder_trades(client, after=after_24h)
            window = compute_window(trades_24h)

            # 3) WEEK (последние 7 дней) — тоже через after
            trades_7d = fetch_all_builder_trades(client, after=after_7d)
            week = compute_window(trades_7d)  # те же метрики, но за 7 дней

            # 4) DAILY/WEEKLY breakdown — строим из trades_7d
            daily_list, weekly_list = compute_daily_weekly_from_trades(trades_7d)

            data = {
                "generated_at_utc": now.isoformat(),
                "window_hours": hours,
                "window_start_utc": (now - timedelta(hours=hours)).isoformat(),
                "window_end_utc": now.isoformat(),

                "all_time": all_time,

                "last_24h": window,        # метрики за hours
                "last_7d": week,           # метрики за 7 дней

                "daily": daily_list,
                "weekly": weekly_list,

                # отладка, можно потом убрать:
                "debug": {
                    "trades_all_fetched": len(trades_all),
                    "trades_24h_fetched": len(trades_24h),
                    "trades_7d_fetched": len(trades_7d),
                    "after_24h": after_24h,
                    "after_7d": after_7d,
                }
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "error": str(e),
                "detail": error_detail
            }, indent=2).encode())
