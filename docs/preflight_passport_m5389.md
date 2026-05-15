# 사전 검증 리포트: 여권 게시판 m_5389

실행일: 2026-05-14  
대상: 주토론토 대한민국 총영사관 > 영사 서비스 > 여권  
목록 URL: https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do

## 1. 결론

여권 게시판은 브라우저/검색 인덱스 기준으로 목록과 상세 본문이 HTML에 노출된다. 따라서 게시글 데이터 자체는 정적 HTML 기반으로 수집 가능해 보인다.

다만 현재 개발 환경에서 `python3`, `curl`로 직접 접근하면 MOFA 쪽 보안 장비로 보이는 `TMOSHCooKie` 쿠키와 `HTTP/1.0 307 Temporary Redirect` 반복 또는 connection reset이 발생한다. 즉, 실제 크롤러 구현 전에 HTTP 클라이언트가 이 보안 쿠키/redirect 흐름을 통과할 수 있는지 별도 해결이 필요하다.

권장 구현 방향:

- 1차: `requests.Session()` + 충분한 브라우저 헤더 + 쿠키 유지 + redirect 제한 설정으로 재검증
- 2차: `curl_cffi` 또는 browser-like TLS fingerprint 클라이언트 검토
- 3차: Playwright 기반 수집기로 fallback

현재 상태에서 일반 `urllib` 또는 기본 `curl`만으로 전체 크롤링을 진행하면 실패할 가능성이 높다.

## 2. robots.txt 확인

로컬 직접 확인 결과:

```text
python3 scripts/probe_passport_board.py
robots.txt check failed: <urlopen error [Errno 104] Connection reset by peer>
```

`curl` 직접 확인 결과:

```text
curl -L --max-time 20 -A "Mozilla/5.0" https://www.mofa.go.kr/robots.txt
curl: (35) Recv failure: Connection reset by peer
```

판정:

- 현재 환경의 직접 HTTP 클라이언트로는 robots.txt 확인 실패
- 실패 원인은 DNS가 아니라 서버 측 연결 reset 또는 보안 장비 응답으로 보임
- 구현 전 robots.txt는 browser-capable fetcher 또는 다른 네트워크 환경에서 재확인 필요

## 3. 목록 페이지 검증

브라우징 경로에서 확인된 목록 페이지 정보:

- 게시판명: 여권
- 전체 건수: 8건
- 페이지: 1/1페이지
- 목록 행에 번호, 제목, 첨부 여부, 작성일이 노출됨
- 공지 글 `[중요] 방문 예약 안내`가 상단 공지와 일반 1번 글로 중복 출현함

확인된 목록 일부:

| 번호 | 제목 | 첨부 | 작성일 |
| --- | --- | --- | --- |
| 공지 | [중요] 방문 예약 안내 | 없음 | 2020-01-01 |
| 8 | ✅긴급배송(DHL) 전자여권 신청 (약 1주일 소요)✅ | 없음 | 2026-03-01 |
| 7 | ✅긴급여권 (비전자식 단수여권, 일주일 이내 발급)✅ | 있음 | 2026-01-21 |
| 6 | ✅일반 전자여권 신청 (약 3~4주 소요)✅ | 있음 | 2026-01-21 |
| 5 | 여권사진 표준규격 안내 | 없음 | 2023-05-20 |
| 4 | 여권사본증명서 발급 안내 | 있음 | 2023-04-20 |
| 3 | 여권정보증명서를 비롯한 각종 여권사실증명 발급 안내 | 있음 | 2021-03-29 |
| 2 | 온라인 여권 재발급 신청 | 없음 | 2021-03-04 |
| 1 | [중요] 방문 예약 안내 | 없음 | 2020-01-01 |

판정:

- 목록 데이터는 HTML 텍스트에 노출됨
- 공지 글은 URL 기반 dedup 필요
- 표시상 전체 8건이지만 공지 중복 노출 때문에 목록 행은 9개처럼 보일 수 있음

## 4. 상세 URL 검증

검색/브라우징 경로에서 확인된 상세 URL 예:

```text
https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/view.do?seq=1344536
https://overseas.mofa.go.kr/ca-toronto-ko/brd/m_5389/view.do?page=1&seq=1344541
```

판정:

- 상세 페이지는 `view.do?seq=...` 패턴을 사용
- `page=1`은 선택적 파라미터로 보이며, 핵심 식별자는 `seq`
- 도메인은 `www.mofa.go.kr`, `overseas.mofa.go.kr`, `toronto.mofa.go.kr`가 혼재될 수 있으므로 canonical URL 정책 필요

권장 canonical URL:

```text
https://www.mofa.go.kr/ca-toronto-ko/brd/{board_id}/view.do?seq={seq}
```

단, 실제 접근 성공률은 도메인별로 재측정해야 한다.

## 5. 상세 페이지 본문 검증

샘플 1:

- 제목: ✅긴급배송(DHL) 전자여권 신청 (약 1주일 소요)✅
- URL: https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/view.do?seq=1344536
- 작성일: 2023-07-11
- 수정일: 2025-07-10
- 본문: HTML 텍스트로 노출됨
- 첨부: 없음
- 관련 링크: DHL Express 긴급여권특급 배송서비스 바로가기

샘플 2:

- 제목: ✅일반 전자여권 신청 (약 3~4주 소요)✅
- URL: https://overseas.mofa.go.kr/ca-toronto-ko/brd/m_5389/view.do?page=1&seq=1344541
- 작성일: 2026-01-21
- 수정일: 2026-04-10
- 첨부파일명 노출:
  - 여권발급신청서-A4용지 전용.pdf
  - 법정대리인 동의서.pdf
  - 여권우편수령신청서.pdf
  - 여권분실신고서.pdf
- 본문: 예약/방문 안내, 발급확인, 구비서류 표가 HTML 텍스트로 노출됨

판정:

- 상세 페이지 본문은 JavaScript 렌더링 없이도 최종 텍스트가 확인됨
- 첨부파일명은 상세 페이지 텍스트에 노출되므로 메타데이터 수집 가능
- 본문에 표가 포함됨. `content_html` 보존 및 table 단위 chunking이 필요

## 6. 표 구조 보존 검증

`일반 전자여권 신청` 상세 페이지에는 구비서류 표가 포함되어 있다.

확인된 표 성격:

- 행 단위로 구비서류 번호, 항목명, 필수/선택 여부, 설명이 나뉨
- 체류 자격별 증명서류 안에 하위 표 형태의 정보가 포함됨
- 단순 텍스트 추출 시 셀 경계가 약해질 수 있음

판정:

- `content_text`만 저장하면 표 구조가 손상될 위험이 있음
- `content_html` 원본 저장은 필수
- chunk 생성 시 `<table>`을 markdown table 또는 구조화 텍스트로 별도 변환해야 함

## 7. 로컬 HTTP 클라이언트 결과

추가한 프로브:

```text
scripts/probe_passport_board.py
```

초기 실행 결과:

```text
Target board: 여권
Board URL: https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do
robots.txt check failed: <urlopen error [Errno -3] Temporary failure in name resolution>
...
urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name resolution>
```

외부 네트워크 승인 후 재실행 결과:

```text
Target board: 여권
Board URL: https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do
robots.txt check failed: <urlopen error [Errno 104] Connection reset by peer>
...
urllib.error.URLError: <urlopen error [Errno 104] Connection reset by peer>
```

`curl` 결과:

```text
HTTP/1.0 307 Temporary Redirect
Location: https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do
Set-Cookie: TMOSHCooKie=...
Cache-Control: no-cache
Connection: close
Content-Length: 0
```

위 응답이 반복되다가 timeout 또는 reset 발생.

대체 도메인 결과:

- `https://toronto.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do`: 307 redirect 반복 후 timeout
- `https://overseas.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do`: connection reset

판정:

- 로컬 기본 HTTP 클라이언트는 현재 그대로 사용하기 어렵다.
- 사이트 구조가 동적이라기보다는, 보안 장비의 쿠키/redirect/TLS fingerprint 처리 문제가 더 유력하다.

## 8. selector 후보

브라우징 텍스트 기준으로 상세 페이지의 안정적인 추출 기준은 다음 순서로 잡는 것이 좋다.

1. 제목: 상세 영역의 `h2` 또는 view title class
2. 작성일/수정일: `작성일`, `수정일` 라벨 주변 텍스트
3. 첨부: `첨부` 라벨 이후 파일 다운로드 링크 목록
4. 본문: 제목/작성자/작성일/수정일/첨부 영역 이후부터 `목록`, `이전 글`, `다음 글` 이전까지

실제 CSS selector는 raw HTML fixture 확보 후 확정해야 한다. 현재 웹 텍스트 렌더링만으로는 class명을 확정하지 않는다.

## 9. 다음 단계

1. 로컬 접근 문제 해결
   - `requests.Session()`에 redirect 횟수 제한과 쿠키 추적 로그 추가
   - `curl -v`로 TLS/redirect 흐름 상세 확인
   - 필요 시 `curl_cffi` 또는 Playwright 검토

2. fixture 확보
   - 로컬 fetch가 가능해지는 방식으로 `list_passport.html`, `detail_passport_sample.html` 저장
   - raw HTML 기준 selector 확정

3. parser 단위 테스트 작성
   - 목록 건수 8건 검증
   - 공지 중복 URL dedup 검증
   - 상세 제목/작성일/첨부파일명/본문 추출 검증
   - 표 포함 게시글의 `content_html` 보존 검증

4. 구현 순서 잠금
   - 기본 HTTP 클라이언트로 성공하면 `requests.Session()` 기반으로 진행
   - 실패하면 Playwright fallback을 crawler/http.py 설계에 포함

## 10. 추가 검증 결과

2026-05-14 추가 검증에서 `toronto.mofa.go.kr` 도메인과 `requests.Session()` 조합으로 수집이 가능함을 확인했다.

확인 사항:

- `www.mofa.go.kr`, `overseas.mofa.go.kr`는 로컬 HTTP 클라이언트에서 connection reset이 발생할 수 있음
- `toronto.mofa.go.kr`는 최초 요청에서 307 redirect 및 `TMOSHCooKie`가 발생할 수 있으나, session cookie 유지와 재시도 후 200 응답 수신 가능
- 여권 게시판 8건 수집 성공
- 전체 11개 게시판 216건 수집 성공
- 원본 HTML 216개 저장
- 게시글 JSONL 216행 생성
- RAG chunk JSONL 339행 생성

따라서 초기 구현은 Playwright 없이 `requests.Session()` 기반으로 진행 가능하다. 단, connection reset이 간헐적으로 발생하므로 fetch 함수에는 재시도와 backoff를 반드시 유지한다.
