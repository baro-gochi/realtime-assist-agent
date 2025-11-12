# [2025 KT CS 일경험 사업] 실시간 상담 어시스턴트 AI 에이전트 개발
## Team 바로고치
- 팀장 : 🧑 이찬구
- 팀원 : 🧑 김재홍 🧑 장윤호

Realtime Assist Agent
상담사를 위한 WebRTC 기반 오디오 통화 및 AI 에이전트 시스템

## 프로젝트 개요

**목표**: STT, LangGraph 기반 상담 어시스턴트 에이전트 개발

**현재 상태**: ✅ 방 기반 WebRTC 비디오/오디오 통화 시스템 구현 완료

## 기능

### ✅ 구현 완료

- **방 기반 비디오 통화**: 같은 방 이름의 사용자들끼리만 통화
- **서버 중계 미디어**: FastAPI + aiortc를 통한 SFU 방식 중계
- **오디오 캡처**: 서버에서 오디오 프레임 저장 (STT 연동 준비 완료)
- **참가자 관리**: 실시간 입장/퇴장 알림 및 참가자 목록
- **반응형 UI**: Welcome → Join Room → Video Call 플로우

### 🔜 다음 단계

- **Google STT 연동**: 실시간 음성 → 텍스트 변환
- **LangGraph 상담 어시스턴트 에이전트**: 대화 흐름 관리 및 응답 생성

## 기술 스택

### Backend
- **FastAPI**: WebSocket 시그널링 서버
- **aiortc**: Python WebRTC 구현 (미디어 중계)
- **LangGraph**: 상담 에이전트 (예정)
- **Google Cloud Speech**: STT 엔진 (예정)

### Frontend
- **React 18**: UI 프레임워크
- **Vite**: 빌드 도구
- **WebRTC API**: 브라우저 네이티브 API

## 빠른 시작

### 1. 의존성 설치

```bash
# Python 의존성 (backend)
uv sync

# Node.js 의존성 (frontend)
cd frontend
npm install
```

### 2. 서버 실행

**Backend (Terminal 1)**
```bash
cd backend
python app.py
```
→ http://localhost:8000

**Frontend (Terminal 2)**
```bash
cd frontend
npm run dev
```
→ http://localhost:3000

### 3. 테스트

1. **첫 번째 탭**: http://localhost:3000
   - "Connect to Server" 클릭
   - 방 이름: `test-room`, 닉네임: `Alice`
   - "Join Room" → "Start Call"

2. **두 번째 탭**: http://localhost:3000 (새 탭)
   - "Connect to Server" 클릭
   - 방 이름: `test-room`, 닉네임: `Bob`
   - "Join Room" → "Start Call"

3. **결과**: 양쪽에서 서로의 비디오/오디오 확인! 🎥🎤

## 프로젝트 구조

```
realtime-counselor-agent/
├── backend/                    # FastAPI 서버
│   ├── app.py                 # 시그널링 서버
│   ├── room_manager.py        # 방 관리
│   └── peer_manager.py        # WebRTC 연결 관리
│
├── frontend/                   # React 앱
│   ├── src/
│   │   ├── App.jsx           # 메인 컴포넌트
│   │   ├── webrtc.js         # WebRTC 클라이언트
│   │   └── main.jsx
│   └── package.json
│
├── claudedocs/                 # 개발 문서
│   └── room-based-webrtc-implementation.md
│
├── WEBRTC_SETUP.md            # 사용자 가이드
├── pyproject.toml             # Python 의존성
└── README.md                  # 이 파일
```

## 아키텍처

```
┌─────────────┐                      ┌──────────────────┐
│  Client A   │ ◄─── WebSocket ────► │  FastAPI Server  │
│  (Browser)  │    (Signaling)       │  + RoomManager   │
└─────────────┘                      │  + aiortc        │
      │                              └──────────────────┘
      │ WebRTC Media                         ▲
      │ (Same Room Only)                     │
      └──────────────┬──────────────────────┘
                     │
              ┌──────┴──────┐
              │             │
       ┌──────▼────┐ ┌─────▼──────┐
       │ Client B  │ │ Client C   │
       │ Same Room │ │ Same Room  │
       └───────────┘ └────────────┘
```

### 핵심 개념

- **방(Room)**: 같은 방 이름으로 입장한 사용자들끼리만 통화 가능
- **SFU 방식**: 서버가 미디어 스트림을 방별로 중계
- **오디오 캡처**: 서버의 `AudioRelayTrack.audio_frames` 큐에 저장

## 개발 가이드

### 개발 워크플로우

1. **Backend 개발**:
   ```bash
   cd backend
   # 코드 수정
   python app.py  # 자동 재시작은 없음, 수동 재실행
   ```

2. **Frontend 개발**:
   ```bash
   cd frontend
   npm run dev  # Hot reload 자동 지원
   ```

3. **디버깅**:
   - Backend 로그: 터미널 출력 확인
   - Frontend 로그: 브라우저 개발자 도구 콘솔

### API 엔드포인트

**HTTP**:
- `GET /`: 헬스 체크
- `GET /rooms`: 활성 방 목록

**WebSocket** (`/ws`):
- `join_room`: 방 입장
- `offer`: WebRTC offer
- `leave_room`: 방 퇴장
- → `room_joined`, `user_joined`, `user_left`, `answer`

## 트러블슈팅

### 비디오가 안 보일 때
- 방 이름이 **정확히 일치**하는지 확인 (대소문자 구분)
- 각 탭에서 "Start Call" 실행 확인
- 브라우저 콘솔에서 에러 확인

### 카메라/마이크 권한 에러
- 브라우저에서 권한 허용 필요
- HTTPS가 아닌 경우 localhost에서만 작동

### 서버 연결 실패
- Backend 서버가 실행 중인지 확인
- WebSocket URL이 올바른지 확인 (`ws://localhost:8000/ws`)

## 다음 개발 단계

### Phase 1: STT 통합 (우선순위)
```python
# backend/stt_processor.py 구현
- audio_frames 큐에서 프레임 추출
- PCM 변환 (16kHz, mono)
- Google Cloud Speech-to-Text API 호출
- WebSocket으로 텍스트 전송
```

### Phase 2: 상담 에이전트
```python
# LangGraph 기반 상담 흐름
- STT 텍스트 → 에이전트 입력
- 상담 로직 실행
- 에이전트 응답 → TTS
```

## 라이선스

MIT

## 참고 자료

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [aiortc Documentation](https://aiortc.readthedocs.io/)
- [WebRTC API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
- [LangGraph](https://python.langchain.com/docs/langgraph)
- [Google Cloud Speech-to-Text](https://cloud.google.com/speech-to-text)

---
**Version**: 0.1.0 (WebRTC Phase Complete)