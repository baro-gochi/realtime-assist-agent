# Realtime Assist Agent - 프로젝트 성과 및 핵심 기능

> LangGraph 기반 실시간 상담 어시스턴트 AI 에이전트

---

## 프로젝트 성과

### 기술적 성과

| 영역 | 성과 지표 | 상세 내용 |
|------|----------|----------|
| **실시간 처리** | 7개 병렬 분석 노드 | 순차 처리 대비 응답 시간 단축 (3-5초/턴) |
| **음성 인식** | Google Chirp 모델 적용 | 한국어 특화 STT, 도메인 용어 Phrase Boost 적용 |
| **캐싱 최적화** | TTFT 50% 감소 | OpenAI Implicit Caching + Redis Semantic Cache |
| **RAG 검색** | 6개 정책 컬렉션 | 요금제, 인터넷, TV, 결합할인, 멤버십, 위약금 |
| **증분 처리** | 중복 분석 제거 | `last_*_index` 추적으로 신규 발화만 분석 |

### 시스템 아키텍처 성과

```
WebRTC SFU 아키텍처 도입
+-- 클라이언트 연결: N:N -> 1:1 (서버 경유)
+-- 네트워크 부하: 클라이언트당 (N-1) -> 1 연결
+-- 장점: 서버에서 실시간 음성 분석 가능
```

| 구성 요소 | 적용 기술 | 성과 |
|----------|----------|------|
| WebRTC | aiortc + Metered TURN | NAT 환경에서도 안정적 연결 |
| 데이터베이스 | PostgreSQL + pgvector | 벡터 검색 + 트랜잭션 안정성 확보 |
| 캐시 | Redis 6.2 | 10-20ms 응답 시간 (캐시 히트 시) |
| 에이전트 | LangGraph 1.0.3+ | 상태 기반 워크플로우 + 병렬 실행 |

### 코드 품질 성과

- **모듈화**: 6개 독립 모듈 (`webrtc`, `stt`, `agent`, `database`, `vector_db`, `routes`)
- **디자인 패턴**: Singleton, Repository, Manager/Lifecycle, Context Manager 적용
- **비동기 처리**: 전체 I/O 작업 `async/await` 기반
- **타입 안전성**: Pydantic 모델 + TypedDict 상태 정의

---

## 핵심 기능

### 1. 실시간 WebRTC 통화 시스템

**기능 설명**: 브라우저 기반 실시간 음성/영상 통화

```
클라이언트 --WebRTC--> SFU 서버 --Relay--> 다른 참가자
                         |
                         +--> STT 큐 (음성 분석)
```

| 세부 기능 | 구현 방식 |
|----------|----------|
| 피어 연결 관리 | `PeerConnectionManager` - ICE/SDP 협상 |
| 룸 관리 | `RoomManager` - 참가자 추적, 세션 저장 |
| 오디오 릴레이 | `AudioRelayTrack` - 48kHz, 960샘플 프레임 처리 |
| TURN 서버 | Metered.ca - NAT/방화벽 우회 |

**주요 파일**:
- `backend/modules/webrtc/peer_manager.py`
- `backend/modules/webrtc/room_manager.py`
- `backend/modules/webrtc/tracks.py`

---

### 2. 실시간 음성 인식 (STT)

**기능 설명**: Google Cloud Speech-to-Text v2 기반 한국어 음성 인식

| 세부 기능 | 상세 내용 |
|----------|----------|
| 스트리밍 인식 | 실시간 음성 -> 텍스트 변환 |
| 도메인 적응 | PhraseSet으로 통신 용어 인식률 향상 |
| 자동 구두점 | 문장 단위 자동 구분 |
| WebSocket 브로드캐스트 | 인식 결과 즉시 전달 |

**파이프라인**:
```
AudioFrame (48kHz, 960 samples)
  -> PCM bytes (16-bit linear)
  -> Google STT v2 API
  -> Transcript + Confidence
  -> WebSocket broadcast
```

**주요 파일**:
- `backend/modules/stt/service.py`
- `backend/modules/stt/adaptation.py`

---

### 3. LangGraph 기반 AI 분석 에이전트

**기능 설명**: 7개 병렬 노드로 대화 실시간 분석

```
START
  +---> summarize (대화 요약)
  +---> intent (의도 분류) ---> rag_policy (정책 검색)
  +---> faq_search (FAQ 매칭)
  +---> sentiment (감정 분석)
  +---> draft_reply (응답 제안)
  +---> risk (이탈 위험도)
```

| 노드 | 기능 | 출력 |
|------|------|------|
| `summarize` | 증분 대화 요약 | 핵심 내용 요약문 |
| `intent` | 고객 의도 분류 | 16+ 카테고리 (요금 조회, 해지 등) |
| `sentiment` | 감정 톤 분석 | positive/neutral/negative |
| `draft_reply` | AI 응답 제안 | 상담사용 응답 초안 |
| `risk` | 이탈 위험 감지 | 위험도 + 요인 분석 |
| `faq_search` | FAQ 시맨틱 검색 | 관련 FAQ + 신뢰도 |
| `rag_policy` | 정책 문서 검색 | 추천 상품 + 근거 |

**상태 관리** (`ConversationState`):
```python
ConversationState(MessagesState):
  # Core
  room_name: str
  conversation_history: List[Dict]

  # Analysis Results
  summary_result: Dict | None
  intent_result: Dict | None
  sentiment_result: Dict | None
  draft_replies: Dict | None
  risk_result: Dict | None
  rag_policy_result: Dict | None
  faq_result: Dict | None

  # Tracking Indices (증분 처리)
  last_summarized_index: int
  last_intent_index: int
  ...
```

**주요 파일**:
- `backend/modules/agent/graph.py`
- `backend/modules/agent/manager.py`
- `backend/modules/agent/utils/nodes.py`
- `backend/modules/agent/utils/states.py`

---

### 4. RAG 기반 정책 검색

**기능 설명**: 의도 기반 벡터 검색으로 관련 정책/상품 추천

| 컬렉션 | 내용 |
|--------|------|
| `kt_mobile_plans` | 모바일 요금제 |
| `kt_internet_plans` | 인터넷 서비스 |
| `kt_tv_plans` | TV 서비스 |
| `kt_bundle_discount` | 결합 할인 |
| `kt_membership` | 멤버십 혜택 |
| `kt_mobile_penalty` | 위약금 정책 |

**의도-컬렉션 매핑**:
```python
INTENT_COLLECTION_MAP = {
    "요금 조회": ["mobile"],
    "요금제 변경": ["mobile"],
    "해지": ["mobile", "penalty"],
    "멤버십 문의": ["membership"],
    ...
}
```

**검색 흐름**:
```
의도 감지 -> 컬렉션 선택 -> pgvector 검색 -> Top-K 추천 + 근거 반환
```

**주요 파일**:
- `backend/modules/vector_db/manager.py`
- `backend/modules/agent/utils/nodes.py` (rag_policy_node)

---

### 5. FAQ 시맨틱 캐시

**기능 설명**: 유사 질문 캐싱으로 반복 검색 최적화

| 단계 | 처리 |
|------|------|
| 1 | 질문 임베딩 생성 (OpenAI text-embedding-3-small) |
| 2 | 캐시 유사도 검색 |
| 3-A | 유사도 > 0.85 -> 캐시 반환 |
| 3-B | 유사도 < 0.85 -> DB 검색 -> 결과 캐싱 |

**주요 파일**:
- `backend/modules/database/faq_cache.py`
- `backend/modules/database/faq_service.py`

---

### 6. 상담 세션 관리

**기능 설명**: 전체 상담 이력 저장 및 조회

| API 엔드포인트 | 기능 |
|---------------|------|
| `GET /api/consultation/sessions/{customer_id}` | 고객별 세션 목록 |
| `GET /api/consultation/session/{id}/transcripts` | 대화 내역 |
| `GET /api/consultation/session/{id}/results` | 분석 결과 조회 |
| `POST /api/test/scenario` | 텍스트 기반 테스트 |

**데이터 모델**:
```sql
-- 상담 세션
consultation_sessions (
  id UUID PRIMARY KEY,
  customer_id INTEGER,
  agent_id INTEGER,
  room_id UUID,
  session_data JSONB,
  started_at TIMESTAMP,
  ended_at TIMESTAMP
)

-- 대화 내역
consultation_transcripts (
  id UUID PRIMARY KEY,
  session_id UUID,
  turn_index INTEGER,
  speaker_type VARCHAR,
  text TEXT,
  confidence FLOAT
)

-- AI 분석 결과
agent_results (
  id UUID PRIMARY KEY,
  session_id UUID,
  node_name VARCHAR,
  result JSONB,
  execution_time_ms INTEGER
)
```

**주요 파일**:
- `backend/modules/database/consultation_repository.py`
- `backend/routes/consultation.py`

---

### 7. 실시간 상담 UI

**기능 설명**: React 기반 상담사 지원 화면

| 컴포넌트 | 기능 |
|----------|------|
| 대화 패널 | 실시간 STT 결과 표시 |
| 분석 패널 | 요약/의도/감정/위험도 표시 |
| 추천 패널 | RAG 검색 결과 + 응답 제안 |
| 이력 패널 | 과거 상담 세션 조회 |

**WebSocket 메시지 타입**:
```json
// STT 결과
{
  "type": "transcript",
  "peer_id": "abc123",
  "nickname": "고객",
  "text": "요금제 변경하고 싶어요",
  "is_final": true
}

// AI 분석 결과
{
  "type": "agent_update",
  "result_type": "intent",
  "data": {
    "intent": "요금제변경",
    "confidence": 0.95
  }
}
```

**주요 파일**:
- `frontend/src/AssistantMain.jsx`
- `frontend-next/src/components/assistant/`

---

## 기술 스택 요약

| 레이어 | 기술 |
|--------|------|
| **Frontend** | React 18 + Vite, Next.js 16.1, WebRTC API |
| **Backend** | FastAPI, aiortc, LangGraph 1.0.3+ |
| **AI/ML** | OpenAI GPT, LangChain, pgvector |
| **STT** | Google Cloud Speech-to-Text v2 (Chirp) |
| **Database** | PostgreSQL, Redis 6.2, ChromaDB |
| **Infrastructure** | Docker, Metered TURN |

---

## 캐싱 전략

### OpenAI Implicit Caching
- 동일한 정적 시스템 메시지가 모든 노드에서 재사용
- OpenAI 백엔드에서 자동으로 캐싱하여 TTFT 감소
- 예: `FINAL_SUMMARY_SYSTEM_PROMPT`가 모든 요약 작업에 캐싱됨

### Redis LangChain Cache
- 유사 프롬프트 결과 저장
- 동일/유사 프롬프트 즉시 반환
- 설정: `redis_cache_config` in `utils/config.py`

### FAQ Semantic Cache
- 질문 임베딩 (OpenAI text-embedding-3-small, 1536-dim)
- FAQ 쿼리와 응답 저장
- 재사용 임계값: 0.85 유사도
- 백엔드: pgvector + ChromaDB

---

## 증분 처리 전략

**문제**: 새 발화마다 전체 대화 재분석은 비효율적

**해결**: 상태에서 인덱스 추적
```python
ConversationState:
  last_summarized_index: int = 0      # 마지막 요약된 턴
  last_intent_index: int = 0          # 마지막 의도 분석 턴
  last_sentiment_index: int = 0       # ...

# 새 transcript 발생 시:
new_turns = conversation_history[last_summarized_index:]
# 신규 턴만 분석
```

---

## 디자인 패턴

### Singleton Pattern
```python
class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```
사용처: DB, Redis, FAQService, RoomAgent 인스턴스

### Repository Pattern
```python
class ConsultationSessionRepository:
    async def create_session(self, ...): ...
    async def get_customer_sessions(self, ...): ...
    async def update_session(self, ...): ...
```
사용처: 데이터 접근 추상화 (consultation, transcripts, agent results)

### Manager/Lifecycle Pattern
```python
class RoomAgent:
    async def on_new_transcript(self, ...):
        # 증분 상태 업데이트
        # 그래프 실행
        # 결과 집계
        # DB 저장
```
사용처: 에이전트 생명주기, WebRTC 피어 관리

### Context Manager
```python
@asynccontextmanager
async def lifespan(app):
    # 초기화
    yield
    # 정리
```
사용처: 앱 시작/종료, 리소스 관리

---

## 프로젝트 통계

| 항목 | 수치 |
|------|------|
| 백엔드 Python 파일 | 35개 (~5,500 lines) |
| 프론트엔드 JS/JSX/TSX | 15개 (~3,500 lines) |
| 전체 코드 라인 | ~9,000 lines |
| 데이터베이스 테이블 | 12개 |
| LangGraph 노드 | 7개 |
| API 엔드포인트 | 14+ HTTP + 1 WebSocket |
| RAG 컬렉션 | 6개 |

---

## 관련 문서

| 문서 | 설명 |
|------|------|
| [README.md](../README.md) | 프로젝트 개요 및 설정 |
| [CLAUDE.md](../CLAUDE.md) | 개발자 지침 |
| [STT_SETUP.md](STT_SETUP.md) | Google STT 설정 |
| [WEBRTC_SETUP.md](WEBRTC_SETUP.md) | WebRTC 연결 설정 |
| [ER_DIAGRAM.md](ER_DIAGRAM.md) | 데이터베이스 스키마 |

---

**Version**: 1.0.0
**Last Updated**: 2025-01
