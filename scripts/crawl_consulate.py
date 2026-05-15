from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlunparse

import requests


FETCH_BASE = "https://toronto.mofa.go.kr"
CANONICAL_BASE = "https://www.mofa.go.kr"
SITE_PATH = "/ca-toronto-ko/brd"

BOARDS = [
    ("여권", "m_5389", "passport"),
    ("비자", "m_5390", "visa"),
    ("양식 다운로드", "m_5396", "forms"),
    ("공증", "m_5391", "notarization"),
    ("병역", "m_5392", "military"),
    ("가족관계등록", "m_5393", "family_registry"),
    ("국적", "m_5394", "nationality"),
    ("공동인증서", "m_27012", "certificate"),
    ("각종 증명서 발급", "m_21301", "certificates"),
    ("재외국민등록", "m_5395", "overseas_registration"),
    ("해외이주신고", "m_24767", "emigration"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass(frozen=True)
class Board:
    topic: str
    board_id: str
    slug: str

    @property
    def list_url(self) -> str:
        return f"{FETCH_BASE}{SITE_PATH}/{self.board_id}/list.do"


@dataclass
class ListItem:
    topic: str
    board_id: str
    board_url: str
    post_number: str
    title: str
    post_date: str
    seq: str
    url: str
    has_attachment: bool


class TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "ol",
        "p",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_entityref(self, name: str) -> None:
        self.parts.append(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.parts.append(html.unescape(f"&#{name};"))

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        text = "".join(self.parts)
        text = html.unescape(text)
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(fragment: str) -> str:
    parser = TextExtractor()
    parser.feed(fragment)
    return parser.text()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_text(value: str) -> str:
    return html_to_text(value)


def clean_title(value: str) -> str:
    lines = [line.strip() for line in clean_text(value).splitlines() if line.strip()]
    lines = [line for line in lines if line != "공지"]
    return "\n".join(lines).strip()


def absolute_fetch_url(path_or_url: str) -> str:
    if path_or_url.startswith("http"):
        parsed = urlparse(path_or_url)
        return urlunparse(parsed._replace(scheme="https", netloc="toronto.mofa.go.kr"))
    return urljoin(FETCH_BASE, path_or_url)


def canonical_url(board_id: str, seq: str) -> str:
    return f"{CANONICAL_BASE}{SITE_PATH}/{board_id}/view.do?seq={seq}"


def fetch(session: requests.Session, url: str, timeout: int = 25, retries: int = 4) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(min(2**attempt, 10))
    assert last_error is not None
    raise last_error


def extract_balanced_div(document: str, class_name: str) -> str | None:
    match = re.search(
        rf"<div\b[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>",
        document,
        flags=re.I,
    )
    if not match:
        return None
    start = match.start()
    pos = match.end()
    depth = 1
    token_re = re.compile(r"</?div\b[^>]*>", re.I)
    for token in token_re.finditer(document, pos):
        token_text = token.group(0)
        if token_text.startswith("</"):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return document[start : token.end()]
    return None


def parse_total_pages(list_html: str) -> tuple[int | None, int]:
    text = html_to_text(list_html)
    total_match = re.search(r"전체\s*([0-9,]+)\s*건", text)
    page_match = re.search(r"([0-9]+)\s*/\s*([0-9]+)\s*페이지", text)
    total = int(total_match.group(1).replace(",", "")) if total_match else None
    pages = int(page_match.group(2)) if page_match else 1
    return total, max(pages, 1)


def parse_list_items(board: Board, list_html: str) -> list[ListItem]:
    tbody_match = re.search(r"<tbody>(.*?)</tbody>", list_html, flags=re.I | re.S)
    if not tbody_match:
        return []

    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", tbody_match.group(1), flags=re.I | re.S)
    items: list[ListItem] = []
    for row in rows:
        seq_match = re.search(r"f_view\('([0-9]+)'\)", row)
        if not seq_match:
            continue
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if len(cells) < 4:
            continue

        seq = seq_match.group(1)
        post_number = clean_text(cells[0])
        title = clean_title(cells[1])
        post_date = clean_text(cells[-1])
        has_attachment = "icon_board_file" in row or "첨부파일" in row
        items.append(
            ListItem(
                topic=board.topic,
                board_id=board.board_id,
                board_url=f"{CANONICAL_BASE}{SITE_PATH}/{board.board_id}/list.do",
                post_number=post_number,
                title=title,
                post_date=post_date,
                seq=seq,
                url=canonical_url(board.board_id, seq),
                has_attachment=has_attachment,
            )
        )
    return items


def parse_detail(board: Board, seq: str, detail_html: str) -> dict[str, object]:
    detail = extract_balanced_div(detail_html, "board_detail")
    if detail is None:
        return {
            "title": "",
            "post_date": "",
            "modified_date": "",
            "content_html": "",
            "content_text": "",
            "attachments": [],
            "status": "parse_failed",
        }

    title_match = re.search(r"<h2[^>]*>(.*?)</h2>", detail, flags=re.I | re.S)
    title = clean_title(title_match.group(1)) if title_match else ""

    post_date = ""
    modified_date = ""
    date_pairs = re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", detail, flags=re.I | re.S)
    for label_html, value_html in date_pairs:
        label = clean_text(label_html)
        value = clean_text(value_html)
        if label == "작성일":
            post_date = value
        elif label == "수정일":
            modified_date = value

    attachments = parse_attachments(detail, board.board_id, seq)
    content_html = extract_balanced_div(detail, "bo_con") or ""
    content_text = html_to_text(content_html) if content_html else ""
    status = "active"
    if not content_html:
        status = "parse_failed"
    elif not content_text:
        status = "empty_body"

    return {
        "title": title,
        "post_date": post_date,
        "modified_date": modified_date,
        "content_html": content_html,
        "content_text": content_text,
        "attachments": attachments,
        "status": status,
    }


def parse_attachments(detail_html: str, board_id: str, seq: str) -> list[dict[str, str]]:
    file_block = extract_balanced_div(detail_html, "bo_file")
    if not file_block:
        return []

    attachments: list[dict[str, str]] = []
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", file_block, flags=re.I | re.S):
        name_match = re.search(r"<span[^>]*>(.*?)</span>", item, flags=re.I | re.S)
        href_match = re.search(r"f_down\('([^']+)'\)", item, flags=re.I | re.S)
        if not name_match:
            continue
        filename = clean_text(name_match.group(1))
        href = html.unescape(href_match.group(1)) if href_match else ""
        download_url = absolute_fetch_url(f"{SITE_PATH}/{board_id}/{href[2:]}") if href.startswith("./") else absolute_fetch_url(href)
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        attachments.append(
            {
                "filename": filename,
                "url": download_url,
                "extension": extension,
                "seq": seq,
            }
        )
    return attachments


def dedupe_items(items: Iterable[ListItem]) -> list[ListItem]:
    seen: set[str] = set()
    unique: list[ListItem] = []
    for item in items:
        key = f"{item.board_id}:{item.seq}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def crawl_board(
    session: requests.Session,
    board: Board,
    output_dir: Path,
    delay: float,
    max_posts: int | None = None,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    print(f"[{board.topic}] 목록 수집: {board.list_url}")
    first_html = fetch(session, board.list_url)
    total_count, total_pages = parse_total_pages(first_html)
    list_items = parse_list_items(board, first_html)

    for page in range(2, total_pages + 1):
        time.sleep(delay)
        page_url = f"{board.list_url}?page={page}"
        page_html = fetch(session, page_url)
        list_items.extend(parse_list_items(board, page_html))

    list_items = dedupe_items(list_items)
    if max_posts is not None:
        list_items = list_items[:max_posts]

    records: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for index, item in enumerate(list_items, start=1):
        time.sleep(delay)
        detail_url = f"{FETCH_BASE}{SITE_PATH}/{board.board_id}/view.do?seq={item.seq}&page=1"
        print(f"[{board.topic}] {index}/{len(list_items)} {item.seq} {item.title}")
        try:
            detail_html = fetch(session, detail_url)
            raw_dir = output_dir / "raw_html" / board.slug
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{item.seq}.html"
            raw_path.write_text(detail_html, encoding="utf-8")

            detail = parse_detail(board, item.seq, detail_html)
            title = str(detail["title"] or item.title)
            post_date = str(detail["post_date"] or item.post_date)
            content_text = str(detail["content_text"])
            content_html = str(detail["content_html"])
            record = {
                "post_id": f"{board.board_id}_{item.seq}",
                "topic": item.topic,
                "board_id": item.board_id,
                "board_url": item.board_url,
                "post_number": item.post_number,
                "title": title,
                "post_date": post_date,
                "modified_date": detail["modified_date"],
                "url": item.url,
                "fetch_url": detail_url,
                "content_text": content_text,
                "content_html": content_html,
                "raw_html_path": str(raw_path),
                "attachments": detail["attachments"],
                "fetched_at": datetime.now().astimezone().isoformat(),
                "content_sha256": sha256_text(content_text),
                "content_html_sha256": sha256_text(content_html),
                "raw_html_sha256": sha256_text(detail_html),
                "status": detail["status"],
            }
            records.append(record)
        except Exception as exc:  # noqa: BLE001 - report must preserve crawl failures.
            failures.append({"seq": item.seq, "title": item.title, "error": f"{type(exc).__name__}: {exc}"})

    report = {
        "topic": board.topic,
        "board_id": board.board_id,
        "listed_total": total_count,
        "pages": total_pages,
        "list_items_after_dedupe": len(list_items),
        "saved": len(records),
        "failures": failures,
        "empty_body": sum(1 for record in records if record["status"] == "empty_body"),
        "parse_failed": sum(1 for record in records if record["status"] == "parse_failed"),
    }
    return records, report


def make_chunks(records: Iterable[dict[str, object]], chunk_size: int = 1100, overlap: int = 150) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for record in records:
        if record.get("status") != "active":
            continue
        text = str(record.get("content_text", ""))
        if not text:
            continue
        starts = [0]
        while starts[-1] + chunk_size < len(text):
            starts.append(max(starts[-1] + chunk_size - overlap, starts[-1] + 1))
        for idx, start in enumerate(starts, start=1):
            end = min(len(text), start + chunk_size)
            chunks.append(
                {
                    "chunk_id": f"{record['post_id']}_chunk_{idx:03d}",
                    "post_id": record["post_id"],
                    "topic": record["topic"],
                    "title": record["title"],
                    "post_date": record["post_date"],
                    "url": record["url"],
                    "text": text[start:end],
                    "char_start": start,
                    "char_end": end,
                    "content_sha256": record["content_sha256"],
                }
            )
    return chunks


def write_report(path: Path, reports: list[dict[str, object]], record_count: int, chunk_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 크롤링 리포트",
        "",
        f"실행 시각: {datetime.now().astimezone().isoformat()}",
        "",
        "| 주제 | 목록 건수 | 페이지 | 상세 링크 | 저장 성공 | 실패 | empty_body | parse_failed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for report in reports:
        lines.append(
            "| {topic} | {listed_total} | {pages} | {list_items_after_dedupe} | {saved} | {failures} | {empty_body} | {parse_failed} |".format(
                topic=report["topic"],
                listed_total=report["listed_total"] if report["listed_total"] is not None else "",
                pages=report["pages"],
                list_items_after_dedupe=report["list_items_after_dedupe"],
                saved=report["saved"],
                failures=len(report["failures"]),
                empty_body=report["empty_body"],
                parse_failed=report["parse_failed"],
            )
        )
    lines.extend(["", f"- 저장 게시글: {record_count}", f"- 생성 chunk: {chunk_count}", ""])
    failures = [report for report in reports if report["failures"]]
    if failures:
        lines.append("## 실패 목록")
        lines.append("")
        for report in failures:
            for failure in report["failures"]:
                lines.append(f"- {report['topic']} / {failure['seq']} / {failure['title']} / {failure['error']}")
    path.write_text("\n".join(lines), encoding="utf-8")


def selected_boards(values: list[str] | None) -> list[Board]:
    boards = [Board(topic, board_id, slug) for topic, board_id, slug in BOARDS]
    if not values:
        return boards
    wanted = set(values)
    return [board for board in boards if board.topic in wanted or board.board_id in wanted or board.slug in wanted]


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl Toronto consulate board posts.")
    parser.add_argument("--board", action="append", help="Topic, board id, or slug. Repeatable. Defaults to all.")
    parser.add_argument("--output-dir", default="data", help="Output directory.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests in seconds.")
    parser.add_argument("--max-posts", type=int, default=None, help="Limit posts per board for testing.")
    args = parser.parse_args()

    boards = selected_boards(args.board)
    if not boards:
        print("No board matched.", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    session = requests.Session()
    session.headers.update(HEADERS)

    all_records: list[dict[str, object]] = []
    reports: list[dict[str, object]] = []
    for board in boards:
        try:
            records, report = crawl_board(session, board, output_dir, args.delay, args.max_posts)
            all_records.extend(records)
            reports.append(report)
        except Exception as exc:  # noqa: BLE001 - top-level board failure belongs in report.
            reports.append(
                {
                    "topic": board.topic,
                    "board_id": board.board_id,
                    "listed_total": None,
                    "pages": 0,
                    "list_items_after_dedupe": 0,
                    "saved": 0,
                    "failures": [{"seq": "", "title": "board", "error": f"{type(exc).__name__}: {exc}"}],
                    "empty_body": 0,
                    "parse_failed": 0,
                }
            )

    chunks = make_chunks(all_records)
    write_jsonl(output_dir / "exports" / "consulate_posts.jsonl", all_records)
    write_jsonl(output_dir / "exports" / "rag_chunks.jsonl", chunks)
    report_path = Path("logs") / f"crawl_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    write_report(report_path, reports, len(all_records), len(chunks))
    print(f"Saved posts: {len(all_records)}")
    print(f"Saved chunks: {len(chunks)}")
    print(f"Report: {report_path}")
    return 0 if all(not report["failures"] for report in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
