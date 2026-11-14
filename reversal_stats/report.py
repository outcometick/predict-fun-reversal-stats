"""rounds/*.csv.gz -> results/*.csv (+ the numbers the README shows).

Only settled rounds (outcome up or down) enter a statistic; flat and unknown
rounds are counted in data_quality.csv and nowhere else. Every breakdown
except by_price_basis.csv uses the mid basis.
"""

from __future__ import annotations

import csv
import datetime as dt
import glob
import math
import os
from collections import defaultdict

from .rounds import THRESHOLDS, read_rounds, tkey

MAIN = "mid"
ALL = "ALL"
STC_BUCKETS = ((0, 15), (15, 30), (30, 60), (60, 120), (120, 300))
PEAKS = (0.90, 0.93, 0.95, 0.98, 0.99, 0.995)


def wilson(k: int, n: int, z: float = 1.959963984540054):
    """95% Wilson score interval for k successes in n, as fractions."""
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def pct(x, digits=3):
    return "" if x is None else f"{100 * x:.{digits}f}"


def rate(k, n):
    return k / n if n else None


def day_of(start_sec) -> str:
    return dt.datetime.fromtimestamp(int(start_sec), dt.timezone.utc).strftime("%Y-%m-%d")


def load(rounds_dir: str):
    """Rounds of every day, one day file in memory at a time."""
    for p in sorted(glob.glob(os.path.join(rounds_dir, "*.csv.gz"))):
        for r in read_rounds(p):
            r["date"] = day_of(r["start_sec"])
            yield r


def bases_of(row) -> list[str]:
    return [c[: -len("_90_side")] for c in row if c.endswith("_90_side")]


def trig(r, basis, t):
    """(side, ts_ms, px) of a round's trigger, or None."""
    k = f"{basis}_{tkey(t)}"
    side = r.get(f"{k}_side")
    if not side:
        return None
    return side, int(r[f"{k}_ts_ms"]), float(r[f"{k}_px"])


class Tally:
    __slots__ = ("n", "k", "px")

    def __init__(self):
        self.n = self.k = 0
        self.px = 0.0

    def add(self, reversed_, px):
        self.n += 1
        self.k += reversed_
        self.px += px


def stc_bucket(seconds_left: float):
    """Bucket label for seconds from the trigger to the close. A trigger at the
    open itself (exactly 300 s left) belongs to the last bucket."""
    for lo, hi in STC_BUCKETS:
        if lo <= seconds_left < hi or (hi == STC_BUCKETS[-1][1] and seconds_left == hi):
            return f"{lo}-{hi}"
    return None


def _write(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    os.replace(tmp, path)


def summarise(rows):
    """Compute every table in ONE pass over ``rows`` (any iterable), holding
    only counters -- memory does not grow with the length of the history.
    Returns {name: (header, rows)} plus 'meta'."""
    bases = None
    per_day = defaultdict(Tally)       # (date, asset, t) -> mid tally
    per_basis = defaultdict(Tally)     # (basis, asset, t)
    per_hour = defaultdict(Tally)      # (hour, asset, t)
    per_stc = defaultdict(Tally)       # (bucket, asset, t)
    loser = defaultdict(int)           # (asset, peak) -> rounds
    settled_n = defaultdict(int)       # asset -> settled rounds
    days_of = defaultdict(set)         # asset -> dates with a settled round
    rounds_n = defaultdict(int)        # (date, asset)
    settled_d = defaultdict(int)       # (date, asset)
    quality = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    asset_set, day_set = set(), set()
    total = settled_total = 0

    for r in rows:
        if bases is None:
            bases = bases_of(r)
        total += 1
        a, d, out = r["asset"], r["date"], r["outcome"]
        asset_set.add(a)
        day_set.add(d)
        samples = int(r["samples"] or 0)
        q = quality[(d, a)]
        q[0] += 1
        q[1] += out in ("up", "down")
        q[2] += out == "flat"
        q[3] += out == "unknown"
        q[4] += samples == 0
        q[5] += samples
        for x in (a, ALL):
            rounds_n[(d, x)] += 1
        if out not in ("up", "down"):
            continue
        settled_total += 1
        hour = dt.datetime.fromtimestamp(int(r["start_sec"]), dt.timezone.utc).hour
        end_ms = int(r["end_sec"]) * 1000
        lpeak = r["peak_down"] if out == "up" else r["peak_up"]
        lpeak = float(lpeak) if lpeak != "" else None
        for x in (a, ALL):
            settled_n[x] += 1
            settled_d[(d, x)] += 1
            days_of[x].add(d)
            for p in PEAKS:
                if lpeak is not None and lpeak >= p - 1e-9:
                    loser[(x, p)] += 1
        for b in bases:
            for t in THRESHOLDS:
                h = trig(r, b, t)
                if h is None:
                    continue
                rev = h[0] != out
                for x in (a, ALL):
                    per_basis[(b, x, t)].add(rev, h[2])
                    if b == MAIN:
                        per_day[(d, x, t)].add(rev, h[2])
                        per_hour[(hour, x, t)].add(rev, h[2])
                        bucket = stc_bucket((end_ms - h[1]) / 1000)
                        if bucket is not None:
                            per_stc[(bucket, x, t)].add(rev, h[2])

    bases = bases or [MAIN]
    assets = [ALL] + sorted(asset_set, key=lambda x: (x != "BTC", x))
    days = sorted(day_set)
    tables = {}

    summary = []
    for a in assets:
        nd = len(days_of[a])
        for t in THRESHOLDS:
            tl = [x for x in (per_day.get((d, a, t)) for d in sorted(days_of[a])) if x]
            n = sum(x.n for x in tl)
            k = sum(x.k for x in tl)
            pxs = sum(x.px for x in tl)
            lo, hi = wilson(k, n)
            win = rate(n - k, n)
            avg = pxs / n if n else None
            summary.append([
                a, tkey(t), settled_n[a], n, k, pct(rate(k, n)), pct(lo), pct(hi),
                pct(win), "" if avg is None else f"{avg:.4f}",
                "" if avg is None else f"{100 * (win - avg):.3f}",
                nd, f"{n / nd:.2f}" if nd else "", f"{k / nd:.2f}" if nd else "",
                sum(1 for x in tl if x.k), max((x.k for x in tl), default=0),
            ])
    tables["summary"] = ([
        "asset", "threshold_pct", "settled_rounds", "triggered", "reversed", "reversal_rate_pct",
        "wilson95_low_pct", "wilson95_high_pct", "favourite_win_rate_pct", "avg_trigger_price",
        "win_rate_minus_price_pp", "days", "triggered_per_day", "reversed_per_day",
        "days_with_reversal", "max_reversed_in_a_day",
    ], summary)

    basis_rows = []
    for b in bases:
        for a in assets:
            for t in THRESHOLDS:
                x = per_basis.get((b, a, t)) or Tally()
                lo, hi = wilson(x.k, x.n)
                avg = x.px / x.n if x.n else None
                win = rate(x.n - x.k, x.n)
                basis_rows.append([
                    a, tkey(t), b, x.n, x.k, pct(rate(x.k, x.n)), pct(lo), pct(hi),
                    "" if avg is None else f"{avg:.4f}",
                    "" if avg is None else f"{100 * (win - avg):.3f}",
                ])
    tables["by_price_basis"] = ([
        "asset", "threshold_pct", "basis", "triggered", "reversed", "reversal_rate_pct",
        "wilson95_low_pct", "wilson95_high_pct", "avg_trigger_price", "win_rate_minus_price_pp",
    ], basis_rows)

    daily = []
    for d in days:
        for a in assets:
            if not rounds_n.get((d, a)):
                continue
            for t in THRESHOLDS:
                x = per_day.get((d, a, t)) or Tally()
                daily.append([d, a, tkey(t), rounds_n[(d, a)], settled_d[(d, a)], x.n, x.k, pct(rate(x.k, x.n))])
    tables["daily"] = (["date", "asset", "threshold_pct", "rounds", "settled_rounds", "triggered", "reversed", "reversal_rate_pct"], daily)

    def period_table(keyfn):
        days_in = defaultdict(list)
        for d in days:
            days_in[keyfn(d)].append(d)
        out = []
        for key in sorted(days_in):
            ds = days_in[key]
            for a in assets:
                for t in THRESHOLDS:
                    n = k = 0
                    for d in ds:
                        x = per_day.get((d, a, t))
                        if x:
                            n += x.n
                            k += x.k
                    if n:
                        out.append([key, ds[0], ds[-1], len(ds), a, tkey(t), n, k, pct(rate(k, n))])
        return out

    def week(d):
        x = dt.date.fromisoformat(d)
        return (x - dt.timedelta(days=x.weekday())).isoformat()

    tables["weekly"] = (
        ["week_start", "first_day", "last_day", "days", "asset", "threshold_pct", "triggered", "reversed", "reversal_rate_pct"],
        period_table(week),
    )
    tables["monthly"] = (
        ["month", "first_day", "last_day", "days", "asset", "threshold_pct", "triggered", "reversed", "reversal_rate_pct"],
        period_table(lambda d: d[:7]),
    )

    tables["by_hour_utc"] = (
        ["asset", "threshold_pct", "hour_utc", "triggered", "reversed", "reversal_rate_pct"],
        [[a, tkey(t), hour, x.n, x.k, pct(rate(x.k, x.n))]
         for a in assets for t in THRESHOLDS for hour in range(24)
         for x in [per_hour.get((hour, a, t)) or Tally()]],
    )
    tables["by_seconds_to_close"] = (
        ["asset", "threshold_pct", "seconds_to_close", "triggered", "reversed", "reversal_rate_pct"],
        [[a, tkey(t), f"{lo}-{hi}", x.n, x.k, pct(rate(x.k, x.n))]
         for a in assets for t in THRESHOLDS for lo, hi in STC_BUCKETS
         for x in [per_stc.get((f"{lo}-{hi}", a, t)) or Tally()]],
    )
    tables["by_loser_peak"] = (
        ["asset", "loser_peak_at_least_pct", "settled_rounds", "rounds", "share_pct"],
        [[a, tkey(p), settled_n[a], loser[(a, p)], pct(rate(loser[(a, p)], settled_n[a]))] for a in assets for p in PEAKS],
    )
    tables["data_quality"] = (
        ["date", "asset", "rounds", "settled_rounds", "flat_rounds", "unknown_outcome_rounds", "rounds_without_mid_quotes", "mid_quotes_in_window"],
        [[d, a] + quality[(d, a)] for d, a in sorted(quality, key=lambda k: (k[0], k[1] != "BTC", k[1]))],
    )
    tables["meta"] = {
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
        "days": len(days),
        "rounds": total,
        "settled_rounds": settled_total,
        "assets": assets[1:],
        "bases": bases,
    }
    return tables


def write_results(tables, out_dir):
    for name, v in tables.items():
        if name == "meta":
            continue
        header, rows = v
        _write(os.path.join(out_dir, "results", f"{name}.csv"), header, rows)
