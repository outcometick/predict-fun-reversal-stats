"""Predict.fun 5-minute crypto Up/Down markets -> rounds.

Inputs, from the archive layout (``data/predict-fun/``):

* markets/predict-markets-<day>.jsonl.gz    -- day D and, when present, D+1
* orderbook/<ASSET>-5M/...-<day>.jsonl.gz   -- day D, full book snapshots

Each market has ONE book, the Up ladder; Down is its mirror (a Down bid at
``1 - p`` is an Up ask at ``p``). Bases: ``mid`` and ``bid`` only -- Predict.fun
publishes no trade tape. Outcome: ``end_price`` vs ``start_price``; equal is a
push (both sides refunded), reported as ``flat`` and excluded like Polymarket's
flat slots. A market without ``end_price`` has no outcome yet (``status`` is
not a settlement flag).
"""

from __future__ import annotations

import gzip
import json
import os
from decimal import Decimal, InvalidOperation

from .rounds import Scan, row

BASES = ("mid", "bid")
VENUE = "predict"
ASSETS = ("BTC", "ETH", "BNB")


def _jsonl(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def outcome_of(m: dict) -> str:
    try:
        start, end = Decimal(str(m["start_price"])), Decimal(str(m["end_price"]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return "unknown"
    if m.get("end_price") in (None, "") or m.get("start_price") in (None, ""):
        return "unknown"
    if end > start:
        return "up"
    if end < start:
        return "down"
    return "flat"


def _best(levels, pick):
    """Best price of a ``[[price, size], ...]`` ladder, ignoring empty levels
    and prices outside (0, 1); None when nothing usable is left."""
    best = None
    for lv in levels or ():
        try:
            p, size = float(lv[0]), float(lv[1])
        except (TypeError, ValueError, IndexError):
            continue
        if size <= 0 or not (0.0 < p < 1.0):
            continue
        if best is None or pick(p, best):
            best = p
    return best


def markets_for(root, day, day_start, next_day):
    out = {}
    for d in (day, next_day):
        p = os.path.join(root, "data", "predict-fun", "markets", f"predict-markets-{d}.jsonl.gz")
        if not os.path.exists(p):
            continue
        for m in _jsonl(p):
            try:
                start, end, mid = int(m["start_sec"]), int(m["end_sec"]), int(m["market_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if end - start != 300 or not (day_start <= start < day_start + 86400):
                continue
            old = out.get(mid)
            if old is None or outcome_of(m) != "unknown" or outcome_of(old) == "unknown":
                out[mid] = m
    return out


def extract(root, day, day_start, next_day, assets=ASSETS):
    rows = []
    mk = markets_for(root, day, day_start, next_day)
    for asset in assets:
        ob = os.path.join(root, "data", "predict-fun", "orderbook", f"{asset}-5M", f"{asset}-5M-predict-orderbook-{day}.jsonl.gz")
        if not os.path.exists(ob):
            continue
        mine = {mid: m for mid, m in mk.items() if str(m.get("asset", "")).upper() == asset}
        scans = {mid: Scan(int(m["start_sec"]) * 1000, int(m["end_sec"]) * 1000) for mid, m in mine.items()}
        for r in _jsonl(ob):
            try:
                mid = int(r["market_id"])
            except (KeyError, TypeError, ValueError):
                continue
            sc = scans.get(mid)
            ts = r.get("update_ts_ms")
            if sc is None or ts is None:
                continue
            p = r.get("payload") or {}
            bb = _best(p.get("bids"), lambda a, b: a > b)
            ba = _best(p.get("asks"), lambda a, b: a < b)
            ts = int(ts)
            if bb is not None and ba is not None:
                m = (bb + ba) / 2
                sc.add(ts, "mid", "up", m)
                sc.add(ts, "mid", "down", 1 - m)
            if bb is not None:
                sc.add(ts, "bid", "up", bb)
            if ba is not None:
                sc.add(ts, "bid", "down", 1 - ba)
        for mid, m in mine.items():
            scan = scans[mid].result(BASES)
            slug = m.get("category_slug") or str(mid)
            rows.append(row(VENUE, asset, slug, int(m["start_sec"]), int(m["end_sec"]), outcome_of(m), scan, BASES))
    return rows
