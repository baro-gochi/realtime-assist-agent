# WebRTC Video Call Application - Room Based

FastAPI + aiortc + React를 사용한 **방 기반** 실시간 비디오/오디오 통화 애플리케이션입니다.

zoom-clone의 Socket.IO 방식을 FastAPI WebSocket으로 구현했습니다.

## 아키텍처

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│   Client 1  │ ◄─────── Signaling ───────► │  FastAPI Server  │
│   (React)   │      (join_room)            │  + RoomManager   │
│             │      (offer/answer)         │  + aiortc        │
└─────────────┘                             └──────────────────┘
      │                                              ▲
      │         WebRTC Media Stream                 │
      │         (Same Room Only)                    │
      └────────────────────┬────────────────────────┘
                           │
                    ┌─────────────┐
                    │   Client 2  │
                    │   (React)   │
                    │ Same Room   │
                    └─────────────┘
```

### 주요 특징

1. **방 기반 통화**: 같은 방 이름으로 입장한 사용자들끼리만 통화
2. **닉네임 지원**: 각 참가자를 닉네임으로 식별
3. **서버 중계 방식 (SFU-like)**: 서버가 방별로 미디어 스트림 중계
4. **오디오 캡처**: 서버가 오디오 프레임을 캡처하여 나중에 STT 엔진 연동 가능
5. **비디오 + 오디오**: 카메라와 마이크를 모두 사용
6. **참가자 추적**: 실시간으로 방 참가자 목록 표시

## 프로젝트 구조

```
realtime-counselor-agent/
├── backend/
│   ├── app.py              # FastAPI 시그널링 서버 (방 기반)
│   ├── room_manager.py     # 방 및 피어 관리
│   └── peer_manager.py     # aiortc 피어 연결 관리 (방별 중계)
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # React 메인 컴포넌트 (방 입장 UI)
│   │   ├── App.css         # 스타일
│   │   ├── webrtc.js       # WebRTC 클라이언트 (방 기반 시그널링)
│   │   └── main.jsx        # React 엔트리 포인트
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── pyproject.toml          # Python dependencies
```

## 설치 및 실행

### 1. Backend 실행

```bash
# 프로젝트 루트에서
cd backend
python app.py
```

서버가 http://localhost:8000 에서 실행됩니다.

### 2. Frontend 실행

새 터미널에서:

```bash
# 프로젝트 루트에서
cd frontend
npm run dev
```

프론트엔드가 http://localhost:3000 에서 실행됩니다.

## 사용 방법

### 방 생성 및 입장

1. 브라우저에서 http://localhost:3000 접속
2. **"Connect to Server"** 버튼 클릭 (시그널링 서버 연결)
3. **방 이름**과 **닉네임** 입력
4. **"Join Room"** 버튼 클릭
5. **"Start Call"** 버튼 클릭 (카메라/마이크 권한 허용)

### 다른 사용자와 통화

1. **다른 탭이나 창**에서 같은 주소(http://localhost:3000) 열기
2. "Connect to Server" 클릭
3. **같은 방 이름**과 다른 닉네임 입력
4. "Join Room" → "Start Call" 실행
5. 양쪽에서 비디오/오디오 스트림 확인! 🎥🎤

## 기술 스택

### Backend
- **FastAPI**: WebSocket 시그널링 서버
- **aiortc**: Python WebRTC 구현
- **uvicorn**: ASGI 서버
- **Room-based Architecture**: Socket.IO의 room 개념을 FastAPI로 구현

### Frontend
- **React 18**: UI 프레임워크
- **Vite**: 빌드 도구
- **WebRTC API**: 브라우저 네이티브 API
- **Multi-screen UI**: Welcome → Join Room → Video Call

## WebRTC 흐름 (Room-based)

### 1. 연결 및 방 입장
```
Client → Server: WebSocket 연결
Server → Client: peer_id 할당
Client → Server: join_room { room_name, nickname }
Server: RoomManager에 피어 추가
Server → Other Clients: user_joined 알림
```

### 2. WebRTC 연결 시작
```
Client: getUserMedia() → 로컬 미디어 획득
Client: createOffer() → Offer 생성
Client → Server: offer { sdp, type }
Server: 같은 방의 다른 피어 트랙 추가
Server: createAnswer() → Answer 생성
Server → Client: answer { sdp, type }
Client: setRemoteDescription(answer)
```

### 3. 미디어 전송 및 중계
```
Client → Server: 오디오/비디오 트랙 전송
Server: AudioRelayTrack/VideoRelayTrack 생성
Server: 같은 방의 다른 피어들에게 중계
Other Clients: 미디어 스트림 수신
```

### 4. 방 퇴장
```
Client → Server: leave_room
Server: RoomManager에서 피어 제거
Server: PeerConnection 종료
Server → Other Clients: user_left 알림
```

## 방 관리 시스템

### RoomManager (room_manager.py)

```python
class RoomManager:
    # 방별 피어 관리
    rooms: Dict[str, Dict[str, Peer]]

    # 빠른 조회를 위한 역참조
    peer_to_room: Dict[str, str]

    def join_room(room_name, peer_id, nickname, websocket)
    def leave_room(peer_id)
    def get_room_peers(room_name)
    def get_other_peers(room_name, exclude_peer_id)
```

### PeerConnectionManager (peer_manager.py)

```python
class PeerConnectionManager:
    # 피어별 연결 및 방 매핑
    peers: Dict[str, RTCPeerConnection]
    peer_rooms: Dict[str, str]

    # 방별 미디어 중계
    async def _relay_to_room_peers(source_peer_id, room_name, track)

    # 방 기반 Offer 처리
    async def handle_offer(peer_id, room_name, offer, other_peers_in_room)
```

## 서버 오디오 캡처 구조

`AudioRelayTrack` 클래스가 오디오 프레임을 캡처:

```python
class AudioRelayTrack(MediaStreamTrack):
    def __init__(self, track):
        super().__init__()
        self.track = track
        self.audio_frames = asyncio.Queue(maxsize=100)  # 오디오 프레임 저장

    async def recv(self):
        frame = await self.track.recv()
        # STT 처리를 위해 프레임 저장
        self.audio_frames.put_nowait(frame)
        return frame
```

나중에 `audio_frames` 큐에서 프레임을 가져와 Google STT나 다른 STT 엔진으로 전송할 수 있습니다.

## 다음 단계: STT 통합

1. `AudioRelayTrack`의 `audio_frames` 큐에서 오디오 프레임 가져오기
2. 오디오 프레임을 적절한 형식으로 변환 (예: PCM, 16kHz, mono)
3. Google Cloud Speech-to-Text API로 실시간 전송
4. 실시간 텍스트 결과를 클라이언트로 전달 (WebSocket 통해)
5. LangGraph 기반 상담 에이전트와 연동

## API 엔드포인트

### HTTP Endpoints
- `GET /`: 헬스 체크
- `GET /rooms`: 모든 방 목록 및 참가자 수

### WebSocket
- `WS /ws`: 시그널링 WebSocket 연결

### WebSocket 메시지 타입

**Client → Server:**
- `join_room`: 방 입장 (`{ room_name, nickname }`)
- `offer`: WebRTC offer (`{ sdp, type }`)
- `ice_candidate`: ICE candidate 교환
- `leave_room`: 방 퇴장
- `get_rooms`: 방 목록 요청

**Server → Client:**
- `peer_id`: 서버가 할당한 피어 ID
- `room_joined`: 방 입장 성공 (`{ room_name, peer_count, other_peers }`)
- `user_joined`: 새 사용자 입장 알림 (`{ peer_id, nickname, peer_count }`)
- `user_left`: 사용자 퇴장 알림 (`{ peer_id, nickname, peer_count }`)
- `answer`: WebRTC answer (`{ sdp, type }`)
- `error`: 에러 메시지

## 트러블슈팅

### 카메라/마이크 권한 오류
- 브라우저에서 권한을 명시적으로 허용해야 합니다
- HTTPS가 아닌 경우 localhost에서만 작동합니다

### 연결이 안 될 때
- Backend 서버가 실행 중인지 확인
- 브라우저 콘솔에서 WebSocket 연결 상태 확인
- STUN 서버 연결 확인 (기본: Google STUN 서버)

### 같은 방에 있는데 비디오가 안 보일 때
- **방 이름이 정확히 일치**하는지 확인 (대소문자 구분)
- 각 탭에서 "Start Call"을 실행해야 합니다
- WebRTC 연결 상태가 "connected"인지 확인
- 브라우저 콘솔에서 에러 메시지 확인

### 방 관련 이슈
- 방 이름은 대소문자를 구분합니다
- 닉네임은 같은 방 내에서 중복 가능합니다 (peer_id로 구분)
- 빈 방은 자동으로 삭제됩니다

## zoom-clone과의 차이점

| 기능 | zoom-clone (Socket.IO + Node.js) | 이 프로젝트 (FastAPI + Python) |
|------|----------------------------------|--------------------------------|
| 시그널링 | Socket.IO | FastAPI WebSocket |
| 방 관리 | Socket.IO의 내장 room 기능 | 커스텀 RoomManager |
| 미디어 중계 | 브라우저 간 P2P | 서버 중계 (aiortc) |
| 오디오 처리 | 클라이언트에서만 | 서버에서 캡처 가능 (STT 준비) |
| 데이터 채널 | P2P DataChannel | 서버 중계 (추후 구현 가능) |

## 주요 개선사항

✅ **방 기반 격리**: 같은 방의 피어들끼리만 미디어 공유
✅ **참가자 추적**: 실시간 참가자 목록 및 입장/퇴장 알림
✅ **서버 오디오 접근**: STT 엔진 연동을 위한 오디오 프레임 캡처
✅ **확장성**: 여러 방을 동시에 운영 가능
✅ **사용자 경험**: Welcome → Join Room → Call의 명확한 플로우

## 라이선스

MIT
