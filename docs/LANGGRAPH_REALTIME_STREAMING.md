# LangGraph 실시간 스트리밍 구현 가이드

## 목차
1. [LangGraph 스트리밍 개념](#langgraph-스트리밍-개념)
2. [아키텍처 설계](#아키텍처-설계)
3. [구현 패턴](#구현-패턴)
4. [코드 예제](#코드-예제)

---

## LangGraph 스트리밍 개념

### Stream Modes

LangGraph는 3가지 주요 스트리밍 모드를 제공합니다:

#### 1. `stream_mode="values"` - 전체 State 스트리밍
```python
for chunk in graph.stream(initial_state, stream_mode="values"):
    # chunk는 매 노드 실행 후의 "전체 State" 스냅샷
    print(chunk)
```

**특징:**
- 매 노드 실행 후 전체 State 반환
- State 전체를 보고 싶을 때 유용
- 데이터 중복이 많음 (매번 전체 State 전송)

**사용 시나리오:**
- 디버깅 및 개발 단계
- State 전체 변화 추적 필요
- 작은 State 크기

---

#### 2. `stream_mode="updates"` - State 변경 부분만 스트리밍 ⭐
```python
for chunk in graph.stream(initial_state, stream_mode="updates"):
    # chunk는 {"node_name": {변경된 State 부분만}}
    for node_name, node_output in chunk.items():
        print(f"Node: {node_name}, Update: {node_output}")
```

**특징:**
- 각 노드가 변경한 State 부분만 반환
- 효율적 (변경 사항만 전송)
- 실시간 업데이트에 최적

**사용 시나리오:**
- **실시간 상담 에이전트 (우리 케이스)** ✅
- 대용량 State 처리
- WebSocket 전송 최적화

**출력 예시:**
```python
# transcribe 노드 실행 후
{
  "transcribe": {
    "transcription": "안녕하세요",
    "full_transcript": ["안녕하세요"]
  }
}

# summarize 노드 실행 후
{
  "summarize": {
    "current_summary": "인사를 나눴습니다"
  }
}

# rag_retrieve 노드 실행 후
{
  "rag_retrieve": {
    "retrieved_docs": ["문서1", "문서2"]
  }
}
```

---

#### 3. `stream_mode="custom"` - 사용자 정의 이벤트 스트리밍
```python
from langgraph.config import get_stream_writer

def my_node(state):
    writer = get_stream_writer()

    # 중간 진행 상황 전송
    writer({"status": "processing", "progress": 30})
    # ... 처리 중 ...
    writer({"status": "processing", "progress": 70})

    return {"result": "done"}

# 스트리밍
for chunk in graph.stream(initial_state, stream_mode="custom"):
    print(chunk)  # {"status": "processing", "progress": 30}
```

**특징:**
- 노드 내부에서 임의의 데이터 전송 가능
- 진행률, 로그, 중간 결과 전송
- 가장 유연한 방식

**사용 시나리오:**
- 긴 작업의 진행률 표시
- 디버깅 로그 실시간 전송
- 복잡한 노드의 중간 결과 전송

---

## 아키텍처 설계

### 전체 시스템 흐름

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│  Frontend   │         │   Backend        │         │  LangGraph  │
│  (Browser)  │         │   (FastAPI)      │         │   Agent     │
└─────────────┘         └──────────────────┘         └─────────────┘
       │                         │                          │
       │  WebRTC Audio           │                          │
       ├────────────────────────>│                          │
       │                         │                          │
       │                         │  STT Transcription       │
       │                         │  (from stt_service)      │
       │                         ├─────────┐                │
       │                         │         │                │
       │                         │<────────┘                │
       │                         │                          │
       │                         │  graph.stream()          │
       │                         ├─────────────────────────>│
       │                         │  (stream_mode="updates") │
       │                         │                          │
       │                         │  ┌──────────────────┐   │
       │                         │  │ transcribe_node  │   │
       │                         │  └────────┬─────────┘   │
       │                         │           │             │
       │                         │  ┌────────▼─────────┐   │
       │                         │  │ summarize_node   │   │
       │                         │  │   (병렬)         │   │
       │                         │  └────────┬─────────┘   │
       │                         │           │             │
       │                         │<──────────┘             │
       │  WebSocket: summary     │  {"summarize": {...}}   │
       │<────────────────────────┤                         │
       │                         │                          │
       │  (화면에 요약 표시) ✅  │  ┌──────────────────┐   │
       │                         │  │ rag_retrieve     │   │
       │                         │  │   (병렬)         │   │
       │                         │  └────────┬─────────┘   │
       │                         │           │             │
       │                         │  ┌────────▼─────────┐   │
       │                         │  │ generate_suggest │   │
       │                         │  └────────┬─────────┘   │
       │                         │           │             │
       │                         │<──────────┘             │
       │  WebSocket: suggestion  │  {"generate_suggest":...}│
       │<────────────────────────┤                         │
       │                         │                          │
       │  (화면에 추천 표시) ✅  │                          │
       │                         │                          │
```

### 핵심 아이디어

1. **STT로부터 전사 텍스트 수신**
   ```python
   # backend/stt_service.py
   async def on_stt_result(peer_id: str, transcript: str):
       # LangGraph 실행 트리거
       await trigger_langgraph(peer_id, transcript)
   ```

2. **LangGraph 스트리밍 실행**
   ```python
   # backend/agent.py
   async for chunk in graph.stream(state, stream_mode="updates"):
       # 각 노드의 업데이트를 WebSocket으로 즉시 전송
       await websocket.send_json({
           "type": "agent_update",
           "data": chunk
       })
   ```

3. **Frontend에서 실시간 업데이트 수신**
   ```javascript
   // frontend/src/agent.js
   websocket.onmessage = (event) => {
       const msg = JSON.parse(event.data);
       if (msg.type === 'agent_update') {
           if ('summarize' in msg.data) {
               updateSummaryUI(msg.data.summarize.current_summary);
           }
           if ('generate_suggestion' in msg.data) {
               updateSuggestionUI(msg.data.generate_suggestion.suggestion);
           }
       }
   };
   ```

---

## 구현 패턴

### 패턴 1: 단일 WebSocket 연결 (권장)

**장점:**
- 연결 관리 단순
- 오버헤드 최소화
- 순서 보장

**구조:**
```python
@app.websocket("/ws/{peer_id}")
async def websocket_endpoint(websocket: WebSocket, peer_id: str):
    await websocket.accept()

    # WebRTC 연결도 처리
    # + LangGraph 업데이트도 처리

    try:
        while True:
            message = await websocket.receive_json()

            if message['type'] == 'stt_transcript':
                # LangGraph 실행 시작
                await run_agent_streaming(websocket, peer_id, message['transcript'])

            elif message['type'] == 'offer':
                # WebRTC offer 처리
                await handle_webrtc_offer(...)

    except WebSocketDisconnect:
        cleanup()
```

---

### 패턴 2: 별도 WebSocket 연결

**장점:**
- 관심사 분리
- 독립적 에러 처리

**구조:**
```python
# WebRTC용
@app.websocket("/webrtc/{peer_id}")
async def webrtc_endpoint(...):
    # WebRTC signaling만 처리
    pass

# Agent용
@app.websocket("/agent/{peer_id}")
async def agent_endpoint(...):
    # LangGraph 업데이트만 처리
    pass
```

---

### 패턴 3: Server-Sent Events (SSE)

**특징:**
- 단방향 스트리밍 (서버 → 클라이언트)
- HTTP 기반
- 자동 재연결

**구조:**
```python
@app.get("/agent/stream/{peer_id}")
async def stream_agent_updates(peer_id: str):
    async def event_generator():
        async for chunk in graph.stream(..., stream_mode="updates"):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

```javascript
const eventSource = new EventSource('/agent/stream/' + peerId);
eventSource.onmessage = (event) => {
    const update = JSON.parse(event.data);
    handleAgentUpdate(update);
};
```

---

## 코드 예제

### 1. LangGraph Agent with Streaming

```python
# backend/agent.py
from typing import TypedDict, AsyncIterator
from langgraph.graph import StateGraph, START, END
from langgraph.config import RunnableConfig

class ConversationState(TypedDict):
    session_id: str
    transcription: str
    full_transcript: list[str]
    current_summary: str
    retrieved_docs: list[str]
    suggestion: str
    timestamp: float

def transcribe_node(state: ConversationState) -> dict:
    """전사 텍스트를 State에 추가"""
    return {
        "full_transcript": state.get("full_transcript", []) + [state["transcription"]]
    }

async def summarize_node(state: ConversationState) -> dict:
    """대화 요약 생성 (LLM 호출)"""
    # TODO: 실제 LLM 요약
    full_text = "\n".join(state["full_transcript"])

    # OpenAI API 예시
    # summary = await openai.ChatCompletion.acreate(
    #     model="gpt-4",
    #     messages=[
    #         {"role": "system", "content": "대화를 간단히 요약해주세요."},
    #         {"role": "user", "content": full_text}
    #     ]
    # )

    summary = f"[요약: {len(state['full_transcript'])}개 발화]"

    return {
        "current_summary": summary
    }

async def rag_retrieve_node(state: ConversationState) -> dict:
    """RAG 검색"""
    # TODO: Vector DB 검색
    # results = await vector_db.similarity_search(
    #     query=state["transcription"],
    #     top_k=3
    # )

    docs = [f"문서 {i}" for i in range(3)]

    return {
        "retrieved_docs": docs
    }

async def generate_suggestion_node(state: ConversationState) -> dict:
    """답변 추천 생성"""
    # TODO: RAG 기반 LLM 생성
    # suggestion = await llm.generate(
    #     context=state["retrieved_docs"],
    #     query=state["transcription"]
    # )

    suggestion = f"[추천: {len(state['retrieved_docs'])}개 문서 기반]"

    return {
        "suggestion": suggestion
    }

def create_agent_graph():
    """Agent 그래프 생성"""
    graph = StateGraph(ConversationState)

    graph.add_node("transcribe", transcribe_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("rag_retrieve", rag_retrieve_node)
    graph.add_node("generate_suggestion", generate_suggestion_node)

    # 그래프 연결
    graph.add_edge(START, "transcribe")
    graph.add_edge("transcribe", "summarize")
    graph.add_edge("transcribe", "rag_retrieve")
    graph.add_edge("rag_retrieve", "generate_suggestion")
    graph.add_edge("summarize", END)
    graph.add_edge("generate_suggestion", END)

    return graph.compile()

# 글로벌 인스턴스
agent_graph = create_agent_graph()

async def stream_agent_updates(
    initial_state: ConversationState
) -> AsyncIterator[dict]:
    """
    Agent 실행 결과를 스트리밍합니다.

    Yields:
        {"node_name": {업데이트된 State 부분}}
    """
    async for chunk in agent_graph.astream(
        initial_state,
        stream_mode="updates"  # ⭐ 변경 부분만 스트리밍
    ):
        yield chunk
```

---

### 2. FastAPI WebSocket Handler

```python
# backend/app.py
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
import asyncio
import time

# 세션별 State 저장
session_states: Dict[str, ConversationState] = {}

@app.websocket("/ws/{peer_id}")
async def websocket_endpoint(websocket: WebSocket, peer_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected: {peer_id}")

    # 초기 State 생성
    if peer_id not in session_states:
        session_states[peer_id] = {
            "session_id": peer_id,
            "transcription": "",
            "full_transcript": [],
            "current_summary": "",
            "retrieved_docs": [],
            "suggestion": "",
            "timestamp": time.time()
        }

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

            if message_type == "stt_transcript":
                # STT 결과 수신
                transcript = message.get("transcript")
                logger.info(f"📝 STT transcript: {transcript}")

                # State 업데이트
                current_state = session_states[peer_id]
                current_state["transcription"] = transcript
                current_state["timestamp"] = time.time()

                # LangGraph 스트리밍 실행
                async for chunk in stream_agent_updates(current_state):
                    # 각 노드의 업데이트를 즉시 전송
                    await websocket.send_json({
                        "type": "agent_update",
                        "node": list(chunk.keys())[0],
                        "data": list(chunk.values())[0]
                    })
                    logger.info(f"📤 Sent update: {list(chunk.keys())[0]}")

                    # State 동기화
                    for key, value in list(chunk.values())[0].items():
                        current_state[key] = value

            elif message_type == "offer":
                # WebRTC offer 처리 (기존 코드)
                await handle_webrtc_offer(websocket, peer_id, message)

            elif message_type == "ice_candidate":
                # ICE candidate 처리 (기존 코드)
                await handle_ice_candidate(websocket, peer_id, message)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {peer_id}")
        # 세션 정리
        if peer_id in session_states:
            del session_states[peer_id]
```

---

### 3. STT Service Integration

```python
# backend/stt_service.py
class STTService:
    def __init__(self):
        self.websocket_connections: Dict[str, WebSocket] = {}

    def register_websocket(self, peer_id: str, websocket: WebSocket):
        """WebSocket 연결 등록"""
        self.websocket_connections[peer_id] = websocket

    async def on_transcription_result(self, peer_id: str, transcript: str):
        """
        STT 결과를 WebSocket으로 전송하여 LangGraph 트리거
        """
        websocket = self.websocket_connections.get(peer_id)
        if websocket:
            await websocket.send_json({
                "type": "stt_transcript",
                "transcript": transcript
            })
            logger.info(f"📤 Sent STT transcript to WebSocket: {transcript}")
```

**WebSocket Handler 수정:**
```python
@app.websocket("/ws/{peer_id}")
async def websocket_endpoint(websocket: WebSocket, peer_id: str):
    await websocket.accept()

    # STT Service에 WebSocket 등록
    stt_service.register_websocket(peer_id, websocket)

    # ... 기존 코드 ...
```

---

### 4. Frontend: Real-time Updates

```javascript
// frontend/src/agent.js
class AgentClient {
    constructor(wsUrl, peerId) {
        this.ws = new WebSocket(`${wsUrl}/ws/${peerId}`);
        this.onSummaryUpdate = null;
        this.onSuggestionUpdate = null;

        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
    }

    handleMessage(message) {
        switch (message.type) {
            case 'agent_update':
                this.handleAgentUpdate(message);
                break;
            case 'answer':
                this.handleWebRTCAnswer(message);
                break;
            case 'ice_candidate':
                this.handleICECandidate(message);
                break;
        }
    }

    handleAgentUpdate(message) {
        const node = message.node;
        const data = message.data;

        console.log(`📥 Agent update from ${node}:`, data);

        switch (node) {
            case 'summarize':
                // 요약 업데이트
                if (this.onSummaryUpdate && data.current_summary) {
                    this.onSummaryUpdate(data.current_summary);
                }
                break;

            case 'generate_suggestion':
                // 추천 업데이트
                if (this.onSuggestionUpdate && data.suggestion) {
                    this.onSuggestionUpdate(data.suggestion);
                }
                break;

            case 'transcribe':
                // 전사 업데이트
                console.log('Transcription:', data.transcription);
                break;
        }
    }
}

// 사용 예시
const agent = new AgentClient('ws://localhost:8000', peerId);

// 요약 업데이트 핸들러 등록
agent.onSummaryUpdate = (summary) => {
    document.getElementById('summary-panel').textContent = summary;
    console.log('✅ Summary updated:', summary);
};

// 추천 업데이트 핸들러 등록
agent.onSuggestionUpdate = (suggestion) => {
    document.getElementById('suggestion-panel').textContent = suggestion;
    console.log('✅ Suggestion updated:', suggestion);
};
```

---

### 5. UI 컴포넌트 (HTML)

```html
<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>실시간 상담 어시스턴트</title>
    <style>
        .panel {
            border: 1px solid #ccc;
            padding: 20px;
            margin: 10px 0;
            border-radius: 8px;
        }
        .summary-panel {
            background-color: #e3f2fd;
        }
        .suggestion-panel {
            background-color: #f3e5f5;
        }
        .transcript-panel {
            background-color: #fff3e0;
        }
        .status {
            font-size: 0.9em;
            color: #666;
        }
    </style>
</head>
<body>
    <h1>📞 실시간 상담 어시스턴트</h1>

    <!-- 연결 상태 -->
    <div class="status" id="connection-status">
        연결 중...
    </div>

    <!-- 전사 -->
    <div class="panel transcript-panel">
        <h2>🎤 실시간 전사</h2>
        <div id="transcript-content">
            전사 내용이 여기에 표시됩니다...
        </div>
    </div>

    <!-- 요약 -->
    <div class="panel summary-panel">
        <h2>📝 대화 요약</h2>
        <div id="summary-panel">
            요약이 여기에 실시간으로 표시됩니다...
        </div>
    </div>

    <!-- 추천 답변 -->
    <div class="panel suggestion-panel">
        <h2>💡 추천 답변</h2>
        <div id="suggestion-panel">
            AI 추천 답변이 여기에 실시간으로 표시됩니다...
        </div>
    </div>

    <script src="/src/webrtc.js"></script>
    <script src="/src/agent.js"></script>
    <script>
        // 초기화
        const peerId = 'peer-' + Math.random().toString(36).substr(2, 9);
        const agent = new AgentClient('ws://localhost:8000', peerId);

        // 연결 상태
        agent.ws.onopen = () => {
            document.getElementById('connection-status').textContent = '✅ 연결됨';
        };

        // 요약 업데이트
        agent.onSummaryUpdate = (summary) => {
            document.getElementById('summary-panel').textContent = summary;
        };

        // 추천 업데이트
        agent.onSuggestionUpdate = (suggestion) => {
            document.getElementById('suggestion-panel').textContent = suggestion;
        };

        // 전사 업데이트 (별도 처리)
        agent.ws.addEventListener('message', (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'stt_transcript') {
                const transcript = msg.transcript;
                const content = document.getElementById('transcript-content');
                content.innerHTML += `<p>${transcript}</p>`;
                content.scrollTop = content.scrollHeight;
            }
        });
    </script>
</body>
</html>
```

---

## 실행 흐름 요약

### 1. 초기 연결
```
Client → WebSocket Connect → Backend
Backend → Agent Graph 초기화
Backend → STT Service 연결 등록
```

### 2. 음성 입력
```
Microphone → WebRTC → Backend
Backend → STT Service → Transcription
STT Service → WebSocket.send({"type": "stt_transcript"})
```

### 3. LangGraph 실행 (스트리밍)
```
WebSocket Handler → agent_graph.astream(state, stream_mode="updates")

[transcribe 노드 실행]
  → {"transcribe": {"full_transcript": [...]}}
  → WebSocket.send({"type": "agent_update", "node": "transcribe"})
  → Client receives → (UI 업데이트 없음, 내부 상태만)

[summarize 노드 실행] (병렬)
  → {"summarize": {"current_summary": "..."}}
  → WebSocket.send({"type": "agent_update", "node": "summarize"})
  → Client receives → ✅ 요약 UI 즉시 업데이트!

[rag_retrieve 노드 실행] (병렬)
  → {"rag_retrieve": {"retrieved_docs": [...]}}
  → WebSocket.send({"type": "agent_update", "node": "rag_retrieve"})
  → Client receives → (UI 업데이트 없음, 내부에서만 사용)

[generate_suggestion 노드 실행]
  → {"generate_suggestion": {"suggestion": "..."}}
  → WebSocket.send({"type": "agent_update", "node": "generate_suggestion"})
  → Client receives → ✅ 추천 UI 즉시 업데이트!
```

### 4. 결과
```
사용자가 말하는 순간부터:
  1초: 전사 완료
  2초: 요약 화면에 표시 ✅
  3초: 추천 답변 화면에 표시 ✅
```

---

## 핵심 포인트

### ✅ 실시간성
- `stream_mode="updates"` 사용으로 각 노드 완료 즉시 전송
- WebSocket을 통한 양방향 실시간 통신
- 병렬 노드 결과도 완료되는 즉시 개별 전송

### ✅ 효율성
- 변경된 State 부분만 전송 (전체 State 아님)
- 병렬 처리로 요약과 RAG 동시 실행
- 클라이언트는 필요한 업데이트만 선택적으로 UI 반영

### ✅ 확장성
- 새로운 노드 추가 시 자동으로 스트리밍 지원
- Frontend는 관심 있는 노드만 구독
- State 구조 변경해도 스트리밍 로직 불변

---

## 다음 단계

1. ✅ LangGraph 스트리밍 구조 이해
2. ⏳ `backend/agent.py` 파일 생성 및 그래프 구현
3. ⏳ `backend/app.py`에 Agent 스트리밍 통합
4. ⏳ `frontend/src/agent.js` 클라이언트 구현
5. ⏳ UI 컴포넌트 추가 (`index.html`)
6. ⏳ 실제 LLM/RAG 통합 (OpenAI, Anthropic, Vector DB)
7. ⏳ 테스트 및 최적화

---

**작성일:** 2025-01-19
**프로젝트:** realtime-assist-agent
**문서 버전:** 1.0
