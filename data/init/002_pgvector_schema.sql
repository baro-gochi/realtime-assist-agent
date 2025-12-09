-- pgvector 벡터 검색 테이블 스키마
-- LangChain PGVector와 호환되는 구조

-- langchain_pg_collection: 컬렉션 메타데이터 저장
CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    uuid UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    cmetadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- langchain_pg_embedding: 임베딩 벡터와 문서 저장
-- text-embedding-3-large의 벡터 차원: 3072
CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID REFERENCES langchain_pg_collection(uuid) ON DELETE CASCADE,
    embedding vector(3072),
    document TEXT,
    cmetadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 벡터 인덱스 참고 사항:
-- - pgvector 0.8.x는 IVFFlat/HNSW 인덱스에 2000차원 제한이 있음
-- - 3072차원(text-embedding-3-large)은 순차 스캔 사용
-- - 수천 개 문서에서는 순차 스캔도 충분히 빠름
-- - 대규모 데이터의 경우 차원 축소나 halfvec 타입 고려

-- 참고: 2000차원 이하 벡터용 인덱스 예시 (필요시 활성화)
-- CREATE INDEX IF NOT EXISTS idx_langchain_embedding_hnsw
-- ON langchain_pg_embedding
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- 인덱스: collection_id로 빠른 필터링
CREATE INDEX IF NOT EXISTS idx_langchain_embedding_collection
ON langchain_pg_embedding(collection_id);

-- 인덱스: 메타데이터 JSONB 검색
CREATE INDEX IF NOT EXISTS idx_langchain_embedding_metadata
ON langchain_pg_embedding
USING gin (cmetadata);

-- 코멘트
COMMENT ON TABLE langchain_pg_collection IS 'LangChain PGVector 컬렉션 메타데이터';
COMMENT ON TABLE langchain_pg_embedding IS 'LangChain PGVector 임베딩 벡터 저장';
COMMENT ON COLUMN langchain_pg_embedding.embedding IS 'OpenAI text-embedding-3-large 벡터 (3072차원)';
