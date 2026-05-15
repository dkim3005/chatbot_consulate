from __future__ import annotations

import html
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.robotparser import RobotFileParser


BASE_URL = "https://www.mofa.go.kr"
BOARD_URL = "https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do"
ROBOTS_URL = "https://www.mofa.go.kr/robots.txt"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class Link:
    href: str
    text: str


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[Link] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        self._href = attr_map.get("href")
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = normalize_text(" ".join(self._text))
            self.links.append(Link(self._href, text))
            self._href = None
            self._text = []


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"p", "div", "li", "tr", "table"}:
            self.parts.append("\n")

    def text(self) -> str:
        return normalize_text("\n".join(self.parts))


def fetch(url: str) -> tuple[int, str]:
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    with urlopen(request, timeout=20) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return response.status, body


def normalize_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\n\s*\n\s*\n+", "\n\n", value)
    return value.strip()


def can_fetch_robots() -> bool:
    parser = RobotFileParser()
    parser.set_url(ROBOTS_URL)
    parser.read()
    return parser.can_fetch(USER_AGENT, BOARD_URL)


def parse_links(document: str) -> list[Link]:
    parser = LinkParser()
    parser.feed(document)
    return parser.links


def candidate_detail_links(links: Iterable[Link]) -> list[Link]:
    candidates: list[Link] = []
    seen: set[str] = set()
    for link in links:
        href = link.href or ""
        if "view.do" not in href and "seq=" not in href:
            continue
        absolute = urljoin(BOARD_URL, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        candidates.append(Link(absolute, link.text))
    return candidates


def extract_title(document: str) -> str | None:
    patterns = [
        r"<h\d[^>]*>(.*?)</h\d>",
        r"<th[^>]*>\s*제목\s*</th>\s*<td[^>]*>(.*?)</td>",
        r"<div[^>]+class=[\"'][^\"']*(?:title|subject|view_tit)[^\"']*[\"'][^>]*>(.*?)</div>",
    ]
    for pattern in patterns:
        match = re.search(pattern, document, flags=re.I | re.S)
        if match:
            return html_to_text(match.group(1))
    return None


def html_to_text(fragment: str) -> str:
    parser = TextParser()
    parser.feed(fragment)
    return parser.text()


def extract_meta_date(document: str) -> str | None:
    match = re.search(r"(?:작성일|등록일)\s*</[^>]+>\s*<[^>]+>\s*([0-9]{4}[-.][0-9]{2}[-.][0-9]{2})", document, flags=re.I)
    if match:
        return match.group(1)
    match = re.search(r"([0-9]{4}[-.][0-9]{2}[-.][0-9]{2})", document)
    return match.group(1) if match else None


def summarize_detail(document: str) -> dict[str, object]:
    text = html_to_text(document)
    body_markers = [
        "view_cont",
        "view-con",
        "board_view",
        "viewContent",
        "bbs_view",
        "view_content",
        "cont_view",
    ]
    selector_hits = {marker: bool(re.search(marker, document, flags=re.I)) for marker in body_markers}
    return {
        "title": extract_title(document),
        "date": extract_meta_date(document),
        "text_length": len(text),
        "has_table": bool(re.search(r"<table\b", document, flags=re.I)),
        "has_attachment_hint": bool(re.search(r"첨부|download|fileDown|atch", document, flags=re.I)),
        "selector_hits": selector_hits,
        "text_preview": text[:700],
    }


def main() -> int:
    print("Target board: 여권")
    print(f"Board URL: {BOARD_URL}")

    try:
        print(f"robots.txt can_fetch: {can_fetch_robots()}")
    except Exception as exc:
        print(f"robots.txt check failed: {exc}")

    try:
        status, list_html = fetch(BOARD_URL)
    except URLError as exc:
        print(f"List fetch failed: {exc}")
        print("Diagnosis: direct Python HTTP access is not currently enough from this environment.")
        print("Next check: reproduce the site security cookie/redirect flow or use a browser-capable fetcher.")
        return 2
    except OSError as exc:
        print(f"List fetch failed: {exc}")
        print("Diagnosis: direct Python HTTP access is not currently enough from this environment.")
        print("Next check: reproduce the site security cookie/redirect flow or use a browser-capable fetcher.")
        return 2
    links = parse_links(list_html)
    detail_links = candidate_detail_links(links)
    count_match = re.search(r"전체\s*([0-9,]+)\s*건", html_to_text(list_html))

    print(f"List HTTP status: {status}")
    print(f"List HTML bytes: {len(list_html.encode('utf-8'))}")
    print(f"Static list count text: {count_match.group(1) if count_match else 'not found'}")
    print(f"Candidate detail links: {len(detail_links)}")

    if not detail_links:
        print("No detail link found. This board may require JS/form reproduction.")
        return 1

    sample = detail_links[0]
    print(f"Sample title from list: {sample.text}")
    print(f"Sample detail URL: {sample.href}")

    try:
        detail_status, detail_html = fetch(sample.href)
    except URLError as exc:
        print(f"Detail fetch failed: {exc}")
        return 2
    except OSError as exc:
        print(f"Detail fetch failed: {exc}")
        return 2
    summary = summarize_detail(detail_html)
    print(f"Detail HTTP status: {detail_status}")
    print(f"Detail HTML bytes: {len(detail_html.encode('utf-8'))}")
    print(f"Parsed title candidate: {summary['title'] or 'not found'}")
    print(f"Parsed date candidate: {summary['date'] or 'not found'}")
    print(f"Detail text length: {summary['text_length']}")
    print(f"Has table: {summary['has_table']}")
    print(f"Has attachment hint: {summary['has_attachment_hint']}")
    print("Selector marker hits:")
    for marker, found in summary["selector_hits"].items():
        print(f"  - {marker}: {found}")
    print("Text preview:")
    print(summary["text_preview"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
