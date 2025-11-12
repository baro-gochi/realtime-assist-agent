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

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
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
     * WebSocket 프록시 설정
     * @description
     * '/ws' 경로로 오는 WebSocket 요청을 백엔드 서버로 전달합니다.
     * 개발 중 CORS 문제를 해결하기 위한 설정입니다.
     */
    allowedHosts: [
      "my-dev-webrtc.loca.lt",
      "*",
    ],
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  }
})
