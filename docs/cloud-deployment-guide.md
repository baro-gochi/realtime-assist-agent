# 클라우드 환경 배포 가이드: HTTPS + WebRTC 지원

> GitHub Pages + AWS 백엔드 환경에서 HTTPS를 지원하면서 WebRTC로 접속 가능하게 배포하기 위한 종합 가이드

## 현재 아키텍처 요약

현재 시스템은 다음 구성 요소로 이루어져 있습니다:

| 구성 요소 | 기술 스택 | 포트 |
|-----------|----------|------|
| **Frontend** | React + Vite | 3000 |
| **Backend** | FastAPI + aiortc (SFU) | 8000 |
| **TURN/STUN** | AWS coturn | 3478 (UDP/TCP) |
| **STT** | Google Cloud Speech-to-Text v2 | - |
| **LLM** | OpenAI GPT | - |

---

## 클라우드 배포 아키텍처

```
                    ┌─────────────────────────────────────────┐
                    │            GitHub Pages                  │
                    │     (HTTPS 자동 지원, React Static)      │
                    │  https://username.github.io/repo-name   │
                    └───────────────┬─────────────────────────┘
                                    │
                                    │ API 호출 (Cross-Origin)
                                    │
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │          AWS Backend (EC2/ECS)          │
                    │     ALB + HTTPS (ACM 인증서)            │
                    │      https://api.your-domain.com        │
                    │  - FastAPI (REST API + WebSocket)       │
                    └───────────────┬─────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │          EC2 (coturn)                    │
                    │      turn:IP:3478 (TLS)                  │
                    │   TURN/STUN with Let's Encrypt          │
                    └─────────────────────────────────────────┘
```

### GitHub Pages 장점
- **무료 HTTPS**: SSL 인증서 자동 제공
- **간단한 배포**: `git push`만으로 배포 완료
- **CDN 제공**: 글로벌 CDN으로 빠른 로딩
- **CI/CD 통합**: GitHub Actions와 쉬운 연동

### 주의사항
- **Cross-Origin 통신**: 백엔드와 도메인이 다르므로 CORS 설정 필수
- **URL 하드코딩**: 백엔드 URL을 프론트엔드에 명시적으로 설정
- **Mixed Content 방지**: 백엔드도 반드시 HTTPS 사용

---

## 1. React 프론트엔드: GitHub Pages 배포

### Step 1: gh-pages 패키지 설치

```bash
cd frontend
npm install --save-dev gh-pages
```

### Step 2: package.json 수정

```json
{
  "name": "realtime-assist-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "homepage": "https://username.github.io/realtime-assist-agent",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "predeploy": "npm run build",
    "deploy": "gh-pages -d dist"
  }
}
```

> **중요**: `homepage` 필드에 실제 GitHub 사용자명과 저장소 이름을 입력하세요.

### Step 3: vite.config.js 수정

```javascript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // GitHub Pages 서브경로 설정
  base: '/realtime-assist-agent/',
  server: {
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  }
})
```

### Step 4: 환경 변수 설정

```bash
# frontend/.env.production
VITE_API_URL=https://api.your-domain.com
VITE_WS_URL=wss://api.your-domain.com/ws
```

### Step 5: 배포 실행

```bash
# 빌드 + GitHub Pages 배포
npm run deploy
```

배포 후 접속 URL: `https://username.github.io/realtime-assist-agent`

### Step 6: GitHub 저장소 설정

1. GitHub 저장소 → Settings → Pages
2. Source: `gh-pages` 브랜치 선택
3. 저장 후 몇 분 내에 배포 완료

---

## 2. FastAPI 백엔드: HTTPS 지원 배포

### 옵션 A: EC2 + ALB (Application Load Balancer)

```yaml
# ALB 리스너 설정
Listeners:
  - Port: 443
    Protocol: HTTPS
    Certificates:
      - CertificateArn: arn:aws:acm:ap-northeast-2:xxx:certificate/xxx
    DefaultActions:
      - Type: forward
        TargetGroupArn: !Ref BackendTargetGroup

  # WebSocket sticky sessions 필수!
  - Port: 443
    Protocol: HTTPS
    Rules:
      - Conditions:
          - PathPattern: /ws*
        Actions:
          - Type: forward
            TargetGroupArn: !Ref WebSocketTargetGroup
            # Sticky session 활성화 (WebSocket 연결 유지)
            StickinessConfig:
              Enabled: true
              DurationSeconds: 86400
```

### 옵션 B: ECS Fargate + ALB

```dockerfile
# Dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY backend/ .
RUN pip install uv && uv sync

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 옵션 C: EC2 + Nginx + Let's Encrypt (간단한 설정)

```nginx
# /etc/nginx/sites-available/api
server {
    listen 443 ssl;
    server_name api.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/api.your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;  # WebSocket용 긴 타임아웃
    }
}
```

```bash
# Let's Encrypt 인증서 발급
sudo certbot --nginx -d api.your-domain.com
```

---

## 3. coturn TURN/STUN 서버: TLS 지원 (필수!)

### 현재 coturn 설정 업데이트

```bash
# /etc/turnserver.conf
# 기존 설정 유지...
listening-ip=0.0.0.0
listening-port=3478
relay-ip=10.0.7.16  # Private IP
external-ip=13.209.180.128  # Public IP

# TLS 설정 추가 (HTTPS 필수)
tls-listening-port=5349
cert=/etc/letsencrypt/live/turn.your-domain.com/fullchain.pem
pkey=/etc/letsencrypt/live/turn.your-domain.com/privkey.pem

# Static credentials
user=username1:password1
realm=your-domain.com
```

### Let's Encrypt 인증서 발급

```bash
# certbot 설치
sudo apt install certbot

# DNS 또는 HTTP 챌린지로 인증서 발급
sudo certbot certonly --standalone -d turn.your-domain.com

# 자동 갱신 설정
sudo systemctl enable certbot.timer
```

### Security Group 업데이트

```
Inbound Rules:
- 3478/TCP (STUN/TURN)
- 3478/UDP (STUN/TURN)
- 5349/TCP (TURN over TLS) ← 추가!
- 49152-65535/UDP (RTP relay)
```

---

## 4. 환경 변수 및 코드 수정

### Backend `.env` (프로덕션)

```bash
# backend/.env.production
GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp-key.json
GOOGLE_CLOUD_PROJECT=your-project-id

# TURN/STUN - TLS 사용
TURN_SERVER_URL=turns:turn.your-domain.com:5349
TURN_USERNAME=username1
TURN_CREDENTIAL=password1
STUN_SERVER_URL=stun:turn.your-domain.com:3478

# API Keys
OPENAI_API_KEY=sk-xxx
ELEVENLABS_API_KEY=xxx

# CORS 허용 오리진 (GitHub Pages)
ALLOWED_ORIGINS=https://username.github.io
```

### Frontend 코드 수정 (`webrtc.js:113`)

GitHub Pages는 다른 도메인이므로 URL을 명시적으로 설정해야 합니다:

```javascript
// 수정 전
constructor(signalingUrl = 'ws://localhost:8000/ws') {

// 수정 후 - 환경 변수 기반
constructor(signalingUrl = null) {
  if (!signalingUrl) {
    if (import.meta.env.PROD) {
      // 프로덕션: 환경 변수 또는 하드코딩된 URL 사용
      signalingUrl = import.meta.env.VITE_WS_URL || 'wss://api.your-domain.com/ws';
    } else {
      // 개발: Vite 프록시 사용
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      signalingUrl = `${protocol}//${window.location.host}/ws`;
    }
  }
```

### API URL도 수정 필요 (`webrtc.js` 내 fetch 호출)

```javascript
// TURN 크레덴셜 fetch 예시
const getApiBaseUrl = () => {
  if (import.meta.env.PROD) {
    return import.meta.env.VITE_API_URL || 'https://api.your-domain.com';
  }
  return '';  // 개발 환경에서는 프록시 사용
};

// 사용 예
const response = await fetch(`${getApiBaseUrl()}/api/turn-credentials`);
```

### Frontend 환경 변수 파일

```bash
# frontend/.env.development
VITE_API_URL=
VITE_WS_URL=

# frontend/.env.production
VITE_API_URL=https://api.your-domain.com
VITE_WS_URL=wss://api.your-domain.com/ws
```

---

## 5. CORS 설정 업데이트 (`app.py:108-120`)

```python
# app.py 수정
import os

# 환경 변수에서 읽거나 기본값 사용
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
origins = [
    "http://localhost:3000",  # 개발 환경
]

# 프로덕션 오리진 추가
if allowed_origins_env:
    origins.extend(allowed_origins_env.split(","))
else:
    # 기본 GitHub Pages 오리진
    origins.extend([
        "https://username.github.io",  # GitHub Pages
    ])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 6. WebRTC ICE 설정 확인

### HTTPS 환경에서 WebRTC 요구사항

| 요구사항 | 상태 | 비고 |
|----------|------|------|
| HTTPS 오리진 | ✅ 충족 | GitHub Pages 자동 HTTPS |
| WSS (WebSocket Secure) | 필수 | 백엔드 HTTPS 필수 |
| TURNS (TURN over TLS) | 권장 | 방화벽 통과율 향상 |
| STUN | 유지 | 기존 설정 유지 가능 |

### Frontend ICE 서버 설정 (`webrtc.js:529-548`)

현재 잘 구성되어 있습니다. TURN 크레덴셜은 `/api/turn-credentials`에서 동적 획득.

---

## 배포 체크리스트

### Phase 1: 인프라 준비
- [ ] GitHub 저장소 생성 또는 확인
- [ ] ALB 생성 및 HTTPS 리스너 설정 (ACM 인증서)
- [ ] Route 53 DNS 레코드 설정 (`api.your-domain.com`)
- [ ] EC2 Security Group 설정

### Phase 2: 보안 설정
- [ ] ACM 인증서 발급 (ALB용, ap-northeast-2 리전)
- [ ] Let's Encrypt 인증서 발급 (coturn TLS용)
- [ ] Security Group 업데이트 (5349/TCP 추가)

### Phase 3: 백엔드 배포
- [ ] Backend 환경 변수 설정 (.env.production)
- [ ] Backend Docker 이미지 빌드 (또는 EC2 직접 배포)
- [ ] CORS 설정에 GitHub Pages 도메인 추가
- [ ] WebSocket 연결 테스트

### Phase 4: 프론트엔드 배포
- [ ] `gh-pages` 패키지 설치
- [ ] `vite.config.js`에 base path 설정
- [ ] `.env.production`에 백엔드 URL 설정
- [ ] `npm run deploy` 실행
- [ ] GitHub Pages 설정 확인 (gh-pages 브랜치)

### Phase 5: coturn 업데이트
- [ ] TLS 인증서 설정
- [ ] turnserver.conf 수정
- [ ] coturn 서비스 재시작
- [ ] 연결 테스트

### Phase 6: 통합 테스트
- [ ] GitHub Pages URL로 접속 확인
- [ ] WebSocket (WSS) 연결 확인
- [ ] WebRTC ICE 연결 확인 (chrome://webrtc-internals)
- [ ] TURN relay 연결 확인
- [ ] STT 기능 테스트
- [ ] 모바일 브라우저 테스트

---

## 트러블슈팅

### "getUserMedia() requires HTTPS" 오류
- GitHub Pages는 자동으로 HTTPS를 제공하므로 이 문제는 발생하지 않습니다
- 단, 백엔드도 HTTPS여야 Mixed Content 오류가 발생하지 않습니다

### WebSocket 연결 실패
- 백엔드 URL이 `wss://`로 시작하는지 확인
- CORS 설정에 GitHub Pages 도메인이 포함되어 있는지 확인
- ALB의 idle timeout을 4000초로 늘리기 (WebSocket용)

### Mixed Content 오류
- GitHub Pages (HTTPS)에서 HTTP 백엔드로 연결 시 발생
- **해결**: 백엔드를 반드시 HTTPS로 배포

### ICE Connection Failed
- coturn TLS 설정 확인
- Security Group에 5349/TCP 허용 확인
- `chrome://webrtc-internals`에서 candidate 확인

### CORS 오류
- `app.py`의 `allow_origins`에 `https://username.github.io` 추가
- Preflight 요청 (OPTIONS) 허용 확인

### 404 오류 (GitHub Pages SPA 라우팅)
React Router 사용 시 직접 URL 접근하면 404 발생. 해결책:

```bash
# 빌드 후 404.html 복사
cp dist/index.html dist/404.html
```

또는 `package.json`의 deploy 스크립트 수정:

```json
"deploy": "gh-pages -d dist && cp dist/index.html dist/404.html"
```

---

## GitHub Actions 자동 배포 (선택사항)

`.github/workflows/deploy.yml` 생성:

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'frontend/**'

jobs:
  deploy:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend

    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Install dependencies
        run: npm ci

      - name: Build
        run: npm run build
        env:
          VITE_API_URL: ${{ secrets.VITE_API_URL }}
          VITE_WS_URL: ${{ secrets.VITE_WS_URL }}

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./frontend/dist
```

GitHub 저장소 Settings → Secrets에 환경 변수 추가:
- `VITE_API_URL`: `https://api.your-domain.com`
- `VITE_WS_URL`: `wss://api.your-domain.com/ws`

---

## 핵심 요약

### Q: React는 GitHub Pages에 올려도 되나요?
**예.** GitHub Pages는 정적 파일 호스팅에 최적화되어 있고, HTTPS를 무료로 자동 제공합니다.

**단, 주의점:**
- 백엔드 URL을 **명시적으로 설정**해야 합니다 (환경 변수 사용)
- 백엔드도 **반드시 HTTPS**여야 합니다 (Mixed Content 방지)
- **CORS 설정**에 GitHub Pages 도메인을 추가해야 합니다

### Q: coturn 서버 설정은?
현재 AWS coturn (13.209.180.128:3478) 사용 중입니다.

**HTTPS 환경에서 필요한 추가 설정:**
- **TLS 인증서 추가** (Let's Encrypt 권장)
- **turns:5349** 포트 활성화 (TURN over TLS)
- Security Group에 5349/TCP 추가

### 코드 수정 필요 사항

| 파일 | 수정 내용 |
|------|----------|
| `webrtc.js:113` | WebSocket URL을 환경 변수 기반으로 변경 |
| `webrtc.js` (fetch) | API URL을 환경 변수 기반으로 변경 |
| `app.py:108-120` | CORS 허용 오리진에 GitHub Pages 도메인 추가 |
| `backend/.env` | TURN URL을 `turns:` 스키마로 변경 |
| `vite.config.js` | base path를 저장소 이름으로 설정 |
| `package.json` | homepage, deploy 스크립트 추가 |
| `.env.production` | 백엔드 API/WS URL 설정 |
