"""
주토론토 대한민국 총영사관 민원 안내 챗봇 — 백엔드

검색 단위: 청크(조각)가 아닌 게시글 전체(post)
- 게시글 1개당 임베딩 1개 → 조각 분리 없음
- 상위 3개 게시글 전문을 LLM에 전달 (GPT-4o 128k 컨텍스트 활용)
- 답변: 핵심 3~5줄 + 원문 링크
"""

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from pydantic import BaseModel
from rank_bm25 import BM25Okapi

load_dotenv(dotenv_path=Path(__file__).with_name(".env"), override=True)

POSTS_PATH = Path("data/exports/consulate_posts.jsonl")
EMBED_CACHE = Path("data/embeddings_cache.npy")
EMBED_IDS_CACHE = Path("data/embeddings_ids.json")
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o")
CHAT_PASSWORD = os.getenv("CHAT_PASSWORD", "").strip()
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "false").lower() == "true"
TOP_K = 5           # 상위 5개 게시글 검색 (TOP3 핵심 답변 + TOP4~5 추가 링크)
MAX_POST_CHARS = 4000  # 게시글 1개당 최대 전달 문자 (전체 avg ~2000자)
MAX_CONTEXT_CHARS = 16000  # TOP5 수용을 위해 확장
LOW_CONFIDENCE_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_THRESHOLD", "1.0"))

SYSTEM_PROMPT = """\
당신은 주토론토 대한민국 총영사관 공식 민원 안내 챗봇입니다.

[핵심 원칙]
1. 제공된 영사관 게시글 원문에 있는 내용만 답변합니다.
2. 원문에 없는 내용은 절대 추가하지 않습니다.
3. 수수료, 처리기간, 구비서류, 신청 조건은 원문 표현 그대로 사용합니다.
4. 내용이 방대하거나 복잡하면 핵심만 간략히 안내하고 원문 링크를 제공합니다.
5. 매 답변 말미에 면책 고지를 포함합니다.

[절대 금지]
- 원문에 없는 구비서류·조건 추가
- 수수료 환율 변환 또는 추산
- 처리기간 임의 단축·확대
- 첨부파일 내용을 확인한 것처럼 답변
- ## 공관 공식 게시글 섹션에 게시글 본문 내 링크(양식·첨부파일 등) 포함 — 반드시 [게시글 N]의 URL 필드 링크만 나열할 것

[답변 형식]
답변은 반드시 아래 마크다운 형식을 따르세요.

## 핵심 안내
(핵심 3~5개 bullet. 방대한 경우 가장 중요한 항목만. bullet 내에 [게시글 N] 같은 인용 번호 절대 표기 금지)

> ⚠️ 구비서류 및 절차는 변경될 수 있으므로, 신청 전 반드시 아래 공관 공식 게시글을 직접 확인하신 후 진행하시기 바랍니다.

## 공관 공식 게시글 (필수 확인)
제공된 게시글 전체(최대 5개)를 아래 형식으로 모두 나열하세요.
- 게시글 1~3: 제목 앞에 "✅ " 추가
- 게시글 4~5: 제목 앞에 "📎 " 추가
반드시 아래 형식을 정확히 지키세요 (괄호와 URL 사이에 공백 없이):
✅ [게시글 제목](URL)
📎 [게시글 제목](URL)
⚠️ 제목에 괄호가 포함된 경우에도 위 형식 유지. 절대로 URL 앞에 토픽명이나 설명을 추가하지 말 것.

---
⚠️ 본 내용은 AI가 주토론토총영사관 공식 홈페이지 게시글을 기반으로 요약한 것입니다. \
실제 최신 정보와 다를 수 있으므로, 전체 필요서류 및 안내사항은 반드시 위 공관 공식 게시글 원문을 직접 확인하시기 바랍니다.
📅 모든 민원은 사전 예약이 원칙입니다 → [torbooking.com](https://www.torbooking.com)

[구비서류·절차 등 상세 내용이 많을 때]
모든 항목을 나열하지 말고, 가장 핵심적인 2~3개만 안내한 뒤
"정확한 구비서류와 절차는 위 공관 공식 게시글에서 반드시 확인하시기 바랍니다."로 마무리하세요.

[관련 게시글이 없을 때]
"현재 수집된 게시글에서 해당 내용을 찾을 수 없습니다. \
공식 홈페이지(https://toronto.mofa.go.kr)에서 직접 확인하시거나 \
영사관(+1-416-920-3809 / toronto@mofa.go.kr)에 문의하시기 바랍니다."

[언어 규칙]
한국어 질문 → 한국어 답변 / 영어 질문 → 영어 답변
"""

posts: list[dict] = []
bm25_index: BM25Okapi | None = None
topic_indices: dict[str, tuple[list[int], BM25Okapi]] = {}  # topic → (global_idxs, bm25)
embeddings: np.ndarray | None = None
client: AsyncOpenAI | None = None

# 쿼리 구어체 어미 제거 패턴
_STRIP_SUFFIX = re.compile(
    r"[이가을를은는]?\s*"
    r"(궁금합니다|궁금해요|알고\s*싶습니다|알고\s*싶어요|알려주세요"
    r"|어떻게\s*하나요|어떻게\s*되나요|해주세요|부탁드립니다)\s*[.?！!]*$"
)

# 토픽 감지 키워드 (순서 중요: 더 구체적인 것 먼저)
_TOPIC_KEYWORDS: list[tuple[list[str], str]] = [
    (["긴급여권", "단수여권"], "여권"),
    (["여권"], "여권"),
    (["비자", "사증", "visa", "사증면제", "재입국"], "비자"),
    (["공증"], "공증"),
    (["병역", "병무"], "병역"),
    (["공동인증서", "금융인증서"], "공동인증서"),
    (["가족관계", "출생신고", "혼인신고", "사망신고", "이혼신고"], "가족관계등록"),
    (["국적", "귀화", "시민권"], "국적"),
    (["재외국민"], "재외국민등록"),
    (["해외이주"], "해외이주신고"),
    (["증명서"], "각종 증명서 발급"),
]


def detect_topic(query: str) -> str | None:
    q = query.lower()
    for keywords, topic in _TOPIC_KEYWORDS:
        if any(kw in q for kw in keywords):
            return topic
    return None


def clean_query(query: str) -> str:
    return _STRIP_SUFFIX.sub("", query.strip()).strip() or query.strip()


def embed_text(post: dict) -> str:
    """임베딩용 텍스트: topic + title + 본문 앞부분."""
    return f"{post['topic']} | {post['title']}\n{post.get('content_text', '')[:2000]}"


def tokenize(text: str) -> list[str]:
    """한국어 BM25 토크나이저: 어절 + 2~3자 n-gram."""
    text = text.lower()
    tokens = re.findall(r"[가-힣a-z0-9]+", text)
    ngrams = [
        t[i : i + n]
        for t in tokens
        for n in (2, 3)
        for i in range(max(len(t) - n + 1, 0))
    ]
    return tokens + ngrams


def is_useful_post(post: dict) -> bool:
    """본문이 80자 미만인 빈 게시글은 제외."""
    return len(post.get("content_text", "").strip()) >= 80


async def build_embeddings() -> np.ndarray:
    current_ids = [p["post_id"] for p in posts]
    if EMBED_CACHE.exists() and EMBED_IDS_CACHE.exists():
        if json.loads(EMBED_IDS_CACHE.read_text()) == current_ids:
            print("임베딩 캐시 로드 완료.")
            return np.load(EMBED_CACHE)

    print(f"임베딩 생성 중 ({len(posts)}개 게시글)...")
    texts = [embed_text(p) for p in posts]
    all_vecs: list[list[float]] = []
    for i in range(0, len(texts), 50):
        resp = await client.embeddings.create(model=EMBED_MODEL, input=texts[i : i + 50])
        all_vecs.extend([e.embedding for e in resp.data])
        await asyncio.sleep(0.3)

    arr = np.array(all_vecs, dtype=np.float32)
    np.save(EMBED_CACHE, arr)
    EMBED_IDS_CACHE.write_text(json.dumps(current_ids), encoding="utf-8")
    print("임베딩 생성 완료.")
    return arr


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global posts, bm25_index, embeddings, client

    api_key = os.getenv("OPENAI_API_KEY", "")
    client = AsyncOpenAI(api_key=api_key)

    with open(POSTS_PATH, encoding="utf-8") as f:
        all_posts = [json.loads(l) for l in f if l.strip()]
    posts = [p for p in all_posts if is_useful_post(p)]
    print(f"게시글 로드: {len(all_posts)}개 중 {len(posts)}개 사용")

    def make_doc(p: dict) -> list[str]:
        return tokenize(p["topic"] + " " + p["title"] * 3 + " " + p.get("content_text", ""))

    corpus = [make_doc(p) for p in posts]
    bm25_index = BM25Okapi(corpus)

    # 토픽별 서브인덱스 빌드
    from collections import defaultdict
    topic_map: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(posts):
        topic_map[p["topic"]].append(i)
    for topic, idxs in topic_map.items():
        sub_corpus = [corpus[i] for i in idxs]
        topic_indices[topic] = (idxs, BM25Okapi(sub_corpus))
    print(f"BM25 인덱스 완료. 토픽별 서브인덱스: {list(topic_map.keys())}")

    if ENABLE_EMBEDDINGS and api_key and api_key != "your_openai_api_key_here":
        try:
            embeddings = await build_embeddings()
        except Exception as e:
            print(f"임베딩 실패 ({e}). BM25 단독 모드.")
    elif not ENABLE_EMBEDDINGS:
        print("ENABLE_EMBEDDINGS=false. BM25 단독 모드.")
    else:
        print("API 키 미설정. BM25 단독 모드.")

    yield


async def hybrid_search(query: str) -> tuple[list[dict], float]:
    """Returns (top posts, max_bm25_score). Low max_bm25_score signals low confidence."""
    q_clean = clean_query(query)
    q_tokens = tokenize(q_clean)
    topic = detect_topic(q_clean)

    # 토픽이 감지되면 해당 토픽 서브인덱스 우선 사용
    if topic and topic in topic_indices:
        global_idxs, sub_bm25 = topic_indices[topic]
        sub_scores = sub_bm25.get_scores(q_tokens)
        max_bm25 = float(sub_scores.max())
        top_local = np.argsort(sub_scores)[::-1][:TOP_K].tolist()
        result_posts = [posts[global_idxs[i]] for i in top_local]
        print(f"[search] topic={topic!r} q={q_clean!r} bm25_max={max_bm25:.2f}")
        return result_posts, max_bm25

    # 토픽 미감지: 전체 인덱스 사용
    bm25_scores = bm25_index.get_scores(q_tokens)
    max_bm25 = float(bm25_scores.max())
    bm25_ranked = np.argsort(bm25_scores)[::-1][:20].tolist()

    sem_ranked: list[int] = []
    if embeddings is not None:
        resp = await client.embeddings.create(model=EMBED_MODEL, input=[query])
        q_vec = np.array(resp.data[0].embedding, dtype=np.float32)
        norms = np.linalg.norm(embeddings, axis=1) + 1e-10
        sims = (embeddings @ q_vec) / norms
        sem_ranked = np.argsort(sims)[::-1][:20].tolist()

    scores: dict[int, float] = {}
    for rank, idx in enumerate(bm25_ranked):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (60 + rank + 1)
    for rank, idx in enumerate(sem_ranked):
        scores[idx] = scores.get(idx, 0.0) + 1.0 / (60 + rank + 1)

    fused = sorted(scores, key=scores.__getitem__, reverse=True)
    print(f"[search] topic=None q={q_clean!r} bm25_max={max_bm25:.2f}")
    return [posts[i] for i in fused[:TOP_K]], max_bm25


app = FastAPI(title="주토론토총영사관 챗봇", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str


class AuthRequest(BaseModel):
    password: str


def require_chat_password(password: str | None) -> None:
    if CHAT_PASSWORD and (password or "").strip() != CHAT_PASSWORD:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")


@app.post("/api/auth")
async def auth(req: AuthRequest):
    require_chat_password(req.password)
    return {"ok": True}


@app.post("/api/chat")
async def chat(req: ChatRequest, x_chat_password: str | None = Header(default=None)):
    require_chat_password(x_chat_password)
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다.")

    results, bm25_confidence = await hybrid_search(query)
    low_confidence = bm25_confidence < LOW_CONFIDENCE_THRESHOLD
    print(f"[search] query={query!r} bm25_max={bm25_confidence:.3f} low_confidence={low_confidence}")

    def safe_title(title: str) -> str:
        """제목의 [ ] → ( ) 치환 — GPT 마크다운 링크 생성 시 중첩 괄호 방지."""
        return title.replace("[", "(").replace("]", ")")

    # 게시글 전문을 컨텍스트로 구성
    context_parts: list[str] = []
    used: list[dict] = []
    total = 0
    for i, p in enumerate(results, 1):
        body = p.get("content_text", "")[:MAX_POST_CHARS]
        part = (
            f"[게시글 {i}] 주제: {p['topic']} | 제목: {safe_title(p['title'])} | "
            f"작성일: {p.get('post_date', '미상')} | URL: {p['url']}\n{body}\n"
        )
        if total + len(part) > MAX_CONTEXT_CHARS:
            break
        context_parts.append(part)
        used.append(p)
        total += len(part)

    context = "\n---\n".join(context_parts)
    user_msg = (
        "아래 영사관 게시글을 근거로 질문에 답변해주세요.\n"
        "게시글 1~3번이 핵심 출처입니다. 4~5번은 추가 참고용입니다.\n"
        "내용이 방대하면 핵심만 간략히 안내하고 게시글 링크를 모두 제공하세요.\n\n"
        f"게시글:\n{context}\n\n질문: {query}"
    )

    sources = [
        {
            "title": p["title"],
            "topic": p["topic"],
            "url": p["url"],
            "post_date": p.get("post_date", ""),
        }
        for p in used
    ]

    async def stream() -> AsyncIterator[str]:
        try:
            if low_confidence:
                topics = "、".join(p["topic"] for p in used)
                header = (
                    f"문의하신 내용을 정확히 파악하기 어렵습니다. "
                    f"혹시 **{topics}** 관련 내용을 문의하신 건가요?\n\n"
                    f"관련 게시글을 참고로 안내해 드립니다.\n\n---\n\n"
                )
                yield f"data: {json.dumps({'t': header}, ensure_ascii=False)}\n\n"

            response = await client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.05,
                max_tokens=800,   # 짧고 정확하게
                stream=True,
            )
            async for event in response:
                delta = event.choices[0].delta.content or ""
                if delta:
                    yield f"data: {json.dumps({'t': delta}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True, 'sources': sources}, ensure_ascii=False)}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory="static", html=True), name="static")
