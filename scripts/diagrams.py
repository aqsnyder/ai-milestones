"""Draw simple, factual SVG diagrams for milestones that have no free photo.

A diagram only ever plots numbers already stated (and sourced) in the entry
itself: scores, win/loss records, error rates, intervals. There is no
illustration or imagery, so a diagram can't be mistaken for a photo of the event.

Three types, all declared under `diagram:` in data/milestones.yaml:

  bars   horizontal bars, optionally against a reference line (e.g. a gold cutoff)
  split  one or more rows, each a 100% bar split into segments (wins/draws/losses)
  strip  intervals on a number line (e.g. where zeta zeros are known to lie)

Each bar, segment or band has a `group`: ai, human or other (sets the colour).
"""
from __future__ import annotations

import html

TYPES = {"bars", "split", "strip"}
GROUPS = {"ai", "human", "other"}

W = 520                      # viewBox width; shown at 300 px in the README
PAD = 22
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
INK = "#1f2328"
MUTED = "#59636e"
GRID = "#d1d9e0"
COLORS = {"ai": "#2f6fdb", "human": "#d9642b", "other": "#9aa4ae"}
LIGHT = {"ai": "#dbe7fb", "human": "#f9e1d4", "other": "#eef1f4"}
GROUP_LABEL = {"ai": "AI", "human": "Humans", "other": "Other"}


# ---------------------------------------------------------------- validation

def validate(d: dict, where: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(d, dict):
        return [f"{where}: diagram must be a mapping"]
    t = d.get("type")
    if t not in TYPES:
        return [f"{where}: diagram type must be one of {sorted(TYPES)}"]
    if not d.get("title"):
        errs.append(f"{where}: diagram needs a 'title'")

    def num(v, what):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            errs.append(f"{where}: diagram {what} must be a number, got {v!r}")
            return False
        return True

    def grp(item, what):
        if item.get("group", "other") not in GROUPS:
            errs.append(f"{where}: diagram {what} group must be one of {sorted(GROUPS)}")

    if t == "bars":
        bars = d.get("bars") or []
        if not bars:
            errs.append(f"{where}: bars diagram needs 'bars'")
        for b in bars:
            if not b.get("label"):
                errs.append(f"{where}: every bar needs a label")
            num(b.get("value"), "bar value")
            grp(b, "bar")
        if "max" in d and num(d["max"], "max"):
            if any(isinstance(b.get("value"), (int, float)) and b["value"] > d["max"] for b in bars):
                errs.append(f"{where}: a bar value exceeds diagram max")
        if d.get("reference"):
            num(d["reference"].get("value"), "reference value")
    elif t == "split":
        rows = d.get("rows") or []
        if not rows:
            errs.append(f"{where}: split diagram needs 'rows'")
        for r in rows:
            if not r.get("label"):
                errs.append(f"{where}: every split row needs a label")
            segs = r.get("segments") or []
            if not segs:
                errs.append(f"{where}: split row '{r.get('label')}' has no segments")
            for s in segs:
                if not s.get("label"):
                    errs.append(f"{where}: every segment needs a label")
                if num(s.get("value"), "segment value") and s["value"] < 0:
                    errs.append(f"{where}: segment values must be >= 0")
                grp(s, "segment")
            if segs and sum(s.get("value", 0) or 0 for s in segs) <= 0:
                errs.append(f"{where}: split row '{r.get('label')}' sums to zero")
    elif t == "strip":
        ok = num(d.get("min"), "min") & num(d.get("max"), "max")
        for b in d.get("bands") or []:
            if num(b.get("from"), "band from") and num(b.get("to"), "band to") and ok:
                if not d["min"] <= b["from"] < b["to"] <= d["max"]:
                    errs.append(f"{where}: band {b.get('label')!r} outside min..max or reversed")
            if not b.get("label"):
                errs.append(f"{where}: every band needs a label")
            grp(b, "band")
        if not d.get("bands"):
            errs.append(f"{where}: strip diagram needs 'bands'")
        for x in (d.get("lines") or []) + (d.get("ticks") or []):
            num(x.get("value"), "line/tick value")
    return errs


# ---------------------------------------------------------------- helpers

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fmt(v, unit: str = "") -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = f"{v:,}" if isinstance(v, int) else f"{v:g}"
    return f"{s}{unit}"


def text(x, y, s, size=20, color=INK, anchor="start", weight="normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{color}" text-anchor="{anchor}" '
            f'font-weight="{weight}">{esc(s)}</text>')


def wrap(s: str, size: int, width: float) -> list[str]:
    """Greedy word wrap using an average glyph width estimate."""
    max_chars = max(8, int(width / (size * 0.53)))
    lines, cur = [], ""
    for word in str(s).split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def label_lines(body: list[str], x: float, y: float, label: str, size: int = 20) -> float:
    """Draw a (wrapped) label whose first baseline is y + 4; return the y of its last baseline."""
    lines = wrap(label, size, W - 2 * PAD)
    for i, line in enumerate(lines):
        body.append(text(x, y + 4 + i * (size + 4), line, size, INK))
    return y + (len(lines) - 1) * (size + 4)


def svg(body: list[str], height: float, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height:.0f}" width="{W}" height="{height:.0f}" '
        f'font-family="{FONT}" role="img" aria-label="{esc(title)}">\n'
        f'<rect width="{W}" height="{height:.0f}" fill="#ffffff"/>\n'
        + "\n".join(body) + "\n</svg>\n"
    )


def header(d: dict) -> tuple[list[str], float]:
    out, y = [], PAD + 6
    for line in wrap(d["title"], 25, W - 2 * PAD):
        y += 28
        out.append(text(PAD, y, line, 25, INK, weight="600"))
    if d.get("subtitle"):
        for line in wrap(d["subtitle"], 18, W - 2 * PAD):
            y += 24
            out.append(text(PAD, y, line, 18, MUTED))
    return out, y + 34


def footer(body: list[str], y: float, d: dict, legend: list[tuple[str, str]]) -> float:
    if legend:
        x = PAD
        y += 10
        for color, label in legend:
            body.append(f'<rect x="{x}" y="{y - 13}" width="16" height="16" rx="3" fill="{color}"/>')
            body.append(text(x + 22, y, label, 17, MUTED))
            x += 22 + len(label) * 9.5 + 22
        y += 14
    y += 22
    note = d.get("note")
    if note:
        for line in wrap(note, 15, W - 2 * PAD):
            body.append(text(PAD, y, line, 15, MUTED))
            y += 19
    body.append(text(W - PAD, y + 4, "Data: this entry's sources · CC0 · AI Milestones", 13, MUTED, "end"))
    return y + PAD


def legend_for(groups: list[str], labels: dict | None = None) -> list[tuple[str, str]]:
    labels = labels or {}
    seen, out = set(), []
    for g in groups:
        if g not in seen:
            seen.add(g)
            out.append((COLORS[g], labels.get(g, GROUP_LABEL[g])))
    return out


# ---------------------------------------------------------------- renderers

def render_bars(d: dict) -> str:
    body, y = header(d)
    bars = d["bars"]
    unit = d.get("unit", "")
    vmax = d.get("max") or max(b["value"] for b in bars) * 1.08
    ref = d.get("reference")
    x0, x1 = PAD, W - PAD - 60           # leave room for a value label after short bars
    scale = (x1 - x0) / vmax
    bar_h, gap = 30, 18
    bar_tops: list[float] = []
    for b in bars:
        y = label_lines(body, x0, y, b["label"])
        y += 12
        bar_tops.append(y)
        w = max(2.0, b["value"] * scale)
        g = b.get("group", "other")
        body.append(f'<rect x="{x0}" y="{y:.1f}" width="{x1 - x0:.1f}" height="{bar_h}" rx="4" fill="{LIGHT[g] if d.get("max") else "#ffffff"}"/>')
        body.append(f'<rect x="{x0}" y="{y:.1f}" width="{w:.1f}" height="{bar_h}" rx="4" fill="{COLORS[g]}"/>')
        label = b.get("display", fmt(b["value"], unit))
        if w > len(label) * 12 + 16:
            body.append(text(x0 + w - 8, y + bar_h - 8, label, 20, "#ffffff", "end", "600"))
        else:
            body.append(text(x0 + w + 8, y + bar_h - 8, label, 20, INK, weight="600"))
        y += bar_h + gap
    if ref:
        rx = x0 + ref["value"] * scale
        body.append(f'<line x1="{rx:.1f}" y1="{bar_tops[0] - 4:.1f}" x2="{rx:.1f}" y2="{y - gap + 6:.1f}" '
                    f'stroke="{INK}" stroke-width="2" stroke-dasharray="6 5"/>')
        y += 8
        anchor = "end" if rx > W * 0.6 else "start"
        body.append(text(rx + (-6 if anchor == "end" else 6), y + 6,
                         f'{ref.get("label", "")}: {fmt(ref["value"], unit)}', 17, INK, anchor))
        y += 14
    legend = [] if d.get("no_legend") else legend_for([b.get("group", "other") for b in bars], d.get("legend"))
    y = footer(body, y, d, legend if len(legend) > 1 else [])
    return svg(body, y, d["title"])


def render_split(d: dict) -> str:
    body, y = header(d)
    x0, x1 = PAD, W - PAD
    bar_h, gap = 36, 22
    for r in d["rows"]:
        y = label_lines(body, x0, y, r["label"])
        y += 12
        total = sum(s["value"] for s in r["segments"])
        x = x0
        for s in r["segments"]:
            w = (x1 - x0) * s["value"] / total
            if w <= 0:
                continue
            g = s.get("group", "other")
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{bar_h}" fill="{COLORS[g]}" '
                        f'stroke="#ffffff" stroke-width="2"/>')
            label = fmt(s["value"])
            if w > len(label) * 12 + 10:
                body.append(text(x + w / 2, y + bar_h - 11, label, 19, "#ffffff", "middle", "600"))
            x += w
        y += bar_h + gap
    legend, seen = [], set()
    for r in d["rows"]:
        for s in r["segments"]:
            key = (s.get("group", "other"), s["label"])
            if key not in seen:
                seen.add(key)
                legend.append((COLORS[s.get("group", "other")], s["label"]))
    y = footer(body, y - gap + 16, d, legend)
    return svg(body, y, d["title"])


def render_strip(d: dict) -> str:
    body, y = header(d)
    lo, hi = d["min"], d["max"]
    x0, x1 = PAD + 10, W - PAD - 10
    sx = lambda v: x0 + (v - lo) / (hi - lo) * (x1 - x0)
    band_h = 34
    band_ys = []
    for b in d["bands"]:
        g = b.get("group", "other")
        y = label_lines(body, x0, y, b["label"], 19)
        y += 12
        body.append(f'<rect x="{x0}" y="{y:.1f}" width="{x1 - x0}" height="{band_h}" fill="#f6f8fa" stroke="{GRID}"/>')
        body.append(f'<rect x="{sx(b["from"]):.1f}" y="{y:.1f}" width="{sx(b["to"]) - sx(b["from"]):.1f}" '
                    f'height="{band_h}" fill="{COLORS[g]}" opacity="0.9"/>')
        band_ys.append(y)
        y += band_h + 20
    axis_y = y
    body.append(f'<line x1="{x0}" y1="{axis_y}" x2="{x1}" y2="{axis_y}" stroke="{INK}" stroke-width="2"/>')
    for t in d.get("ticks") or []:
        tx = sx(t["value"])
        body.append(f'<line x1="{tx:.1f}" y1="{axis_y - 6}" x2="{tx:.1f}" y2="{axis_y + 6}" stroke="{INK}" stroke-width="2"/>')
        body.append(text(tx, axis_y + 28, t.get("label", fmt(t["value"])), 18, INK, "middle"))
    for ln in d.get("lines") or []:
        lx = sx(ln["value"])
        for by in band_ys:
            body.append(f'<line x1="{lx:.1f}" y1="{by - 4:.1f}" x2="{lx:.1f}" y2="{by + band_h + 4:.1f}" stroke="{INK}" '
                        f'stroke-width="2.5" stroke-dasharray="5 4"/>')
    y = axis_y + 50
    for ln in d.get("lines") or []:
        for line in wrap(f'Dashed line: {ln["label"]}', 17, W - 2 * PAD):
            body.append(text(PAD, y, line, 17, MUTED))
            y += 22
    if d.get("axis_label"):
        body.append(text(W / 2, axis_y + 50 if not d.get("lines") else y, d["axis_label"], 17, MUTED, "middle"))
        y += 22
    y = footer(body, y - 10, d, [])
    return svg(body, y, d["title"])


RENDERERS = {"bars": render_bars, "split": render_split, "strip": render_strip}


def render(d: dict) -> str:
    return RENDERERS[d["type"]](d)


def alt_text(d: dict) -> str:
    """A plain-text description of the data, so the chart is accessible."""
    if d.get("alt"):
        return d["alt"]
    t = d["type"]
    if t == "bars":
        unit = d.get("unit", "")
        parts = [f'{b["label"]} {b.get("display", fmt(b["value"], unit))}' for b in d["bars"]]
        s = f'Bar chart, {d["title"]}: ' + "; ".join(parts)
        if d.get("reference"):
            s += f'; {d["reference"].get("label", "reference")} {fmt(d["reference"]["value"], unit)}'
        return s + "."
    if t == "split":
        rows = [r["label"] + ": " + ", ".join(f'{fmt(s["value"])} {s["label"].lower()}' for s in r["segments"])
                for r in d["rows"]]
        return f'Chart, {d["title"]}. ' + "; ".join(rows) + "."
    bands = "; ".join(f'{b["label"]}' for b in d["bands"])
    return f'Number line, {d["title"]}: {bands}.'
