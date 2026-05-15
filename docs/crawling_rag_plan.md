# 주토론토 총영사관 게시판 크롤링 및 LLM 챗봇 구축 계획서

## 1. 목적

주토론토 대한민국 총영사관 웹사이트의 민원 관련 게시판 자료를 수집하여, 민원인이 여권, 비자, 공증, 병역, 가족관계등록 등 영사 서비스 정보를 쉽게 찾을 수 있는 LLM 기반 챗봇을 구축한다.

이 프로젝트의 핵심 원칙은 다음과 같다.

- 게시글의 원문 내용을 최대한 훼손 없이 보존한다.
- LLM이 행정 정보를 임의로 해석하거나 추정하지 않도록 한다.
- 챗봇 답변은 수집된 공관 게시글 원문과 링크에 근거하도록 한다.
- 민원 안내 목적에 집중하며, 첨부파일 전체 다운로드 및 첨부파일 내용 추출은 초기 범위에서 제외한다.

## 2. 수집 대상

초기 수집 대상은 주토론토 총영사관 국문 사이트의 영사 서비스 게시판이다.

| 주제 | 목록 URL |
| --- | --- |
| 여권 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5389/list.do |
| 비자 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5390/list.do |
| 양식 다운로드 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5396/list.do |
| 공증 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5391/list.do |
| 병역 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5392/list.do |
| 가족관계등록 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5393/list.do |
| 국적 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5394/list.do |
| 공동인증서 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_27012/list.do |
| 각종 증명서 발급 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_21301/list.do |
| 재외국민등록 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_5395/list.do |
| 해외이주신고 | https://www.mofa.go.kr/ca-toronto-ko/brd/m_24767/list.do |

향후 확장 대상은 다음과 같다.

- 자주묻는질문(FAQ)
- 순회영사
- 공지사항 중 민원 업무와 직접 관련 있는 게시글
- 업무별 연락처, 근무시간 및 휴무일 등 정적 안내 페이지

## 3. 수집 필수 필드

각 게시글은 최소한 다음 필드를 가져야 한다.

```json
{
  "topic": "여권",
  "title": "게시글 제목",
  "content": "게시글 본문 원문 텍스트",
  "url": "게시글 상세 페이지 URL"
}
```

운영과 검증을 위해 실제 저장 데이터에는 다음 필드를 추가한다.

```json
{
  "post_id": "게시글 고유 식별자",
  "topic": "여권",
  "board_url": "게시판 목록 URL",
  "title": "게시글 제목",
  "post_number": "게시글 번호 또는 공지",
  "post_date": "작성일",
  "url": "게시글 상세 페이지 URL",
  "content_text": "게시글 본문 원문 텍스트",
  "content_html": "게시글 본문 HTML",
  "raw_html_path": "원본 HTML 저장 경로",
  "attachments": [
    {
      "filename": "첨부파일명",
      "url": "첨부파일 다운로드 URL"
    }
  ],
  "fetched_at": "수집 시각",
  "content_sha256": "본문 텍스트 해시",
  "content_html_sha256": "본문 HTML 해시",
  "raw_html_sha256": "상세 페이지 전체 HTML 해시",
  "status": "active"
}
```

첨부파일은 초기 버전에서 다운로드하지 않는다. 다만 게시글에 첨부파일이 있다는 사실, 첨부파일명, 다운로드 URL은 메타데이터로 보존한다. 민원인이 실제 서식을 받아야 하는 경우 챗봇은 원문 게시글 링크 또는 첨부 링크를 안내한다.

## 4. 원문 보존 원칙

공관 민원 정보는 작은 표현 차이도 의미가 달라질 수 있으므로, 크롤러는 본문을 임의로 고치지 않는다.

금지 사항:

- 문장 요약 후 저장
- 맞춤법, 띄어쓰기, 문장부호 수정
- 수수료, 처리 기간, 구비서류 표현 재작성
- 표 내용을 일반 문장으로 임의 변환
- 이미지 또는 첨부파일 내용을 원문 본문처럼 섞어 저장

허용 사항:

- HTML 태그 제거 후 화면 표시 텍스트 추출
- 불필요한 사이트 공통 메뉴, 푸터, SNS 공유 영역 제거
- 본문 영역 안의 줄바꿈 보존
- 본문 HTML 원본 별도 저장
- 첨부파일명과 첨부파일 URL 메타데이터 저장

본문은 두 형태로 저장한다.

- `content_html`: 상세 페이지 본문 영역의 HTML 원본
- `content_text`: 본문 영역을 사람이 읽는 텍스트로 추출한 값

LLM 검색과 답변에는 `content_text`를 사용하되, 추출 품질 검증과 재처리를 위해 `content_html`과 전체 `raw_html`도 반드시 보존한다.

## 5. 크롤링 단계

### 5.1 사전 검증

실제 크롤러 구현에 앞서 1개 게시판을 대상으로 다음 항목을 먼저 검증한다. 이 결과에 따라 이후 단계의 구현 방식과 의존성이 달라진다.

- `robots.txt` 확인 및 수집 허용 여부 점검
- 게시판 목록과 상세 페이지가 정적 HTML로 응답하는지, 또는 `javascript:fn_view(...)` 형태의 JS 기반 form POST로 동작하는지 확인
- 정적이면 `requests.Session()`만으로 충분, JS 기반이면 form POST 재현 또는 Playwright 도입 여부 결정
- 상세 페이지에서 제목, 본문, 첨부파일 영역의 안정적인 CSS selector 후보 식별
- 표(`<table>`)와 목록(`<ul>`, `<ol>`) 구조가 본문 영역에 그대로 보존되는지 확인
- 한 게시글의 원본 HTML과 추출 본문을 사람이 직접 비교하여 손실 여부 검토

### 5.2 게시판 목록 수집

각 게시판 목록 페이지에서 다음 작업을 수행한다.

1. `requests.Session()`으로 목록 페이지 요청
2. 게시판명, 전체 게시글 수, 현재 페이지, 전체 페이지 수 추출
3. 목록 행에서 게시글 번호, 제목, 작성일, 첨부 여부, 상세 링크 추출
4. 페이지네이션을 따라 모든 페이지 순회
5. 수집한 상세 URL을 중복 제거

주의 사항:

- 제목 텍스트로 상세 URL을 조합하지 않는다.
- HTML의 `<a href>` 또는 JavaScript 이동 값에서 실제 상세 링크를 추출한다.
- 공지 게시글은 페이지마다 상단에 고정 출현할 수 있으므로 URL 기반으로 중복 제거한다. list_parser는 목록 행의 클래스 또는 셀 표기에서 공지 여부를 식별하여 `post_number`에 `공지`를 저장한다.
- 목록의 `전체 N 건`과 실제 추출한 상세 링크 수를 비교한다.

### 5.3 상세 페이지 수집

각 상세 페이지에서 다음 작업을 수행한다.

1. 상세 페이지 HTML 다운로드
2. 전체 HTML을 파일로 저장
3. 제목, 작성일, 본문 영역, 첨부파일 영역 분리
4. 본문 영역 HTML 저장
5. 본문 영역 텍스트 추출
6. 첨부파일명과 첨부파일 URL만 추출
7. SHA-256 해시 생성
8. SQLite 또는 JSONL 저장소에 기록

상세 페이지 본문 추출기는 CSS selector 기반으로 구현한다. selector가 실패하면 해당 게시글을 `parse_failed` 상태로 저장하고 원본 HTML을 남긴다.

### 5.4 재시도와 요청 간격

공공기관 웹사이트에 부담을 주지 않도록 요청 속도를 보수적으로 잡는다.

- 목록 페이지 요청 간격: 2~5초
- 상세 페이지 요청 간격: 1~3초
- 연결 실패 시 최대 3회 재시도
- 재시도 간격은 5초, 10초, 20초처럼 점진적으로 증가
- HTTP 429, 403, 5xx 응답은 별도 실패 로그에 기록

기본 요청 헤더:

```python
{
    "User-Agent": "Mozilla/5.0 ...",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}
```

## 6. 저장 구조

초기 구현은 SQLite와 JSONL을 함께 사용한다.

```text
data/
  raw_html/
    passport/
      post_12345.html
    visa/
      post_23456.html
  exports/
    consulate_posts.jsonl
    rag_chunks.jsonl
  crawler.db
logs/
  crawl_YYYYMMDD.log
  crawl_report_YYYYMMDD.md
```

SQLite는 크롤링 상태 관리, 중복 방지, 변경 감지에 사용한다.

JSONL은 RAG 인덱싱과 백업용 export에 사용한다.

### 6.1 테이블 설계

`boards`

| 컬럼 | 설명 |
| --- | --- |
| id | 내부 게시판 ID |
| topic | 주제명 |
| url | 목록 URL |
| enabled | 수집 여부 |
| last_crawled_at | 마지막 수집 시각 |

`posts`

| 컬럼 | 설명 |
| --- | --- |
| id | 내부 게시글 ID |
| topic | 주제 |
| board_url | 목록 URL |
| post_number | 게시글 번호 또는 공지 |
| title | 제목 |
| post_date | 작성일 |
| url | 상세 URL |
| content_text | 본문 텍스트 |
| content_html | 본문 HTML |
| raw_html_path | 원본 HTML 경로 |
| content_sha256 | 본문 텍스트 해시 |
| content_html_sha256 | 본문 HTML 해시 |
| raw_html_sha256 | 전체 HTML 해시 |
| status | active, changed, removed_from_site, parse_failed, empty_body |
| fetched_at | 수집 시각 |
| updated_at | 내부 갱신 시각 |

`attachments`

| 컬럼 | 설명 |
| --- | --- |
| id | 내부 첨부 ID |
| post_id | 게시글 ID |
| filename | 첨부파일명 |
| url | 첨부파일 URL |
| extension | 파일 확장자 (소문자 정규화, 예: pdf, hwp) |
| discovered_at | 최초 발견 시각 |
| last_seen_at | 마지막 발견 시각 |

`crawl_runs`

| 컬럼 | 설명 |
| --- | --- |
| id | 실행 ID |
| started_at | 시작 시각 |
| finished_at | 종료 시각 |
| status | success, partial, failed |
| total_boards | 대상 게시판 수 |
| total_posts_found | 목록에서 발견한 게시글 수 |
| total_posts_saved | 저장 성공 게시글 수 |
| total_errors | 오류 수 |
| report_path | 리포트 경로 |

## 7. 변경 감지

게시글은 시간이 지나며 수정될 수 있다. 따라서 매 수집마다 해시를 비교한다.

비교 기준:

- 상세 페이지 URL이 기존에 있으면 같은 게시글로 본다.
- `content_sha256`이 바뀌면 본문 변경으로 판단한다.
- `content_html_sha256`만 바뀌고 `content_sha256`이 같으면 HTML 구조 변경으로 판단한다.
- 목록에서 사라진 기존 게시글은 삭제하지 않고 `removed_from_site`로 표시한다.

변경 이력은 별도 테이블 또는 JSON 파일로 보존할 수 있다.

```json
{
  "url": "게시글 URL",
  "title": "제목",
  "previous_content_sha256": "...",
  "new_content_sha256": "...",
  "changed_at": "2026-05-14T19:00:00-04:00"
}
```

초기 버전에서는 최신본만 RAG에 사용하고, 이전 원문은 감사 추적용으로 보관한다.

## 8. 품질 검증

크롤링 후 매번 검증 리포트를 생성한다.

검증 항목:

- 게시판별 목록의 `전체 N 건`과 수집 건수 일치 여부
- 상세 페이지 접근 실패 수
- 본문 추출 실패 수
- 제목 누락 여부
- 본문 길이 0 여부
- 중복 URL 여부
- 첨부파일 메타데이터 추출 여부
- 해시 변경 게시글 목록

리포트 예:

```text
# 크롤링 리포트

실행 시각: 2026-05-14 19:00:00 America/Toronto

| 주제 | 목록 건수 | 상세 링크 | 저장 성공 | 실패 | 변경 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 여권 | 8 | 8 | 8 | 0 | 0 |
| 비자 | 14 | 14 | 14 | 0 | 1 |

## 실패 목록

- 공증 / 게시글 URL / 본문 selector 실패
```

본문 추출 실패가 있는 경우 해당 실행은 `partial` 상태로 기록하고, 실패 원본 HTML을 보존한다.

## 9. RAG 데이터 생성

LLM 챗봇은 게시글 전체를 한 번에 모델에 넣지 않고, 검색 가능한 조각으로 나누어 사용한다.

### 9.1 Chunk 생성 원칙

- 원문 텍스트를 임의로 요약하지 않는다.
- 문단, 목록, 표 단위가 깨지지 않도록 한다.
- 구비서류, 수수료, 처리기간, 예약 안내 같은 정보는 가능한 한 같은 chunk 안에 유지한다.
- 각 chunk에는 반드시 주제, 제목, URL, 작성일을 metadata로 포함한다.
- chunk 본문에는 원문 표현을 유지한다.

구체적 파라미터:

- 최대 chunk 크기: 약 800~1200자 (사용 모델 토크나이저 기준으로 조정)
- chunk 간 overlap: 100~200자
- 분할 우선순위: 문단(`\n\n`) → 문장 → 마지막 fallback으로 문자 단위
- 표(`<table>`)는 분할하지 않고 한 chunk에 통째로 둔다. `content_html` 기반으로 markdown table로 변환하여 chunk 텍스트에 포함한다.
- 표가 chunk 크기를 초과하면 해당 표만 별도 chunk로 두고 크기 제한을 예외 처리한다.
- 짧은 게시글은 분할하지 않고 단일 chunk로 둔다.

예시:

```json
{
  "chunk_id": "post_12345_chunk_001",
  "post_id": "post_12345",
  "topic": "여권",
  "title": "일반 전자여권 신청 안내",
  "post_date": "2026-01-21",
  "url": "https://www.mofa.go.kr/...",
  "text": "원문 본문 일부",
  "char_start": 0,
  "char_end": 850,
  "content_sha256": "..."
}
```

### 9.2 검색 인덱스

초기에는 다음 두 검색 방식을 함께 사용한다.

- 키워드 검색: BM25 또는 SQLite FTS5
- 의미 검색: embedding 기반 vector search

민원 질의는 정확한 키워드가 중요한 경우가 많다. 예를 들어 `DHL`, `긴급여권`, `공증`, `국적상실`, `가족관계증명서` 같은 단어는 의미 검색만으로는 놓칠 수 있으므로 키워드 검색을 반드시 병행한다.

임베딩 모델은 한국어 행정 도메인 성능과 운영 비용을 함께 고려하여 다음 후보 중 하나를 선정한다.

- `BAAI/bge-m3`: 다국어, 한국어 성능 우수, 자체 호스팅 가능
- OpenAI `text-embedding-3-large`: API 기반, 운영 부담 적음
- `intfloat/multilingual-e5-large`: 자체 호스팅 가능

선정 기준은 한국어 행정 도메인 샘플 질의 10~20건에 대한 recall@5 비교로 한다.

### 9.3 인덱스 동기화 정책

게시글 상태 변경 시 검색 인덱스(BM25, vector)를 다음과 같이 갱신한다.

| 상태 | 인덱스 처리 |
| --- | --- |
| `active` | 인덱스에 포함 |
| `changed` | 기존 chunk를 삭제 후 새 chunk로 재생성 |
| `removed_from_site` | 인덱스에서 제외, DB와 원본 HTML은 보존 |
| `parse_failed` | 인덱스에 포함하지 않음 |
| `empty_body` | 인덱스에 포함하지 않음 |

매 크롤링 실행 종료 시 변경된 게시글에 한해 차분 인덱싱(incremental indexing)을 수행한다. 인덱스와 SQLite의 정합성은 `crawl_runs` 종료 시점에 검증한다.

## 10. 챗봇 답변 정책

챗봇은 친절하게 안내하되, 행정 정보는 원문 근거를 벗어나지 않아야 한다.

시스템 정책:

```text
당신은 주토론토 대한민국 총영사관 게시글을 근거로 민원 정보를 안내하는 챗봇이다.
답변은 검색된 게시글 내용에 근거해서만 작성한다.
구비서류, 수수료, 처리기간, 신청 조건, 예약 방법은 원문 표현을 우선 사용한다.
근거가 부족하면 추정하지 말고 "수집된 게시글에서 확인되지 않습니다"라고 답한다.
답변에는 관련 게시글 제목, 작성일(post_date), URL을 포함한다.
중요한 행정 문구는 가능한 한 원문을 그대로 인용한다.
답변 말미에 행정 정보의 시점과 정확성에 관한 면책 고지를 포함한다.
```

답변 형식:

```text
문의하신 내용은 "일반 전자여권 신청 안내" 게시글 기준으로 확인됩니다.

핵심 안내:
- ...
- ...

원문 근거:
"..."

출처:
- 일반 전자여권 신청 안내 (작성일 2026-01-21): https://www.mofa.go.kr/...

※ 본 안내는 영사관 게시글(2026-01-21 기준)을 근거로 작성되었으며, 최신 정보와 다를 수 있습니다. 정확한 안내는 영사관에 직접 문의해 주세요.
```

금지 답변:

- 원문에 없는 준비서류 추가
- 원문 수수료를 환율로 임의 변환
- 처리기간을 임의로 단축 또는 확대 해석
- 첨부파일 내용을 확인한 것처럼 답변
- 캐나다 일반 행정 정보와 공관 게시글 내용을 섞어서 단정

### 10.1 인용 검증

답변 정책만으로는 LLM이 원문에 없는 표현을 인용하는 환각을 막을 수 없다. 답변 생성 후 다음을 자동 검증한다.

- 답변 내 따옴표(`"..."`)로 둘러싸인 모든 인용을 추출
- 각 인용이 검색 결과로 사용된 chunk 텍스트 중 하나에 부분 문자열로 존재하는지 확인 (공백 정규화 후 비교)
- 검증 실패 시 해당 인용을 제거하고 응답을 재생성하거나 "확인되지 않습니다" 응답으로 대체

### 10.2 응답 언어

- 사용자 입력 언어(한국어, 영어)를 감지하여 같은 언어로 응답한다.
- 게시글 원문 인용은 항상 원문(한국어)을 그대로 사용한다. 영어 사용자에게는 핵심 안내 부분만 입력 언어로 번역하여 함께 제공하되, 원문 인용은 변형하지 않는다.
- 영어 응답 시에도 면책 고지와 출처(게시글 URL, 작성일)를 동일하게 포함한다.

### 10.3 LLM 모델 선택

초기 LLM은 한국어 행정 도메인 품질, 응답 지연, 비용을 기준으로 Claude 4.x Sonnet 또는 GPT-4o 계열 중 선정한다. 선정 시 다음 항목을 평가한다.

- 한국어 행정 문장 인용 유지력
- 검색된 근거를 벗어난 응답 빈도
- 다수 chunk를 동시에 다룰 때의 응답 지연
- 토큰당 비용

## 11. 첨부파일 처리 범위

초기 버전에서는 첨부파일을 다운로드하지 않는다.

수집하는 정보:

- 첨부파일명
- 첨부파일 링크
- 첨부파일이 연결된 게시글 제목과 URL

챗봇 동작:

- 첨부파일 자체의 내용은 답변 근거로 사용하지 않는다.
- 사용자가 양식이나 신청서를 요구하면 게시글 URL 또는 첨부파일 링크를 안내한다.
- 답변에는 "첨부파일 내용은 별도 추출하지 않았으므로, 최신 양식은 원문 게시글에서 확인해야 합니다"라는 취지의 안내를 포함할 수 있다.

향후 필요해질 경우 다음 순서로 확장한다.

1. PDF 파일만 다운로드
2. PDF 텍스트 추출
3. HWP, DOCX 등 문서 파일 추출
4. OCR 기반 이미지 문서 처리
5. 첨부파일 내용도 별도 source type으로 RAG 인덱싱

## 12. 구현 구성

권장 파일 구조:

```text
chatbot_consulate/
  config/
    boards.yaml
    selectors.yaml
  crawler/
    __init__.py
    http.py
    list_parser.py
    detail_parser.py
    storage.py
    export.py
    report.py
    run.py
  tests/
    fixtures/
      list_passport.html
      detail_passport_sample.html
    test_list_parser.py
    test_detail_parser.py
    test_chunker.py
  data/
    raw_html/
    exports/
    crawler.db
  logs/
  docs/
    crawling_rag_plan.md
```

역할:

- `config/boards.yaml`: 게시판 이름과 URL 관리
- `config/selectors.yaml`: 게시판별 제목, 본문, 첨부파일 영역 CSS selector 관리 (코드 수정 없이 사이트 구조 변경에 대응)
- `crawler/http.py`: 세션, 헤더, 재시도, rate limit
- `crawler/list_parser.py`: 목록 페이지 파싱
- `crawler/detail_parser.py`: 상세 페이지 본문 파싱
- `crawler/storage.py`: SQLite 저장, 해시 비교
- `crawler/export.py`: JSONL, RAG chunk export
- `crawler/report.py`: 수집 결과 리포트 생성
- `crawler/run.py`: 전체 실행 진입점
- `tests/fixtures/`: 게시판별 대표 HTML 스냅샷 (parser 회귀 방지용)
- `tests/`: parser, chunker, 인용 검증 등 단위 테스트

## 13. 구현 순서

1. 사전 검증 (5.1) 실시 및 결과 기록
2. `boards.yaml`, `selectors.yaml` 초기값 작성
3. 대표 게시판 HTML 1~2건을 `tests/fixtures/`에 저장
4. HTTP 세션과 재시도 로직 구현
5. 목록 페이지 parser 구현 + fixture 기반 단위 테스트
6. 상세 URL 추출 검증
7. 상세 페이지 parser 구현 + fixture 기반 단위 테스트
8. 원본 HTML 저장 구현
9. SQLite schema 구현
10. 게시글 저장 및 중복 방지 구현
11. 해시 기반 변경 감지 구현
12. 첨부파일 메타데이터 추출 구현
13. JSONL export 구현
14. RAG chunk 생성 구현 + chunker 단위 테스트 (표 보존, overlap 동작 확인)
15. 크롤링 리포트 생성 구현
16. 샘플 게시판 1개로 end-to-end 검증
17. 전체 11개 게시판 수집
18. 임베딩 모델 선정 (recall@5 비교)
19. 챗봇 검색 파이프라인 연결
20. 인용 검증, 면책 고지, 응답 언어 정책 통합 테스트

## 14. 운영 방식

수집 주기:

- 개발 중: 수동 실행
- 초기 운영: 하루 1회
- 안정화 후: 하루 1회 또는 주 2~3회

운영 체크:

- 실패 게시글이 있는지 확인
- 게시판별 수집 건수 차이 확인
- 변경된 게시글 목록 확인
- 본문 길이가 비정상적으로 짧은 게시글 확인
- selector 실패가 발생하면 `selectors.yaml` 업데이트
- "수집된 게시글에서 확인되지 않습니다" 응답 비율 확인
- 검색 결과 0건 비율 확인
- 인용 검증 실패 비율 확인

게시글이 수정되었을 때:

- 최신 내용을 RAG 인덱스에 반영한다.
- 이전 원문은 감사와 비교용으로 보관한다.
- 챗봇에는 최신본만 노출한다.

관측성과 피드백 루프:

- 검색 적중률, 답변 거부율, 인용 검증 실패율, 사용자 thumbs up/down을 로깅한다.
- 사용자 질의, 검색된 chunk ID, 최종 응답을 함께 저장하여 사후 분석에 사용한다. 개인정보가 포함되지 않도록 주의한다.
- 거부율이 높거나 부정 피드백이 많은 질의 패턴은 주기적으로 검토하여 chunking 규칙, 검색 가중치, 답변 정책을 개선한다.
- 운영 초기에는 주 단위로 위 지표를 검토한다.

## 15. 주요 리스크와 대응

| 리스크 | 영향 | 대응 |
| --- | --- | --- |
| 사이트 HTML 구조 변경 | 본문 추출 실패 | selector fallback, 실패 리포트, 원본 HTML 보존 |
| 게시글 내용 수정 | 챗봇이 오래된 정보 제공 | 해시 비교, 변경 감지, 재인덱싱 |
| 첨부파일에 핵심 정보 존재 | 답변 누락 가능 | 첨부파일 링크 안내, 향후 PDF 추출 확장 |
| LLM의 임의 해석 | 잘못된 민원 안내 | 원문 기반 답변 정책, 출처 강제, 모르면 모른다고 답변, 인용 검증 자동화, 면책 고지 |
| 사이트 동적 렌더링 | 크롤러 작동 불가 | 사전 검증(5.1)에서 정적/JS 응답 여부 확인, 필요 시 form POST 재현 또는 Playwright 도입 |
| 게시글 작성일 누락 | 정보 시점 판단 불가 | post_date 필수 필드화, 누락 시 parse_failed 처리, 답변에 작성일 명시 |
| 의미 검색 누락 | 관련 게시글 미검색 | BM25와 vector search 병행 |
| 표/목록 구조 손상 | 구비서류 오해 가능 | 본문 HTML 저장, 표 단위 chunking |

## 16. 완료 기준

초기 크롤러 완료 기준:

- 11개 게시판 목록을 모두 순회한다.
- 각 게시글의 주제, 제목, 본문, 링크를 저장한다.
- 원본 HTML과 본문 HTML을 보존한다.
- 첨부파일명과 첨부파일 URL을 메타데이터로 저장한다.
- 게시판별 목록 건수와 수집 건수를 리포트한다.
- 실패한 게시글을 누락하지 않고 실패 상태로 기록한다.
- JSONL export를 생성한다.
- 동일 URL 재수집 시 중복 저장하지 않는다.
- 본문 변경 시 해시 차이를 감지한다.

챗봇 연동 준비 완료 기준:

- `rag_chunks.jsonl` 생성
- 각 chunk에 topic, title, url, post_date 포함
- 검색 결과에서 원문 게시글 URL 추적 가능
- 답변 생성 프롬프트에 원문 근거 사용 정책 반영
- 답변에 작성일과 면책 고지가 포함됨
- 따옴표 인용에 대한 자동 검증이 동작함
- 임베딩 모델이 선정되고 recall@5 평가 기록이 보존됨

## 17. 초기 개발에서 제외하는 범위

다음 항목은 초기 버전에서 제외한다.

- 첨부파일 다운로드
- 첨부파일 본문 추출
- OCR
- 로그인 또는 인증이 필요한 페이지
- 사이트 외부 링크 본문 크롤링
- 게시글 자동 번역
- LLM fine-tuning
- 민원 처리 가능 여부에 대한 법률적 판단

## 18. 결론

이 프로젝트는 단순한 웹 크롤러가 아니라, 민원 안내에 사용할 수 있는 신뢰 가능한 원문 저장소를 만드는 작업이다. 따라서 가장 중요한 것은 크롤링 속도나 요약 품질이 아니라, 원문 보존, 출처 추적, 변경 감지, 답변 근거 통제다.

초기 버전은 게시글 본문과 링크 중심으로 작게 시작하고, 첨부파일은 메타데이터와 링크만 안내한다. 이후 실제 민원 질문에서 첨부파일 내용이 자주 필요하다고 확인되면 PDF 또는 문서 추출 기능을 단계적으로 추가한다.
