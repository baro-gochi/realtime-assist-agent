/**
 * @fileoverview React 애플리케이션 진입점 (Entry Point)
 *
 * 이 파일은 React 애플리케이션을 시작하는 메인 파일입니다.
 * HTML의 'root' 엘리먼트에 React 앱을 마운트(연결)합니다.
 *
 * @description
 * React 앱의 시작점으로 다음 작업을 수행합니다:
 * 1. HTML의 'root' div를 찾습니다 (index.html의 <div id="root">)
 * 2. React 앱을 생성하고 해당 div에 연결합니다
 * 3. StrictMode로 감싸서 개발 중 잠재적 문제를 조기에 발견합니다
 *
 * @see {@link https://react.dev/reference/react-dom/client/createRoot} React createRoot 문서
 *
 * @example
 * // HTML 구조 (public/index.html)
 * <body>
 *   <div id="root"></div> <!-- 여기에 React 앱이 렌더링됨 -->
 * </body>
 *
 * @tutorial
 * React.StrictMode란?
 * - 개발 모드에서만 활성화되는 도구
 * - 잠재적인 문제를 경고로 알려줌
 * - 프로덕션 빌드에는 영향 없음
 * - 컴포넌트를 2번 렌더링해서 부작용을 찾아냄
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

// HTML의 id="root" 엘리먼트를 찾아서 React 앱을 렌더링합니다
ReactDOM.createRoot(document.getElementById('root')).render(
  // StrictMode: 개발 중 문제를 미리 발견할 수 있게 도와주는 도구
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
