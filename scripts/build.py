#!/usr/bin/env python3
"""Validate data/milestones.yaml, fetch image credits from Wikimedia Commons,
and render README.md, CREDITS.md and data/milestones.json.

Usage:
  python scripts/build.py              # validate + render (uses cached image credits)
  python scripts/build.py --fetch      # also download images + attribution from Commons
  python scripts/build.py --check      # validate only; non-zero exit on any error

Images are only ever taken from Wikimedia Commons, and every image is shown
with its author and license, as those licenses require. Entries without a free
image can instead declare a `diagram:` — a simple chart of numbers already in the
entry, drawn by scripts/diagrams.py into assets/diagrams/ (CC0).
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diagrams  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "milestones.yaml"
META = ROOT / "data" / "meta.yaml"
CREDITS_CACHE = ROOT / "data" / "image-credits.json"
IMG_DIR = ROOT / "assets" / "img"
DIAGRAM_DIR = ROOT / "assets" / "diagrams"
README = ROOT / "README.md"
CREDITS_MD = ROOT / "CREDITS.md"
JSON_OUT = ROOT / "data" / "milestones.json"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
REPO = "aqsnyder/ai-milestones"
USER_AGENT = f"ai-milestones-build/1.0 (https://github.com/{REPO})"
THUMB_WIDTH = 640

CATEGORIES = {
    "games": ("♟️", "Games & competitions"),
    "math": ("🧮", "Mathematics, code & reasoning"),
    "science": ("🔬", "Science"),
    "perception": ("👁️", "Vision & speech"),
    "language": ("💬", "Language"),
    "robotics": ("🤖", "Robotics & autonomy"),
    "foundations": ("🧱", "Foundations"),
}
SOURCE_KINDS = {"primary", "paper", "news", "reference"}
# Optional per-entry status. Omit for results that are confirmed / independently verified.
STATUSES = {
    "self-reported": "ℹ️ **Self-reported:** announced by the developers; not yet independently confirmed.",
    "under-review": "⚠️ **Claim under review:** experts have not yet verified this result.",
    "disputed": "⚠️ **Disputed:** the result or its framing has been publicly challenged — see summary.",
}
FREE_LICENSE_HINTS = ("cc0", "cc by", "cc-by", "public domain", "pd", "gfdl", "attribution", "no restrictions")
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# ---------------------------------------------------------------- loading / validation

def load_milestones() -> list[dict]:
    with DATA.open(encoding="utf-8") as f:
        items = yaml.safe_load(f) or []
    if not isinstance(items, list):
        sys.exit("data/milestones.yaml must be a YAML list")
    return items


def validate(items: list[dict]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for i, m in enumerate(items):
        where = f"entry #{i + 1} ({m.get('id', '?')})"
        for key in ("id", "date", "title", "category", "field", "summary", "significance", "sources"):
            if not m.get(key):
                errors.append(f"{where}: missing '{key}'")
        mid = str(m.get("id", ""))
        if mid and not ID_RE.match(mid):
            errors.append(f"{where}: id must be kebab-case")
        if mid in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(mid)
        date = str(m.get("date", ""))
        if date and not DATE_RE.match(date):
            errors.append(f"{where}: date must be YYYY, YYYY-MM or YYYY-MM-DD")
        elif date:
            parts = [int(p) for p in date.split("-")]
            try:
                dt.date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
            except ValueError:
                errors.append(f"{where}: invalid calendar date {date}")
        if m.get("status") and m["status"] not in STATUSES:
            errors.append(f"{where}: status must be one of {sorted(STATUSES)} (or omitted)")
        if m.get("category") and m["category"] not in CATEGORIES:
            errors.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        if len(str(m.get("title", ""))) > 90:
            errors.append(f"{where}: title longer than 90 characters")
        sources = m.get("sources") or []
        if len(sources) < 2:
            errors.append(f"{where}: needs at least 2 sources")
        for s in sources:
            if not str(s.get("url", "")).startswith("https://") and not str(s.get("url", "")).startswith("http://"):
                errors.append(f"{where}: source without a valid url: {s}")
            if not s.get("title"):
                errors.append(f"{where}: source missing title: {s.get('url')}")
            if s.get("kind") and s["kind"] not in SOURCE_KINDS:
                errors.append(f"{where}: source kind must be one of {sorted(SOURCE_KINDS)}")
        img = m.get("image")
        if img:
            if not img.get("file"):
                errors.append(f"{where}: image needs a Commons 'file'")
            if not img.get("alt"):
                errors.append(f"{where}: image needs 'alt' text")
            if str(img.get("file", "")).lower().startswith("file:"):
                errors.append(f"{where}: image file must not include the 'File:' prefix")
        if m.get("diagram"):
            if img:
                errors.append(f"{where}: use either a Commons image or a diagram, not both")
            errors.extend(diagrams.validate(m["diagram"], where))
    return errors


def sort_key(m: dict) -> tuple:
    parts = [int(p) for p in str(m["date"]).split("-")]
    while len(parts) < 3:
        parts.append(0)
    return (*parts, m["id"])


# ---------------------------------------------------------------- Commons images

def load_credits() -> dict:
    if CREDITS_CACHE.exists():
        return json.loads(CREDITS_CACHE.read_text(encoding="utf-8"))
    return {}


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def clean_artist(a: str) -> str:
    """Commons sometimes repeats the author name (e.g. 'Unknown authorUnknown author')."""
    a = (a or "").strip()
    half = len(a) // 2
    if len(a) % 2 == 0 and a and a[:half] == a[half:]:
        a = a[:half]
    return a or "Unknown author"


def flatten_images(credits: dict) -> None:
    """Put transparent images on a white background so line drawings stay visible in dark mode."""
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow not installed; skipping transparency flattening)")
        return
    for c in credits.values():
        path = ROOT / c["path"]
        if not path.exists():
            continue
        with Image.open(path) as im:
            has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
            if not has_alpha:
                continue
            rgba = im.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        bg.convert("RGB").save(path)
        print(f"  flattened transparency: {c['path']}")


def fetch_images(items: list[dict], credits: dict) -> list[str]:
    """Download thumbnails + attribution for every entry with an image. Returns problems."""
    import requests

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    wanted = {m["id"]: m["image"]["file"] for m in items if m.get("image") and m["image"].get("file")}

    for mid, filename in wanted.items():
        cached = credits.get(mid)
        if cached and cached.get("file") == filename and (ROOT / cached["path"]).exists():
            continue
        params = {
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime",
            "iiurlwidth": str(THUMB_WIDTH), "titles": f"File:{filename}", "redirects": "1",
        }
        try:
            r = session.get(COMMONS_API, params=params, timeout=30)
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", [])
        except Exception as exc:  # network problems shouldn't wipe the cache
            problems.append(f"{mid}: Commons lookup failed for '{filename}': {exc}")
            continue
        if not pages or pages[0].get("missing") or not pages[0].get("imageinfo"):
            problems.append(f"{mid}: '{filename}' not found on Wikimedia Commons")
            credits.pop(mid, None)
            continue
        info = pages[0]["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        if not any(h in license_name.lower() for h in FREE_LICENSE_HINTS):
            problems.append(f"{mid}: '{filename}' has an unrecognised license '{license_name}' — skipped")
            credits.pop(mid, None)
            continue
        thumb = info.get("thumburl") or info.get("url")
        ext = Path(urllib.parse.urlparse(thumb).path).suffix.lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
            ext = ".png"
        rel = f"assets/img/{mid}{ext}"
        try:
            img = session.get(thumb, timeout=60)
            img.raise_for_status()
        except Exception as exc:
            problems.append(f"{mid}: download failed for '{filename}': {exc}")
            continue
        for old in IMG_DIR.glob(f"{mid}.*"):
            old.unlink()
        (ROOT / rel).write_bytes(img.content)
        artist = clean_artist(strip_html(meta.get("Artist", {}).get("value", "")))
        credits[mid] = {
            "file": filename,
            "path": rel,
            "page_url": info.get("descriptionurl") or commons_page(filename),
            "artist": artist[:160],
            "license": license_name,
            "license_url": meta.get("LicenseUrl", {}).get("value", ""),
            "fetched": dt.date.today().isoformat(),
        }
        print(f"  image ok: {mid} <- {filename} ({license_name})")

    # forget images for entries that no longer exist or changed to no image
    for mid in list(credits):
        if mid not in wanted:
            for old in IMG_DIR.glob(f"{mid}.*"):
                old.unlink()
            credits.pop(mid)
    return problems


def commons_page(filename: str) -> str:
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(filename.replace(" ", "_"))


def commons_filepath(filename: str, width: int = THUMB_WIDTH) -> str:
    return ("https://commons.wikimedia.org/wiki/Special:FilePath/"
            + urllib.parse.quote(filename.replace(" ", "_")) + f"?width={width}")


# ---------------------------------------------------------------- rendering

def human_date(date: str) -> str:
    parts = [int(p) for p in str(date).split("-")]
    if len(parts) == 3:
        return f"{MONTHS[parts[1] - 1]} {parts[2]}, {parts[0]}"
    if len(parts) == 2:
        return f"{MONTHS[parts[1] - 1]} {parts[0]}"
    return str(parts[0])


def md_escape(text: str) -> str:
    return str(text).replace("|", "\\|").strip()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", text.lower()).strip().replace(" ", "-")


def diagram_path(m: dict) -> str:
    return f"assets/diagrams/{m['id']}.svg"


def write_diagrams(items: list[dict]) -> int:
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {diagram_path(m) for m in items if m.get("diagram")}
    for old in DIAGRAM_DIR.glob("*.svg"):
        if f"assets/diagrams/{old.name}" not in wanted:
            old.unlink()
    for m in items:
        if m.get("diagram"):
            (ROOT / diagram_path(m)).write_text(diagrams.render(m["diagram"]), encoding="utf-8")
    return len(wanted)


def render_image_cell(m: dict, credits: dict) -> str:
    img = m.get("image")
    if not img and m.get("diagram"):
        src = diagram_path(m)
        alt = html.escape(diagrams.alt_text(m["diagram"]), quote=True)
        return (
            '<td width="300" valign="top">'
            f'<a href="{src}"><img src="{src}" width="300" alt="{alt}"></a><br>'
            '<sub>Diagram of figures from this entry\'s sources · CC0 · '
            '<a href="MAINTAINING.md#images-and-diagrams">why a diagram?</a></sub></td>'
        )
    if not img:
        return '<td width="300" valign="top" align="center"><sub><i>No freely licensed image yet</i></sub></td>'
    c = credits.get(m["id"])
    alt = html.escape(img.get("alt", ""), quote=True)
    if c:
        src = c["path"]
        page = c["page_url"]
        lic = html.escape(c.get("license", ""))
        lic_html = f'<a href="{c["license_url"]}">{lic}</a>' if c.get("license_url") else lic
        credit = f'{html.escape(c.get("artist", ""))} · {lic_html}'
    else:  # not fetched yet: hotlink Commons until the build workflow downloads it
        src = commons_filepath(img["file"])
        page = commons_page(img["file"])
        credit = html.escape(img.get("license", "see Wikimedia Commons"))
    return (
        '<td width="300" valign="top">'
        f'<a href="{page}"><img src="{src}" width="300" alt="{alt}"></a><br>'
        f'<sub>{credit} · <a href="{page}">Wikimedia Commons</a></sub></td>'
    )


def render_entry(m: dict, credits: dict) -> str:
    emoji, label = CATEGORIES[m["category"]]
    who = []
    if m.get("system"):
        who.append(f"*{md_escape(m['system'])}*")
    if m.get("opponent"):
        who.append(f"vs. *{md_escape(m['opponent'])}*")
    meta_line = f"**{human_date(m['date'])}** · {emoji} {md_escape(m['field'])}"
    if who:
        meta_line += " · " + " ".join(who)
    sources = " · ".join(
        f"[{md_escape(s['title'])}]({s['url']})" + (f" ({md_escape(s['publisher'])})" if s.get("publisher") else "")
        for s in m["sources"]
    )
    return "\n".join([
        f'<a id="{m["id"]}"></a>',
        "<table><tr>",
        render_image_cell(m, credits),
        '<td valign="top">',
        "",
        f"#### {emoji} {md_escape(m['title'])}",
        meta_line,
        "",
        md_escape(" ".join(str(m["summary"]).split())),
        "",
        *( [STATUSES[m["status"]], ""] if m.get("status") else [] ),
        f"**Why it matters:** {md_escape(' '.join(str(m['significance']).split()))}",
        "",
        f"**Sources:** {sources}",
        "",
        "</td></tr></table>",
        "",
    ])


def decade_of(m: dict) -> str:
    return f"{str(m['date'])[:3]}0s"


def last_data_change() -> str:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", "data/milestones.yaml"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return dt.date.today().isoformat()


def render_readme(items: list[dict], credits: dict, meta: dict) -> str:
    decades: dict[str, list[dict]] = {}
    for m in items:
        decades.setdefault(decade_of(m), []).append(m)
    first_year, last_year = str(items[0]["date"])[:4], str(items[-1]["date"])[:4]
    counts = {k: sum(1 for m in items if m["category"] == k) for k in CATEGORIES}
    reviewed = meta.get("last_reviewed", "")

    out: list[str] = []
    out.append("<!-- This file is generated by scripts/build.py from data/milestones.yaml. Edit the YAML, not this file. -->")
    out.append("# AI Milestones")
    out.append("")
    out.append("**A sourced, illustrated timeline of the moments artificial intelligence crossed a line** — "
               "from the first theorem-proving program to Deep Blue, AlphaGo, AlphaStar, protein folding and olympiad gold.")
    out.append("")
    out.append(f"**{len(items)} milestones** · {first_year}–{last_year} · every entry cites at least two sources · "
               f"data last changed {last_data_change()}" + (f" · last reviewed for new milestones {reviewed}" if reviewed else ""))
    out.append("")
    gh = f"https://github.com/{REPO}/actions/workflows"
    out.append(f"[![Build]({gh}/build.yml/badge.svg)]({gh}/build.yml) "
               f"[![Link check]({gh}/links.yml/badge.svg)]({gh}/links.yml)")
    out.append("")
    out.append("> [!NOTE]")
    out.append("> This timeline is kept up to date automatically: a scheduled review looks for new milestones every week, "
               "and every source link is checked weekly. See [MAINTAINING.md](MAINTAINING.md) for how entries are chosen and verified.")
    out.append("")
    out.append("## Contents")
    out.append("")
    out.append("- [Humans vs. machines](#humans-vs-machines) — every contest that pitted an AI directly against human experts")
    for d in decades:
        out.append(f"- [{d}](#{slug(d)}) ({len(decades[d])})")
    out.append("- [How this repo works](#how-this-repo-works)")
    out.append("")
    out.append("**Categories:** " + " · ".join(f"{e} {lbl} ({counts[k]})" for k, (e, lbl) in CATEGORIES.items() if counts[k]))
    out.append("")

    vs = [m for m in items if m.get("opponent")]
    if vs:
        out.append("## Humans vs. machines")
        out.append("")
        out.append("Every entry where an AI system was measured directly against human experts. "
                   "Most are AI wins; a few are draws, narrow losses or simulated contests — each entry says which.")
        out.append("")
        out.append("| Year | Arena | AI system | Human opponent(s) |")
        out.append("|---|---|---|---|")
        for m in vs:
            out.append(f"| {str(m['date'])[:4]} | [{md_escape(m['field'])}](#{m['id']}) | {md_escape(m.get('system', ''))} | {md_escape(m['opponent'])} |")
        out.append("")

    out.append("## Timeline")
    out.append("")
    for d, ms in decades.items():
        out.append(f"### {d}")
        out.append("")
        for m in ms:
            out.append(render_entry(m, credits))
        out.append("<p align=\"right\"><a href=\"#contents\">↑ back to contents</a></p>")
        out.append("")

    out.append("## How this repo works")
    out.append("")
    out.append("- **Data:** every milestone lives in [`data/milestones.yaml`](data/milestones.yaml) "
               "(also exported as [`data/milestones.json`](data/milestones.json)). This README is generated from it.")
    out.append("- **Images:** only freely licensed images from Wikimedia Commons, each credited with author and license. "
               "Where no free photo exists, some entries show a plain chart of the figures in their own sources instead "
               "(never an illustration or AI-generated picture). Full list in [CREDITS.md](CREDITS.md).")
    out.append("- **Automation:** a weekly scheduled review adds new milestones and fixes broken links ([MAINTAINING.md](MAINTAINING.md)); "
               "GitHub Actions rebuild this page and check every link. Changes are logged in [CHANGELOG.md](CHANGELOG.md).")
    out.append("- **Contributing:** see [CONTRIBUTING.md](CONTRIBUTING.md) for what counts as a milestone.")
    out.append("")
    out.append("Text and data: [CC BY 4.0](LICENSE.md). Images keep their own licenses; diagrams are CC0 (see [CREDITS.md](CREDITS.md)).")
    out.append("")
    return "\n".join(out)


def render_credits(items: list[dict], credits: dict) -> str:
    lines = ["<!-- Generated by scripts/build.py -->", "# Image credits", "",
             "All images come from [Wikimedia Commons](https://commons.wikimedia.org/) under free licenses. "
             "Thumbnails were downloaded and resized; no other changes were made.", "",
             "| Milestone | Image | Author | License |", "|---|---|---|---|"]
    for m in items:
        c = credits.get(m["id"])
        if not c:
            continue
        lic = f"[{md_escape(c['license'])}]({c['license_url']})" if c.get("license_url") else md_escape(c["license"])
        lines.append(f"| [{md_escape(m['title'])}](README.md#{m['id']}) | [{md_escape(c['file'])}]({c['page_url']}) "
                     f"| {md_escape(c['artist'])} | {lic} |")
    lines.append("")
    drawn = [m for m in items if m.get("diagram")]
    if drawn:
        lines += ["## Diagrams", "",
                  "Entries with no freely licensed photo may show a simple chart instead. Each one plots only figures "
                  "stated in the entry, which come from its cited sources. The charts are drawn by "
                  "[`scripts/diagrams.py`](scripts/diagrams.py) and released under "
                  "[CC0](https://creativecommons.org/publicdomain/zero/1.0/).", "",
                  "| Milestone | Diagram |", "|---|---|"]
        for m in drawn:
            lines.append(f"| [{md_escape(m['title'])}](README.md#{m['id']}) | [{diagram_path(m)}]({diagram_path(m)}) |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download images and attribution from Wikimedia Commons")
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args()

    items = load_milestones()
    errors = validate(items)
    if errors:
        print("Validation failed:")
        for e in errors:
            print("  -", e)
        return 1
    items.sort(key=sort_key)
    print(f"{len(items)} milestones valid.")
    if args.check:
        return 0
    if not items:
        print("No milestones yet; nothing to render.")
        return 0

    meta = yaml.safe_load(META.read_text(encoding="utf-8")) if META.exists() else {}
    credits = load_credits()
    problems: list[str] = []
    if args.fetch:
        problems = fetch_images(items, credits)
    for c in credits.values():
        c["artist"] = clean_artist(c.get("artist", ""))
    flatten_images(credits)
    CREDITS_CACHE.write_text(json.dumps(credits, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")

    n_diagrams = write_diagrams(items)
    README.write_text(render_readme(items, credits, meta or {}), encoding="utf-8")
    CREDITS_MD.write_text(render_credits(items, credits), encoding="utf-8")
    export = [{k: v for k, v in dict(m, image_credit=credits.get(m["id"]),
                                      diagram_file=diagram_path(m) if m.get("diagram") else None).items()
               if k != "notes"} for m in items]
    JSON_OUT.write_text(json.dumps(export, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Wrote README.md, CREDITS.md, data/milestones.json and {n_diagrams} diagrams")

    missing = [m["id"] for m in items if m.get("image") and m["id"] not in credits]
    if problems:
        print("\nImage problems:")
        for p in problems:
            print("  -", p)
    if args.fetch and (problems or missing):
        # surface as a GitHub Actions warning without failing the build
        for p in problems:
            print(f"::warning title=Image problem::{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
