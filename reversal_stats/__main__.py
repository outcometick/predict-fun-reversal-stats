"""python -m reversal_stats {fetch,extract,report} ...

  fetch    download a date range from the outcometick data API (needs OT_KEY
           and `pip install outcometick`) into the archive layout
  extract  archive layout -> rounds/<day>.csv.gz
  report   rounds/ -> results/*.csv, charts/*.svg, README.md, README.zh-CN.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from . import charts, polymarket, predict, readme, report
from .rounds import THRESHOLDS, tkey, write_rounds

VENUES = {"polymarket": polymarket, "predict": predict}


def _days(a):
    if a.day:
        return [a.day]
    if not (a.from_ and a.to):
        sys.exit("give --day, or --from and --to")
    d0, d1 = dt.date.fromisoformat(a.from_), dt.date.fromisoformat(a.to)
    return [(d0 + dt.timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def _day_start(day):
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp())


def cmd_extract(a):
    mod = VENUES[a.venue]
    os.makedirs(a.out, exist_ok=True)
    for day in _days(a):
        nxt = (dt.date.fromisoformat(day) + dt.timedelta(days=1)).isoformat()
        rows = mod.extract(a.data, day, _day_start(day), nxt)
        if not rows:
            print(f"{day}: no input files under {a.data}", file=sys.stderr)
            continue
        write_rounds(os.path.join(a.out, f"{day}.csv.gz"), rows, mod.BASES)
        print(f"{day}: {len(rows)} rounds", file=sys.stderr)


def cmd_report(a):
    tables = report.summarise(report.load(a.rounds))
    if not tables["meta"]["rounds"]:
        sys.exit(f"no rounds under {a.rounds}")
    report.write_results(tables, a.out)

    s = {(r[0], r[1]): r for r in tables["summary"][1]}
    h = tables["summary"][0]
    col = {k: i for i, k in enumerate(h)}
    pts = []
    for t in THRESHOLDS:
        r = s[("ALL", tkey(t))]
        if not r[col["triggered"]]:
            continue
        pts.append((tkey(t), float(r[col["reversal_rate_pct"]]), float(r[col["wilson95_low_pct"]]),
                    float(r[col["wilson95_high_pct"]]), 100 * (1 - float(r[col["avg_trigger_price"]]))))
    wh, wrows = tables["weekly"]
    wc = {k: i for i, k in enumerate(wh)}
    weeks = sorted({r[wc["week_start"]] for r in wrows})
    series = []
    for t in ("90", "95", "99"):
        by = {r[wc["week_start"]]: float(r[wc["reversal_rate_pct"]]) for r in wrows
              if r[wc["asset"]] == "ALL" and r[wc["threshold_pct"]] == t and r[wc["reversal_rate_pct"]] != ""}
        series.append((f"{t}%", [by.get(w) for w in weeks]))
    name = readme.NAME[a.venue]
    os.makedirs(os.path.join(a.out, "charts"), exist_ok=True)
    with open(os.path.join(a.out, "charts", "calibration.svg"), "w", encoding="utf-8") as f:
        f.write(charts.calibration(pts, f"{name} 5m: realised vs implied reversal rate"))
    with open(os.path.join(a.out, "charts", "weekly.svg"), "w", encoding="utf-8") as f:
        f.write(charts.weekly(weeks, series, f"{name} 5m: weekly reversal rate by threshold"))

    updated = a.updated or tables["meta"]["last_day"]
    for lang, fn in (("en", "README.md"), ("zh", "README.zh-CN.md")):
        with open(os.path.join(a.out, fn), "w", encoding="utf-8") as f:
            f.write(readme.render(a.venue, tables, lang, updated))
    print(f"{tables['meta']['days']} days, {tables['meta']['settled_rounds']} settled rounds", file=sys.stderr)


def archive_path(venue, f):
    """Archive-layout path of a /v1/files row this tool needs, else None."""
    name, ds, asset, iv = f.get("name") or "", f.get("dataset"), f.get("asset"), f.get("interval")
    if "/" in name or not name.endswith(".jsonl.gz"):
        return None
    if venue == "polymarket":
        if ds in ("markets", "best_bid_ask", "last_trade_price") and iv == "5m" and asset:
            return f"data/polymarket/daily/{ds}/{asset}-5m/{name}"
        return None
    if ds == "markets":
        return f"data/predict-fun/markets/{name}"
    if ds == "orderbook" and iv == "5m" and asset:
        return f"data/predict-fun/orderbook/{asset}-5M/{name}"
    return None


def cmd_fetch(a):
    try:
        from outcometick.data import DataClient
    except ImportError:
        sys.exit("pip install outcometick  (provides outcometick.data.DataClient)")
    ot = DataClient()
    days = _days(a)
    last = (dt.date.fromisoformat(days[-1]) + dt.timedelta(days=1)).isoformat()
    for day in days + [last]:
        venue = "polymarket" if a.venue == "polymarket" else "predict-fun"
        try:
            res = ot.files(date=day, venue=venue)
        except Exception as e:  # noqa: BLE001 -- report and keep going
            print(f"{day}: {e}", file=sys.stderr)
            continue
        for f in res.get("files", []):
            p = archive_path(a.venue, f)
            if p is None or (day == last and f.get("dataset") != "markets"):
                continue
            dest = os.path.join(a.data, p)
            if os.path.exists(dest):
                continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            ot.download(f, save_to=dest)
            print(f"  {p}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m reversal_stats")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def dates(p):
        p.add_argument("--day")
        p.add_argument("--from", dest="from_")
        p.add_argument("--to")

    p = sub.add_parser("extract")
    p.add_argument("--venue", choices=VENUES, required=True)
    p.add_argument("--data", required=True, help="root of the archive layout (contains data/)")
    p.add_argument("--out", default="rounds")
    dates(p)
    p.set_defaults(fn=cmd_extract)

    p = sub.add_parser("report")
    p.add_argument("--venue", choices=VENUES, required=True)
    p.add_argument("--rounds", default="rounds")
    p.add_argument("--out", default=".")
    p.add_argument("--updated", help="date shown as 'last updated' (default: last day in the data)")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("fetch")
    p.add_argument("--venue", choices=VENUES, required=True)
    p.add_argument("--data", default="archive")
    dates(p)
    p.set_defaults(fn=cmd_fetch)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
