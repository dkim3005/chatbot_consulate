from __future__ import annotations

import sys
from urllib.parse import urljoin

import requests


URLS = [
    "https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do",
    "https://toronto.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do",
    "https://overseas.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


def show_response(response: requests.Response) -> None:
    print(f"status={response.status_code}")
    print(f"url={response.url}")
    print(f"history={[item.status_code for item in response.history]}")
    print(f"cookies={response.cookies.get_dict()}")
    print(f"content_type={response.headers.get('content-type')}")
    print(f"bytes={len(response.content)}")
    text = response.text
    print(f"has_count={'전체 8 건' in text or '전체 8건' in text}")
    print(f"has_title={'긴급배송' in text}")
    print(f"has_view={'view.do' in text}")


def try_url(url: str) -> bool:
    print(f"\n== {url}")
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        response = session.get(url, timeout=20, allow_redirects=False)
        print("-- first request, redirects disabled")
        show_response(response)
    except requests.RequestException as exc:
        print(f"first request failed: {type(exc).__name__}: {exc}")
        return False

    if response.is_redirect:
        location = response.headers.get("location")
        print(f"redirect location={location}")
        if location:
            redirected_url = urljoin(url, location)
            try:
                second = session.get(redirected_url, timeout=20, allow_redirects=False)
                print("-- second request, redirects disabled")
                show_response(second)
            except requests.RequestException as exc:
                print(f"second request failed: {type(exc).__name__}: {exc}")

    try:
        final = session.get(url, timeout=20, allow_redirects=True)
        print("-- automatic redirects")
        show_response(final)
        return final.ok and ("전체" in final.text or "긴급배송" in final.text)
    except requests.TooManyRedirects as exc:
        print(f"automatic redirects failed: TooManyRedirects: {exc}")
    except requests.RequestException as exc:
        print(f"automatic redirects failed: {type(exc).__name__}: {exc}")
    return False


def main() -> int:
    any_success = False
    for url in URLS:
        any_success = try_url(url) or any_success
    return 0 if any_success else 2


if __name__ == "__main__":
    sys.exit(main())
