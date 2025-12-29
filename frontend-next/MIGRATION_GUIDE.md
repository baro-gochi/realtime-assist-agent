# Next.js + TailwindCSS Migration Guide

> Vite + React 프로젝트에서 Next.js 16.1 + TailwindCSS 4로 마이그레이션한 과정 문서

## 1. 프로젝트 개요

### 기존 프로젝트 (frontend)
| 항목 | 값 |
|------|-----|
| Build Tool | Vite 6.0.5 |
| Framework | React 18.3.1 |
| Routing | react-router-dom 7.9.6 |
| Styling | Plain CSS (CSS Variables) |
| Language | JavaScript (JSX) |

### 새 프로젝트 (frontend-next)
| 항목 | 값 |
|------|-----|
| Framework | Next.js 16.1.0 |
| React | React 19.2.3 |
| Routing | App Router (file-based) |
| Styling | TailwindCSS 4 + CSS Variables |
| Language | TypeScript |

---

## 2. 설치 과정

### 2.1 Next.js 프로젝트 생성
```bash
npx create-next-app@latest frontend-next \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --src-dir \
  --import-alias "@/*" \
  --use-npm
```

### 2.2 생성된 패키지
```json
{
  "dependencies": {
    "next": "16.1.0",
    "react": "19.2.3",
    "react-dom": "19.2.3"
  },
  "devDependencies": {
    "@tailwindcss/postcss": "^4",
    "tailwindcss": "^4",
    "typescript": "^5",
    "eslint": "^9",
    "eslint-config-next": "16.1.0"
  }
}
```

---

## 3. 주요 설정 변경

### 3.1 Backend Proxy (next.config.ts)

**Vite (기존)**:
```js
// vite.config.js
proxy: {
  '/ws': { target: 'http://localhost:8000', ws: true },
  '/api': { target: 'http://localhost:8000' }
}
```

**Next.js (신규)**:
```ts
// next.config.ts
async rewrites() {
  const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  return [
    { source: "/ws/:path*", destination: `${backendUrl}/ws/:path*` },
    { source: "/api/:path*", destination: `${backendUrl}/api/:path*` },
  ];
}
```

### 3.2 환경변수 변경

| Vite | Next.js |
|------|---------|
| `import.meta.env.VITE_API_URL` | `process.env.NEXT_PUBLIC_API_URL` |
| `.env` 파일에서 `VITE_` prefix | `NEXT_PUBLIC_` prefix |

### 3.3 TailwindCSS 4 설정

**globals.css 구조**:
```css
@import "tailwindcss";

/* CSS Variables for theming */
:root, [data-theme="light"] {
  --bg-primary: #f5f5f5;
  --text-primary: #2c2c2c;
  /* ... */
}

[data-theme="dark"] {
  --bg-primary: #121212;
  --text-primary: #f5f5f5;
  /* ... */
}

/* Tailwind CSS 4 Theme Integration */
@theme inline {
  --color-bg-primary: var(--bg-primary);
  --color-text-primary: var(--text-primary);
  /* ... */
}
```

---

## 4. 라우팅 구조 변환

### 4.1 react-router-dom vs App Router

**기존 (react-router-dom)**:
```jsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<AssistantMain />} />
    <Route path="/agent/register" element={<AgentRegister />} />
    <Route path="/agent/history" element={<AgentHistory />} />
  </Routes>
</BrowserRouter>
```

**신규 (App Router)**:
```
src/app/
├── page.tsx                    # /
├── assistant/
│   └── page.tsx               # /assistant
├── agent/
│   ├── register/
│   │   └── page.tsx           # /agent/register
│   └── history/
│       └── page.tsx           # /agent/history
└── layout.tsx                 # Root layout
```

---

## 5. 컴포넌트 구조

### 5.1 생성된 컴포넌트

```
src/components/
├── Providers.tsx         # Client-side providers wrapper
├── ThemeProvider.tsx     # Dark/Light mode context
├── ThemeToggle.tsx       # Theme toggle button
├── AuthGuard.tsx         # 인증 가드 컴포넌트
└── assistant/            # 상담 대시보드 컴포넌트
    ├── index.ts              # 컴포넌트 exports
    ├── AssistantMain.tsx     # 메인 조합 컴포넌트
    ├── RoleSelection.tsx     # 상담사/고객 역할 선택
    ├── ConnectionPanel.tsx   # WebRTC 연결 및 룸 관리
    ├── TranscriptPanel.tsx   # 실시간 대화 표시
    └── InsightPanel.tsx      # AI 인사이트 패널
```

### 5.2 React Hooks

```
src/hooks/
├── index.ts              # Hooks exports
├── useWebRTCClient.ts    # WebRTC 클라이언트 상태 관리
└── useCallTimer.ts       # 통화 시간 타이머
```

### 5.3 공유 라이브러리

```
src/lib/
├── types.ts              # 공유 TypeScript 타입 정의
└── webrtc-client.ts      # WebRTC 클라이언트 클래스
```

### 5.4 Server vs Client Components

| 컴포넌트 | 타입 | 이유 |
|----------|------|------|
| `layout.tsx` | Server | 정적 HTML 구조 |
| `page.tsx` (home) | Server | 정적 콘텐츠 |
| `Providers.tsx` | Client | Context 사용 |
| `ThemeProvider.tsx` | Client | useState, useEffect |
| `ThemeToggle.tsx` | Client | Context 사용 |
| `AuthGuard.tsx` | Client | localStorage, useEffect |
| `assistant/page.tsx` | Client | WebRTC, 상태 관리 |
| `AssistantMain.tsx` | Client | WebRTC hooks, 상태 관리 |
| `RoleSelection.tsx` | Client | onClick 이벤트 |
| `ConnectionPanel.tsx` | Client | async 이벤트 핸들러 |
| `TranscriptPanel.tsx` | Client | useState, 스크롤 관리 |
| `InsightPanel.tsx` | Client | useState, 동적 UI |

### 5.5 'use client' 사용 규칙

```tsx
// 파일 최상단에 선언
"use client";

// 다음 경우에 필요:
// - useState, useEffect 등 React hooks 사용
// - Context API 사용
// - 브라우저 전용 API (window, document)
// - WebRTC, Audio 등 클라이언트 전용 기능
```

---

## 6. TailwindCSS 사용법

### 6.1 유틸리티 클래스 예시

```tsx
// 기존 CSS
<div className="password-card">

// TailwindCSS
<div className="rounded-xl border border-border-primary bg-bg-card p-8 shadow-lg">
```

### 6.2 커스텀 색상 사용

```tsx
// CSS 변수 기반 색상 (globals.css에서 정의)
<div className="bg-bg-primary text-text-primary">
<button className="bg-primary hover:bg-primary-hover">
<p className="text-accent-blue">
```

### 6.3 반응형 디자인

```tsx
// 모바일 우선 접근법
<div className="flex flex-col md:flex-row">
<div className="w-full md:w-1/2 lg:w-1/3">
```

---

## 7. 개발 서버 실행

```bash
# 개발 서버 시작
cd frontend-next
npm run dev

# 프로덕션 빌드
npm run build

# 프로덕션 서버 시작
npm start
```

**기본 포트**: http://localhost:3000

---

## 8. 남은 마이그레이션 작업

### 8.1 우선순위 높음
- [x] WebRTC 클라이언트 통합 (`webrtc.js` → `lib/webrtc-client.ts`) - 완료
- [x] 인증 시스템 마이그레이션 (PasswordScreen → AuthGuard) - 완료
- [x] AssistantMain 핵심 기능 이전 - 완료
  - RoleSelection.tsx: 역할 선택 UI
  - ConnectionPanel.tsx: WebRTC 연결 및 룸 관리
  - TranscriptPanel.tsx: 실시간 대화 표시
  - InsightPanel.tsx: AI 인사이트 (요약, 감정, 응답 초안)
  - AssistantMain.tsx: 메인 조합 컴포넌트

### 8.2 우선순위 중간
- [ ] 상담 이력 API 연동 (AgentHistory)
- [ ] 상담사 등록 API 연동 (AgentRegister)
- [ ] STT 스트리밍 통합

### 8.3 우선순위 낮음
- [ ] 기존 CSS 완전 제거
- [ ] 테스트 코드 작성
- [ ] 성능 최적화

---

## 9. Next.js 16.1 주요 기능

### 9.1 Turbopack (기본 활성화)
- 개발 서버 재시작 최대 14배 빠름
- 파일 시스템 캐싱으로 HMR 개선

### 9.2 디버깅
```bash
# Node.js 디버거 연결
npm run dev -- --inspect
```

### 9.3 Bundle Analyzer
```bash
# 번들 크기 분석
npx next experimental-analyze
```

---

## 10. 보안 고려사항

### 10.1 최신 패치 적용
Next.js 16.1.0은 CVE-2025-55184, CVE-2025-55183 패치가 적용된 버전입니다.

### 10.2 환경변수 보안
- `NEXT_PUBLIC_` prefix가 있는 변수만 클라이언트에 노출
- 민감한 정보는 서버 전용 환경변수로 관리

---

## 11. 참고 자료

- [Next.js Documentation](https://nextjs.org/docs)
- [TailwindCSS v4 Documentation](https://tailwindcss.com/docs)
- [Next.js 16.1 Release Notes](https://nextjs.org/blog/next-16-1)
- [Security Update 2025-12-11](https://nextjs.org/blog/security-update-2025-12-11)

---

## 12. 파일 구조 요약

```
frontend-next/
├── src/
│   ├── app/
│   │   ├── globals.css          # TailwindCSS + Theme Variables
│   │   ├── layout.tsx           # Root Layout (Server Component)
│   │   ├── page.tsx             # Home Page
│   │   ├── login/
│   │   │   └── page.tsx         # Login Page
│   │   ├── assistant/
│   │   │   └── page.tsx         # Consultation Dashboard
│   │   └── agent/
│   │       ├── register/
│   │       │   └── page.tsx     # Agent Registration
│   │       └── history/
│   │           └── page.tsx     # Consultation History
│   │
│   ├── components/
│   │   ├── Providers.tsx        # Client Providers Wrapper
│   │   ├── ThemeProvider.tsx    # Theme Context
│   │   ├── ThemeToggle.tsx      # Theme Toggle Button
│   │   ├── AuthGuard.tsx        # Authentication Guard
│   │   └── assistant/           # Consultation Dashboard Components
│   │       ├── index.ts             # Component exports
│   │       ├── AssistantMain.tsx    # Main composition component
│   │       ├── RoleSelection.tsx    # Role selection UI
│   │       ├── ConnectionPanel.tsx  # WebRTC connection management
│   │       ├── TranscriptPanel.tsx  # Real-time transcript display
│   │       └── InsightPanel.tsx     # AI insights panel
│   │
│   ├── hooks/
│   │   ├── index.ts             # Hooks exports
│   │   ├── useWebRTCClient.ts   # WebRTC client hook
│   │   └── useCallTimer.ts      # Call timer hook
│   │
│   └── lib/
│       ├── types.ts             # Shared TypeScript types
│       └── webrtc-client.ts     # WebRTC client class
│
├── public/                      # Static assets
├── next.config.ts               # Next.js configuration
├── postcss.config.mjs           # PostCSS configuration
├── tailwind.config.ts           # TailwindCSS configuration
├── tsconfig.json                # TypeScript configuration
├── MIGRATION_GUIDE.md           # This file
└── package.json
```
