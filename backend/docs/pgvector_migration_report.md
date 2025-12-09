# pgvector 마이그레이션 보고서

## 개요

ChromaDB에서 PostgreSQL pgvector로 벡터 데이터베이스를 마이그레이션했습니다.

**마이그레이션 일자**: 2024-12-09

## 데이터베이스 현황

### 컬렉션 목록

| 컬렉션 이름 | UUID | 문서 수 | 임베딩 차원 | 테이블 |
|------------|------|--------|------------|--------|
| aicc_documents | bcd79797-ae3a-436b-b4d4-1fcc6d98dde8 | 2,971 | 3072 | langchain_pg_embedding |
| aicc_documents_dummie | d250b68a-f380-4af6-989d-f7d3251e295b | 139 | 1536 | langchain_pg_embedding_1536 |

### 테이블 구조

#### langchain_pg_embedding (3072차원)
```sql
CREATE TABLE langchain_pg_embedding (
    id UUID PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid),
    embedding vector(3072),
    document TEXT,
    cmetadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE
);
```
- **사용 모델**: text-embedding-3-large
- **인덱스**: 순차 스캔 (pgvector 0.8.x는 2000차원 초과 인덱스 미지원)

#### langchain_pg_embedding_1536 (1536차원)
```sql
CREATE TABLE langchain_pg_embedding_1536 (
    id UUID PRIMARY KEY,
    collection_id UUID REFERENCES langchain_pg_collection(uuid),
    embedding vector(1536),
    document TEXT,
    cmetadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE
);
```
- **사용 모델**: text-embedding-3-small
- **인덱스**: IVFFlat (lists=11)

### 인덱스 목록

| 테이블 | 인덱스 이름 | 유형 |
|-------|-----------|------|
| langchain_pg_embedding | langchain_pg_embedding_pkey | btree (id) |
| langchain_pg_embedding | idx_langchain_embedding_collection | btree (collection_id) |
| langchain_pg_embedding | idx_langchain_embedding_metadata | gin (cmetadata) |
| langchain_pg_embedding_1536 | langchain_pg_embedding_1536_pkey | btree (id) |
| langchain_pg_embedding_1536 | idx_embedding_1536_ivfflat | ivfflat (embedding) |

---

## aicc_documents_dummie 컬렉션 상세

### 메타데이터 필드

| 필드명 | 설명 | 예시 |
|-------|------|------|
| `category` | 문서 카테고리 | kt_additional_plans, kt_billing_micropayment |
| `classification` | 상담 분류 | 요금제문의, 부가서비스, 결합문의 |
| `classification_confidence` | 분류 신뢰도 | 0.9 |
| `customer_intents` | 고객 의도 | 요금제문의, 요금제변경, 비용절감 |
| `target_customers` | 대상 고객 | 월 20~50GB 사용자, 비용 절감 원하는 고객 |
| `keywords` | 문서 키워드 | 5G 스탠다드, 75,000원, 50GB |
| `combined_keywords` | 통합 키워드 | 문서 + 상담 키워드 결합 |
| `consultation_keywords` | 상담 키워드 | 5G 스탠다드, 5G 슬림, QoS, 속도제한 |
| `document_keywords` | 문서 키워드 | VIP, 무제한, 25% 할인 |
| `title` | 문서 제목 | 추가 요금제 정보 > 5G 스탠다드 > 핵심 정보 |
| `source` | 원본 파일 경로 | ./docs_data/json_dummie\kt_additional_plans.json |
| `document_type` | 문서 유형 | mobile_plan |
| `chunk_type` | 청크 유형 | text |
| `price_info` | 가격 정보 (JSON) | {"5G 스탠다드": {"monthly_price": 75000, ...}} |
| `discount_info` | 할인 정보 (JSON) | {"선택약정 12개월 할인": {"amount": 5000, ...}} |
| `hypothetical_queries` | 가상 질문 (HyDE) | ["5G 스탠다드 요금제 어떻게 신청하나요?", ...] |
| `has_hyde` | HyDE 적용 여부 | true |
| `has_contextual` | 컨텍스트 정보 포함 | true |
| `is_split` | 분할 여부 | false |
| `split_part` | 분할 파트 번호 | 0 |
| `split_total` | 전체 분할 수 | 1 |
| `conditions` | 조건 | (빈 값) |
| `required_documents` | 필요 서류 | (빈 값) |

### 카테고리별 문서 분포

| 카테고리 | 문서 수 | 설명 |
|---------|--------|------|
| kt_consultation_guide | 28 | 상담 가이드 |
| kt_billing_micropayment | 22 | 소액결제/청구 |
| kt_tv_services | 22 | TV 서비스 |
| kt_roaming_service | 19 | 로밍 서비스 |
| kt_bundle_detail | 18 | 결합 상품 상세 |
| kt_name_change_account | 16 | 명의변경/계정 |
| kt_additional_plans | 14 | 추가 요금제 |
| **합계** | **139** | |

### 분류(Classification)별 문서 분포

| 분류 | 문서 수 | 비율 |
|-----|--------|------|
| 부가서비스 | 64 | 46.0% |
| 결합문의 | 18 | 12.9% |
| 요금제문의 | 16 | 11.5% |
| 명의변경 | 15 | 10.8% |
| 일반문의 | 12 | 8.6% |
| 비용절감 | 6 | 4.3% |
| 약정문의 | 5 | 3.6% |
| 요금제변경 | 2 | 1.4% |
| 결합변경 | 1 | 0.7% |
| **합계** | **139** | **100%** |

---

## 샘플 문서

### Document 1: kt_consultation_kt_additional_plans_0

**제목**: 추가 요금제 정보 > 5G 스탠다드 > 핵심 정보

**분류**: 요금제문의 (신뢰도: 0.9)

**대상 고객**:
- 월 20~50GB 사용자
- 데이터 무제한이 필요하지만 비용 절감 원하는 고객
- 월 20~30GB 사용자
- 와이파이 환경이 좋은 고객
- 가성비 중시 고객

**가격 정보**:
```json
{
  "5G 스탠다드": {
    "monthly_price": 75000,
    "data": {
      "base_amount": "50GB",
      "after_exhaustion_speed": "5Mbps",
      "unlimited_after_base": true
    },
    "membership": "VIP"
  },
  "5G 슬림": {
    "monthly_price": 61000,
    "data": {
      "base_amount": "30GB",
      "after_exhaustion_speed": "1Mbps"
    },
    "membership": "일반"
  },
  "5G 초이스": {
    "monthly_price": 69000,
    "data": {
      "base_amount": "40GB",
      "after_exhaustion_speed": "3Mbps"
    },
    "membership": "VIP"
  }
}
```

**할인 정보**:
```json
{
  "선택약정 12개월 할인": {
    "amount": 5000,
    "rate": null,
    "period": 12
  },
  "선택약정 24개월 할인": {
    "amount": null,
    "rate": 25,
    "period": 24
  }
}
```

**가상 질문 (HyDE)**:
1. "5G 스탠다드 요금제 어떻게 신청하나요?"
2. "저는 매달 75,000원을 내고 있는데, 데이터가 부족해서 고민이에요..."
3. "5G 스탠다드 요금제와 다른 요금제는 어떤 차이가 있나요?"
4. "5G 스탠다드 약정하면 위약금이 얼마나 나오나요?"
5. "VIP 멤버십이면 5G 스탠다드 요금제에서 어떤 추가 혜택이 있나요?"

**문서 내용 (일부)**:
```
[상담 분류: 요금제문의]
[고객 의도: 요금제문의, 요금제변경, 비용절감]
[대상 고객: 월 20~50GB 사용자, 데이터 무제한이 필요하지만 비용 절감 원하는 고객, 월 20~30GB 사용자]
[문서 키워드: 5G 스탠다드, 75000원, VIP, 무제한, 25% 할인, 데이터 소진 후 5Mbps, 월 20~50GB 사용자, 비용 절감, 5G, 선택약정...]
```

---

## 쿼리 예시

### PostgreSQL에서 유사도 검색

```sql
-- 1536차원 벡터 검색 (aicc_documents_dummie)
SELECT
    document,
    cmetadata->>'title' as title,
    cmetadata->>'classification' as classification,
    1 - (embedding <=> '[query_vector]') as similarity
FROM langchain_pg_embedding_1536
WHERE collection_id = 'd250b68a-f380-4af6-989d-f7d3251e295b'
ORDER BY embedding <=> '[query_vector]'
LIMIT 5;

-- 메타데이터 필터링
SELECT document, cmetadata->>'title' as title
FROM langchain_pg_embedding_1536
WHERE collection_id = 'd250b68a-f380-4af6-989d-f7d3251e295b'
  AND cmetadata->>'classification' = '요금제문의'
ORDER BY embedding <=> '[query_vector]'
LIMIT 5;

-- 카테고리별 집계
SELECT
    cmetadata->>'category' as category,
    COUNT(*) as count
FROM langchain_pg_embedding_1536
GROUP BY cmetadata->>'category'
ORDER BY count DESC;
```

### Python LangChain PGVector 사용

```python
from langchain_postgres import PGVector
from langchain_openai import OpenAIEmbeddings

# 1536차원 컬렉션용
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vectorstore = PGVector(
    embeddings=embeddings,
    collection_name="aicc_documents_dummie",
    connection="postgresql+psycopg://assistant:assistant123@localhost:5432/realtime_assist",
    use_jsonb=True,
)

# 유사도 검색
results = vectorstore.similarity_search("5G 요금제 추천해주세요", k=5)

# 메타데이터 필터링
results = vectorstore.similarity_search(
    "요금제 변경",
    k=5,
    filter={"classification": "요금제문의"}
)
```

---

## 마이그레이션 스크립트

마이그레이션 스크립트 위치: `backend/scripts/migrate_chroma_to_pgvector.py`

### 사용법

```bash
cd backend

# 기본 실행 (환경변수 사용)
uv run python scripts/migrate_chroma_to_pgvector.py

# 환경변수 지정
CHROMA_DB_PATH=/path/to/chroma CHROMA_COLLECTION_NAME=my_collection \
    uv run python scripts/migrate_chroma_to_pgvector.py
```

### 환경변수

| 변수 | 설명 | 기본값 |
|-----|------|--------|
| CHROMA_DB_PATH | ChromaDB 데이터 경로 | (필수) |
| CHROMA_COLLECTION_NAME | ChromaDB 컬렉션 이름 | kt_terms |
| DATABASE_URL | PostgreSQL 연결 문자열 | postgresql://assistant:assistant123@localhost:5432/realtime_assist |

---

## 제한 사항 및 참고 사항

1. **pgvector 차원 제한**
   - pgvector 0.8.x는 IVFFlat/HNSW 인덱스에 2000차원 제한
   - 3072차원(text-embedding-3-large)은 순차 스캔 사용
   - 1536차원(text-embedding-3-small)은 IVFFlat 인덱스 가능

2. **성능 고려사항**
   - 2971개 문서: 순차 스캔으로도 충분히 빠름
   - 139개 문서: IVFFlat 인덱스로 최적화

3. **두 개의 임베딩 테이블**
   - `langchain_pg_embedding`: 3072차원 (기존 데이터)
   - `langchain_pg_embedding_1536`: 1536차원 (dummie 데이터)
   - 사용하는 임베딩 모델에 맞는 테이블 선택 필요
