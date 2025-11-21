# [2025 KT CS 일경험 사업] 실시간 상담 어시스턴트 AI 에이전트 개발

## Team 바로고치
- 팀장 : 🧑 이찬구
- 팀원 : 🧑 김재홍 🧑 장윤호

## 프로젝트 개요

**Realtime Assist Agent** - LangGraph 기반 실시간 상담 어시스턴트 에이전트

상담사를 위한 WebRTC 기반 오디오/비디오 통화 및 AI 에이전트 시스템으로, Google Cloud STT를 활용하여 실시간 음성 인식 및 대화 분석 기능을 제공합니다.

**현재 상태**: ✅ STT 통합 및 TURN 서버 설정 완료

## 주요 기능

### ✅ 구현 완료

#### WebRTC 통화 시스템
- **방 기반 통화**: 같은 방 이름의 사용자들끼리만 통화
- **SFU 방식 중계**: FastAPI + aiortc를 통한 서버 중계
- **NAT/방화벽 우회**: Metered.ca TURN 서버 통합 (UDP/TCP/TLS)
- **참가자 관리**: 실시간 입장/퇴장 알림 및 참가자 목록
- **반응형 UI**: Welcome → Join Room → Video Call 플로우

#### 실시간 음성 인식 (STT)
- **Google Cloud Speech-to-Text v2 API** 통합
- **실시간 스트리밍 인식**: WebRTC 오디오 → STT → WebSocket 브로드캐스트
- **피어별 독립 처리**: 각 참가자마다 독립적인 STT 인스턴스
- **한국어 최적화**: Chirp 모델 사용으로 높은 인식 정확도
- **자동 구두점 추가**: 자연스러운 텍스트 변환
- **실시간 트랜스크립트 UI**: 채팅 스타일의 발화자별 구분 표시

#### 네트워크 안정성
- **TURN 서버 지원**: NAT/방화벽 환경에서 안정적 연결
- **동적 Credential 관리**: Metered.ca API를 통한 보안 강화
- **ICE Candidate 교환**: Backend ↔ Frontend 양방향 처리
- **모바일 접속 지원**: PC-Mobile 간 연결 안정화

### 🔜 다음 단계

- **LangGraph 상담 어시스턴트 에이전트**: 대화 흐름 관리 및 지능형 응답 생성
- **대화 분석 및 인사이트**: 상담 품질 개선을 위한 AI 분석
- **실시간 상담 가이드**: 상담사를 위한 실시간 정보 제공

## 기술 스택

### Backend
- **FastAPI**: WebSocket 시그널링 서버
- **aiortc**: Python WebRTC 구현 (SFU 미디어 중계)
- **Google Cloud Speech-to-Text v2**: 실시간 음성 인식
- **Python 3.13+**: 비동기 처리 및 타입 힌트
- **UV**: 빠른 의존성 관리

### Frontend
- **React 18**: UI 프레임워크
- **Vite**: 고속 빌드 도구
- **WebRTC API**: 브라우저 네이티브 실시간 통신

### Infrastructure
- **Metered.ca TURN**: NAT/방화벽 우회 서버
- **Google Cloud Platform**: STT API 및 인증

## 빠른 시작

### 1. 환경 설정

#### Google Cloud 설정
1. [Google Cloud Console](https://console.cloud.google.com/)에서 프로젝트 생성
2. Speech-to-Text API 활성화
3. 서비스 계정 생성 및 JSON 키 다운로드
4. JSON 키 파일을 `gcloud-keys/` 폴더에 저장

#### 환경 변수 설정

**Backend** (`backend/.env`):
```bash
cp backend/.env.example backend/.env
```

```env
# Google Cloud Speech-to-Text v2
GOOGLE_APPLICATION_CREDENTIALS=../gcloud-keys/your-service-account-key.json
GOOGLE_CLOUD_PROJECT=your-project-id

# STT Configuration
STT_LANGUAGE_CODE=ko-KR
STT_MODEL=chirp
STT_ENABLE_AUTOMATIC_PUNCTUATION=true

# TURN Server (Metered.ca)
METERED_API_KEY=your-metered-api-key
```

**Frontend** (`frontend/.env`):
```bash
cp frontend/.env.example frontend/.env
```

```env
# API Endpoints
VITE_BACKEND_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

### 2. 의존성 설치

```bash
# Python 의존성 (backend)
uv sync

# Node.js 의존성 (frontend)
cd frontend
npm install
```

### 3. 서버 실행

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

### 4. 테스트

1. **첫 번째 탭**: http://localhost:3000
   - "Connect to Server" 클릭
   - 방 이름: `test-room`, 닉네임: `Alice`
   - "Join Room" → "Start Call"
   - 마이크/카메라 권한 허용

2. **두 번째 탭**: http://localhost:3000 (새 탭)
   - "Connect to Server" 클릭
   - 방 이름: `test-room`, 닉네임: `Bob`
   - "Join Room" → "Start Call"

3. **결과 확인**:
   - ✅ 양쪽에서 비디오/오디오 확인
   - ✅ 발화 시 실시간 트랜스크립트 표시
   - ✅ 대화 내용 자동 저장 (`transcripts/` 폴더)

## 프로젝트 구조

```
realtime-assist-agent/
├── backend/                    # FastAPI 서버
│   ├── app.py                 # 시그널링 서버 + WebSocket
│   ├── room_manager.py        # 방 관리 및 참가자 추적
│   ├── peer_manager.py        # WebRTC 연결 및 미디어 중계
│   ├── stt_service.py         # Google STT v2 스트리밍 서비스
│   └── .env.example           # 환경 변수 템플릿
│
├── frontend/                   # React 앱
│   ├── src/
│   │   ├── App.jsx           # 메인 UI 컴포넌트
│   │   ├── webrtc.js         # WebRTC 클라이언트 로직
│   │   ├── App.css           # 스타일링
│   │   └── main.jsx          # 엔트리 포인트
│   ├── vite.config.js         # Vite 설정 (TURN 프록시)
│   └── .env.example           # 환경 변수 템플릿
│
├── docs/                       # 기술 문서
│   ├── STT_SETUP.md           # STT 설정 가이드
│   ├── WEBRTC_SETUP.md        # WebRTC 설정 가이드
│   ├── WEBRTC_CONNECTION_FLOW.md  # 연결 흐름 상세
│   └── LANGGRAPH_REALTIME_STREAMING.md  # LangGraph 계획
│
├── gcloud-keys/                # Google Cloud 서비스 계정 키
│   └── *.json                 # (gitignore됨)
│
├── transcripts/                # STT 결과 자동 저장
│   └── room_*/                # 방별 대화 기록
│
├── pyproject.toml             # Python 의존성
└── README.md                  # 이 파일
```

## 아키텍처

### 전체 시스템 구성

```
┌─────────────┐                    ┌──────────────────────┐
│  Client A   │ ◄── WebSocket ───► │   FastAPI Server     │
│  (Browser)  │    (Signaling)     │   + RoomManager      │
│             │                    │   + PeerManager      │
└─────────────┘                    │   + STT Service      │
      │                            └──────────────────────┘
      │ WebRTC Media                         ▲
      │ (TURN Relay)                         │
      │                                      │
      └──────────────┬───────────────────────┘
                     │
              ┌──────┴──────┐
              │             │
       ┌──────▼────┐ ┌─────▼──────┐
       │ Client B  │ │ Client C   │
       │ Same Room │ │ Same Room  │
       └───────────┘ └────────────┘
```

### STT 처리 파이프라인

```
WebRTC Audio → AudioRelayTrack → STT Queue
                                      ↓
                              STTService (per peer)
                                      ↓
                        Google Cloud Speech-to-Text v2
                                      ↓
                            Recognized Text
                                      ↓
                          WebSocket Broadcast
                                      ↓
                          Frontend Display
                                      ↓
                        File System (transcripts/)
```

### 핵심 개념

- **방(Room)**: 같은 방 이름으로 입장한 사용자들끼리만 통화 가능
- **SFU 방식**: 서버가 미디어 스트림을 방별로 중계 (Selective Forwarding Unit)
- **피어별 STT**: 각 참가자마다 독립적인 STT 인스턴스로 병렬 처리
- **TURN 중계**: NAT/방화벽 환경에서 TURN 서버를 통한 미디어 전송

## API 엔드포인트

### HTTP
- `GET /`: 헬스 체크
- `GET /rooms`: 활성 방 목록 및 참가자 정보
- `GET /api/turn-credentials`: TURN 서버 동적 credentials

### WebSocket (`/ws`)

**Client → Server:**
- `join_room`: 방 입장 (`{ room_name, nickname }`)
- `offer`: WebRTC offer (`{ sdp, type }`)
- `ice_candidate`: ICE candidate 교환
- `leave_room`: 방 퇴장
- `get_rooms`: 방 목록 요청

**Server → Client:**
- `peer_id`: 서버가 할당한 고유 ID
- `room_joined`: 방 입장 성공 알림
- `user_joined`: 새 사용자 입장 알림
- `user_left`: 사용자 퇴장 알림
- `renegotiation_needed`: 재협상 요청
- `answer`: WebRTC answer (`{ sdp, type }`)
- `ice_candidate`: ICE candidate (backend → frontend)
- `transcript`: STT 인식 결과 (`{ peer_id, nickname, text, timestamp }`)
- `error`: 에러 메시지

## 개발 가이드

### Backend 개발

```bash
cd backend

# 코드 수정 후 재실행 (자동 재시작 없음)
python app.py
```

**주요 모듈:**
- `app.py`: WebSocket 시그널링 및 라우팅
- `peer_manager.py`: WebRTC 연결 및 STT 통합
- `room_manager.py`: 방 및 참가자 관리
- `stt_service.py`: Google STT v2 스트리밍

### Frontend 개발

```bash
cd frontend

# Hot reload 지원
npm run dev

# 프로덕션 빌드
npm run build
```

**주요 파일:**
- `App.jsx`: UI 컴포넌트 및 상태 관리
- `webrtc.js`: WebRTC 클라이언트 로직
- `App.css`: 스타일링 및 애니메이션

### 디버깅

**Backend 로그:**
```bash
# 터미널 출력 확인
# 주요 로그:
# - 🎤 STT 처리 시작
# - 💬 Transcript 인식 결과
# - 🔄 Renegotiation 이벤트
# - ❌ 에러 메시지
```

**Frontend 로그:**
```javascript
// 브라우저 개발자 도구 콘솔
// 주요 로그:
// - WebRTC connection state
// - ICE candidate 교환
// - STT transcript 수신
```

## 트러블슈팅

### 비디오/오디오가 안 보일 때
- ✅ 방 이름이 **정확히 일치**하는지 확인 (대소문자 구분)
- ✅ 각 탭에서 "Start Call" 실행 확인
- ✅ 브라우저 콘솔에서 connection state가 "connected"인지 확인
- ✅ TURN 서버 credentials 확인 (`.env`의 `METERED_API_KEY`)

### STT가 작동하지 않을 때
- ✅ Google Cloud Speech-to-Text API 활성화 확인
- ✅ `GOOGLE_APPLICATION_CREDENTIALS` 경로가 올바른지 확인
- ✅ `GOOGLE_CLOUD_PROJECT` 환경 변수 설정 확인
- ✅ 서비스 계정 키 파일이 존재하는지 확인
- ✅ 마이크 권한이 허용되어 있는지 확인

### 모바일 연결 실패
- ✅ PC와 모바일이 **같은 Wi-Fi 네트워크**에 있는지 확인
- ✅ Frontend: `npm run dev -- --host 0.0.0.0`로 실행
- ✅ Backend: `app.py`에서 이미 `0.0.0.0`으로 설정됨
- ✅ PC IP 주소 확인 후 모바일에서 `http://<PC_IP>:3000` 접속

### ICE 연결 실패
- ✅ TURN 서버 설정 확인 (Metered.ca credentials)
- ✅ 방화벽에서 UDP/TCP 포트 허용
- ✅ 브라우저 콘솔에서 ICE candidate 교환 로그 확인

## 보안 및 권장사항

### 보안
- 🔐 서비스 계정 키는 **절대 Git에 커밋하지 말 것** (`.gitignore`에 추가됨)
- 🔐 프로덕션 환경에서는 Secret Manager 사용 권장
- 🔐 `.env` 파일은 Git에 커밋하지 말고, `.env.example`만 공유

### 비용 관리
- 💰 Google STT: 매월 처음 60분 무료, 이후 분당 $0.006
- 💰 Metered.ca TURN: 무료 티어 50GB/월 제공
- 💰 자세한 내용: [Google STT 요금](https://cloud.google.com/speech-to-text/pricing)

## 문서

상세한 설정 및 구현 가이드는 `docs/` 디렉토리를 참고하세요:

- **[STT_SETUP.md](docs/STT_SETUP.md)**: Google Speech-to-Text v2 설정 가이드
- **[WEBRTC_SETUP.md](docs/WEBRTC_SETUP.md)**: WebRTC 연결 설정 및 테스트
- **[WEBRTC_CONNECTION_FLOW.md](docs/WEBRTC_CONNECTION_FLOW.md)**: 연결 흐름 상세 설명
- **[LANGGRAPH_REALTIME_STREAMING.md](docs/LANGGRAPH_REALTIME_STREAMING.md)**: LangGraph 통합 계획

## 다음 개발 단계

### Phase 1: LangGraph 상담 에이전트 (진행 중)
- [ ] LangGraph StateGraph 기반 대화 흐름 설계
- [ ] STT 텍스트 → 에이전트 입력 파이프라인
- [ ] 상담 시나리오별 응답 로직 구현
- [ ] 에이전트 응답 → WebSocket 전송

### Phase 2: 고급 기능
- [ ] 대화 분석 및 감정 인식
- [ ] 상담 품질 평가 및 인사이트
- [ ] 실시간 상담 가이드 및 추천
- [ ] TTS(Text-to-Speech) 통합

## 참고 자료

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [aiortc Documentation](https://aiortc.readthedocs.io/)
- [WebRTC API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API)
- [Google Cloud Speech-to-Text v2](https://cloud.google.com/speech-to-text/v2/docs)
- [LangGraph](https://python.langchain.com/docs/langgraph)
- [Metered.ca TURN Server](https://www.metered.ca/tools/openrelay/)

## 라이선스

MIT

---

**Version**: 0.2.0 (STT Integration Complete)
