# Realtime Assist Agent

**LangGraph 기반 실시간 상담 어시스턴트 AI 에이전트**

WebRTC 기반 오디오/비디오 통화 + Google Cloud STT + LangGraph 에이전트를 활용한 실시간 상담 지원 시스템입니다.

## Team 바로고치 (2025 KT CS 일경험 사업)

| 역할 | 이름 |
|------|------|
| 팀장 | 이찬구 |
| 팀원 | 김재홍 |
| 팀원 | 장윤호 |

---

## 프로젝트 성과

### 기술적 성과

| 영역 | 성과 지표 | 상세 내용 |
|------|----------|----------|
| **실시간 처리** | 7개 병렬 분석 노드 | 순차 처리 대비 응답 시간 단축 (3-5초/턴) |
| **음성 인식** | Google Chirp 모델 | 한국어 특화 STT, 도메인 용어 Phrase Boost 적용 |
| **캐싱 최적화** | TTFT 50% 감소 | OpenAI Implicit Caching + Redis Semantic Cache |
| **RAG 검색** | 6개 정책 컬렉션 | 요금제, 인터넷, TV, 결합할인, 멤버십, 위약금 |
| **증분 처리** | 중복 분석 제거 | `last_*_index` 추적으로 신규 발화만 분석 |

### 시스템 아키텍처 성과

| 구성 요소 | 적용 기술 | 성과 |
|----------|----------|------|
| WebRTC | aiortc SFU + Metered TURN | NAT 환경에서도 안정적 연결, 클라이언트 부하 N-1 -> 1 |
| 데이터베이스 | PostgreSQL + pgvector | 벡터 검색 + 트랜잭션 안정성 확보 |
| 캐시 | Redis 6.2 | 10-20ms 응답 시간 (캐시 히트 시) |
| 에이전트 | LangGraph 1.0.3+ | 상태 기반 워크플로우 + 병렬 실행 |

### 코드 품질 성과

- **모듈화**: 6개 독립 모듈 (`webrtc`, `stt`, `agent`, `database`, `vector_db`, `routes`)
- **디자인 패턴**: Singleton, Repository, Manager/Lifecycle, Context Manager 적용
- **비동기 처리**: 전체 I/O 작업 `async/await` 기반
- **타입 안전성**: Pydantic 모델 + TypedDict 상태 정의

---

## 핵심 기능 요약

| 기능 | 설명 | 핵심 기술 |
|------|------|----------|
| **실시간 통화** | 브라우저 기반 음성/영상 통화 | WebRTC SFU, Metered TURN |
| **음성 인식** | 실시간 한국어 STT | Google Cloud Speech v2 (Chirp) |
| **AI 분석** | 7개 병렬 노드 대화 분석 | LangGraph, OpenAI GPT |
| **RAG 검색** | 의도 기반 정책/상품 추천 | pgvector, LangChain |
| **FAQ 캐시** | 유사 질문 시맨틱 캐싱 | OpenAI Embeddings, Redis |
| **세션 관리** | 상담 이력 저장/조회 | PostgreSQL, Repository Pattern |
| **상담 UI** | 실시간 인사이트 대시보드 | React 18, WebSocket |

> 상세 기능 문서: [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)

---

## 주요 기능

### 1. WebRTC 실시간 통화
- **방 기반 통화**: 같은 방 이름의 사용자들끼리 통화
- **SFU 아키텍처**: FastAPI + aiortc 서버 중계 방식
- **NAT/방화벽 우회**: Metered.ca TURN 서버 통합
- **실시간 참가자 관리**: 입장/퇴장 알림

### 2. 실시간 음성 인식 (STT)
- **Google Cloud Speech-to-Text v2**: Chirp 모델 사용
- **스트리밍 인식**: 실시간 음성 → 텍스트 변환
- **피어별 독립 처리**: 각 참가자마다 별도 STT 인스턴스
- **한국어 최적화**: 자동 구두점, 높은 인식률

### 3. LangGraph AI 분석 (7개 병렬 노드)

| 노드 | 기능 | 설명 |
|------|------|------|
| `summarize` | 대화 요약 | 핵심 내용 실시간 요약 |
| `intent` | 의도 분석 | 기술지원, 요금제변경, 해지 등 |
| `sentiment` | 감정 분석 | 긍정/중립/부정 판단 |
| `draft_reply` | 응답 제안 | 상담사용 답변 초안 생성 |
| `risk` | 리스크 감지 | 해지 위험 고객 식별 |
| `faq_search` | FAQ 검색 | 시맨틱 검색 기반 FAQ 매칭 |
| `rag_policy` | 정책 RAG | 관련 정책 문서 검색 |

### 4. 데이터 영속성
- **PostgreSQL**: 상담 세션, 트랜스크립트, 분석 결과 저장
- **Redis**: 캐싱 및 세션 관리
- **ChromaDB**: FAQ/정책 문서 벡터 저장소

---

## 기술 스택

### Backend
| 기술 | 용도 |
|------|------|
| FastAPI | WebSocket 시그널링 + REST API |
| aiortc | Python WebRTC (SFU) |
| LangGraph | AI 에이전트 오케스트레이션 |
| LangChain | LLM 프레임워크 |
| Google Cloud STT v2 | 음성 인식 |
| asyncpg | PostgreSQL 비동기 드라이버 |
| Redis | 캐싱 |
| ChromaDB | 벡터 데이터베이스 |

### Frontend (Legacy - Vite)
| 기술 | 용도 |
|------|------|
| React 18 | UI 프레임워크 |
| Vite | 빌드 도구 |
| WebRTC API | 실시간 통신 |

### Frontend (Next.js - 신규)
| 기술 | 용도 |
|------|------|
| Next.js 16.1 | App Router 기반 프레임워크 |
| React 19 | UI 프레임워크 |
| TailwindCSS 4 | 스타일링 |
| TypeScript | 타입 안전성 |
| WebRTC API | 실시간 통신 |

### Infrastructure
| 서비스 | 용도 |
|--------|------|
| PostgreSQL (pgvector) | 메인 데이터베이스 |
| Redis Stack | 캐싱 |
| Metered.ca TURN | NAT 우회 |
| Google Cloud Platform | STT API |

---

## 시스템 아키텍처

### 전체 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Client (Browser)                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │   Microphone  │───►│   WebRTC     │───►│   Signaling (WS)     │  │
│  └──────────────┘    │   Media      │    └──────────┬───────────┘  │
│                       └──────────────┘               │              │
└──────────────────────────────────────────────────────│──────────────┘
                                                        │
                        ┌───────────────────────────────▼───────────────┐
                        │              FastAPI Server                    │
                        │  ┌─────────────────────────────────────────┐  │
                        │  │          WebSocket Handler               │  │
                        │  └────────────────┬────────────────────────┘  │
                        │                   │                           │
                        │  ┌────────────────▼────────────────────────┐  │
                        │  │     PeerConnectionManager (SFU)          │  │
                        │  │  ┌────────────┐  ┌────────────────────┐ │  │
                        │  │  │AudioRelay  │─►│    STT Service     │ │  │
                        │  │  │Track       │  │  (Google Cloud)    │ │  │
                        │  │  └────────────┘  └────────┬───────────┘ │  │
                        │  └───────────────────────────│─────────────┘  │
                        │                              │                │
                        │  ┌───────────────────────────▼─────────────┐  │
                        │  │         RoomAgent (LangGraph)           │  │
                        │  │  ┌─────────────────────────────────┐   │  │
                        │  │  │        Parallel Nodes            │   │  │
                        │  │  │  ┌───────┐ ┌────────┐ ┌───────┐ │   │  │
                        │  │  │  │summary│ │ intent │ │ risk  │ │   │  │
                        │  │  │  └───────┘ └────────┘ └───────┘ │   │  │
                        │  │  │  ┌─────────┐ ┌─────┐ ┌────────┐ │   │  │
                        │  │  │  │sentiment│ │ FAQ │ │ draft  │ │   │  │
                        │  │  │  └─────────┘ └─────┘ └────────┘ │   │  │
                        │  │  │        ┌─────────────┐          │   │  │
                        │  │  │        │  RAG Policy │          │   │  │
                        │  │  │        └─────────────┘          │   │  │
                        │  │  └─────────────────────────────────┘   │  │
                        │  └────────────────────┬────────────────────┘  │
                        │                       │                       │
                        │  ┌────────────────────▼────────────────────┐  │
                        │  │              Database Layer              │  │
                        │  │  ┌──────────┐ ┌───────┐ ┌────────────┐ │  │
                        │  │  │PostgreSQL│ │ Redis │ │  ChromaDB  │ │  │
                        │  │  └──────────┘ └───────┘ └────────────┘ │  │
                        │  └─────────────────────────────────────────┘  │
                        └───────────────────────────────────────────────┘
                                                        │
                        ┌───────────────────────────────▼───────────────┐
                        │             WebSocket Broadcast                │
                        │     transcript, agent_update, user_joined      │
                        └───────────────────────────────────────────────┘
                                                        │
┌───────────────────────────────────────────────────────▼─────────────────┐
│                       Counselor Dashboard (React)                        │
│  ┌────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  Transcript    │  │   AI Insights   │  │   Response Suggestions  │  │
│  │  (Left Panel)  │  │  (Center Panel) │  │     (Right Panel)       │  │
│  │                │  │                 │  │                         │  │
│  │  - STT 결과    │  │  - 의도 분석    │  │  - 응답 초안            │  │
│  │  - 화자 구분   │  │  - 대화 요약    │  │  - FAQ 매칭             │  │
│  │  - 타임스탬프  │  │  - 감정 분석    │  │  - 리스크 알림          │  │
│  └────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### LangGraph 노드 구조

```
                              START
                                │
        ┌───────────┬───────────┼───────────┬───────────┬───────────┐
        │           │           │           │           │           │
        ▼           ▼           ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │summarize│ │ intent  │ │sentiment│ │  draft  │ │  risk   │ │faq_search│
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │           │           │           │
        │           ▼           │           │           │           │
        │    ┌────────────┐     │           │           │           │
        │    │ rag_policy │     │           │           │           │
        │    └─────┬──────┘     │           │           │           │
        │          │            │           │           │           │
        └──────────┴────────────┴───────────┴───────────┴───────────┘
                                │
                               END
```

---

## 프로젝트 구조

```
realtime-assist-agent/
├── backend/
│   ├── app.py                      # FastAPI 메인 앱 (1700+ lines)
│   ├── config/
│   │   └── .env                    # 환경 변수
│   │
│   └── modules/
│       ├── __init__.py             # 메인 exports
│       │
│       ├── webrtc/                 # WebRTC 모듈
│       │   ├── peer_manager.py     # PeerConnectionManager (SFU)
│       │   ├── room_manager.py     # RoomManager, Peer
│       │   ├── tracks.py           # AudioRelayTrack
│       │   └── config.py           # WebRTC 설정
│       │
│       ├── stt/                    # Speech-to-Text 모듈
│       │   ├── service.py          # STTService (Google Cloud v2)
│       │   ├── adaptation.py       # PhraseSet/CustomClass
│       │   └── config.py           # STT 설정
│       │
│       ├── agent/                  # LangGraph 에이전트
│       │   ├── graph.py            # StateGraph 정의
│       │   ├── manager.py          # RoomAgent 생명주기
│       │   ├── graph_test.py       # 테스트용 그래프
│       │   └── utils/
│       │       ├── states.py       # ConversationState
│       │       ├── nodes.py        # 7개 노드 정의
│       │       ├── prompts.py      # LLM 프롬프트
│       │       ├── schemas.py      # Pydantic 모델
│       │       └── config.py       # 에이전트 설정
│       │
│       ├── database/               # 데이터베이스 모듈
│       │   ├── connection.py       # DatabaseManager
│       │   ├── redis_connection.py # RedisManager
│       │   ├── repository.py       # 기본 Repository
│       │   ├── consultation_repository.py
│       │   ├── faq_service.py      # FAQ 서비스
│       │   └── log_handler.py      # DB 로깅
│       │
│       └── vector_db/              # 벡터 DB 모듈
│           ├── manager.py          # VectorDBManager
│           └── doc_registry.py     # DocumentRegistry
│
├── frontend/                          # Legacy (Vite + React)
│   ├── src/
│   │   ├── App.jsx                 # 메인 라우터
│   │   ├── AssistantMain.jsx       # 상담사 대시보드
│   │   ├── AgentRegister.jsx       # 상담사 등록
│   │   ├── AgentHistory.jsx        # 상담 이력
│   │   ├── webrtc.js               # WebRTC 클라이언트
│   │   └── logger.js               # 프론트엔드 로깅
│   ├── vite.config.js
│   └── package.json
│
├── frontend-next/                     # Next.js + TailwindCSS (신규)
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx          # 루트 레이아웃
│   │   │   ├── page.tsx            # 홈 페이지
│   │   │   ├── login/page.tsx      # 로그인 페이지
│   │   │   └── assistant/page.tsx  # 상담 대시보드
│   │   │
│   │   ├── components/
│   │   │   ├── AuthGuard.tsx       # 인증 가드
│   │   │   └── assistant/
│   │   │       ├── AssistantMain.tsx    # 메인 조합 컴포넌트
│   │   │       ├── RoleSelection.tsx    # 역할 선택 UI
│   │   │       ├── ConnectionPanel.tsx  # WebRTC 연결 관리
│   │   │       ├── TranscriptPanel.tsx  # 실시간 대화 표시
│   │   │       ├── InsightPanel.tsx     # AI 인사이트 표시
│   │   │       └── index.ts             # 컴포넌트 exports
│   │   │
│   │   ├── hooks/
│   │   │   ├── useWebRTCClient.ts  # WebRTC 클라이언트 훅
│   │   │   ├── useCallTimer.ts     # 통화 타이머 훅
│   │   │   └── index.ts
│   │   │
│   │   └── lib/
│   │       ├── types.ts            # 공유 타입 정의
│   │       └── webrtc-client.ts    # WebRTC 클라이언트 클래스
│   │
│   ├── tailwind.config.ts
│   └── package.json
│
├── data/
│   ├── docker-compose.yaml         # PostgreSQL + Redis
│   └── .env.example
│
├── docs/                           # 기술 문서
│   ├── STT_SETUP.md
│   ├── WEBRTC_SETUP.md
│   ├── WEBRTC_CONNECTION_FLOW.md
│   ├── ER_DIAGRAM.md
│   └── ...
│
├── gcloud-keys/                    # Google Cloud 키 (gitignore)
├── logs/                           # 서버 로그
├── transcripts/                    # STT 결과 아카이브
│
├── pyproject.toml                  # Python 의존성 (UV)
├── CLAUDE.md                       # 개발자 가이드
└── README.md
```

---

## 빠른 시작

### 1. 사전 요구사항

- Python 3.13+
- Node.js 18+
- Docker & Docker Compose
- Google Cloud 계정 (STT API)
- Metered.ca 계정 (TURN 서버)

### 2. 저장소 클론

```bash
git clone https://github.com/your-org/realtime-assist-agent.git
cd realtime-assist-agent
```

### 3. Docker 서비스 시작

```bash
cd data
cp .env.example .env
# .env 파일 수정 (필요시)

docker-compose up -d
```

### 4. 백엔드 설정

```bash
# 의존성 설치
uv sync

# 환경 변수 설정
cp backend/config/.env.example backend/config/.env
```

**backend/config/.env 설정:**

```env
# Google Cloud
GOOGLE_APPLICATION_CREDENTIALS=../gcloud-keys/your-key.json
GOOGLE_CLOUD_PROJECT=your-project-id

# STT
STT_LANGUAGE_CODE=ko-KR
STT_MODEL=chirp
STT_ENABLE_AUTOMATIC_PUNCTUATION=true

# TURN Server
METERED_API_KEY=your-metered-api-key

# Database
DATABASE_URL=postgresql://assistant:assistant123@localhost:5432/realtime_assist
REDIS_URL=redis://localhost:6379

# OpenAI (LangGraph)
OPENAI_API_KEY=sk-...

# Application
ACCESS_PASSWORD=your-password
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=60
```

### 5. 프론트엔드 설정

```bash
cd frontend
npm install
cp .env.example .env
```

**frontend/.env 설정:**

```env
VITE_API_URL=http://localhost:8000
VITE_BACKEND_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

### 6. 서버 실행

**Terminal 1 - Backend:**
```bash
cd backend
uv run python app.py
```
> http://localhost:8000

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```
> http://localhost:5173

### 7. 테스트

1. 브라우저 탭 2개 열기
2. 비밀번호 입력 (ACCESS_PASSWORD)
3. 같은 방 이름으로 입장 (예: `test-room`)
4. "Start Call" 클릭
5. 마이크 권한 허용
6. 대화 시작 → STT + AI 분석 결과 확인

---

## API 문서

### HTTP Endpoints

| Endpoint | Method | 설명 | 인증 |
|----------|--------|------|------|
| `/` | GET | 헬스 체크 | - |
| `/api/auth/verify` | POST | 비밀번호 검증 | - |
| `/api/rooms` | GET | 활성 방 목록 | Bearer |
| `/api/turn-credentials` | GET | TURN 서버 credentials | Bearer |
| `/api/consultation/sessions/{customer_id}` | GET | 고객 상담 세션 조회 | Bearer |
| `/api/consultation/session/{session_id}/transcripts` | GET | 세션 트랜스크립트 | Bearer |
| `/api/consultation/session/{session_id}/results` | GET | 에이전트 분석 결과 | Bearer |
| `/api/agent/register` | POST | 상담사 등록 | - |
| `/api/agent/login` | POST | 상담사 로그인 | - |
| `/api/agent/{agent_id}/sessions` | GET | 상담사별 세션 | Bearer |
| `/api/health` | GET | 전체 헬스 상태 | - |
| `/api/health/db` | GET | DB 헬스 체크 | - |
| `/api/health/redis` | GET | Redis 헬스 체크 | - |

### WebSocket Messages (`/ws`)

**Client → Server:**

```json
// 방 입장
{ "type": "join_room", "room_name": "test", "nickname": "Alice", "token": "..." }

// WebRTC Offer
{ "type": "offer", "sdp": "...", "type": "offer" }

// ICE Candidate
{ "type": "ice_candidate", "candidate": "...", "sdpMLineIndex": 0, "sdpMid": "0" }

// 방 퇴장
{ "type": "leave_room" }
```

**Server → Client:**

```json
// 피어 ID 할당
{ "type": "peer_id", "peer_id": "abc123" }

// 방 입장 성공
{ "type": "room_joined", "room_name": "test", "peer_id": "abc123" }

// 사용자 입장/퇴장
{ "type": "user_joined", "peer_id": "def456", "nickname": "Bob" }
{ "type": "user_left", "peer_id": "def456", "nickname": "Bob" }

// STT 결과
{
  "type": "transcript",
  "peer_id": "abc123",
  "nickname": "Alice",
  "text": "안녕하세요, 요금제 변경 문의드립니다.",
  "timestamp": "2025-01-15T10:30:00Z",
  "is_final": true
}

// AI 분석 결과
{
  "type": "agent_update",
  "result_type": "intent",  // summarize, sentiment, draft_reply, risk, faq_search, rag_policy
  "data": {
    "intent": "요금제변경",
    "confidence": 0.95
  }
}
```

---

## 데이터베이스 스키마

### 주요 테이블

```sql
-- 실시간 통화
rooms (id, room_name, status, created_at, ended_at)
peers (id, room_id, peer_id, nickname, joined_at, left_at)
transcripts (room_id, peer_id, text, timestamp, source, is_final)

-- 상담 세션
consultation_sessions (session_id, room_id, customer_id, agent_id, status, duration)
consultation_transcripts (session_id, turn_index, speaker_type, text, confidence)
consultation_agent_results (session_id, turn_id, result_type, result_data)

-- 고객/상담사
customers (customer_id, name, phone, plan, monthly_fee, ...)
agents (agent_id, agent_code, agent_name, created_at)

-- 벡터 DB (LangChain)
langchain_pg_collection (id, name, cmetadata)
langchain_pg_embedding (id, embedding, document, cmetadata)

-- 시스템
system_logs (timestamp, level, logger_name, message, module, exception)
faq_query_cache (query_text, query_embedding, faq_results, hit_count)
```

---

## 트러블슈팅

| 문제 | 원인 | 해결 |
|------|------|------|
| 오디오/비디오 안됨 | 방 이름 불일치 | 정확히 동일한 방 이름 사용 (대소문자 구분) |
| STT 작동 안함 | Google Cloud 설정 오류 | `GOOGLE_APPLICATION_CREDENTIALS` 경로 확인 |
| 연결 타임아웃 | TURN 서버 문제 | `METERED_API_KEY` 유효성 확인 |
| 에이전트 응답 없음 | Redis 연결 실패 | Redis 서버 실행 상태 확인 |
| DB 에러 | PostgreSQL 미실행 | `docker-compose up -d` 실행 |
| ICE 연결 실패 | 방화벽 차단 | UDP/TCP 포트 허용 |
| 메모리 누수 | 에이전트 미정리 | 방 종료 시 `remove_agent()` 호출 확인 |

---

## 개발 가이드

### LangGraph 노드 추가

```python
# 1. backend/modules/agent/utils/nodes.py에 노드 정의
def create_my_node(llm):
    def node(state: ConversationState, context: ContextSchema) -> Dict:
        result = llm.invoke(...)
        return {"my_result": result}
    return node

# 2. backend/modules/agent/graph.py에 노드 추가
graph.add_node("my_node", my_node)
graph.add_edge(START, "my_node")
graph.add_edge("my_node", END)

# 3. utils/states.py에 상태 필드 추가
my_result: Dict[str, Any] | None
```

### 새 API 엔드포인트 추가

```python
# backend/app.py
@app.get("/api/my-endpoint")
async def my_endpoint(auth: bool = Depends(verify_auth_header)):
    result = await get_db_manager().query("SELECT ...")
    return {"result": result}
```

---

## 문서

| 문서 | 설명 |
|------|------|
| [STT_SETUP.md](docs/STT_SETUP.md) | Google STT 설정 가이드 |
| [WEBRTC_SETUP.md](docs/WEBRTC_SETUP.md) | WebRTC 연결 설정 |
| [WEBRTC_CONNECTION_FLOW.md](docs/WEBRTC_CONNECTION_FLOW.md) | 연결 흐름 상세 |
| [ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | 데이터베이스 스키마 |
| [CLAUDE.md](CLAUDE.md) | 개발자 지침 |

---

## 비용 정보

| 서비스 | 무료 티어 | 이후 요금 |
|--------|-----------|-----------|
| Google Cloud STT | 월 60분 | $0.006/분 |
| Metered.ca TURN | 월 50GB | 유료 플랜 |
| OpenAI API | - | 모델별 상이 |

---

## 통계

| 항목 | 수치 |
|------|------|
| 백엔드 Python 파일 | 35개 (~5,500 lines) |
| 프론트엔드 JS/JSX | 7개 (~2,500 lines) |
| 전체 코드 라인 | ~8,200 lines |
| 데이터베이스 테이블 | 12개 |
| LangGraph 노드 | 7개 |
| API 엔드포인트 | 14+ HTTP + 1 WebSocket |

---

## 라이선스

MIT License

---

**Version**: 1.0.0
