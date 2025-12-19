# Database ER Diagram

## Overview

PostgreSQL 데이터베이스 구조 (realtime_assist)

```mermaid
erDiagram
    %% 고객 및 상담 이력 도메인
    customers {
        bigint customer_id PK
        varchar customer_name
        varchar phone_number
        int age
        varchar gender
        varchar residence
        varchar membership_grade
        varchar current_plan
        int monthly_fee
        varchar contract_status
        varchar bundle_info
        varchar data_allowance
        date subscription_date
        jsonb consultation_history
        timestamptz created_at
    }

    consultation_history {
        bigint consultation_id PK
        bigint customer_id FK
        date consultation_date
        varchar consultation_type
        jsonb detail
        timestamptz created_at
    }

    %% 상담사 도메인
    agents {
        int agent_id PK
        varchar agent_code UK
        varchar agent_name
        timestamptz created_at
    }

    %% 실시간 통화 도메인 (rooms 중심)
    rooms {
        uuid id PK
        varchar room_name
        timestamptz created_at
        timestamptz ended_at
        varchar status
        jsonb metadata
    }

    peers {
        uuid id PK
        uuid room_id FK
        varchar peer_id
        varchar nickname
        timestamptz joined_at
        timestamptz left_at
    }

    transcripts {
        bigint id PK
        uuid room_id FK
        varchar peer_id
        varchar nickname
        text text
        timestamptz timestamp
        varchar source
        boolean is_final
        timestamptz created_at
    }

    agent_summaries {
        bigint id PK
        uuid room_id FK
        text summary_text
        int last_summarized_index
        timestamptz created_at
    }

    %% 상담 세션 도메인 (consultation_sessions 중심)
    consultation_sessions {
        uuid session_id PK
        uuid room_id FK
        bigint customer_id
        varchar agent_id
        varchar agent_name
        timestamptz started_at
        timestamptz ended_at
        int duration_seconds
        varchar status
        varchar channel
        text final_summary
        varchar consultation_type
        jsonb metadata
        timestamptz created_at
    }

    consultation_transcripts {
        bigint transcript_id PK
        uuid session_id FK
        int turn_index
        varchar speaker_type
        varchar speaker_name
        text text
        timestamptz timestamp
        float confidence
        boolean is_final
        varchar source
        timestamptz created_at
    }

    consultation_agent_results {
        bigint result_id PK
        uuid session_id FK
        varchar turn_id
        varchar result_type
        jsonb result_data
        int processing_time_ms
        varchar model_version
        timestamptz created_at
    }

    %% 벡터 DB 도메인 (LangChain)
    langchain_pg_collection {
        uuid uuid PK
        varchar name UK
        jsonb cmetadata
        timestamptz created_at
    }

    langchain_pg_embedding {
        uuid id PK
        uuid collection_id FK
        vector embedding
        text document
        jsonb cmetadata
        timestamptz created_at
    }

    langchain_pg_embedding_1536 {
        uuid id PK
        uuid collection_id FK
        vector embedding
        text document
        jsonb cmetadata
        timestamptz created_at
    }

    %% 캐시 및 로그
    faq_query_cache {
        int id PK
        text query_text
        vector query_embedding
        varchar category
        jsonb faq_results
        timestamp created_at
        int hit_count
    }

    system_logs {
        bigint id PK
        varchar level
        varchar logger_name
        text message
        varchar module
        varchar func_name
        int line_no
        text exception
        jsonb extra
        timestamptz created_at
    }

    %% 관계 정의
    customers ||--o{ consultation_history : "has"

    rooms ||--o{ peers : "contains"
    rooms ||--o{ transcripts : "records"
    rooms ||--o{ agent_summaries : "generates"
    rooms ||--o| consultation_sessions : "links to"

    consultation_sessions ||--o{ consultation_transcripts : "has"
    consultation_sessions ||--o{ consultation_agent_results : "produces"

    langchain_pg_collection ||--o{ langchain_pg_embedding : "contains"
    langchain_pg_collection ||--o{ langchain_pg_embedding_1536 : "contains"
```

## Table Summary

| Domain | Table | Description |
|--------|-------|-------------|
| **Customer** | `customers` | KT 고객 정보 (요금제, 등급 등) |
| | `consultation_history` | 고객별 상담 이력 |
| **Agent** | `agents` | 상담사 정보 |
| **Realtime Call** | `rooms` | WebRTC 상담 룸 |
| | `peers` | 룸 참가자 |
| | `transcripts` | STT 실시간 전사 |
| | `agent_summaries` | LangGraph 요약 결과 |
| **Consultation Session** | `consultation_sessions` | 상담 세션 메타데이터 |
| | `consultation_transcripts` | 정제된 대화 기록 |
| | `consultation_agent_results` | AI 분석 결과 |
| **Vector DB** | `langchain_pg_collection` | 임베딩 컬렉션 |
| | `langchain_pg_embedding` | 문서 임베딩 (3072 dim) |
| | `langchain_pg_embedding_1536` | 문서 임베딩 (1536 dim) |
| **System** | `faq_query_cache` | FAQ 검색 캐시 |
| | `system_logs` | 시스템 로그 |

## Domain Details

### Customer Domain
- `customers`: 고객 기본 정보, 요금제, 멤버십 등급 관리
- `consultation_history`: 고객별 상담 이력 추적 (FK: customer_id)

### Realtime Call Domain
- `rooms`: WebRTC 기반 상담 룸 (중심 엔티티)
- `peers`: 룸에 참가한 사용자 (상담사/고객)
- `transcripts`: Google STT로 실시간 전사된 대화
- `agent_summaries`: LangGraph 에이전트가 생성한 요약

### Consultation Session Domain
- `consultation_sessions`: 상담 세션 메타데이터 (rooms와 연결)
- `consultation_transcripts`: turn 단위로 정제된 대화 기록
- `consultation_agent_results`: AI 분석 결과 (의도 파악, 추천 등)

### Vector DB Domain (LangChain/RAG)
- `langchain_pg_collection`: 벡터 컬렉션 (FAQ, 정책 문서 등)
- `langchain_pg_embedding`: 문서 임베딩 저장
- `langchain_pg_embedding_1536`: 1536차원 임베딩 (OpenAI ada-002)

### System Domain
- `faq_query_cache`: FAQ 검색 결과 캐싱 (벡터 유사도 검색 최적화)
- `system_logs`: 애플리케이션 로그 저장

## Views

- `customer_consultation_summary`: 고객별 상담 요약 뷰
- `room_conversation_summary`: 룸별 대화 요약 뷰
