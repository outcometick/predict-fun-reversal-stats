"""Polymarket 5-minute crypto Up/Down markets -> rounds.

Inputs per asset, from the archive layout
(``data/polymarket/daily/<dataset>/<ASSET>-5m/``):

* markets           -- day D and, when present, day D+1 (a slot's row can land
                       in the file of the day it ends)
* best_bid_ask      -- day D, top of book for each token at every update
* last_trade_price  -- day D, trade prints

Bases: ``mid`` = (best bid + best ask) / 2, ``bid`` = best bid, ``trade`` =
trade price; each per token, Up = ``token_ids[0]``, Down = ``token_ids[1]``.
Outcome comes from ``outcome_prices``: ["1","0"] up, ["0","1"] down,
["0.5","0.5"] flat (excluded from the statistics).
"""

from __future__ import annotations

import gzip
import json
import os

from .rounds import Scan, row

BASES = ("mid", "bid", "trade")
VENUE = "polymarket"
ASSETS = ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE")


def _jsonl(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def _price(v):
    """A quoted price strictly inside (0, 1), else None (empty side or junk)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if 0.0 < x < 1.0 else None


def outcome_of(m: dict) -> str:
    if not m.get("resolved"):
        return "unknown"
    op = m.get("outcome_prices")
    if isinstance(op, str):
        try:
            op = json.loads(op)
        except ValueError:
            return "unknown"
    try:
        up, down = (float(x) for x in op)
    except (TypeError, ValueError):
        return "unknown"
    if up == 1 and down == 0:
        return "up"
    if up == 0 and down == 1:
        return "down"
    if up == 0.5 and down == 0.5:
        return "flat"
    return "unknown"


def _path(root, dataset, asset, day):
    s = f"{asset}-5m"
    return os.path.join(root, "data", "polymarket", "daily", dataset, s, f"{s}-{dataset}-{day}.jsonl.gz")


def markets_for(root, asset, day, day_start, next_day):
    """Slots of ``asset`` starting within day D, from D's and D+1's markets
    files. A row with a known outcome wins over one without; the later file
    otherwise wins, being the fresher read."""
    out = {}
    for d in (day, next_day):
        p = _path(root, "markets", asset, d)
        if not os.path.exists(p):
            continue
        for m in _jsonl(p):
            try:
                start, end = int(m["start_sec"]), int(m["end_sec"])
            except (KeyError, TypeError, ValueError):
                continue
            if end - start != 300 or not (day_start <= start < day_start + 86400):
                continue
            ids = m.get("token_ids")
            if isinstance(ids, str):
                ids = json.loads(ids)
            if not isinstance(ids, list) or len(ids) != 2:
                continue
            old = out.get(m["slug"])
            if old is None or outcome_of(m) != "unknown" or outcome_of(old) == "unknown":
                out[m["slug"]] = m
    return out


def extract(root, day, day_start, next_day, assets=ASSETS):
    """Rounds of every asset whose day-D price files exist under ``root``."""
    rows = []
    for asset in assets:
        bba = _path(root, "best_bid_ask", asset, day)
        if not os.path.exists(bba):
            continue
        mk = markets_for(root, asset, day, day_start, next_day)
        side = {}
        for slug, m in mk.items():
            ids = m["token_ids"] if isinstance(m["token_ids"], list) else json.loads(m["token_ids"])
            side[str(ids[0])] = (slug, "up")
            side[str(ids[1])] = (slug, "down")
        scans = {slug: Scan(int(m["start_sec"]) * 1000, int(m["end_sec"]) * 1000) for slug, m in mk.items()}

        for r in _jsonl(bba):
            hit = side.get(str(r.get("asset_id")))
            ts = r.get("event_ts_ms")
            if hit is None or ts is None:
                continue
            p = r.get("payload") or {}
            bid, ask = _price(p.get("best_bid")), _price(p.get("best_ask"))
            slug, s = hit
            sc, ts = scans[slug], int(ts)
            if bid is not None and ask is not None:
                sc.add(ts, "mid", s, (bid + ask) / 2)
            if bid is not None:
                sc.add(ts, "bid", s, bid)

        trades = _path(root, "last_trade_price", asset, day)
        if os.path.exists(trades):
            for r in _jsonl(trades):
                p = r.get("payload") or {}
                hit = side.get(str(r.get("asset_id") or p.get("asset_id")))
                ts = r.get("event_ts_ms")
                px = _price(p.get("price"))
                if hit is None or ts is None or px is None:
                    continue
                scans[hit[0]].add(int(ts), "trade", hit[1], px)

        for slug, m in mk.items():
            scan = scans[slug].result(BASES)
            rows.append(row(VENUE, asset, slug, int(m["start_sec"]), int(m["end_sec"]), outcome_of(m), scan, BASES))
    return rows
