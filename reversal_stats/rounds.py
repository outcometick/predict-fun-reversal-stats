"""One row per market ("round"): its outcome and, for every price basis and
threshold, the first moment either side's price reached that threshold.

Everything in results/ is aggregated from these rows, so they are the facts a
reader can re-check or re-slice with other thresholds.

Definitions:

* window   -- events with ``start_ms <= ts < end_ms``; anything else is ignored.
* trigger  -- for basis ``b`` and threshold ``t``, the first in-window event
              whose price on basis ``b`` is ``>= t``, on either side. The side
              that crossed is the *favourite*.
* reversal -- the favourite lost: the market settled for the other side.
* peak     -- the highest mid each side reached in the window.
"""

from __future__ import annotations

import csv
import gzip
import io
import os

THRESHOLDS = (0.90, 0.93, 0.95, 0.98, 0.99)
SIDES = ("up", "down")

# Prices are decimal strings on the wire; a mid of 0.94 and 0.96 is
# 0.9500000000000001 or 0.9499999999999999 in binary. Compare with slack far
# below the 0.001 tick so a quoted 0.95 counts as reaching 0.95.
EPS = 1e-9


def tkey(t: float) -> str:
    """Column key of a threshold: 0.9 -> "90", 0.995 -> "99.5"."""
    s = f"{t * 100:.1f}"
    return s[:-2] if s.endswith(".0") else s


def columns(bases) -> list[str]:
    cols = ["venue", "asset", "slug", "start_sec", "end_sec", "outcome", "samples", "peak_up", "peak_down"]
    for b in bases:
        for t in THRESHOLDS:
            k = f"{b}_{tkey(t)}"
            cols += [f"{k}_side", f"{k}_ts_ms", f"{k}_px"]
    return cols


class Scan:
    """Per-market accumulator, fed events in any order, in fixed memory.

    The trigger for ``(basis, t)`` is the earliest event, by ``(ts, arrival
    order)``, whose price is ``>= t``; so only that one candidate per pair is
    kept. Sample count and peaks do not depend on order either.
    """

    __slots__ = ("start_ms", "end_ms", "samples", "peak", "best", "seq")

    def __init__(self, start_ms: int, end_ms: int):
        self.start_ms, self.end_ms = start_ms, end_ms
        self.samples = 0
        self.peak = {"up": None, "down": None}
        self.best = {}   # (basis, t) -> (ts, seq, side, px)
        self.seq = 0

    def add(self, ts: int, basis: str, side: str, px: float) -> None:
        if ts < self.start_ms or ts >= self.end_ms:
            return
        if basis == "mid":
            self.samples += 1
            if self.peak[side] is None or px > self.peak[side]:
                self.peak[side] = px
        seq = self.seq
        self.seq += 1
        for t in THRESHOLDS:
            if px < t - EPS:
                break
            cur = self.best.get((basis, t))
            if cur is None or (ts, seq) < (cur[0], cur[1]):
                self.best[(basis, t)] = (ts, seq, side, px)

    def result(self, bases) -> dict:
        """``{"samples", "peak_up", "peak_down", "hits"}``; ``hits`` maps
        ``(basis, threshold)`` to ``(side, ts_ms, price)``."""
        hits = {k: (v[2], v[0], v[3]) for k, v in self.best.items() if k[0] in bases}
        return {"samples": self.samples, "peak_up": self.peak["up"], "peak_down": self.peak["down"], "hits": hits}


def detect(events, start_ms: int, end_ms: int, bases) -> dict:
    """Scan ``(ts_ms, basis, side, price)`` events of one market (any order)."""
    sc = Scan(start_ms, end_ms)
    for ts, basis, side, px in events:
        if basis in bases:
            sc.add(ts, basis, side, px)
    return sc.result(bases)


def fmt(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.6f}".rstrip("0").rstrip(".") or "0"
    return str(x)


def row(venue, asset, slug, start_sec, end_sec, outcome, scan, bases) -> dict:
    r = {
        "venue": venue, "asset": asset, "slug": slug,
        "start_sec": start_sec, "end_sec": end_sec, "outcome": outcome,
        "samples": scan["samples"], "peak_up": fmt(scan["peak_up"]), "peak_down": fmt(scan["peak_down"]),
    }
    for b in bases:
        for t in THRESHOLDS:
            k = f"{b}_{tkey(t)}"
            h = scan["hits"].get((b, t))
            r[f"{k}_side"] = h[0] if h else ""
            r[f"{k}_ts_ms"] = h[1] if h else ""
            r[f"{k}_px"] = fmt(h[2]) if h else ""
    return r


def write_rounds(path: str, rows, bases) -> None:
    """Write rows sorted by (asset, start_sec) as gzip CSV with a fixed mtime,
    so an unchanged day produces byte-identical output and no git diff."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns(bases), lineterminator="\n")
    w.writeheader()
    for r in sorted(rows, key=lambda r: (r["asset"], int(r["start_sec"]), r["slug"])):
        w.writerow({k: fmt(v) if not isinstance(v, str) else v for k, v in r.items()})
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
            gz.write(buf.getvalue().encode("utf-8"))
    os.replace(tmp, path)  # an interrupted run never leaves a truncated day


def read_rounds(path: str) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))
