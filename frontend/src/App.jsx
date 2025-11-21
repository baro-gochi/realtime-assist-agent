/**
 * @fileoverview 메인 App 라우터 컴포넌트
 *
 * @description
 * React Router를 사용하여 페이지 라우팅을 관리합니다.
 *
 * 라우트:
 * - / : AssistantMain (AI 상담 어시스턴트 대시보드)
 * - /video-call : VideoCall (기능 프로토타입 - 기존 비디오 통화 UI)
 */

import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import AssistantMain from './AssistantMain';
import VideoCall from './VideoCall';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Main Route: AI Assistant Dashboard */}
        <Route path="/" element={<AssistantMain />} />

        {/* Legacy Route: Original Video Call Prototype */}
        <Route path="/video-call" element={<VideoCall />} />

        {/* 404 Not Found */}
        <Route path="*" element={
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            fontFamily: 'sans-serif'
          }}>
            <h1>404 - Page Not Found</h1>
            <p>요청하신 페이지를 찾을 수 없습니다.</p>
            <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
              <Link to="/" style={{
                padding: '10px 20px',
                background: '#4F46E5',
                color: 'white',
                textDecoration: 'none',
                borderRadius: '5px'
              }}>
                AI 어시스턴트 대시보드
              </Link>
              <Link to="/video-call" style={{
                padding: '10px 20px',
                background: '#6B7280',
                color: 'white',
                textDecoration: 'none',
                borderRadius: '5px'
              }}>
                비디오 콜 (프로토타입)
              </Link>
            </div>
          </div>
        } />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
