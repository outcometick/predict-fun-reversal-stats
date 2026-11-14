"""README.md / README.zh-CN.md for one venue, regenerated from the tables on
every run. Numbers come only from summarise(); nothing here is hand-typed."""

from __future__ import annotations

from .rounds import THRESHOLDS, tkey

SITE = "https://outcometick.com"
UTM = "?utm_source=github&utm_medium=readme&utm_campaign=reversal-stats"

REPO = {
    "polymarket": "https://github.com/outcometick/polymarket-reversal-stats",
    "predict": "https://github.com/outcometick/predict-fun-reversal-stats",
}
SAMPLE = {
    "polymarket": ("https://github.com/outcometick/polymarket-tick-data-samples/releases/latest/download/polymarket-data-samples.tar.gz", "polymarket-data-samples"),
    "predict": ("https://github.com/outcometick/predict.fun-data-samples/releases/latest/download/predict-fun-data-samples.tar.gz", "predict-fun-data-samples"),
}
NAME = {"polymarket": "Polymarket", "predict": "Predict.fun"}
OTHER = {"polymarket": "predict", "predict": "polymarket"}

FILES = [
    ("summary", "per asset × threshold: triggers, reversals, rate, 95% Wilson interval, average trigger price, win rate minus price",
     "每个币种 × 阈值：触发数、反转数、反转率、95% Wilson 区间、首次触发平均价、胜率减价格"),
    ("by_price_basis", "the same, for each price basis", "同上，按价格口径拆开"),
    ("daily", "per UTC day", "按 UTC 日"),
    ("weekly", "per week (Monday start, UTC)", "按周（周一起，UTC）"),
    ("monthly", "per month", "按月"),
    ("by_hour_utc", "by the hour the market opened (UTC)", "按开盘的 UTC 小时"),
    ("by_seconds_to_close", "by how many seconds before the close the threshold was first reached", "按首次到达阈值时距收盘的秒数"),
    ("by_loser_peak", "how high the losing side's mid price got before it lost", "输掉的一方在输之前中价最高到过多少"),
    ("data_quality", "per day and asset: rounds, settled, flat, unknown, rounds with no two-sided quote", "每天每币种：局数、已结算、平局、结果未知、没有双边报价的局数"),
]


def _row(cols):
    return "| " + " | ".join(str(c) for c in cols) + " |"


def _table(header, rows, align=None):
    align = align or ["---"] + ["---:"] * (len(header) - 1)
    return "\n".join([_row(header), _row(align)] + [_row(r) for r in rows])


def _summary_index(tables):
    h, rows = tables["summary"]
    return {(r[0], r[1]): dict(zip(h, r)) for r in rows}


def _basis_index(tables):
    h, rows = tables["by_price_basis"]
    return {(r[0], r[1], r[2]): dict(zip(h, r)) for r in rows}


def _f(v, d=2, suffix="%"):
    return "–" if v in ("", None) else f"{float(v):.{d}f}{suffix}"


def headline(tables, lang):
    s = _summary_index(tables)
    hdr = {
        "en": ["favourite first reached", "rounds that got there", "favourite lost", "reversal rate", "95% interval", "avg price at trigger", "win rate − price"],
        "zh": ["领先方首次到达", "到达的局数", "领先方输掉", "反转率", "95% 区间", "触发时平均价", "胜率 − 价格"],
    }[lang]
    rows = []
    for t in THRESHOLDS:
        x = s[("ALL", tkey(t))]
        rows.append([f"{tkey(t)}%", f"{int(x['triggered']):,}", f"{int(x['reversed']):,}", _f(x["reversal_rate_pct"]),
                     f"{_f(x['wilson95_low_pct'])} – {_f(x['wilson95_high_pct'])}",
                     _f(x["avg_trigger_price"], 4, ""), _f(x["win_rate_minus_price_pp"], 2, " pp")])
    return _table(hdr, rows)


def by_asset(tables, lang, assets):
    s = _summary_index(tables)
    hdr = ["asset" if lang == "en" else "币种"] + [f"{tkey(t)}%" for t in THRESHOLDS] + ["rounds at 95%" if lang == "en" else "95% 触发局数"]
    rows = []
    for a in ["ALL"] + assets:
        cells = [a if a != "ALL" else ("**all**" if lang == "en" else "**合计**")]
        cells += [_f(s[(a, tkey(t))]["reversal_rate_pct"]) for t in THRESHOLDS]
        cells.append(f"{int(s[(a, '95')]['triggered']):,}")
        rows.append(cells)
    return _table(hdr, rows)


def by_basis(tables, lang, bases):
    b = _basis_index(tables)
    label = {"en": {"mid": "mid", "bid": "best bid", "trade": "trade"}, "zh": {"mid": "中价", "bid": "买一", "trade": "成交价"}}[lang]
    hdr = ["threshold" if lang == "en" else "阈值"] + [label[x] for x in bases]
    rows = [[f"{tkey(t)}%"] + [_f(b[("ALL", tkey(t), x)]["reversal_rate_pct"]) for x in bases] for t in THRESHOLDS]
    return _table(hdr, rows)


def render(venue, tables, lang, updated):
    m = tables["meta"]
    assets = m["assets"]
    bases = m["bases"]
    name = NAME[venue]
    other = OTHER[venue]
    sample_url, sample_dir = SAMPLE[venue]
    site = f"{SITE}{'/zh' if lang == 'zh' else ''}{UTM}"
    files = "\n".join(f"- [`results/{f}.csv`](results/{f}.csv) — {en if lang == 'en' else zh}" for f, en, zh in FILES)
    flat_en = ("A flat close is a **push** on Predict.fun (both sides are refunded), so those rounds are left out."
               if venue == "predict" else "Flat closes (rare) are left out.")
    flat_zh = ("Predict.fun 上收盘价等于开盘价算 **push**（两边退款），这些局不计入。"
               if venue == "predict" else "极少数平局不计入。")
    basis_en = ("Three price bases: **mid** = (best bid + best ask) / 2, **best bid**, and **trade** = the price of a print. "
                "Up and Down each have their own order book." if venue == "polymarket" else
                "Two price bases: **mid** and **best bid**. Predict.fun publishes one book per market (the Up side); Down is its mirror "
                "(a Down bid at 1 − p is an Up ask at p). There is no trade tape on Predict.fun, so there is no trade basis.")
    basis_zh = ("三种价格口径：**中价** =（买一 + 卖一）/ 2、**买一**、**成交价**。Up 和 Down 各有自己的盘口。" if venue == "polymarket" else
                "两种价格口径：**中价**、**买一**。Predict.fun 每个市场只有一本盘口（Up 方），Down 是它的镜像"
                "（Down 以 1 − p 买入等于 Up 以 p 卖出）。Predict.fun 不公布成交流，所以没有成交价口径。")
    src_en = ("best_bid_ask (unthrottled top of book), last_trade_price and markets" if venue == "polymarket"
              else "orderbook snapshots and markets")
    src_zh = ("best_bid_ask（未抽稀的盘口顶部）、last_trade_price、markets" if venue == "polymarket" else "orderbook 快照、markets")
    fetch_flag = "polymarket" if venue == "polymarket" else "predict"

    if lang == "en":
        return f"""# {name} 5-minute Up/Down: how often does a 90–99% favourite lose?

[中文](README.zh-CN.md) · Data: [outcometick]({site}) · Sister repo: [{NAME[other]} reversal stats]({REPO[other]})

In {name}'s 5-minute crypto Up/Down markets, once one side's price first reaches 90%, 93%, 95%, 98% or 99%, how often does that side still lose at the close? This repository answers that from tick-level order-book data and **updates itself every day**.

**Coverage:** {m['first_day']} → {m['last_day']} (UTC), {m['days']} days, {m['settled_rounds']:,} settled 5-minute markets across {', '.join(assets)}. Last updated {updated}.

## Headline — all assets, mid price

{headline(tables, 'en')}

![realised vs implied reversal rate](charts/calibration.svg)

*Implied* is 1 − the average price paid at the trigger. When the realised rate sits above it, the favourite at that price lost more often than its price said; "win rate − price" is the same gap seen from the buyer's side, before fees.

## By asset — reversal rate at each threshold (mid)

{by_asset(tables, 'en', assets)}

## By price basis — all assets

{by_basis(tables, 'en', bases)}

## Over time

![weekly reversal rate](charts/weekly.svg)

## All the tables

{files}

Every table is computed from [`rounds/`](rounds/): one gzip CSV per UTC day, one row per market, with the outcome and — for each basis and threshold — which side got there first, when, and at what price. Use it to re-check a number or try your own thresholds.

## Definitions

- **Round**: one 5-minute market, assigned to the UTC day it opens.
- **Trigger**: the first moment inside the market's window when either side's price on the chosen basis is ≥ the threshold. That side is the favourite.
- **Reversal**: the favourite lost at settlement.
- {basis_en}
- Only settled rounds count. {flat_en}
- **Wilson interval**: 95% score interval on the reversal rate.
- **Win rate − price**: favourite win rate minus the average trigger price, in percentage points. Mid and best bid are not prices you can buy at (you pay the ask), and no fees are included — read it as a description of the market, not as a strategy result.

## Reproduce it

Code is in [`reversal_stats/`](reversal_stats/) (Python 3.10+, standard library only).

```bash
# one free sample day, no key
curl -L {sample_url} | tar xz
python -m reversal_stats extract --venue {fetch_flag} --data ./{sample_dir} --day <sample day> --out my-rounds
python -m reversal_stats report --venue {fetch_flag} --rounds my-rounds --out my-report

# any range you have a data subscription for
pip install outcometick
export OT_KEY="ck_..."
python -m reversal_stats fetch --venue {fetch_flag} --from <first day> --to <last day> --data ./archive
python -m reversal_stats extract --venue {fetch_flag} --data ./archive --from <first day> --to <last day> --out my-rounds
```

Inputs per day: {src_en}, as delivered by the [outcometick]({site}) archive. The sample README names its day.

## Data and license

Market data: [outcometick]({site}) — tick-level Polymarket and Predict.fun crypto Up/Down archives (order books, trades, settlement feeds), free sample days, and a hosted backtester. Results and rounds: CC BY 4.0, attribution "outcometick". Code: MIT.
"""
    return f"""# {name} 5 分钟涨跌盘：概率到 90–99% 的一方有多大概率翻车？

[English](README.md) · 数据来源：[outcometick]({site}) · 姊妹仓库：[{NAME[other]} 反转统计]({REPO[other]})

{name} 的 5 分钟加密货币涨跌盘里，一方价格首次到 90%、93%、95%、98%、99% 之后，收盘时它仍然输掉的比例有多高？本仓库用逐笔盘口数据统计这个问题，**每天自动更新**。

**覆盖范围：** {m['first_day']} → {m['last_day']}（UTC），共 {m['days']} 天，{', '.join(assets)} 合计 {m['settled_rounds']:,} 个已结算的 5 分钟市场。最近更新 {updated}。

## 总览：全币种，中价口径

{headline(tables, 'zh')}

![实际反转率与价格隐含反转率](charts/calibration.svg)

「隐含」= 1 − 触发时的平均价格。实际反转率高于它，说明这个价位的领先方输得比价格暗示的更多；「胜率 − 价格」是站在买方角度看的同一个差值，未计手续费。

## 分币种：各阈值反转率（中价）

{by_asset(tables, 'zh', assets)}

## 分价格口径：全币种

{by_basis(tables, 'zh', bases)}

## 随时间变化

![每周反转率](charts/weekly.svg)

## 全部表格

{files}

所有表都由 [`rounds/`](rounds/) 算出：每个 UTC 日一个 gzip CSV，一行一个市场，记录结算结果，以及每种口径、每个阈值下哪一方先到、何时到、价格多少。可以用来核对数字，或换自己的阈值重算。

## 口径

- **局**：一个 5 分钟市场，按开盘时刻归入 UTC 日。
- **触发**：市场窗口内，任一方在所选口径下价格 ≥ 阈值的第一个时刻；这一方即「领先方」。
- **反转**：领先方在结算时输掉。
- {basis_zh}
- 只统计已结算的局。{flat_zh}
- **Wilson 区间**：反转率的 95% 置信区间。
- **胜率 − 价格**：领先方胜率减去首次触发平均价，单位百分点。中价和买一都不是你能买到的价格（买入付卖一），也没扣手续费，这是对市场的描述，不是策略收益。

## 自己复现

代码在 [`reversal_stats/`](reversal_stats/)（Python 3.10+，只用标准库）。

```bash
# 免费样本日，不需要 key
curl -L {sample_url} | tar xz
python -m reversal_stats extract --venue {fetch_flag} --data ./{sample_dir} --day <样本日> --out my-rounds
python -m reversal_stats report --venue {fetch_flag} --rounds my-rounds --out my-report

# 订阅覆盖的任意日期范围
pip install outcometick
export OT_KEY="ck_..."
python -m reversal_stats fetch --venue {fetch_flag} --from <起始日> --to <结束日> --data ./archive
python -m reversal_stats extract --venue {fetch_flag} --data ./archive --from <起始日> --to <结束日> --out my-rounds
```

每天用到的数据：{src_zh}，来自 [outcometick]({site}) 归档。样本日见样本仓库 README。

## 数据与许可

市场数据：[outcometick]({site}) —— Polymarket 与 Predict.fun 加密涨跌盘逐笔归档（盘口、成交、结算价流），提供免费样本日和托管回测。统计结果与 rounds：CC BY 4.0，署名「outcometick」。代码：MIT。
"""
