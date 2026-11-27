# Predict.fun 5-minute Up/Down: how often does a 90–99% favourite lose?

[中文](README.zh-CN.md) · Data: [outcometick](https://outcometick.com?utm_source=github&utm_medium=readme&utm_campaign=reversal-stats) · Sister repo: [Polymarket reversal stats](https://github.com/outcometick/polymarket-reversal-stats)

In Predict.fun's 5-minute crypto Up/Down markets, once one side's price first reaches 90%, 93%, 95%, 98% or 99%, how often does that side still lose at the close? This repository answers that from tick-level order-book data and **updates itself every day**.

**Coverage:** 2026-08-25 → 2026-11-25 (UTC), 93 days, 79,902 settled 5-minute markets across BTC, BNB, ETH. Last updated 2026-11-25.

## Headline — all assets, mid price

| favourite first reached | rounds that got there | favourite lost | reversal rate | 95% interval | avg price at trigger | win rate − price |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 90% | 77,295 | 6,732 | 8.71% | 8.51% – 8.91% | 0.9074 | 0.55 pp |
| 93% | 74,377 | 4,496 | 6.04% | 5.88% – 6.22% | 0.9353 | 0.42 pp |
| 95% | 69,465 | 2,913 | 4.19% | 4.05% – 4.34% | 0.9549 | 0.32 pp |
| 98% | 48,084 | 720 | 1.50% | 1.39% – 1.61% | 0.9819 | 0.31 pp |
| 99% | 537 | 7 | 1.30% | 0.63% – 2.67% | 0.9900 | -0.30 pp |

![realised vs implied reversal rate](charts/calibration.svg)

*Implied* is 1 − the average price paid at the trigger. When the realised rate sits above it, the favourite at that price lost more often than its price said; "win rate − price" is the same gap seen from the buyer's side, before fees.

## By asset — reversal rate at each threshold (mid)

| asset | 90% | 93% | 95% | 98% | 99% | rounds at 95% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 8.71% | 6.04% | 4.19% | 1.50% | 1.30% | 69,465 |
| BTC | 8.42% | 5.75% | 3.84% | 1.42% | 1.35% | 25,505 |
| BNB | 8.52% | 6.03% | 4.46% | 2.10% | 2.13% | 18,361 |
| ETH | 9.18% | 6.36% | 4.36% | 1.39% | 1.04% | 25,599 |

## By price basis — all assets

| threshold | mid | best bid |
| --- | ---: | ---: |
| 90% | 8.71% | 7.59% |
| 93% | 6.04% | 5.01% |
| 95% | 4.19% | 3.28% |
| 98% | 1.50% | 1.08% |
| 99% | 1.30% | 0.58% |

## Over time

![weekly reversal rate](charts/weekly.svg)

## All the tables

- [`results/summary.csv`](results/summary.csv) — per asset × threshold: triggers, reversals, rate, 95% Wilson interval, average trigger price, win rate minus price
- [`results/by_price_basis.csv`](results/by_price_basis.csv) — the same, for each price basis
- [`results/daily.csv`](results/daily.csv) — per UTC day
- [`results/weekly.csv`](results/weekly.csv) — per week (Monday start, UTC)
- [`results/monthly.csv`](results/monthly.csv) — per month
- [`results/by_hour_utc.csv`](results/by_hour_utc.csv) — by the hour the market opened (UTC)
- [`results/by_seconds_to_close.csv`](results/by_seconds_to_close.csv) — by how many seconds before the close the threshold was first reached
- [`results/by_loser_peak.csv`](results/by_loser_peak.csv) — how high the losing side's mid price got before it lost
- [`results/data_quality.csv`](results/data_quality.csv) — per day and asset: rounds, settled, flat, unknown, rounds with no two-sided quote

Every table is computed from [`rounds/`](rounds/): one gzip CSV per UTC day, one row per market, with the outcome and — for each basis and threshold — which side got there first, when, and at what price. Use it to re-check a number or try your own thresholds.

## Definitions

- **Round**: one 5-minute market, assigned to the UTC day it opens.
- **Trigger**: the first moment inside the market's window when either side's price on the chosen basis is ≥ the threshold. That side is the favourite.
- **Reversal**: the favourite lost at settlement.
- Two price bases: **mid** and **best bid**. Predict.fun publishes one book per market (the Up side); Down is its mirror (a Down bid at 1 − p is an Up ask at p). There is no trade tape on Predict.fun, so there is no trade basis. Mid is counted only while both sides are quoted: a book with no ask is skipped rather than priced as 1.0. So a 99% mid needs an ask above 0.99, which only sub-cent ticks allow, and the 99% mid row has few rounds; for the 99% line read the best-bid basis.
- Only settled rounds count. A flat close is a **push** on Predict.fun (both sides are refunded), so those rounds are left out.
- **Wilson interval**: 95% score interval on the reversal rate.
- **Win rate − price**: favourite win rate minus the average trigger price, in percentage points. Mid and best bid are not prices you can buy at (you pay the ask), and no fees are included — read it as a description of the market, not as a strategy result.

## Reproduce it

Code is in [`reversal_stats/`](reversal_stats/) (Python 3.10+, standard library only).

```bash
# one free sample day, no key
curl -L https://github.com/outcometick/predict.fun-data-samples/releases/latest/download/predict-fun-data-samples.tar.gz | tar xz
python -m reversal_stats extract --venue predict --data ./predict-fun-data-samples --day <sample day> --out my-rounds
python -m reversal_stats report --venue predict --rounds my-rounds --out my-report

# any range you have a data subscription for
pip install outcometick
export OT_KEY="ck_..."
python -m reversal_stats fetch --venue predict --from <first day> --to <last day> --data ./archive
python -m reversal_stats extract --venue predict --data ./archive --from <first day> --to <last day> --out my-rounds
```

Inputs per day: orderbook snapshots and markets, as delivered by the [outcometick](https://outcometick.com?utm_source=github&utm_medium=readme&utm_campaign=reversal-stats) archive. The sample README names its day.

## Data and license

Market data: [outcometick](https://outcometick.com?utm_source=github&utm_medium=readme&utm_campaign=reversal-stats) — tick-level Polymarket and Predict.fun crypto Up/Down archives (order books, trades, settlement feeds), free sample days, and a hosted backtester. Results and rounds: CC BY 4.0, attribution "outcometick". Code: MIT.
