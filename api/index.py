import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import Flask, jsonify, request
from dotenv import load_dotenv

from py_clob_client.client import ClobClient
from py_builder_signing_sdk.config import BuilderConfig, BuilderApiKeyCreds

app = Flask(__name__)
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


def fetch_all_builder_trades(client: ClobClient, after: Optional[str] = None, before: Optional[str] = None) -> List[Dict[str, Any]]:
    all_trades: List[Dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        params: Dict[str, str] = {}
        if cursor:
            params["id"] = cursor
        if after:
            params["after"] = after
        if before:
            params["before"] = before

        resp = get_builder_trades_call(client, params if params else None)
        trades, next_cursor = normalize_builder_trades_response(resp)
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

    # daily/weekly buckets
    daily: Dict[str, Dict[str, Any]] = {}
    weekly: Dict[str, Dict[str, Any]] = {}

    for t in trades:
        n_all += 1
        size_usdc = to_decimal(t.get("sizeUsdc"))
        vol_all += size_usdc

        txh = (t.get("transactionHash") or "").strip()
        if txh:
            tx_all.add(txh)

        owner = (t.get("owner") or "").strip().lower()
        if owner:
            users_all.add(owner)

        mt = parse_match_time(t.get("matchTime"))
        if not mt:
            continue

        day = mt.date().isoformat()  # UTC day
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

    # window (optional)
    vol_win = Decimal("0")
    n_win = 0
    tx_win: Set[str] = set()
    users_win: Set[str] = set()
    for t in trades:
        mt = parse_match_time(t.get("matchTime"))
        if not mt or mt < start:
            continue
        n_win += 1
        vol_win += to_decimal(t.get("sizeUsdc"))
        txh = (t.get("transactionHash") or "").strip()
        if txh:
            tx_win.add(txh)
        owner = (t.get("owner") or "").strip().lower()
        if owner:
            users_win.add(owner)

    def money(x: Decimal) -> str:
        return str(x.quantize(Decimal("0.01")))

    daily_list = sorted(daily.values(), key=lambda x: x["date"])
    weekly_list = sorted(weekly.values(), key=lambda x: x["week"])

    # normalize sets -> counts + stringify decimals
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


@app.get("/stats")
def stats():
    # ?hours=24 (optional)
    hours = int(request.args.get("hours", "24"))
    client = init_client_builder_only()
    trades = fetch_all_builder_trades(client)
    data = compute_stats(trades, window_hours=hours)
    return jsonify(data)
