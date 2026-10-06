#!/usr/bin/env python3
"""Build the profile's self-contained SVG cards from publicly visible data."""

import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "HenriqueMayer"
CHESS_USERNAME = "hrmayer"
USER_AGENT = "HenriqueMayer-profile/1.0 (https://github.com/HenriqueMayer/HenriqueMayer)"
PALETTES = {
    "dark": dict(paper="#111113", surface="#19191C", raised="#242427", ink="#F0EEE9",
                 muted="#AAA9A4", line="#303033", green="#7FBFA9", sage="#91B9A7",
                 copper="#CFAA80", gold="#C4BA7E"),
    "light": dict(paper="#F7F7F5", surface="#FFFFFF", raised="#ECECEE", ink="#202124",
                  muted="#5B5C60", line="#DEDEE1", green="#176B52", sage="#668475",
                  copper="#B88A59", gold="#7C5C13"),
}


def fetch(url, *, as_json=True):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json" if as_json else "text/html"})
    with urlopen(request, timeout=25) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if as_json else body


class ContributionCalendar(HTMLParser):
    """Join GitHub's dated cells to their accessible count tooltips."""

    def __init__(self):
        super().__init__()
        self.cells = {}
        self.tooltips = {}
        self.current_tooltip = None

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if tag in ("td", "rect") and "data-date" in attributes:
            if attributes["id"] in self.cells:
                raise ValueError(f"Duplicate contribution cell: {attributes['id']}")
            self.cells[attributes["id"]] = {
                "date": attributes["data-date"],
                "level": int(attributes["data-level"]),
            }
        if tag == "tool-tip" and "for" in attributes:
            self.current_tooltip = attributes["for"]
            self.tooltips[self.current_tooltip] = ""

    def handle_data(self, data):
        if self.current_tooltip is not None:
            self.tooltips[self.current_tooltip] += data

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.current_tooltip = None


def parse_calendar(body, first, last):
    parser = ContributionCalendar()
    parser.feed(body)
    days = {}
    for cell_id, cell in parser.cells.items():
        day = date.fromisoformat(cell["date"])
        if not first <= day <= last:
            continue
        tooltip = " ".join(parser.tooltips.get(cell_id, "").split())
        match = re.match(r"([\d,]+) contributions? on ", tooltip)
        if match:
            count = int(match.group(1).replace(",", ""))
        elif tooltip.startswith("No contributions on "):
            count = 0
        else:
            raise ValueError(f"Unrecognized contribution count for {day}: {tooltip!r}")
        if not 0 <= cell["level"] <= 4 or (count == 0) != (cell["level"] == 0):
            raise ValueError(f"Invalid contribution level for {day}")
        if day.isoformat() in days:
            raise ValueError(f"Duplicate contribution day: {day}")
        days[day.isoformat()] = dict(date=day.isoformat(), count=count, level=cell["level"])
    expected = {(first + timedelta(days=i)).isoformat() for i in range((last - first).days + 1)}
    if set(days) != expected:
        raise ValueError(f"Incomplete contribution calendar: expected {len(expected)} dates, received {len(days)}")
    return [days[key] for key in sorted(days)]


def collect(today):
    api = "https://api.github.com"
    user = fetch(f"{api}/users/{USERNAME}")
    repositories = []
    page = 1
    while True:
        batch = fetch(f"{api}/users/{USERNAME}/repos?type=owner&per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("GitHub returned an invalid repository list")
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    public_repositories = [repo for repo in repositories if not repo["private"] and repo["owner"]["login"].lower() == USERNAME.lower()]
    if len(public_repositories) != user["public_repos"]:
        raise ValueError("Repository list and public-repository count disagree; retry after GitHub's cache settles")
    code_repositories = [repo for repo in public_repositories if not repo["fork"] and repo["name"].lower() != USERNAME.lower()]
    languages = Counter()
    for repo in code_repositories:
        language_bytes = fetch(f"{api}/repos/{USERNAME}/{repo['name']}/languages")
        if not isinstance(language_bytes, dict) or any(not isinstance(value, int) or value < 0 for value in language_bytes.values()):
            raise ValueError(f"Invalid language bytes for {repo['name']}")
        languages.update(language_bytes)
    first = today - timedelta(days=364)
    calendar_url = f"https://github.com/users/{USERNAME}/contributions"
    days = parse_calendar(fetch(calendar_url, as_json=False), first, today)
    chess = fetch(f"https://api.chess.com/pub/player/{CHESS_USERNAME}/stats")
    puzzle_best = chess["puzzle_rush"]["best"]["score"]
    if not isinstance(puzzle_best, int) or puzzle_best < 0:
        raise ValueError("Invalid Chess.com Puzzle Rush personal best")
    return {
        "updated_utc": today.isoformat(),
        "username": USERNAME,
        "contribution_period": {"from": first.isoformat(), "to": today.isoformat(), "days": 365},
        "visible_contributions": sum(day["count"] for day in days),
        "active_days": sum(day["count"] > 0 for day in days),
        "public_repositories": len(public_repositories),
        "code_repositories": sorted(repo["name"] for repo in code_repositories),
        "language_bytes": dict(sorted(languages.items(), key=lambda pair: (-pair[1], pair[0]))),
        "calendar": days,
        "chess": {"username": CHESS_USERNAME, "puzzle_rush_best": puzzle_best},
        "sources": {"profile": f"{api}/users/{USERNAME}", "repositories": f"{api}/users/{USERNAME}/repos",
                    "calendar": calendar_url, "chess": f"https://api.chess.com/pub/player/{CHESS_USERNAME}/stats"},
    }


def text(x, y, value, size, color, *, weight=400, anchor="start", spacing=None):
    letter_spacing = f' letter-spacing="{spacing}"' if spacing is not None else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}"{letter_spacing}>{escape(str(value))}</text>'


def rect(x, y, width, height, fill, radius=0, **attributes):
    extras = " ".join(f'{key.rstrip("_").replace("_", "-")}="{escape(str(value))}"' for key, value in attributes.items())
    return f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{fill}" {extras}/>'


def svg(width, height, palette, body, title, description):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">
<title id="title">{escape(title)}</title><desc id="description">{escape(description)}</desc>
<style>text{{font-family:Inter,Arial,sans-serif}}.shine{{animation:shine 8s ease-in-out infinite}}.knight{{animation:knight 12s ease-in-out infinite}}@keyframes shine{{0%,100%{{opacity:.25}}50%{{opacity:.8}}}}@keyframes knight{{0%,16%,100%{{transform:translate(0,0)}}25%,41%{{transform:translate(2px,-1px)}}50%,66%{{transform:translate(1px,-3px)}}75%,91%{{transform:translate(-1px,-2px)}}}}@media(prefers-reduced-motion:reduce){{.shine,.knight{{animation:none}}}}</style>
{rect(1,1,width-2,height-2,palette['paper'],24,stroke=palette['line'])}
{body}
</svg>
'''


def language_mix(data):
    ranked = list(data["language_bytes"].items())
    total = sum(value for _, value in ranked)
    if not total:
        return []
    groups = ranked[:3]
    remaining = sum(value for _, value in ranked[3:])
    if remaining:
        groups.append(("Other", remaining))
    return [(name, value / total) for name, value in groups]


def calendar_art(data, palette, *, mobile):
    today = date.fromisoformat(data["updated_utc"])
    weeks = 12 if mobile else 16
    sunday = today - timedelta(days=(today.weekday() + 1) % 7)
    first = sunday - timedelta(weeks=weeks - 1)
    cells = {day["date"]: day for day in data["calendar"]}
    x, y, step_x, step_y, side = (84, 439, 47, 33, 27) if mobile else (94, 316, 38, 25, 19)
    parts = []
    previous_month = None
    for week in range(weeks):
        day = first + timedelta(weeks=week)
        if day.month != previous_month:
            parts.append(text(x + week * step_x, y - 18, day.strftime("%b").upper(), 20 if mobile else 15, palette["muted"]))
            previous_month = day.month
        for weekday in range(7):
            day = first + timedelta(days=week * 7 + weekday)
            cell = cells.get(day.isoformat())
            level = cell["level"] if cell else 0
            fill = palette["raised"] if level == 0 else palette["green"]
            opacity = (0.28, 0.46, 0.67, 0.9)[level - 1] if level else 1
            if day > today:
                opacity = .25
            count = f"{cell['count']} visible contributions" if cell else "Outside this snapshot"
            parts.append(f'<g><title>{day.isoformat()}: {count}</title>' + rect(x + week * step_x, y + weekday * step_y, side, side, fill, 4, opacity=opacity) + "</g>")
    for weekday, label in ((1, "M"), (3, "W"), (5, "F")):
        parts.append(text(x - 28, y + weekday * step_y + side - 3, label, 22 if mobile else 16, palette["muted"], anchor="middle"))
    legend_y = y + step_y * 7 + (19 if mobile else 18)
    parts.append(text(x, legend_y + 4, "LESS", 18 if mobile else 13, palette["muted"], spacing=1))
    for level in range(5):
        fill = palette["raised"] if level == 0 else palette["green"]
        opacity = (0.28, 0.46, 0.67, 0.9)[level - 1] if level else 1
        parts.append(rect(x + (72 if mobile else 48) + level * (23 if mobile else 17), legend_y - (15 if mobile else 10), 17 if mobile else 12, 17 if mobile else 12, fill, 3, opacity=opacity))
    parts.append(text(x + (200 if mobile else 141), legend_y + 4, "MORE", 18 if mobile else 13, palette["muted"], spacing=1))
    return "\n".join(parts), first, today


def github_art(data, theme, *, mobile=False):
    p = PALETTES[theme]
    parts = []
    width, height = (720, 900) if mobile else (1200, 560)
    parts.append(text(40 if mobile else 48, 55 if mobile else 52, "01 / GITHUB ACTIVITY", 26 if mobile else 21, p["muted"], spacing=2))
    parts.append(text(40 if mobile else 1152, 90 if mobile else 52, f"UPDATED {data['updated_utc']} UTC", 22 if mobile else 17, p["muted"], anchor="start" if mobile else "end"))
    metrics = ((data["visible_contributions"], "Visible contributions"), (data["active_days"], "Active days"), (data["public_repositories"], "Public repositories"))
    if mobile:
        for i, (value, label) in enumerate(metrics[:2]):
            x = 40 + i * 342
            parts += [text(x, 179, f"{value:,}", 76, p["ink"], weight=600), text(x, 218, label, 25, p["muted"]), text(x, 246, "LAST 365 DAYS", 20, p["green"], spacing=1)]
        parts += [text(40, 320, data["public_repositories"], 58, p["ink"], weight=600), text(109, 315, "Public repositories", 26, p["muted"])]
        parts.append(rect(40, 351, 640, 1, p["line"]))
        parts.append(text(40, 391, "CONTRIBUTION CALENDAR", 24, p["ink"], weight=500, spacing=1))
    else:
        for i, (value, label) in enumerate(metrics):
            x = 48 + i * 365
            parts += [text(x, 151, f"{value:,}", 72, p["ink"], weight=600), text(x, 190, label, 23, p["muted"])]
        parts.append(text(48, 223, "LAST 365 DAYS / AS SHOWN ON GITHUB", 16, p["green"], spacing=1.2))
        parts.append(rect(48, 250, 1104, 1, p["line"]))
        parts.append(text(48, 285, "CONTRIBUTION CALENDAR", 18, p["ink"], weight=500, spacing=1))
        parts.append(rect(782, 278, 1, 224, p["line"]))
    calendar, first, last = calendar_art(data, p, mobile=mobile)
    parts.append(calendar)
    if mobile:
        parts.append(text(680, 708, "12 WEEK VIEW / UTC", 18, p["muted"], anchor="end"))
        parts.append(rect(40, 744, 640, 1, p["line"]))
        parts.append(text(40, 785, "PUBLIC CODE BY BYTES", 24, p["ink"], weight=500, spacing=1))
    else:
        parts.append(text(726, 507, f"{first.strftime('%b %d').upper()} — {last.strftime('%b %d').upper()} / UTC", 14, p["muted"], anchor="end"))
        parts.append(text(824, 285, "PUBLIC CODE BY BYTES", 18, p["ink"], weight=500, spacing=1))
    groups = language_mix(data)
    colors = [p["green"], p["sage"], p["copper"], p["gold"]]
    if mobile:
        offset = 40
        parts.append(rect(40, 806, 640, 12, p["raised"], 4))
        for i, (name, fraction) in enumerate(groups):
            segment = 640 * fraction
            parts.append(rect(round(offset, 2), 806, round(segment, 2), 12, colors[i]))
            offset += segment
            x, y = 40 + (i % 2) * 342, 851 + (i // 2) * 31
            parts.append(rect(x, y - 17, 12, 12, colors[i], 3))
            parts.append(text(x + 23, y, f"{name} {fraction:.1%}", 23, p["muted"]))
    else:
        for i, (name, fraction) in enumerate(groups):
            y = 326 + i * 50
            parts += [text(824, y, name, 18, p["muted"]), text(1152, y, f"{fraction:.1%}", 18, p["muted"], anchor="end"), rect(824, y + 11, 328, 6, p["raised"], 3), rect(824, y + 11, round(328 * fraction, 2), 6, colors[i], 3)]
        if not groups:
            parts.append(text(824, 342, "No public code yet", 18, p["muted"]))
        parts.append(text(824, 526, "OWNED SOURCES / EXCLUDES FORKS", 13, p["muted"], spacing=.5))
    parts.append(rect(40 if mobile else 48, height - 2, width - (80 if mobile else 96), 1, p["green"], class_="shine"))
    body = "\n".join(parts)
    description = f"{data['visible_contributions']} visible GitHub contributions and {data['active_days']} active days from {data['contribution_period']['from']} through {data['updated_utc']} UTC. {data['public_repositories']} owned public repositories. Contributions may include anonymized private activity already visible on GitHub. Languages are public repository code bytes, excluding forks and the profile repository."
    return svg(width, height, p, body, "Henrique Mayer / GitHub activity", description)


def chess_board(p, x, y, size):
    square = size / 8
    parts = []
    for row in range(8):
        for column in range(8):
            parts.append(rect(x + column * square, y + row * square, square, square, p["raised"] if (row + column) % 2 else p["surface"]))
    # Original abstract knight silhouette; positions b2 -> d3 -> c5 -> a4 -> b2.
    knight = 'M.20 .76H.80V.88H.20ZM.29 .68L.36 .49L.23 .48L.18 .36L.36 .19L.47 .16L.48 .07L.59 .16L.66 .20C.77 .31 .78 .46 .72 .58L.73 .68ZM.34 .30L.31 .35L.37 .36L.39 .31Z'
    parts.append(f'<g transform="translate({x + square},{y + 6 * square}) scale({square})"><g class="knight"><path d="{knight}" fill="{p["copper"]}" fill-rule="evenodd"/></g></g>')
    parts.append(rect(x, y, size, size, "none", 0, stroke=p["line"], stroke_width=1))
    return "\n".join(parts)


def chess_art(data, theme, *, mobile=False):
    p = PALETTES[theme]
    width, height = (720, 430) if mobile else (1200, 240)
    best = data["chess"]["puzzle_rush_best"]
    parts = [text(40 if mobile else 48, 53 if mobile else 45, "02 / OFF THE KEYBOARD", 25 if mobile else 19, p["muted"], spacing=2), text(40 if mobile else 48, 121 if mobile else 103, "One more move.", 46 if mobile else 42, p["ink"], weight=500), text(40 if mobile else 48, 159 if mobile else 139, "Chess.com / hrmayer", 25 if mobile else 21, p["muted"])]
    if mobile:
        parts += [text(40, 235, "PUZZLE RUSH BEST", 23, p["muted"], spacing=1), text(40, 308, best, 68, p["copper"], weight=600), text(40, 361, "Let's play a game.", 24, p["ink"]), text(40, 401, "ILLUSTRATIVE BOARD", 18, p["muted"], spacing=1), chess_board(p, 434, 178, 232)]
    else:
        parts += [text(48, 192, "Let's play a game.", 21, p["ink"]), rect(478, 52, 1, 139, p["line"]), text(525, 79, "PUZZLE RUSH BEST", 17, p["muted"], spacing=1), text(525, 155, best, 70, p["copper"], weight=600), text(525, 192, "Personal best / Chess.com", 16, p["muted"]), chess_board(p, 900, 25, 168), text(984, 219, "ILLUSTRATIVE BOARD", 13, p["muted"], anchor="middle", spacing=1)]
    description = f"Henrique Mayer plays chess as hrmayer. Puzzle Rush personal best: {best}, fetched on {data['updated_utc']} UTC. The animated knight follows legal L-shaped moves on an illustrative board; this is not a live game."
    return svg(width, height, p, "\n".join(parts), "Henrique Mayer / Off the keyboard", description)


def render(data):
    files = {"assets/profile-data.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n"}
    for theme in PALETTES:
        for mobile in (False, True):
            suffix = "-mobile" if mobile else ""
            files[f"assets/github-{theme}{suffix}.svg"] = github_art(data, theme, mobile=mobile)
            files[f"assets/chess-{theme}{suffix}.svg"] = chess_art(data, theme, mobile=mobile)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, help="Last contribution date; default is today in UTC")
    args = parser.parse_args()
    today = args.date or datetime.now(timezone.utc).date()
    try:
        data = collect(today)
        files = render(data)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Profile refresh failed: {error}. Previous data and artwork were preserved.", file=sys.stderr)
        return 1
    for relative, content in files.items():
        path = ROOT / relative
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    print(f"Updated {len(files)} generated files: {data['visible_contributions']} visible contributions, {data['active_days']} active days, {data['public_repositories']} public repositories; ending {today} UTC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
