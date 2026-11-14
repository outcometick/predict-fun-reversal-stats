"""Hand-computed checks for reversal_stats. Run: python -m unittest discover -s tests"""

import csv
import datetime as dt
import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reversal_stats import __main__ as cli  # noqa: E402
from reversal_stats import polymarket, predict, report  # noqa: E402
from reversal_stats.rounds import detect, read_rounds, tkey  # noqa: E402

DAY = "2026-11-09"
NEXT = "2026-11-10"
D0 = int(dt.datetime(2026, 11, 9, tzinfo=dt.timezone.utc).timestamp())


def gz(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def pm_market(start, outcome, tok):
    return {"slug": f"btc-updown-5m-{start}", "start_sec": start, "end_sec": start + 300, "interval_sec": 300,
            "token_ids": [f"{tok}u", f"{tok}d"], "resolved": outcome is not None,
            "outcome_prices": outcome or ["0.5", "0.5"]}


def bba(slug, tok, ts, bid, ask):
    return {"slug": slug, "asset_id": tok, "event_type": "best_bid_ask", "event_ts_ms": ts, "recv_ms": ts + 5,
            "payload": {"best_bid": bid, "best_ask": ask, "asset_id": tok}}


def trade(slug, tok, ts, px):
    return {"slug": slug, "asset_id": tok, "event_ts_ms": ts, "payload": {"price": px, "asset_id": tok, "side": "BUY", "size": "1"}}


class DetectTest(unittest.TestCase):
    def test_first_crossing_per_threshold_and_window(self):
        ev = [
            (999, "mid", "up", 0.99),        # before the window: ignored
            (1000, "mid", "up", 0.91),
            (1500, "mid", "down", 0.95),     # down reaches 93 and 95 first
            (1600, "mid", "up", 0.995),      # up reaches 98 and 99
            (2000, "mid", "down", 0.999),    # at end_ms: outside
        ]
        s = detect(ev, 1000, 2000, ("mid",))
        h = s["hits"]
        self.assertEqual(h[("mid", 0.90)], ("up", 1000, 0.91))
        self.assertEqual(h[("mid", 0.93)], ("down", 1500, 0.95))
        self.assertEqual(h[("mid", 0.95)], ("down", 1500, 0.95))
        self.assertEqual(h[("mid", 0.98)], ("up", 1600, 0.995))
        self.assertEqual(h[("mid", 0.99)], ("up", 1600, 0.995))
        self.assertEqual((s["peak_up"], s["peak_down"], s["samples"]), (0.995, 0.95, 3))

    def test_binary_rounding_still_counts_as_reached(self):
        s = detect([(0, "mid", "up", (0.94 + 0.96) / 2)], 0, 10, ("mid",))
        self.assertIn(("mid", 0.95), s["hits"])

    def test_order_independent_and_ties_go_to_arrival_order(self):
        ev = [(1500, "mid", "down", 0.97), (1200, "mid", "up", 0.99), (1200, "mid", "down", 0.99),
              (1100, "mid", "up", 0.92)] + [(1300 + i, "mid", "up", 0.995) for i in range(1000)]
        h = detect(ev, 1000, 2000, ("mid",))["hits"]
        self.assertEqual(h[("mid", 0.90)], ("up", 1100, 0.92))
        self.assertEqual(h[("mid", 0.95)], ("up", 1200, 0.99))       # same ts as down: up arrived first
        self.assertEqual(h[("mid", 0.99)], ("up", 1200, 0.99))
        self.assertEqual(len(detect(ev, 1000, 2000, ("mid",))["hits"]), 5)

    def test_threshold_keys(self):
        self.assertEqual([tkey(t) for t in (0.9, 0.93, 0.995)], ["90", "93", "99.5"])


class PolymarketTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        base = os.path.join(self.root, "data", "polymarket", "daily")
        s1, s2, s3 = D0, D0 + 300, D0 + 86400 - 300     # s3 = last slot of the day
        m1, m2, m3 = pm_market(s1, ["1", "0"], "a"), pm_market(s2, ["0", "1"], "b"), pm_market(s3, None, "c")
        prev = pm_market(D0 - 300, ["1", "0"], "z")                    # starts the day before: excluded
        gz(f"{base}/markets/BTC-5m/BTC-5m-markets-{DAY}.jsonl.gz", [prev, m1, m2, m3])
        # m3's outcome only arrives in the next day's file
        gz(f"{base}/markets/BTC-5m/BTC-5m-markets-{NEXT}.jsonl.gz", [pm_market(s3, ["0", "1"], "c")])
        t1, t2, t3 = s1 * 1000, s2 * 1000, s3 * 1000
        gz(f"{base}/best_bid_ask/BTC-5m/BTC-5m-best_bid_ask-{DAY}.jsonl.gz", [
            # m1: up mid 0.95 at +10s; written out of order on purpose
            bba(m1["slug"], "au", t1 + 20_000, "0.97", "0.99"),
            bba(m1["slug"], "au", t1 + 10_000, "0.94", "0.96"),
            bba(m1["slug"], "ad", t1 + 30_000, "0", "1"),            # empty book: no mid, no bid
            # m2: up mid 0.92 then down wins -> reversal at 90
            bba(m2["slug"], "bu", t2 + 5_000, "0.91", "0.93"),
            bba(m2["slug"], "bd", t2 + 200_000, "0.98", "0.99"),
            # m3: one-sided book (no ask): bid basis only
            bba(m3["slug"], "cd", t3 + 290_000, "0.99", ""),
        ])
        gz(f"{base}/last_trade_price/BTC-5m/BTC-5m-last_trade_price-{DAY}.jsonl.gz", [
            trade(m1["slug"], "au", t1 + 15_000, "0.96"),
            trade(m2["slug"], "bu", t2 + 299_999, "0.99"),             # trade basis: up at 99, lost
        ])

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_rounds(self):
        rows = {r["slug"][-10:]: r for r in polymarket.extract(self.root, DAY, D0, NEXT)}
        self.assertEqual(len(rows), 3)
        r1, r2, r3 = rows[str(D0)], rows[str(D0 + 300)], rows[str(D0 + 86100)]
        self.assertEqual(r1["outcome"], "up")
        self.assertEqual((r1["mid_95_side"], r1["mid_95_ts_ms"]), ("up", D0 * 1000 + 10_000))
        self.assertEqual((r1["mid_98_side"], r1["mid_98_px"]), ("up", "0.98"))
        self.assertEqual(r1["bid_95_ts_ms"], D0 * 1000 + 20_000)
        self.assertEqual(r1["trade_95_px"], "0.96")
        self.assertEqual((r1["samples"], r1["peak_down"]), (2, ""))
        self.assertEqual((r2["outcome"], r2["mid_90_side"], r2["mid_95_side"]), ("down", "up", "down"))
        self.assertEqual(r2["trade_99_side"], "up")
        self.assertEqual(r3["outcome"], "down")                         # from the next day's file
        self.assertEqual((r3["mid_90_side"], r3["bid_99_side"]), ("", "down"))

    def test_extract_then_report(self):
        out = tempfile.mkdtemp()
        try:
            cli.main(["extract", "--venue", "polymarket", "--data", self.root, "--day", DAY, "--out", os.path.join(out, "rounds")])
            rows = read_rounds(os.path.join(out, "rounds", f"{DAY}.csv.gz"))
            self.assertEqual(len(rows), 3)
            cli.main(["report", "--venue", "polymarket", "--rounds", os.path.join(out, "rounds"), "--out", out])
            with open(os.path.join(out, "results", "summary.csv"), encoding="utf-8") as f:
                s = {(r["asset"], r["threshold_pct"]): r for r in csv.DictReader(f)}
            # 90%: m1 (up, won), m2 (up, lost) -> 2 triggers, 1 reversal
            self.assertEqual((s[("ALL", "90")]["triggered"], s[("ALL", "90")]["reversed"]), ("2", "1"))
            self.assertEqual(s[("ALL", "90")]["reversal_rate_pct"], "50.000")
            self.assertEqual(s[("BTC", "90")]["avg_trigger_price"], f"{(0.95 + 0.92) / 2:.4f}")
            # 95%: m1 up (won), m2 down (won) -> 0 reversals
            self.assertEqual((s[("ALL", "95")]["triggered"], s[("ALL", "95")]["reversed"]), ("2", "0"))
            with open(os.path.join(out, "results", "by_price_basis.csv"), encoding="utf-8") as f:
                b = {(r["asset"], r["threshold_pct"], r["basis"]): r for r in csv.DictReader(f)}
            # trade 99: only m2's 0.99 print, up lost
            self.assertEqual((b[("ALL", "99", "trade")]["triggered"], b[("ALL", "99", "trade")]["reversed"]), ("1", "1"))
            # bid 99: m3 down at 0.99, won
            self.assertEqual((b[("ALL", "99", "bid")]["triggered"], b[("ALL", "99", "bid")]["reversed"]), ("1", "0"))
            with open(os.path.join(out, "results", "by_seconds_to_close.csv"), encoding="utf-8") as f:
                sc = {(r["asset"], r["threshold_pct"], r["seconds_to_close"]): r for r in csv.DictReader(f)}
            # m1 reached 95 with 290 s left, m2 with 100 s left
            self.assertEqual((sc[("ALL", "95", "120-300")]["triggered"], sc[("ALL", "95", "60-120")]["triggered"]), ("1", "1"))
            with open(os.path.join(out, "results", "by_loser_peak.csv"), encoding="utf-8") as f:
                lp = {(r["asset"], r["loser_peak_at_least_pct"]): r for r in csv.DictReader(f)}
            # m2: up (loser) peaked at mid 0.92
            self.assertEqual((lp[("ALL", "90")]["rounds"], lp[("ALL", "93")]["rounds"]), ("1", "0"))
            for fn in ("README.md", "README.zh-CN.md", "charts/calibration.svg", "charts/weekly.svg"):
                self.assertTrue(os.path.getsize(os.path.join(out, fn)) > 0, fn)
            with open(os.path.join(out, "README.md"), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("predict-fun-reversal-stats", text)
            self.assertIn("a book with no ask is skipped rather than priced as 1.0", text)
            with open(os.path.join(out, "README.zh-CN.md"), encoding="utf-8") as f:
                self.assertIn("没有卖单的盘口直接跳过，不按 1.0 算", f.read())
        finally:
            shutil.rmtree(out)

    def test_rounds_file_is_byte_stable(self):
        out = tempfile.mkdtemp()
        try:
            p = os.path.join(out, "a.csv.gz")
            q = os.path.join(out, "b.csv.gz")
            for path in (p, q):
                cli.main(["extract", "--venue", "polymarket", "--data", self.root, "--day", DAY, "--out", out])
                os.replace(os.path.join(out, f"{DAY}.csv.gz"), path)
            with open(p, "rb") as f1, open(q, "rb") as f2:
                self.assertEqual(f1.read(), f2.read())
        finally:
            shutil.rmtree(out)


class PredictTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        base = os.path.join(self.root, "data", "predict-fun")
        mk = lambda mid, start, sp, ep, asset="btc", lab="5m": {  # noqa: E731
            "category_slug": f"{asset}-updown-5m-{start}", "asset": asset, "interval_label": lab, "market_id": mid,
            "start_sec": start, "end_sec": start + 300, "start_price": sp, "end_price": ep, "status": "OPEN"}
        gz(f"{base}/markets/predict-markets-{DAY}.jsonl.gz", [
            mk(1, D0, "100", "101"),          # up
            mk(2, D0 + 300, "100", "99.5"),   # down
            mk(3, D0 + 600, "100", "100.0"),  # push
            mk(4, D0 + 900, "100", None),     # no outcome yet
            {**mk(5, D0, "1", "2"), "end_sec": D0 + 3600, "interval_label": "hourly"},
        ])
        t = lambda s, off: (s * 1000) + off  # noqa: E731
        gz(f"{base}/orderbook/BTC-5M/BTC-5M-predict-orderbook-{DAY}.jsonl.gz", [
            # market 1: up bid 0.94 / ask 0.96 -> up mid 0.95
            {"market_id": 1, "update_ts_ms": t(D0, 1000), "payload": {"bids": [[0.94, 10], [0.5, 1]], "asks": [[0.96, 5], [0.99, 1]]}},
            # market 2: up bid 0.01 / ask 0.03 -> down mid 0.98, down bid 0.97
            {"market_id": 2, "update_ts_ms": t(D0 + 300, 2000), "payload": {"bids": [[0.01, 10]], "asks": [[0.03, 5], [0.2, 0]]}},
            # market 3: up mid 0.93 (push -> excluded from stats)
            {"market_id": 3, "update_ts_ms": t(D0 + 600, 2000), "payload": {"bids": [[0.92, 1]], "asks": [[0.94, 1]]}},
            # market 1 again, after the window closed
            {"market_id": 1, "update_ts_ms": t(D0, 300_000), "payload": {"bids": [[0.001, 1]], "asks": [[0.002, 1]]}},
        ])

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_rounds(self):
        rows = {r["slug"]: r for r in predict.extract(self.root, DAY, D0, NEXT)}
        self.assertEqual(len(rows), 4)                                  # hourly market excluded
        r1 = rows[f"btc-updown-5m-{D0}"]
        r2 = rows[f"btc-updown-5m-{D0 + 300}"]
        r3 = rows[f"btc-updown-5m-{D0 + 600}"]
        r4 = rows[f"btc-updown-5m-{D0 + 900}"]
        self.assertEqual((r1["outcome"], r1["mid_95_side"], r1["mid_98_side"]), ("up", "up", ""))
        self.assertEqual(r1["bid_93_px"], "0.94")
        self.assertEqual((r2["outcome"], r2["mid_98_side"], r2["mid_98_px"]), ("down", "down", "0.98"))
        self.assertEqual((r2["bid_95_side"], r2["bid_95_px"], r2["bid_98_side"]), ("down", "0.97", ""))
        self.assertEqual((r3["outcome"], r4["outcome"], r4["samples"]), ("flat", "unknown", 0))
        self.assertNotIn("trade_90_side", r1)

    def test_report_excludes_push_and_unknown(self):
        rows = predict.extract(self.root, DAY, D0, NEXT)
        for r in rows:
            r["date"] = report.day_of(r["start_sec"])
            for k, v in list(r.items()):
                r[k] = "" if v is None else str(v)
        t = report.summarise(rows)
        s = {(r[0], r[1]): r for r in t["summary"][1]}
        h = t["summary"][0]
        x = dict(zip(h, s[("ALL", "90")]))
        self.assertEqual((x["settled_rounds"], x["triggered"], x["reversed"]), (2, 2, 0))
        q = {(r[0], r[1]): r for r in t["data_quality"][1]}
        self.assertEqual(q[(DAY, "BTC")][2:6], [4, 2, 1, 1])


class ReportMathTest(unittest.TestCase):
    def test_seconds_to_close_buckets_cover_the_whole_window(self):
        self.assertEqual(report.stc_bucket(300), "120-300")   # trigger at the open
        self.assertEqual(report.stc_bucket(120), "120-300")
        self.assertEqual(report.stc_bucket(0.001), "0-15")
        self.assertEqual(report.stc_bucket(0), "0-15")
        self.assertIsNone(report.stc_bucket(300.5))

    def test_breakdowns_add_up_to_the_summary(self):
        def rnd(start, outcome, side, off_ms, px):
            r = {"venue": "polymarket", "asset": "BTC", "slug": str(start), "start_sec": str(start),
                 "end_sec": str(start + 300), "outcome": outcome, "samples": "3", "peak_up": "", "peak_down": "",
                 "date": report.day_of(start)}
            for t in (0.9, 0.93, 0.95, 0.98, 0.99):
                k = f"mid_{tkey(t)}"
                hit = px >= t
                r[f"{k}_side"] = side if hit else ""
                r[f"{k}_ts_ms"] = str(start * 1000 + off_ms) if hit else ""
                r[f"{k}_px"] = str(px) if hit else ""
            return r
        rows = [rnd(D0, "up", "up", 0, 0.99),            # at the open: 300 s left
                rnd(D0 + 300, "down", "up", 299_000, 0.95),
                rnd(D0 + 86400 * 8, "up", "down", 100_000, 0.93)]
        t = report.summarise(iter(rows))                 # a one-shot iterator is enough
        h, srows = t["summary"]
        summ = {(r[0], r[1]): dict(zip(h, r)) for r in srows}
        for name, key in (("by_seconds_to_close", 2), ("by_hour_utc", 2), ("daily", None), ("weekly", None), ("monthly", None)):
            hh, rr = t[name]
            c = {k: i for i, k in enumerate(hh)}
            for (asset, th), s in summ.items():
                got = [r for r in rr if r[c["asset"]] == asset and r[c["threshold_pct"]] == th]
                self.assertEqual(sum(int(r[c["triggered"]]) for r in got), s["triggered"], (name, asset, th))
                self.assertEqual(sum(int(r[c["reversed"]]) for r in got), s["reversed"], (name, asset, th))
        self.assertEqual(summ[("ALL", "90")]["triggered"], 3)
        self.assertEqual(summ[("ALL", "90")]["reversed"], 2)
        self.assertEqual(t["meta"]["days"], 2)

    def test_wilson(self):
        lo, hi = report.wilson(2062, 20869)   # matches the reference spreadsheet's 9.483 / 10.293
        self.assertEqual((round(100 * lo, 3), round(100 * hi, 3)), (9.483, 10.293))
        self.assertEqual(report.wilson(0, 0), (None, None))

    def test_archive_path(self):
        f = {"name": "BTC-5m-best_bid_ask-2026-11-09.jsonl.gz", "dataset": "best_bid_ask", "asset": "BTC", "interval": "5m"}
        self.assertEqual(cli.archive_path("polymarket", f), "data/polymarket/daily/best_bid_ask/BTC-5m/" + f["name"])
        self.assertIsNone(cli.archive_path("polymarket", {**f, "interval": "15m"}))
        self.assertIsNone(cli.archive_path("polymarket", {**f, "dataset": "book"}))
        g = {"name": "ETH-5M-predict-orderbook-2026-11-09.jsonl.gz", "dataset": "orderbook", "asset": "ETH", "interval": "5m"}
        self.assertEqual(cli.archive_path("predict", g), "data/predict-fun/orderbook/ETH-5M/" + g["name"])
        self.assertEqual(cli.archive_path("predict", {"name": "predict-markets-2026-11-09.jsonl.gz", "dataset": "markets"}),
                         "data/predict-fun/markets/predict-markets-2026-11-09.jsonl.gz")


if __name__ == "__main__":
    unittest.main()
