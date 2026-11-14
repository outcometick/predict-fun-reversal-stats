"""Two static SVG charts for the README (GitHub shows them as images, so no
hover layer; every plotted value is also in a results/ CSV and a README table).

* calibration.svg -- realised reversal rate per threshold (mid basis, all
  assets) with its 95% Wilson interval, against the rate the price implies
  (1 - threshold).
* weekly.svg      -- weekly reversal rate at 90 / 95 / 99%, all assets.

Light and dark steps both ship, switched by prefers-color-scheme.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

W, H = 720, 360
L, R, T, B = 56, 120, 44, 44

STYLE = """
<style>
  .bg{fill:#fcfcfb} .t1{fill:#0b0b0b} .t2{fill:#52514e} .grid{stroke:#e4e3df}
  .s1{stroke:#2a78d6;fill:#2a78d6} .s2{stroke:#eb6834;fill:#eb6834} .s3{stroke:#1baf7a;fill:#1baf7a}
  .ref{stroke:#8a8984;fill:#8a8984} .ring{stroke:#fcfcfb}
  text{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;font-size:12px}
  .title{font-size:14px;font-weight:600}
  @media (prefers-color-scheme: dark){
    .bg{fill:#1a1a19} .t1{fill:#f0efec} .t2{fill:#c3c2b7} .grid{stroke:#34332f}
    .s1{stroke:#3987e5;fill:#3987e5} .s2{stroke:#d95926;fill:#d95926} .s3{stroke:#199e70;fill:#199e70}
    .ref{stroke:#9d9c96;fill:#9d9c96} .ring{stroke:#1a1a19}
  }
</style>
"""


def _nice_max(v):
    for step in (0.5, 1, 2, 2.5, 5, 10, 20, 25, 50):
        if v <= step * 5:
            return step * 5, step
    return v, v / 5


def _frame(title, ymax, ystep, xlabels, xpos):
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{escape(title)}">',
           STYLE, f'<rect class="bg" width="{W}" height="{H}" rx="8"/>',
           f'<text class="t1 title" x="{L}" y="24">{escape(title)}</text>']
    y = 0.0
    while y <= ymax + 1e-9:
        py = _y(y, ymax)
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{py:.1f}" y2="{py:.1f}" stroke-width="1"/>')
        out.append(f'<text class="t2" x="{L - 8}" y="{py + 4:.1f}" text-anchor="end">{y:g}%</text>')
        y += ystep
    for lab, x in zip(xlabels, xpos):
        if lab:
            out.append(f'<text class="t2" x="{x:.1f}" y="{H - B + 18}" text-anchor="middle">{escape(lab)}</text>')
    return out


def _y(v, ymax):
    return T + (H - T - B) * (1 - v / ymax)


def _xs(n):
    span = W - L - R
    return [L + span * (i + 0.5) / n for i in range(n)]


def _line(cls, pts, dash=False):
    d = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    extra = ' stroke-dasharray="5 4"' if dash else ""
    return f'<path class="{cls}" d="{d}" fill="none" stroke-width="2" stroke-linejoin="round"{extra}/>'


def calibration(points, title):
    """points: [(threshold_label, realised_pct, lo_pct, hi_pct, implied_pct)]."""
    top = max(max(p[3] for p in points), max(p[4] for p in points))
    ymax, ystep = _nice_max(top * 1.1)
    xs = _xs(len(points))
    out = _frame(title, ymax, ystep, [f"{p[0]}%" for p in points], xs)
    out.append(_line("ref", [(x, _y(p[4], ymax)) for x, p in zip(xs, points)], dash=True))
    for x, p in zip(xs, points):
        out.append(f'<line class="s1" x1="{x:.1f}" x2="{x:.1f}" y1="{_y(p[2], ymax):.1f}" y2="{_y(p[3], ymax):.1f}" stroke-width="2" stroke-linecap="round"/>')
    out.append(_line("s1", [(x, _y(p[1], ymax)) for x, p in zip(xs, points)]))
    for x, p in zip(xs, points):
        out.append(f'<circle class="s1 ring" cx="{x:.1f}" cy="{_y(p[1], ymax):.1f}" r="5" stroke-width="2"/>')
        out.append(f'<text class="t1" x="{x + 8:.1f}" y="{_y(p[1], ymax) - 6:.1f}">{p[1]:.2f}%</text>')
    lx, last = xs[-1], points[-1]
    out.append(f'<text class="t2" x="{lx + 14:.1f}" y="{_y(last[4], ymax) + 14:.1f}">implied (1 − p)</text>')
    out.append(f'<text class="t2" x="{lx + 14:.1f}" y="{_y(last[1], ymax) - 4:.1f}">realised</text>')
    out.append(f'<text class="t2" x="{L}" y="{H - 8}">threshold the favourite first reached (mid price) · bars: 95% Wilson interval</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def weekly(weeks, series, title):
    """weeks: [label]; series: [(name, [pct or None per week])], at most 3."""
    vals = [v for _, s in series for v in s if v is not None]
    ymax, ystep = _nice_max((max(vals) if vals else 1) * 1.15)
    xs = _xs(len(weeks))
    every = max(1, len(weeks) // 8)
    labels = [w if i % every == 0 else "" for i, w in enumerate(weeks)]
    out = _frame(title, ymax, ystep, labels, xs)
    for i, (name, s) in enumerate(series):
        cls = f"s{i + 1}"
        pts = [(x, _y(v, ymax)) for x, v in zip(xs, s) if v is not None]
        if not pts:
            continue
        out.append(_line(cls, pts))
        x, y = pts[-1]
        out.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="4" stroke="none"/>')
        out.append(f'<text class="t1" x="{x + 10:.1f}" y="{y + 4:.1f}">{escape(name)}</text>')
    out.append(f'<text class="t2" x="{L}" y="{H - 8}">week starting (Monday, UTC) · all assets · mid price</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
