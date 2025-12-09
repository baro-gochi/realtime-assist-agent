"""ChromaDB에서 PostgreSQL pgvector로 데이터 마이그레이션 스크립트.

Usage:
    cd backend
    uv run python scripts/migrate_chroma_to_pgvector.py

환경 변수 설정 필요:
- CHROMA_DB_PATH: ChromaDB 데이터 경로
- DATABASE_URL: PostgreSQL 연결 문자열
"""

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import asyncpg
import chromadb
from chromadb.config import Settings
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
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://assistant:assistant123@localhost:5432/realtime_assist")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "kt_terms")
BATCH_SIZE = 100  # 배치 삽입 크기


def get_chroma_data(chroma_path: str, collection_name: str) -> Tuple[List[str], List[List[float]], List[str], List[Dict[str, Any]]]:
    """ChromaDB에서 모든 데이터 추출.

    Returns:
        Tuple of (ids, embeddings, documents, metadatas)
    """
    logger.info(f"ChromaDB 연결 중: {chroma_path}")

    client = chromadb.PersistentClient(
        path=chroma_path,
        settings=Settings(anonymized_telemetry=False)
    )

    # 컬렉션 정보 확인
    collections = client.list_collections()
    logger.info(f"발견된 컬렉션: {[c.name for c in collections]}")

    collection = client.get_collection(collection_name)
    count = collection.count()
    logger.info(f"컬렉션 '{collection_name}' 문서 수: {count}")

    if count == 0:
        logger.warning("컬렉션이 비어있습니다.")
        return [], [], [], []

    # 모든 데이터 가져오기 (include로 모든 필드 요청)
    result = collection.get(
        include=["embeddings", "documents", "metadatas"]
    )

    ids = result.get("ids", [])
    embeddings = result.get("embeddings", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    logger.info(f"추출된 데이터: {len(ids)} 문서")

    # 데이터 검증 (numpy array 처리)
    if embeddings is not None and len(embeddings) > 0:
        first_embedding = embeddings[0]
        if hasattr(first_embedding, '__len__'):
            logger.info(f"임베딩 차원: {len(first_embedding)}")

    # embeddings를 리스트로 변환 (numpy array일 수 있음)
    if hasattr(embeddings, 'tolist'):
        embeddings = embeddings.tolist()

    return ids, embeddings, documents, metadatas


async def create_pgvector_schema(conn: asyncpg.Connection) -> None:
    """pgvector 스키마 생성."""
    schema_sql = """
    -- 확장 기능 활성화 (이미 있으면 무시)
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    CREATE EXTENSION IF NOT EXISTS "vector";

    -- 컬렉션 테이블
    CREATE TABLE IF NOT EXISTS langchain_pg_collection (
        uuid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        name VARCHAR(255) NOT NULL UNIQUE,
        cmetadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- 임베딩 테이블 (3072차원 = text-embedding-3-large)
    CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
        embedding vector(3072),
        document TEXT,
        cmetadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    -- 인덱스
    CREATE INDEX IF NOT EXISTS idx_langchain_embedding_collection
    ON langchain_pg_embedding(collection_id);

    CREATE INDEX IF NOT EXISTS idx_langchain_embedding_metadata
    ON langchain_pg_embedding
    USING gin (cmetadata);
    """

    await conn.execute(schema_sql)
    logger.info("pgvector 스키마 생성 완료")


async def get_or_create_collection(conn: asyncpg.Connection, collection_name: str) -> str:
    """컬렉션 조회 또는 생성."""
    import json

    # 기존 컬렉션 조회
    row = await conn.fetchrow(
        "SELECT uuid FROM langchain_pg_collection WHERE name = $1",
        collection_name
    )

    if row:
        logger.info(f"기존 컬렉션 사용: {collection_name} ({row['uuid']})")
        return str(row['uuid'])

    # 새 컬렉션 생성
    collection_uuid = str(uuid.uuid4())
    await conn.execute(
        """
        INSERT INTO langchain_pg_collection (uuid, name, cmetadata)
        VALUES ($1::uuid, $2, $3::jsonb)
        """,
        collection_uuid, collection_name, json.dumps({})
    )
    logger.info(f"새 컬렉션 생성: {collection_name} ({collection_uuid})")
    return collection_uuid


async def insert_embeddings_batch(
    conn: asyncpg.Connection,
    collection_uuid: str,
    ids: List[str],
    embeddings: List[List[float]],
    documents: List[str],
    metadatas: List[Dict[str, Any]]
) -> int:
    """배치로 임베딩 삽입."""
    import json

    # 데이터 준비
    records = []
    for i, (doc_id, embedding, document, metadata) in enumerate(zip(ids, embeddings, documents, metadatas)):
        # UUID 변환 또는 새로 생성
        try:
            embedding_uuid = str(uuid.UUID(doc_id))
        except (ValueError, TypeError):
            embedding_uuid = str(uuid.uuid4())

        # 임베딩을 문자열 형식으로 변환 (pgvector 형식)
        embedding_str = f"[{','.join(map(str, embedding))}]"

        records.append((
            embedding_uuid,
            collection_uuid,
            embedding_str,
            document or "",
            json.dumps(metadata or {})
        ))

    # 배치 삽입
    await conn.executemany(
        """
        INSERT INTO langchain_pg_embedding (id, collection_id, embedding, document, cmetadata)
        VALUES ($1::uuid, $2::uuid, $3::vector, $4, $5::jsonb)
        ON CONFLICT (id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            document = EXCLUDED.document,
            cmetadata = EXCLUDED.cmetadata
        """,
        records
    )

    return len(records)


async def migrate_to_pgvector(
    chroma_path: str,
    database_url: str,
    collection_name: str
) -> Dict[str, Any]:
    """ChromaDB에서 pgvector로 마이그레이션 수행."""
    result = {
        "success": False,
        "source_count": 0,
        "migrated_count": 0,
        "errors": []
    }

    # 1. ChromaDB 데이터 추출
    logger.info("=" * 50)
    logger.info("1단계: ChromaDB 데이터 추출")
    logger.info("=" * 50)

    try:
        ids, embeddings, documents, metadatas = get_chroma_data(chroma_path, collection_name)
        result["source_count"] = len(ids)

        if not ids:
            logger.warning("마이그레이션할 데이터가 없습니다.")
            result["success"] = True
            return result

    except Exception as e:
        error_msg = f"ChromaDB 데이터 추출 실패: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result

    # 2. PostgreSQL 연결 및 스키마 생성
    logger.info("=" * 50)
    logger.info("2단계: PostgreSQL 연결 및 스키마 설정")
    logger.info("=" * 50)

    try:
        conn = await asyncpg.connect(database_url)
        logger.info("PostgreSQL 연결 성공")

        await create_pgvector_schema(conn)
        collection_uuid = await get_or_create_collection(conn, collection_name)

    except Exception as e:
        error_msg = f"PostgreSQL 연결/스키마 생성 실패: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result

    # 3. 배치 삽입
    logger.info("=" * 50)
    logger.info("3단계: 데이터 마이그레이션")
    logger.info("=" * 50)

    try:
        total_migrated = 0
        total_batches = (len(ids) + BATCH_SIZE - 1) // BATCH_SIZE

        for batch_num in range(total_batches):
            start_idx = batch_num * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(ids))

            batch_ids = ids[start_idx:end_idx]
            batch_embeddings = embeddings[start_idx:end_idx]
            batch_documents = documents[start_idx:end_idx]
            batch_metadatas = metadatas[start_idx:end_idx]

            migrated = await insert_embeddings_batch(
                conn, collection_uuid,
                batch_ids, batch_embeddings, batch_documents, batch_metadatas
            )

            total_migrated += migrated
            logger.info(f"배치 {batch_num + 1}/{total_batches}: {migrated}개 삽입 (누적: {total_migrated})")

        result["migrated_count"] = total_migrated
        result["success"] = True

    except Exception as e:
        error_msg = f"데이터 마이그레이션 실패: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)

    finally:
        await conn.close()
        logger.info("PostgreSQL 연결 종료")

    # 4. 검증
    if result["success"]:
        logger.info("=" * 50)
        logger.info("4단계: 마이그레이션 검증")
        logger.info("=" * 50)

        try:
            conn = await asyncpg.connect(database_url)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM langchain_pg_embedding WHERE collection_id = $1::uuid",
                collection_uuid
            )
            await conn.close()

            logger.info(f"pgvector 테이블 문서 수: {count}")

            if count == result["source_count"]:
                logger.info("마이그레이션 검증 성공: 모든 문서가 이전되었습니다.")
            else:
                logger.warning(f"경고: 문서 수 불일치 (원본: {result['source_count']}, 이전: {count})")

        except Exception as e:
            logger.error(f"검증 실패: {str(e)}")

    return result


async def create_vector_index(database_url: str, vector_dim: int = 3072) -> None:
    """벡터 인덱스 생성 (마이그레이션 후 실행).

    Args:
        database_url: PostgreSQL 연결 문자열
        vector_dim: 벡터 차원 수. 2000 초과시 HNSW, 이하시 IVFFlat 사용
    """
    logger.info("벡터 인덱스 생성 중...")

    conn = await asyncpg.connect(database_url)

    try:
        # 기존 인덱스 삭제 (있으면)
        await conn.execute("DROP INDEX IF EXISTS idx_langchain_embedding_ivfflat")
        await conn.execute("DROP INDEX IF EXISTS idx_langchain_embedding_hnsw")

        # 데이터 수 확인
        count = await conn.fetchval("SELECT COUNT(*) FROM langchain_pg_embedding")

        if count == 0:
            logger.info("데이터가 없어 인덱스 생성 생략")
            return

        logger.info(f"데이터 수: {count}, 벡터 차원: {vector_dim}")

        if vector_dim > 2000:
            # HNSW 인덱스 사용 (고차원 벡터용)
            # m: 각 레이어의 연결 수 (기본값 16, 높을수록 정확도 증가/메모리 증가)
            # ef_construction: 인덱스 구축시 탐색 범위 (기본값 64)
            logger.info("HNSW 인덱스 생성 중 (고차원 벡터)...")
            await conn.execute("""
                CREATE INDEX idx_langchain_embedding_hnsw
                ON langchain_pg_embedding
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
            logger.info("HNSW 인덱스 생성 완료")
        else:
            # IVFFlat 인덱스 사용 (저차원 벡터용)
            import math
            lists = max(1, min(1000, int(math.sqrt(count))))
            logger.info(f"IVFFlat 인덱스 생성 중 (lists={lists})...")
            await conn.execute(f"""
                CREATE INDEX idx_langchain_embedding_ivfflat
                ON langchain_pg_embedding
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = {lists})
            """)
            logger.info("IVFFlat 인덱스 생성 완료")

    finally:
        await conn.close()


async def main():
    """메인 실행 함수."""
    logger.info("=" * 60)
    logger.info("ChromaDB -> pgvector 마이그레이션 시작")
    logger.info("=" * 60)

    # 설정 확인
    if not CHROMA_DB_PATH:
        logger.error("CHROMA_DB_PATH 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    chroma_path = Path(CHROMA_DB_PATH)
    if not chroma_path.exists():
        logger.error(f"ChromaDB 경로가 존재하지 않습니다: {chroma_path}")
        sys.exit(1)

    logger.info(f"ChromaDB 경로: {CHROMA_DB_PATH}")
    logger.info(f"PostgreSQL URL: {DATABASE_URL.split('@')[0]}@***")
    logger.info(f"컬렉션 이름: {COLLECTION_NAME}")

    # 마이그레이션 실행
    result = await migrate_to_pgvector(
        str(chroma_path),
        DATABASE_URL,
        COLLECTION_NAME
    )

    # 결과 출력
    logger.info("=" * 60)
    logger.info("마이그레이션 결과")
    logger.info("=" * 60)
    logger.info(f"성공 여부: {result['success']}")
    logger.info(f"원본 문서 수: {result['source_count']}")
    logger.info(f"마이그레이션된 문서 수: {result['migrated_count']}")

    if result["errors"]:
        logger.error(f"오류: {result['errors']}")

    # 인덱스 생성
    if result["success"] and result["migrated_count"] > 0:
        await create_vector_index(DATABASE_URL)

    logger.info("=" * 60)
    logger.info("마이그레이션 완료")
    logger.info("=" * 60)

    return 0 if result["success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
