# 개발 중 발생한 문제 분석 보고서

본 문서는 Realtime Assist Agent 프로젝트 개발 과정에서 발생한 주요 문제들과 그 해결 과정을 기록합니다.

---

## 목차

1. [WebRTC Renegotiation Timing 문제](#1-webrtc-renegotiation-timing-문제)
2. [RTP Timestamp Drift로 인한 jitterBufferDelay 증가](#2-rtp-timestamp-drift로-인한-jitterbufferdelay-증가)
3. [오디오 품질 문제](#3-오디오-품질-문제-로봇-소리-끊김)
4. [LLM 요약 JSON 파싱 실패](#4-llm-요약-json-파싱-실패-및-불완전-표시)
5. [RAG API 422 에러](#5-rag-api-422-에러)
6. [WebRTC 재협상 시 트랙 중복 추가](#6-webrtc-재협상-시-트랙-중복-추가)
7. [모듈 구조 복잡성 및 순환 의존성](#7-모듈-구조-복잡성-및-순환-의존성)
8. [ElevenLabs STT 통합 복잡성](#8-elevenlabs-stt-통합-복잡성)
9. [모바일 ICE Candidate 실패 (패킷 로스)](#9-모바일-ice-candidate-실패-패킷-로스)
10. [Audio Consumer Task GC 문제](#10-audio-consumer-task-gc-문제)
11. [ICE Transport Closed 타이밍 문제](#11-ice-transport-closed-타이밍-문제)

---

## 1. WebRTC Renegotiation Timing 문제

### 문제 현상

- 연결 수립 전 renegotiation이 발생하여 `MediaStreamError` 예외 발생
- ICE transport가 조기 종료되는 현상
- `asyncio.CancelledError` 예외 처리 미흡으로 인한 서버 크래시

### 원인 분석

1. **Renegotiation 타이밍 문제**: WebRTC 연결이 완전히 수립되기 전에 트랙 추가/renegotiation을 시도함
2. **리소스 정리 미흡**: 브라우저 종료 시 리소스 정리 핸들러가 없어 연결이 비정상적으로 종료
3. **STT 에러 처리 오류**: Google STT API의 스트림 제한(500 에러)을 비정상 에러로 처리하여 불필요한 에러 로그 발생

### 해결 방법

**커밋**: `804ec8b`

#### Backend (`room_manager.py`, `stt_service.py`)

```python
# room_manager.py - 룸 삭제 시 에이전트 정리 로직 추가
async def delete_room(self, room_name):
    # Save transcript to file before deleting room
    self._save_transcript_to_file(room_name)

    # Clean up agent for this room
    from agent_manager import remove_agent
    remove_agent(room_name)

    # Clean up room data
    del self.rooms[room_name]
```

```python
# stt_service.py - STT 500 에러를 정상 종료로 처리
except Exception as e:
    # Google STT API의 스트림 제한 도달 시 500 에러 발생 (정상적인 종료)
    if "500" in str(e) or "Internal error" in str(e):
        logger.info(f"STT stream limit reached (normal behavior), will restart: {e}")
    else:
        logger.error(f"Unexpected STT error: {e}", exc_info=True)
    result_queue.put(None)
```

#### Frontend (`webrtc.js`)

```javascript
// beforeunload 이벤트 핸들러 추가
window.addEventListener('beforeunload', () => {
    this.disconnect();
});

// agent_ready, agent_update 이벤트 핸들러 추가
case 'agent_ready':
    console.log('Agent ready:', data);
    if (this.onAgentReady) {
        this.onAgentReady(data);
    }
    break;

case 'agent_update':
    if (this.onAgentUpdate) {
        this.onAgentUpdate({
            node: message.node,
            data: message.data
        });
    }
    break;
```

### 해결 결과

- Deferred renegotiation 패턴 적용으로 연결 수립 완료 후에만 renegotiation 허용
- 브라우저 종료 시 즉시 리소스 정리되어 서버 측 고아 연결 방지
- STT 스트림 제한 에러가 정상적인 재시작 트리거로 동작
- 룸 삭제 시 관련 에이전트도 함께 정리되어 메모리 누수 방지

---

## 2. RTP Timestamp Drift로 인한 jitterBufferDelay 증가

### 문제 현상

- 클라이언트의 `inbound-rtp` 통계에서 `jitterBufferDelay`가 시간이 지남에 따라 **직선으로 계속 증가**
- 네트워크 품질 지표(jitter: 0.005~0.015, packetLoss: 0)는 양호
- 오디오 품질 자체는 괜찮지만 지연이 계속 누적됨

### 원인 분석

#### 진단 과정

| 지표 | 값 | 의미 |
|------|-----|------|
| `jitter` | 0.005 ~ 0.015 | 네트워크 품질 매우 양호 |
| `packetsLost` | 약 0 | 패킷 손실 없음 |
| `packetsSent/s` | 약 50 | 정상 (48kHz, 20ms = 50 packets/s) |
| `totalPacketSendDelay` | 약 0 | 서버가 패킷을 즉시 전송 |
| `jitterBufferDelay` | 직선 증가 | **RTP timestamp drift** |

**결론**: 네트워크 문제가 아니라 **서버가 보내는 RTP 패킷의 timestamp 또는 송출 간격이 불규칙**

#### 1차 원인: 트랙 공유 문제

```python
# 문제 코드 (수정 전)
@pc.on("track")
async def on_track(track):
    # 같은 트랙을 여러 소비자에게 직접 전달
    relay_track = AudioRelayTrack(track, stt_queue, elevenlabs_queue)
    self.audio_tracks[peer_id] = relay_track  # 다른 피어 전달용
    consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, relay_track))  # STT용
    await self._relay_to_room_peers(peer_id, room_name, relay_track)  # 릴레이용
```

- 같은 `AudioRelayTrack`을 여러 소비자(STT, 다른 피어들)가 공유
- `recv()` 호출 시 프레임이 분산되어 일부 소비자는 프레임 건너뜀
- RTP timestamp 불연속 발생

#### 2차 원인: 프레임 Pacing 불규칙

- `MediaRelay`는 프레임을 복제하지만 **전달 타이밍(pacing)을 보장하지 않음**
- 원본 트랙에서 프레임이 불규칙하게 도착하면 그대로 전달
- RTP timestamp는 유지되지만, 실제 송출 시간과 drift 발생

**정상적인 RTP 스트림**:
```
패킷 1: timestamp=0,    송출 시간=0ms
패킷 2: timestamp=960,  송출 시간=20ms
패킷 3: timestamp=1920, 송출 시간=40ms
```

**drift가 발생한 RTP 스트림**:
```
패킷 1: timestamp=0,    송출 시간=0ms
패킷 2: timestamp=960,  송출 시간=22ms   (2ms drift)
패킷 3: timestamp=1920, 송출 시간=45ms   (5ms drift, 누적)
```

브라우저가 이를 보정하려고 jitterBuffer를 계속 늘림

### 해결 방법

#### 1차 수정: MediaRelay.subscribe() 사용

**커밋**: `5510ff4`

```python
@pc.on("track")
async def on_track(track):
    # CRITICAL FIX: Use MediaRelay.subscribe() to create independent track copies
    # Without this, multiple consumers (STT + other peers) share the same frame buffer,
    # causing RTP timestamp discontinuities and jitterBufferDelay to increase continuously.

    # 1. STT용 트랙 (별도 구독)
    stt_track_source = self.relay.subscribe(track)
    stt_relay_track = AudioRelayTrack(stt_track_source, stt_queue, elevenlabs_queue)

    # 2. 원본 트랙 저장 (릴레이 시 새로 구독)
    self.audio_tracks[peer_id] = track

    # 3. Start consuming STT track for speech recognition
    consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, stt_relay_track))

    # 4. 각 피어에게 별도 구독 트랙 전달
    await self._relay_to_room_peers(peer_id, room_name, track)

async def _relay_to_room_peers(self, source_peer_id, room_name, track):
    for peer_id, pc in self.peers.items():
        if peer_id != source_peer_id:
            # CRITICAL: Each peer gets their own subscription via MediaRelay
            # This ensures independent frame buffers and stable RTP timestamps
            relayed_track = self.relay.subscribe(track)
            pc.addTrack(relayed_track)
```

**결과**: 음질 개선, 하지만 jitterBufferDelay는 여전히 일부 증가

#### 2차 시도: PacedRelayTrack 구현

**커밋**: `88f5e70`

```python
class PacedRelayTrack(MediaStreamTrack):
    """정확한 20ms 간격으로 오디오 프레임을 pacing하는 릴레이 트랙."""
    kind = "audio"

    def __init__(self, source, sample_rate=48000, frame_duration_ms=20):
        super().__init__()
        self.source = source
        self.sample_rate = sample_rate
        self.samples_per_frame = int(sample_rate * frame_duration_ms / 1000)  # 960

        self._buffer = asyncio.Queue(maxsize=50)  # ~1초 버퍼
        self._pts = 0
        self._time_base = Fraction(1, sample_rate)
        self._start_time = None
        self._frame_index = 0
        self._consumer_task = None

    async def _consume_source(self):
        """백그라운드에서 소스 트랙의 프레임을 버퍼에 저장"""
        while True:
            frame = await self.source.recv()
            try:
                self._buffer.put_nowait(frame)
            except asyncio.QueueFull:
                # 버퍼 오버플로우 시 오래된 프레임 제거
                self._buffer.get_nowait()
                self._buffer.put_nowait(frame)

    async def recv(self):
        # 소비 태스크 시작 (최초 1회)
        if self._consumer_task is None:
            self._consumer_task = asyncio.create_task(self._consume_source())

        # 시작 시간 설정 (최초 1회)
        if self._start_time is None:
            self._start_time = time.perf_counter()

        # 정확한 20ms 간격 대기 (monotonic clock 기반)
        target_time = self._start_time + (self._frame_index * 20) / 1000.0
        wait = target_time - time.perf_counter()
        if wait > 0:
            await asyncio.sleep(wait)

        self._frame_index += 1

        # 버퍼에서 프레임 가져오기 (없으면 silence)
        try:
            frame = self._buffer.get_nowait()
        except asyncio.QueueEmpty:
            frame = self._create_silence_frame()

        # timestamp 정확히 960씩 증가
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += self.samples_per_frame

        return frame
```

**결과**: 복잡한 구현이 오히려 edge case에서 불안정성 야기

#### 최종 결정: PacedRelayTrack 제거

**커밋**: `caa7427`

- `PacedRelayTrack` 완전 제거 (215줄 삭제)
- `MediaRelay.subscribe()`만으로 충분히 안정적
- 단순한 구조가 더 안정적인 결과 제공

### 해결 결과

- `MediaRelay.subscribe()`로 각 소비자에게 독립적인 프레임 버퍼 제공
- jitterBufferDelay가 안정적으로 유지됨
- 복잡한 pacing 로직 없이도 RTP timestamp 안정화 달성

---

## 3. 오디오 품질 문제 (로봇 소리, 끊김)

### 문제 현상

- 오디오가 로봇 소리처럼 들리거나 끊김 현상 발생
- 상담 대화 품질 저하로 STT 인식률에도 영향

### 원인 분석

1. **브라우저 노이즈 억제**: 기본 `noiseSuppression: true` 설정이 실시간 대화에서 음성을 왜곡
2. **오디오 설정 미최적화**: 샘플레이트, 지연 설정이 WebRTC 실시간 통화에 최적화되지 않음

### 해결 방법

**커밋**: `ca606a2`

```javascript
// frontend/src/webrtc.js
this.localStream = await navigator.mediaDevices.getUserMedia({
    video: false,
    audio: {
        // 오디오 품질 설정
        sampleRate: 48000,           // 48kHz - 고품질 오디오
        sampleSize: 16,              // 16비트
        channelCount: 1,             // 모노 (대화용)

        // 음성 처리 설정
        echoCancellation: true,      // 에코 제거 (유지)
        noiseSuppression: false,     // 노이즈 억제 끔 (로봇 소리 방지)
        autoGainControl: true,       // 자동 게인 조절

        // 지연 최소화
        latency: 0                   // 최소 지연
    }
});
```

### 해결 결과

- `noiseSuppression: false`로 로봇 소리 현상 해결
- 48kHz 고품질 오디오로 STT 인식률 향상
- `latency: 0`으로 실시간 대화 지연 최소화
- 에코 제거는 유지하여 피드백 방지

---

## 4. LLM 요약 JSON 파싱 실패 및 불완전 표시

### 문제 현상

- LLM 스트리밍 응답 중 불완전한 JSON이 화면에 표시됨
- 예: `{"summary": "고객이 환불을...` (잘린 상태로 표시)
- 요약이 계속 길어지는 현상 (이전 요약에 누적)

### 원인 분석

1. **파싱 실패 처리 미흡**: JSON 파싱 실패 시 원본 문자열을 그대로 화면에 표시
2. **누적 요약 방식**: 이전 요약에 새 대화를 추가하는 방식으로 요약 길이가 계속 증가

### 해결 방법

**커밋**: `ca606a2`, `adce9ab`

#### Frontend (`AssistantMain.jsx`)

```javascript
// JSON 파싱 실패 시 이전 값 유지 (불완전한 JSON 표시 방지)
if (data.node === 'summarize' && data.data.current_summary) {
    try {
        const summaryJson = JSON.parse(data.data.current_summary);

        // 파싱 성공 시에만 UI 업데이트
        setLlmStatus('connected');
        setSummaryTimestamp(Date.now());
        setParsedSummary(summaryJson);
        console.log('Summary parsed:', summaryJson);
    } catch (parseError) {
        // JSON 파싱 실패 시 UI 업데이트 스킵 (이전 값 유지)
        // 이렇게 하면 불완전한 JSON이 화면에 표시되지 않음
        console.warn('Failed to parse summary JSON, keeping previous value:', parseError.message);
        console.debug('Raw content:', data.data.current_summary);
    }
}
```

#### Backend (`agent.py`)

```python
# 프롬프트 구성: 전체 대화를 한 문장으로 요약 (덮어쓰기 방식)
# 전체 대화를 다시 요약하여 항상 최신 한 문장 요약 유지
all_formatted = []
for entry in conversation_history:
    speaker = entry.get("speaker_name", "Unknown")
    text = entry.get("text", "")
    all_formatted.append(f"{speaker}: {text}")
all_conversation_text = "\n".join(all_formatted)

user_content = f"""전체 대화:
{all_conversation_text}

위 전체 대화 내용을 한 문장으로 요약하여 JSON으로 출력하세요.
요약은 반드시 한 문장이어야 합니다."""
```

#### Backend (`agent_manager.py`)

```python
# 시스템 메시지 - JSON 출력 강제, 한 문장 요약 강조
self.system_message = """
# 역할
고객 상담 대화를 요약하여 반드시 아래 JSON 형식으로만 출력하세요.
다른 텍스트 없이 JSON만 출력하세요.

# 중요 규칙
- summary 필드는 반드시 한 문장이어야 합니다 (20자 이내)
- 이전 요약을 참고하지 말고 현재 대화만 요약하세요

{"summary": "한 문장 요약 (20자 이내)", "customer_issue": "고객 문의 한 줄", "agent_action": "상담사 대응 한 줄"}

# 예시:
{"summary": "고객이 환불을 요청함", "customer_issue": "제품 불량으로 환불 요청", "agent_action": "환불 절차 안내"}
"""
```

### 해결 결과

- 불완전한 JSON이 화면에 표시되지 않음 (이전 유효한 값 유지)
- 덮어쓰기 방식으로 요약 길이가 일정하게 유지
- 시스템 프롬프트 강화로 JSON 형식 준수율 향상

---

## 5. RAG API 422 에러

### 문제 현상

- RAG 서버와의 통신에서 422 Unprocessable Entity 에러 발생
- 상담 가이드 기능 동작 불가

### 원인 분석

- 요청 모델(Pydantic)의 필드명이 RAG 서버가 기대하는 스펙과 불일치
- 기존: `query`, `context`, `conversation_history`
- 실제 RAG 서버 스펙: `summary`, `include_documents`, `max_documents`

### 해결 방법

**커밋**: `856b0cd`

```python
# backend/app.py

# 수정 전
class RAGAssistRequest(BaseModel):
    """RAG 어시스턴트 요청 모델."""
    query: str
    context: Optional[str] = None
    conversation_history: Optional[list] = None

# 수정 후
class RAGAssistRequest(BaseModel):
    """RAG 어시스턴트 요청 모델."""
    summary: str
    include_documents: bool = True
    max_documents: int = 5
```

API 문서 주석도 함께 수정:

```python
@app.post("/api/rag/assist")
async def rag_assist_proxy(request: RAGAssistRequest):
    """RAG 어시스턴트 프록시 엔드포인트.

    Args:
        request: RAG 어시스턴트 요청
            - summary: 상담 내용 요약
            - include_documents: 관련 문서 포함 여부 (기본값: true)
            - max_documents: 최대 문서 수 (기본값: 5)

    Returns:
        dict: RAG 서버의 응답
    """
```

### 해결 결과

- RAG 서버와의 통신 정상화
- 상담 가이드 기능 정상 동작
- API 스펙 문서화로 향후 유지보수 용이

---

## 6. WebRTC 재협상 시 트랙 중복 추가

### 문제 현상

- 연결 재협상 시 동일한 트랙이 중복으로 추가됨
- 오디오가 이중으로 전송되거나 리소스 낭비

### 원인 분석

- 재협상 로직에서 기존 트랙 존재 여부 확인 없이 무조건 `addTrack()` 호출
- 이미 추가된 트랙을 다시 추가하려고 시도

### 해결 방법

**커밋**: `731ffd3`

```python
# backend/peer_manager.py
async def _relay_to_room_peers(self, source_peer_id, room_name, track):
    """같은 룸의 다른 피어들에게 트랙을 릴레이합니다."""
    for peer_id, pc in self.peers.items():
        if (peer_id != source_peer_id and
            self.peer_rooms.get(peer_id) == room_name and
            pc.connectionState != "closed"):

            # 이미 추가된 트랙인지 확인
            existing_senders = pc.getSenders()
            track_already_added = any(
                sender.track and sender.track.id == track.id
                for sender in existing_senders
            )

            if not track_already_added:
                relayed_track = self.relay.subscribe(track)
                pc.addTrack(relayed_track)
                logger.info(f"Relaying {track.kind} from {source_peer_id} to {peer_id}")
            else:
                logger.debug(f"Track already exists for {peer_id}, skipping")
```

### 해결 결과

- 트랙 중복 추가 방지
- 재협상 시에도 안정적인 미디어 스트림 유지
- 불필요한 리소스 사용 방지

---

## 7. 모듈 구조 복잡성 및 순환 의존성

### 문제 현상

- 단일 파일에 모든 로직이 혼재되어 유지보수 어려움
- 파일 간 순환 import 발생으로 런타임 에러
- 코드 재사용성 저하

### 원인 분석

1. **초기 개발 방식**: 기능 중심으로 빠르게 코드 작성하다 보니 구조화 미흡
2. **의존성 설계 부재**: 모듈 간 의존성을 사전에 설계하지 않음
3. **파일 비대화**: `app.py`, `peer_manager.py` 등이 1000줄 이상으로 비대해짐

### 해결 방법

**커밋**: `9055f78`

#### 디렉토리 구조 재설계

```
backend/
├── app.py                      # FastAPI 메인 앱 (라우팅만)
├── modules/
│   ├── __init__.py             # 메인 exports
│   │
│   ├── webrtc/                 # WebRTC 모듈
│   │   ├── __init__.py
│   │   ├── config.py           # WebRTC 설정
│   │   ├── tracks.py           # AudioRelayTrack
│   │   ├── room_manager.py     # RoomManager, Peer, TranscriptEntry
│   │   └── peer_manager.py     # PeerConnectionManager
│   │
│   ├── stt/                    # Speech-to-Text 모듈
│   │   ├── __init__.py
│   │   ├── config.py           # STT 설정
│   │   ├── service.py          # STTService
│   │   └── adaptation.py       # PhraseSet/CustomClass 설정
│   │
│   └── agent/                  # LangGraph 에이전트 모듈
│       ├── __init__.py
│       ├── config.py           # 에이전트 설정
│       ├── graph.py            # StateGraph 정의
│       └── manager.py          # RoomAgent 생명주기 관리
```

#### 순환 의존성 해결 (Lazy Import)

```python
# modules/webrtc/room_manager.py
class RoomManager:
    async def delete_room(self, room_name):
        # ...

        # Lazy import로 순환 의존성 방지
        from modules.agent import remove_agent
        remove_agent(room_name)
```

#### 모듈별 Export 정리

```python
# modules/__init__.py
from modules.webrtc import PeerConnectionManager, RoomManager, AudioRelayTrack
from modules.stt import STTService, STTAdaptationConfig
from modules.agent import RoomAgent, create_agent_graph, get_or_create_agent, remove_agent

__all__ = [
    # WebRTC
    "PeerConnectionManager",
    "RoomManager",
    "AudioRelayTrack",
    # STT
    "STTService",
    "STTAdaptationConfig",
    # Agent
    "RoomAgent",
    "create_agent_graph",
    "get_or_create_agent",
    "remove_agent",
]
```

### 해결 결과

- 도메인별 모듈 분리로 관심사 분리 달성
- 각 모듈에 `config.py` 분리로 설정 관리 용이
- Lazy import로 순환 의존성 해결
- 코드 네비게이션 및 유지보수성 향상
- 불필요한 테스트/예시 파일 정리 (598줄 삭제)

---

## 8. ElevenLabs STT 통합 복잡성

### 문제 현상

- Dual STT(Google + ElevenLabs) 비교 기능으로 인한 코드 복잡성 증가
- 두 STT 엔진 결과 병합 로직 관리 어려움
- ElevenLabs API 비용 문제

### 원인 분석

1. **초기 평가 목적**: STT 엔진 성능 비교를 위해 두 엔진 동시 운영
2. **평가 완료 후 미정리**: Google Cloud STT 선택 후에도 ElevenLabs 코드 잔존
3. **의존성 누적**: ElevenLabs 관련 패키지, 환경 변수, UI 컴포넌트 등 잔존

### 해결 방법

**커밋**: `2a6bafc`

#### 삭제된 파일들

- `backend/elevenlabs_stt_service.py` (422줄)
- `frontend/src/STTComparison.jsx`
- `frontend/src/STTComparison.css`

#### 환경 변수 정리

```bash
# .env.example에서 제거
# ElevenLabs STT API (Optional - for dual STT comparison)
# ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

#### 백엔드 코드 정리

```python
# app.py에서 제거된 핸들러
elif message_type == "enable_dual_stt":
    # Handle dual STT enable/disable request
    # ... (34줄 삭제)
```

#### CORS 설정 업데이트

```python
# ngrok 도메인 추가 (로컬 테스트용)
allow_origin_regex=r"...|^https://.*\.ngrok(-free)?\.app$|^https://.*\.ngrok\.io$"
```

#### 의존성 정리

```toml
# pyproject.toml에서 elevenlabs 패키지 제거
```

### 해결 결과

- Google Cloud STT 단일 사용으로 코드 단순화
- 약 500줄 이상의 코드 삭제
- ElevenLabs API 비용 절감
- 프론트엔드 STT 비교 UI 제거로 UX 단순화
- 환경 변수 및 의존성 정리

---

## 9. 모바일 ICE Candidate 실패 (패킷 로스)

### 문제 현상

- 모바일에서 WebRTC 연결 시 모든 ICE candidate pair 실패
- PC 연결은 정상이지만 모바일 연결에서 `Total frames: 0`
- 오디오/비디오 스트림이 전혀 전달되지 않음

### 원인 분석

#### PC vs 모바일 연결 비교

**PC 연결 (정상)**:
```
ICE state: checking
Discovered peer reflexive candidate
CandidatePair ('172.30.1.15', 54046) -> ('172.30.1.15', 53108)
State: WAITING -> IN_PROGRESS -> SUCCEEDED
ICE completed
Total frames: 1923
```

**모바일 연결 (실패)**:
```
ICE state: checking
Check CandidatePair ('172.30.1.15', 54046) -> ('172.30.1.15', 53109)
State: FROZEN -> FAILED

Check CandidatePair ('172.30.1.15', 54046) -> ('220.118.182.72', 53109)
State: FROZEN -> FAILED

Check CandidatePair ('158.247.200.82', 30797) -> ('158.247.200.82', 29801)
State: FROZEN -> FAILED

(ALL PAIRS FAILED)
Total frames: 0
```

#### 근본 원인: Localtunnel의 UDP 미지원

**Localtunnel은 WebRTC에 적합하지 않음**:

1. **HTTP/WebSocket 터널링만 지원**: ICE/STUN/TURN은 UDP 사용
2. **UDP 미지원**: WebRTC 미디어 스트림에 필수인 UDP 통과 불가
3. **ICE candidate에 private IP 포함**: 터널이 IP를 변환하지 않음
4. **시그널링만 동작**: WebSocket은 되지만 미디어 경로 차단

**Evidence**:
```
Frontend: wss://my-dev-webrtc.loca.lt/ws  (WebSocket 동작)
ICE: All UDP candidate pairs              (미디어 경로 실패)
```

### 해결 방법

#### Solution 1: Direct IP 사용 (테스트용)

같은 네트워크에서 PC의 IP로 직접 접속:

```bash
# PC IP 확인
ipconfig | findstr IPv4
# 결과: 192.168.1.100

# Frontend .env 수정
VITE_BACKEND_URL=http://192.168.1.100:8000
```

#### Solution 2: Force TURN Relay Mode (채택)

모든 트래픽을 TURN 서버 경유하도록 강제:

**Frontend (`webrtc.js`)**:
```javascript
// BEFORE:
this.pc = new RTCPeerConnection({ iceServers });

// AFTER:
this.pc = new RTCPeerConnection({
  iceServers,
  iceTransportPolicy: 'relay'  // Force TURN relay, bypass P2P
});
```

**Backend (`peer_manager.py`)**:
```python
# BEFORE:
config = RTCConfiguration(iceServers=ice_servers)

# AFTER:
config = RTCConfiguration(
    iceServers=ice_servers,
    iceTransportPolicy="relay"  # Force TURN relay
)
```

#### 데이터 흐름 변경

**수정 전**:
```
Mobile -> Localtunnel -> Backend (Signaling + Media 시도, Media 실패)
```

**수정 후**:
```
Mobile -> Localtunnel -> Backend (Signaling only, WebSocket)
Mobile -> TURN Server -> Backend (Media, UDP)
```

### 해결 결과

- 모바일에서 WebRTC 연결 성공
- `iceTransportPolicy: 'relay'`로 P2P 시도 건너뜀
- TURN 서버를 통한 안정적인 미디어 전송
- Host/STUN candidate 무시, Relay candidate만 사용

#### Trade-offs

| 장점 | 단점 |
|------|------|
| Localtunnel 환경에서 동작 | 높은 지연 (TURN 경유) |
| 제한적 NAT/방화벽 통과 | TURN 서버 대역폭 사용 |
| 안정적인 연결 수립 | 무료 TURN 서버 rate limiting |
| 모바일 데이터 네트워크 호환 | 릴레이 오버헤드로 품질 저하 가능 |

---

## 10. Audio Consumer Task GC 문제

### 문제 현상

- STT가 오디오 프레임을 전혀 받지 못함 (`Total frames: 0`)
- 백엔드 로그에 `Task was destroyed but it is pending!` 에러
- WebRTC 연결은 성공했지만 음성 인식 불가

### 원인 분석

AsyncIO task가 생성 후 참조되지 않아 garbage collection으로 파괴됨:

```python
# 문제 코드
@pc.on("track")
async def on_track(track):
    # Task 생성 후 참조 저장 없음
    asyncio.create_task(self._consume_audio_track(peer_id, relay_track))
    # Task가 GC 대상이 되어 실행 전 파괴됨
```

**Python AsyncIO 동작**:
- `create_task()`로 생성된 task는 참조가 없으면 GC 대상
- Task가 완료되기 전에 GC가 실행되면 `Task was destroyed` 경고
- 오디오 소비 루프가 시작도 못하고 종료됨

### 해결 방법

Task를 딕셔너리에 저장하여 GC 방지:

**1. 초기화 (`peer_manager.py`)**:
```python
def __init__(self):
    # ...
    # Audio consumer tasks to prevent garbage collection (peer_id -> List[Task])
    self.audio_consumer_tasks: Dict[str, List[asyncio.Task]] = {}
```

**2. Task 저장 로직**:
```python
@pc.on("track")
async def on_track(track):
    # Task 생성
    consumer_task = asyncio.create_task(self._consume_audio_track(peer_id, relay_track))

    # Store task to prevent it from being garbage collected
    if peer_id not in self.audio_consumer_tasks:
        self.audio_consumer_tasks[peer_id] = []
    self.audio_consumer_tasks[peer_id].append(consumer_task)
```

**3. 정리 로직 (연결 종료 시)**:
```python
async def cleanup_peer(self, peer_id):
    # Cancel audio consumer tasks
    if peer_id in self.audio_consumer_tasks:
        for task in self.audio_consumer_tasks[peer_id]:
            if not task.done():
                task.cancel()
        del self.audio_consumer_tasks[peer_id]
```

### 해결 결과

- `Total frames: 0` 문제 해결, 정상적인 프레임 수신 확인
- `Task was destroyed` 에러 사라짐
- STT 음성 인식 정상 동작
- 연결 종료 시 명시적 task 취소로 리소스 정리

---

## 11. ICE Transport Closed 타이밍 문제

### 문제 현상

- `InvalidStateError: RTCIceTransport is closed` 에러 발생
- WebRTC 연결이 `connecting` 상태에서 바로 `failed`로 전환
- 간헐적으로 발생하여 디버깅 어려움

### 원인 분석

**에러 시퀀스**:
```
1. Frontend sends offer
2. Backend creates answer
3. Frontend receives answer -> sets remote description -> state: stable
4. Backend triggers renegotiation_needed (새 트랙 수신)
5. Frontend receives renegotiation_needed -> creates NEW offer
6. Backend receives NEW offer -> creates NEW answer
7. Frontend receives duplicate answer (already in stable state)
8. ICE transport already closed -> connection fails
```

**핵심 문제**:
- Renegotiation이 **너무 빨리** 트리거됨 (초기 연결 수립 전)
- ICE gathering이 완료되지 않은 상태에서 renegotiation 시작
- Connection state가 `connecting`일 때 새 offer 전송

**Frontend 로그 증거**:
```
webrtc.js:628 Remote description set, state: stable
webrtc.js:304 Received answer from server
webrtc.js:620 Current signaling state: stable
webrtc.js:630 Already in stable state, ignoring duplicate answer
webrtc.js:569 Connection state: connecting
webrtc.js:569 Connection state: failed
```

### 해결 방법

**Deferred Renegotiation 패턴**: 연결이 완료된 후에만 renegotiation 실행

**Frontend (`webrtc.js`)**:

```javascript
// 1. Renegotiation 요청 시 연결 상태 확인
case 'renegotiation_needed':
  console.log('Renegotiation needed:', data.reason);

  // WAIT for connection to be established
  if (this.pc && this.pc.connectionState === 'connected') {
    await this.renegotiate();
  } else {
    console.log('Deferring renegotiation - connection not ready');
    this.needsRenegotiation = true;  // 플래그 설정
  }
  break;

// 2. 연결 완료 시 deferred renegotiation 실행
this.pc.onconnectionstatechange = () => {
  const state = this.pc.connectionState;
  console.log('Connection state:', state);

  if (this.onConnectionStateChange) {
    this.onConnectionStateChange(state);
  }

  // Execute deferred renegotiation when connected
  if (state === 'connected' && this.needsRenegotiation) {
    console.log('Executing deferred renegotiation');
    this.needsRenegotiation = false;
    this.renegotiate();
  }
};
```

### 해결 결과

- 연결이 `connected` 상태가 된 후에만 renegotiation 실행
- Duplicate answer 경고 사라짐
- ICE transport가 정상적으로 수립됨
- 연결 안정성 향상

---

## 요약 테이블

| 번호 | 문제 영역 | 주요 커밋 | 핵심 해결책 |
|------|----------|----------|------------|
| 1 | WebRTC Renegotiation | `804ec8b` | Deferred renegotiation 패턴 |
| 2 | jitterBufferDelay 증가 | `5510ff4`, `caa7427` | MediaRelay.subscribe() 독립 구독 |
| 3 | 오디오 품질 | `ca606a2` | noiseSuppression 비활성화 |
| 4 | JSON 파싱 | `ca606a2`, `adce9ab` | 파싱 실패 시 이전 값 유지 |
| 5 | RAG 422 에러 | `856b0cd` | 요청 모델 필드명 수정 |
| 6 | 트랙 중복 | `731ffd3` | 재협상 시 트랙 확인 로직 |
| 7 | 모듈 구조 | `9055f78` | 도메인별 모듈 분리 |
| 8 | STT 복잡성 | `2a6bafc` | ElevenLabs 제거, 단일 엔진 |
| 9 | 모바일 ICE 실패 | - | iceTransportPolicy: 'relay' |
| 10 | Audio Task GC | - | Task 딕셔너리 저장 |
| 11 | ICE Transport Closed | - | Deferred renegotiation |

---

## 교훈 및 권장사항

### WebRTC 관련

1. **연결 상태 확인 필수**: 트랙 추가/재협상 전 연결 상태 확인
2. **MediaRelay 사용**: 다중 소비자가 있을 때 반드시 `subscribe()` 사용
3. **리소스 정리**: `beforeunload` 이벤트로 브라우저 종료 시 정리
4. **Deferred Renegotiation**: 초기 연결 완료 후에만 renegotiation 실행
5. **TURN Relay 고려**: 제한적 네트워크 환경에서는 `iceTransportPolicy: 'relay'` 사용

### 오디오 품질 관련

1. **노이즈 억제 주의**: 실시간 대화에서는 `noiseSuppression: false` 권장
2. **샘플레이트 일관성**: 48kHz로 전체 파이프라인 통일

### AsyncIO Task 관리

1. **Task 참조 유지**: `create_task()` 결과를 반드시 변수/컬렉션에 저장
2. **명시적 취소**: 연결 종료 시 `task.cancel()`로 명시적 정리
3. **GC 방지**: 장기 실행 task는 딕셔너리 등에 저장하여 GC 방지

### 네트워크/터널링 관련

1. **Localtunnel 제한**: WebRTC 미디어에는 부적합 (UDP 미지원)
2. **대안 고려**: ngrok, 직접 IP 접속, 또는 Force TURN relay mode
3. **프로덕션 배포**: 클라우드 서버에 public IP로 배포 권장

### LLM 응답 처리

1. **스트리밍 응답 파싱**: 불완전한 JSON에 대비한 fallback 로직 필수
2. **프롬프트 강화**: JSON 형식 출력을 위한 명확한 지시 포함

### 코드 구조

1. **초기 설계 중요**: 모듈 구조를 초기에 설계하여 순환 의존성 방지
2. **기능 검증 후 정리**: 비교/테스트 코드는 평가 완료 후 즉시 정리
3. **Lazy Import 활용**: 순환 의존성 발생 시 lazy import로 해결

---

*문서 작성일: 2025-12-18*
*마지막 업데이트: 2025-12-18 (패킷 로스 관련 문제 추가)*
*마지막 분석 커밋: ce90c8a*
