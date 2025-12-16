"""FAQ 질문을 임베딩하여 pgvector에 저장하는 스크립트.

FAQ 질문 텍스트를 OpenAI 임베딩으로 변환하여 pgvector에 저장합니다.
의미 기반 벡터 검색으로 유사한 FAQ를 찾을 수 있습니다.

Usage:
    cd backend
    uv run python scripts/embed_faq_to_pgvector.py

환경 변수 설정 필요:
- DATABASE_URL: PostgreSQL 연결 문자열
- OPENAI_API_KEY: OpenAI API 키
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import List, Dict, Any

import asyncpg
from dotenv import load_dotenv

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 환경 변수 로드
env_path = Path(__file__).parent.parent / "config" / ".env"
load_dotenv(env_path)

# 설정
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://assistant:assistant123@localhost:5432/realtime_assist")
FAQ_JSON_PATH = Path(__file__).parent.parent.parent / "data" / "kt_faq" / "kt_membership_faq.json"
COLLECTION_NAME = "kt_faq"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def load_faq_data() -> List[Dict[str, Any]]:
    """FAQ JSON 파일에서 데이터 로드."""
    if not FAQ_JSON_PATH.exists():
        logger.error(f"FAQ 파일을 찾을 수 없습니다: {FAQ_JSON_PATH}")
        return []

    with open(FAQ_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    faqs = data.get("faqs", [])
    logger.info(f"로드된 FAQ: {len(faqs)}개")
    return faqs


async def get_embeddings(texts: List[str]) -> List[List[float]]:
    """OpenAI API로 텍스트 임베딩 생성."""
    from langchain_openai import OpenAIEmbeddings

    embeddings_model = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    embeddings = await embeddings_model.aembed_documents(texts)
    return embeddings


async def create_collection(conn: asyncpg.Connection) -> str:
    """FAQ 컬렉션 생성 및 UUID 반환."""
    # 기존 컬렉션 삭제 (재생성을 위해)
    await conn.execute("""
        DELETE FROM langchain_pg_embedding
        WHERE collection_id IN (
            SELECT uuid FROM langchain_pg_collection WHERE name = $1
        )
    """, COLLECTION_NAME)

    await conn.execute("""
        DELETE FROM langchain_pg_collection WHERE name = $1
    """, COLLECTION_NAME)

    # 새 컬렉션 생성
    collection_uuid = str(uuid.uuid4())
    await conn.execute("""
        INSERT INTO langchain_pg_collection (uuid, name, cmetadata)
        VALUES ($1, $2, $3)
    """, collection_uuid, COLLECTION_NAME, json.dumps({
        "description": "KT 멤버십 FAQ - 질문 기반 임베딩",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
    }))

    logger.info(f"컬렉션 생성됨: {COLLECTION_NAME} (UUID: {collection_uuid})")
    return collection_uuid


async def insert_faq_embeddings(
    conn: asyncpg.Connection,
    collection_uuid: str,
    faqs: List[Dict[str, Any]],
    embeddings: List[List[float]]
) -> int:
    """FAQ 임베딩을 pgvector에 삽입."""
    inserted = 0

    for faq, embedding in zip(faqs, embeddings):
        faq_id = faq.get("id", "")
        question = faq.get("question", "")
        answer = faq.get("answer", "")
        category = faq.get("category", "")

        # document: 질문 + 답변 (검색 시 컨텍스트 제공)
        document = f"질문: {question}\n\n답변: {answer}"

        # metadata: 검색 및 필터링용
        metadata = {
            "faq_id": faq_id,
            "category": category,
            "question": question,  # 원본 질문 저장
        }

        # 임베딩 벡터를 문자열로 변환
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"

        try:
            await conn.execute("""
                INSERT INTO langchain_pg_embedding (uuid, collection_id, document, embedding, cmetadata)
                VALUES ($1, $2, $3, $4::vector, $5)
            """, str(uuid.uuid4()), collection_uuid, document, embedding_str, json.dumps(metadata))
            inserted += 1
        except Exception as e:
            logger.error(f"FAQ 삽입 실패 ({faq_id}): {e}")

    return inserted


async def main():
    """메인 실행 함수."""
    logger.info("=" * 60)
    logger.info("FAQ 임베딩 → pgvector 저장 시작")
    logger.info("=" * 60)

    # 1. FAQ 데이터 로드
    faqs = load_faq_data()
    if not faqs:
        logger.error("FAQ 데이터가 없습니다.")
        return

    # 2. 질문 텍스트 추출 (임베딩 대상)
    # 질문 + 카테고리를 함께 임베딩하여 의미 검색 정확도 향상
    texts_to_embed = []
    for faq in faqs:
        question = faq.get("question", "")
        category = faq.get("category", "")
        # 카테고리를 포함하여 임베딩 (예: "[VVIP/VIP] VVIP, VIP가 되면 어떤 혜택이 있나요?")
        text = f"[{category}] {question}" if category else question
        texts_to_embed.append(text)

    logger.info(f"임베딩할 질문: {len(texts_to_embed)}개")

    # 3. 임베딩 생성
    logger.info("OpenAI 임베딩 생성 중...")
    embeddings = await get_embeddings(texts_to_embed)
    logger.info(f"임베딩 생성 완료: {len(embeddings)}개, 차원: {len(embeddings[0])}")

    # 4. PostgreSQL 연결 및 저장
    logger.info(f"PostgreSQL 연결 중: {DATABASE_URL.split('@')[-1]}")
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # 컬렉션 생성
        collection_uuid = await create_collection(conn)

        # 임베딩 삽입
        inserted = await insert_faq_embeddings(conn, collection_uuid, faqs, embeddings)

        logger.info("=" * 60)
        logger.info(f"완료! {inserted}/{len(faqs)}개 FAQ 임베딩 저장됨")
        logger.info(f"컬렉션: {COLLECTION_NAME}")
        logger.info("=" * 60)

        # 검증: 저장된 데이터 확인
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = $1
        """, COLLECTION_NAME)
        logger.info(f"검증: pgvector에 {count}개 FAQ 저장 확인")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
