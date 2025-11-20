# Google Speech-to-Text v2 연동 가이드

Google Speech-to-Text API v2를 사용하여 실시간 음성 인식 기능이 구현되었습니다.

## 🎯 구현 완료 내용

### Backend (Python)
1. **STT 서비스 모듈** (`backend/stt_service.py`)
   - Google Cloud Speech-to-Text API v2 통합
   - Recognizer 기반 스트리밍 인식
   - 실시간 스트리밍 인식 지원
   - 한국어 음성 인식 최적화 (chirp 모델)
   - 자동 구두점 추가
   - AutoDetectDecodingConfig로 자동 오디오 포맷 감지

2. **오디오 프레임 처리** (`backend/peer_manager.py`)
   - WebRTC 오디오 트랙 캡처
   - STT 서비스로 오디오 스트림 전송
   - 비동기 처리로 높은 처리량 보장

3. **WebSocket 통신** (`backend/app.py`)
   - STT 인식 결과를 WebSocket을 통해 클라이언트로 브로드캐스트
   - 룸 내 모든 참가자에게 실시간 전송

### Frontend (React)
1. **WebRTC 클라이언트** (`frontend/src/webrtc.js`)
   - `onTranscript` 콜백 추가
   - transcript 메시지 타입 처리

2. **UI 컴포넌트** (`frontend/src/App.jsx`)
   - 실시간 트랜스크립트 표시 영역
   - 자동 스크롤 기능
   - 발화자별 구분 표시 (본인/상대방)
   - 타임스탬프 표시

3. **스타일링** (`frontend/src/App.css`)
   - 채팅 스타일의 트랜스크립트 UI
   - 애니메이션 효과
   - 반응형 디자인

## 📋 설정 방법

### 1. Google Cloud 프로젝트 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. "API 및 서비스" → "라이브러리"에서 "Cloud Speech-to-Text API" 검색 및 활성화
4. "사용자 인증 정보" → "사용자 인증 정보 만들기" → "서비스 계정" 선택
5. 서비스 계정 생성 후 "키 추가" → "새 키 만들기" → JSON 선택
6. 다운로드한 JSON 파일을 프로젝트 디렉토리에 저장

### 2. 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```bash
cp .env.example .env
```

`.env` 파일 수정:

```env
# Google Cloud Speech-to-Text API v2 인증
GOOGLE_APPLICATION_CREDENTIALS=path/to/your-service-account-key.json

# Google Cloud 프로젝트 ID (v2 API 필수)
GOOGLE_CLOUD_PROJECT=your-project-id

# STT v2 설정
STT_LANGUAGE_CODE=ko-KR
STT_SAMPLE_RATE_HERTZ=48000
STT_MODEL=chirp
STT_ENABLE_AUTOMATIC_PUNCTUATION=true
STT_ENABLE_INTERIM_RESULTS=false
```

⚠️ **중요**: `GOOGLE_APPLICATION_CREDENTIALS`에는 다운로드한 JSON 파일의 **절대 경로**를 입력하세요.

**Windows 예시**:
```env
GOOGLE_APPLICATION_CREDENTIALS=C:/Users/yourname/Desktop/study/KT_CS/realtime-assist-agent/service-account-key.json
```

**Linux/Mac 예시**:
```env
GOOGLE_APPLICATION_CREDENTIALS=/home/yourname/projects/realtime-assist-agent/service-account-key.json
```

### 3. 의존성 설치

필요한 패키지는 이미 `pyproject.toml`에 추가되어 있습니다:

```bash
uv sync
```

## 🚀 실행 방법

### Backend 서버 시작

```bash
cd backend
python app.py
```

또는

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

### Frontend 개발 서버 시작

```bash
cd frontend
npm run dev
```

## ✅ 작동 확인

1. 브라우저에서 `http://localhost:3000` 접속
2. "Connect to Server" 클릭
3. 룸 이름과 닉네임 입력 후 "Join Room" 클릭
4. "Start Call" 클릭하여 마이크/카메라 권한 허용
5. 말을 하면 화면 하단의 "💬 Real-time Transcripts" 영역에 인식된 텍스트가 표시됨

## 🆕 v2 API 주요 변경사항

### v1에서 v2로의 주요 변경점

1. **Recognizer 개념 도입**
   - v2에서는 프로젝트 ID와 Recognizer 경로가 필수
   - 기본 Recognizer: `projects/{PROJECT_ID}/locations/global/recognizers/_`

2. **Language Codes가 리스트로 변경**
   - v1: `language_code="ko-KR"` (단일 문자열)
   - v2: `language_codes=["ko-KR"]` (리스트)

3. **Chirp 모델 지원**
   - v2의 고급 음성 인식 모델
   - 더 정확한 한국어 인식 성능
   - 자동 언어 감지 및 다국어 지원

4. **AutoDetectDecodingConfig**
   - 오디오 인코딩 자동 감지
   - 별도의 encoding 파라미터 불필요

5. **25KB 스트림 제한**
   - 각 오디오 청크는 25KB 이하여야 함
   - 자동 분할 처리 구현됨

6. **환경 변수 추가**
   - `GOOGLE_CLOUD_PROJECT`: 프로젝트 ID (필수)
   - `STT_MODEL`: 사용할 모델 선택 (chirp, latest_long 등)
   - `STT_ENABLE_INTERIM_RESULTS`: 중간 결과 활성화 여부

## 🔧 문제 해결

### 1. "GOOGLE_APPLICATION_CREDENTIALS not set" 경고
- `.env` 파일이 프로젝트 루트에 있는지 확인
- 환경 변수 경로가 올바른지 확인 (절대 경로 사용 권장)
- 서버 재시작

### 2. "GOOGLE_CLOUD_PROJECT environment variable must be set" 에러 (v2 전용)
- `.env` 파일에 `GOOGLE_CLOUD_PROJECT=프로젝트ID` 추가
- Google Cloud Console에서 프로젝트 ID 확인 (프로젝트 이름이 아님!)
- 서버 재시작

### 3. STT 결과가 표시되지 않음
- Google Cloud Console에서 Speech-to-Text API가 활성화되어 있는지 확인
- 서비스 계정 JSON 파일이 올바른 위치에 있는지 확인
- 브라우저 콘솔에서 에러 메시지 확인
- 마이크 권한이 허용되어 있는지 확인

### 4. 인식 정확도가 낮음
- `.env` 파일에서 `STT_LANGUAGE_CODE`가 `ko-KR`로 설정되어 있는지 확인
- `STT_MODEL`을 `chirp`로 설정 (v2 고급 모델)
- 마이크 음질이 좋은지 확인
- 주변 소음이 적은 환경에서 테스트

### 5. 오디오 샘플링 레이트 관련
- v2 API는 `AutoDetectDecodingConfig`를 사용하여 자동 감지
- WebRTC는 기본적으로 48kHz 사용
- 별도 설정 불필요하지만, 문제 발생 시 `.env`에서 `STT_SAMPLE_RATE_HERTZ` 조정 가능

## 📊 STT 결과 데이터 구조

WebSocket을 통해 전송되는 transcript 메시지 형식:

```json
{
  "type": "transcript",
  "data": {
    "peer_id": "abc-123-def-456",
    "nickname": "상담사",
    "text": "안녕하세요 무엇을 도와드릴까요",
    "timestamp": 1704067200000
  }
}
```

## 🎨 UI 커스터마이징

트랜스크립트 UI 스타일은 `frontend/src/App.css`의 다음 섹션에서 수정 가능:

- `.transcript-section`: 전체 트랜스크립트 영역
- `.transcript-container`: 스크롤 가능한 컨테이너
- `.transcript-item.own`: 본인 발화 (보라색 그라데이션)
- `.transcript-item.other`: 상대방 발화 (흰색 배경)
- `.transcript-text`: 인식된 텍스트 스타일

## 💰 비용 고려사항

Google Cloud Speech-to-Text API는 사용량에 따라 과금됩니다:
- 매월 처음 60분은 무료
- 이후 분당 $0.006 (스트리밍 인식)

자세한 내용: [Google Cloud Speech-to-Text 요금](https://cloud.google.com/speech-to-text/pricing)

## 🔐 보안 권장사항

1. **서비스 계정 키 보호**
   - `.gitignore`에 `*.json` 추가하여 키 파일이 Git에 커밋되지 않도록 설정
   - 프로덕션 환경에서는 Secret Manager 사용 권장

2. **환경 변수 관리**
   - `.env` 파일은 Git에 커밋하지 말 것
   - `.env.example`은 커밋하여 팀원들이 참고할 수 있도록 함

3. **API 키 권한 제한**
   - 서비스 계정에 최소 권한만 부여 (Speech-to-Text API만)
   - 프로젝트별로 별도의 서비스 계정 사용 권장

## 📚 참고 자료

- [Google Cloud Speech-to-Text v2 문서](https://cloud.google.com/speech-to-text/v2/docs)
- [Python 클라이언트 라이브러리 v2](https://cloud.google.com/python/docs/reference/speech/latest)
- [스트리밍 인식 가이드 v2](https://cloud.google.com/speech-to-text/v2/docs/streaming-recognize)
- [Chirp 모델 소개](https://cloud.google.com/speech-to-text/v2/docs/chirp-model)
