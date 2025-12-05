/**
 * @fileoverview Vite 빌드 도구 설정 파일
 *
 * @description
 * React 개발 서버와 빌드 설정을 관리합니다.
 *
 * 주요 설정:
 * - React 플러그인: JSX 변환 및 Fast Refresh
 * - 개발 서버: 포트, 호스트, 프록시 설정
 * - 외부 접속: 모바일 기기나 다른 컴퓨터에서 접속 가능
 */

import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  // envDir: path.resolve(__dirname, '..'),
  server: {
    /**
     * 개발 서버 포트 번호
     * @type {number}
     */
    port: 3000,

    /**
     * 외부 접속 허용 설정
     * @type {string|boolean}
     *
     * @description
     * '0.0.0.0' 또는 true로 설정하면 외부에서 접속 가능합니다.
     *
     * 사용 방법:
     * 1. 서버 실행: npm run dev
     * 2. 콘솔에 표시되는 "Network: http://192.168.x.x:3000" 주소 확인
     * 3. 같은 네트워크의 다른 기기에서 해당 주소로 접속
     *
     * @example
     * // 모바일에서 접속
     * // PC IP가 192.168.0.100이라면
     * // 모바일 브라우저에서: http://192.168.0.100:3000
     *
     * @tutorial
     * 외부 접속이 필요한 경우:
     * - 모바일 기기에서 테스트
     * - 같은 네트워크의 다른 컴퓨터에서 접속
     * - 팀원과 개발 중인 앱 공유
     *
     * 보안 주의사항:
     * - 개발 환경에서만 사용
     * - 공용 네트워크에서는 주의 필요
     * - 프로덕션에서는 사용하지 않음
     */
    host: '0.0.0.0', // 또는 host: true 도 가능

    /**
     * WebSocket 및 API 프록시 설정
     * @description
     * '/ws' 및 '/api' 경로를 백엔드 서버로 프록시합니다.
     * 터널 사용 시 VITE_BACKEND_URL 환경변수로 백엔드 URL 지정 가능
     *
     * @example
     * # 로컬 개발 (기본값)
     * npm run dev
     *
     * # 터널 사용 시
     * VITE_API_URL=https://my-dev-backend.loca.lt npm run dev
     */
    allowedHosts: ['.loca.lt', '.ngrok.io', '.ngrok-free.app', '.trycloudflare.com'],  // 호스트 허용 (localtunnel, ngrok 등)
    proxy: {
      '/ws': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        ws: true,
        changeOrigin: true,
        secure: false,  // Allow self-signed certs in development
      },
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,  // Allow self-signed certs in development
      }
    }
  }
})
