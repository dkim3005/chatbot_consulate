# 주토론토 대한민국 총영사관 민원 안내 챗봇

영사관 공식 게시글 기반 RAG 챗봇. 여권·비자·공증·병역·가족관계등록 등 민원을 안내합니다.

---

## 아키텍처

```
사용자 질문
    │
    ▼
쿼리 정제 (구어체 어미 제거) + 토픽 감지
    │
    ├─ 토픽 감지됨 → 해당 토픽 BM25 서브인덱스 검색
    └─ 토픽 미감지 → 전체 BM25 + 임베딩 RRF 검색
    │
    ▼
상위 5개 게시글 전문 컨텍스트 구성 (최대 16,000자)
    │
    ▼
GPT-4o (temperature=0.05) → 스트리밍 SSE 응답
    │
    ▼
프론트엔드 marked.js 마크다운 렌더링
```

**검색 방식**: 하이브리드 (BM25 + OpenAI text-embedding-3-small → Reciprocal Rank Fusion)  
**컨텍스트 단위**: 청크 아님, 게시글 전체 (post-level retrieval)  
**임베딩**: 기본 비활성 (`ENABLE_EMBEDDINGS=false`), BM25 단독 모드로 운영

---

## 프로젝트 구조

```
chatbot_consulate/
├── app.py                        # FastAPI 백엔드 (검색 + 스트리밍)
├── requirements.txt
├── .env                          # API 키, 비밀번호 설정 (git 제외)
├── static/
│   └── index.html                # 단일 파일 프론트엔드
├── data/
│   ├── exports/
│   │   └── consulate_posts.jsonl # 크롤링된 게시글 (215개)
│   ├── embeddings_cache.npy      # 임베딩 캐시 (자동 생성)
│   └── embeddings_ids.json       # 캐시 무효화용 ID 목록
├── config/
│   └── boards.yaml               # 크롤링 대상 게시판 목록
├── scripts/
│   ├── crawl_consulate.py        # 게시글 크롤러
│   └── chatbot-consulate.service # systemd 서비스 파일
└── docs/
    └── crawling_rag_plan.md      # 설계 문서
```

---

## 설치 및 실행

### 요구사항

- Python 3.11+
- OpenAI API 키

### 설치

```bash
pip install -r requirements.txt
```

### 환경변수 설정

`.env` 파일 생성:

```env
OPENAI_API_KEY=sk-...
OPENAI_CHAT_MODEL=gpt-4o
CHAT_PASSWORD=your_password
ENABLE_EMBEDDINGS=false
LOW_CONFIDENCE_THRESHOLD=1.0
```

### 개발 서버 실행

```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### systemd 서비스 등록 (운영)

```bash
cp scripts/chatbot-consulate.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now chatbot-consulate.service

# 재시작
systemctl --user restart chatbot-consulate.service

# 로그 확인
journalctl --user -u chatbot-consulate.service -f
```

---

## 데이터 업데이트

게시글 재크롤링 후 서버 재시작:

```bash
python scripts/crawl_consulate.py
systemctl --user restart chatbot-consulate.service
```

임베딩 사용 시 캐시 무효화가 필요한 경우:

```bash
rm data/embeddings_cache.npy data/embeddings_ids.json
systemctl --user restart chatbot-consulate.service
```

---

## 주요 설정값

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_CHAT_MODEL` | `gpt-4o` | 사용할 LLM 모델 |
| `ENABLE_EMBEDDINGS` | `false` | 임베딩 검색 활성화 (비용 발생) |
| `LOW_CONFIDENCE_THRESHOLD` | `1.0` | 이 BM25 점수 미만 시 저신뢰도 안내 |
| `TOP_K` | `5` | 검색 반환 게시글 수 (상위 3개 핵심, 4~5번 추가) |
| `MAX_POST_CHARS` | `4000` | 게시글 1개당 LLM 전달 최대 문자 수 |

---

## 토픽 감지

쿼리에 아래 키워드가 포함되면 해당 토픽 게시글 안에서만 BM25 검색합니다.

| 키워드 | 토픽 |
|--------|------|
| 여권, 긴급여권, 단수여권 | 여권 |
| 비자, 사증, visa, 재입국 | 비자 |
| 공증 | 공증 |
| 병역, 병무 | 병역 |
| 공동인증서, 금융인증서 | 공동인증서 |
| 가족관계, 출생신고, 혼인신고 | 가족관계등록 |
| 국적, 귀화, 시민권 | 국적 |
| 재외국민 | 재외국민등록 |
| 해외이주 | 해외이주신고 |
| 증명서 | 각종 증명서 발급 |

---

## 방문 예약

모든 민원은 사전 예약제입니다.

**예약**: [www.torbooking.com](https://www.torbooking.com)  
**전화**: +1-416-920-3809  
**이메일**: toronto@mofa.go.kr  
**공식 홈페이지**: [toronto.mofa.go.kr](https://toronto.mofa.go.kr)
