/**
 * @fileoverview 메인 App 라우터 컴포넌트 (음성 전용)
 *
 * @description
 * React Router를 사용하여 페이지 라우팅을 관리합니다.
 * 비밀번호 인증을 통해 애플리케이션 접근을 제어합니다.
 * 전역 다크모드 상태를 관리하고 모든 페이지에 전달합니다.
 *
 * 라우트:
 * - / : AssistantMain (AI 상담 어시스턴트 대시보드 - 음성 전용)
 */

import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import AssistantMain from './AssistantMain';
import AgentRegister from './AgentRegister';
import AgentHistory from './AgentHistory';
import './App.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * 테마 토글 버튼 컴포넌트
 */
function ThemeToggleButton({ isDarkMode, onToggle }) {
  return (
    <button
      className="theme-toggle-global"
      onClick={onToggle}
      title={isDarkMode ? '라이트 모드' : '다크 모드'}
    >
      {isDarkMode ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      )}
    </button>
  );
}

/**
 * 비밀번호 입력 화면 컴포넌트
 */
function PasswordScreen({ onAuthenticated, isDarkMode, onToggleTheme }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'bypass-tunnel-reminder': 'true',
          'ngrok-skip-browser-warning': 'true',
        },
        body: `password=${encodeURIComponent(password)}`,
      });

      if (response.ok) {
        sessionStorage.setItem('auth_token', password);
        onAuthenticated(password);
      } else {
        const data = await response.json();
        setError(data.detail || '인증 실패');
      }
    } catch (err) {
      setError('서버 연결 실패. 백엔드가 실행 중인지 확인하세요.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="password-screen">
      <ThemeToggleButton isDarkMode={isDarkMode} onToggle={onToggleTheme} />
      <div className="password-card">
        <h1>실시간 상담 어시스턴트</h1>
        <p className="subtitle">접근하려면 비밀번호를 입력하세요</p>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 입력"
            autoFocus
          />
          {error && (
            <p className="error-text">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading || !password}
            className="submit-btn"
          >
            {loading ? '확인 중...' : '로그인'}
          </button>
        </form>
      </div>
    </div>
  );
}

function App() {
  const [authToken, setAuthToken] = useState(null);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // 다크모드 상태 (localStorage 값 우선, 없으면 시스템 설정 따라감)
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode');
    if (saved !== null) {
      return saved === 'true';
    }
    // localStorage에 저장된 값이 없으면 시스템 설정 따라감
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  // 다크모드 변경 시 localStorage 저장 및 document 속성 설정
  useEffect(() => {
    localStorage.setItem('darkMode', isDarkMode);
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  // 시스템 설정 변경 감지 (사용자가 수동 설정 안 했을 때만)
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e) => {
      // localStorage에 저장된 값이 없을 때만 시스템 설정 따라감
      if (localStorage.getItem('darkMode') === null) {
        setIsDarkMode(e.matches);
      }
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, []);

  const toggleDarkMode = () => {
    setIsDarkMode(prev => !prev);
  };

  useEffect(() => {
    // sessionStorage에서 저장된 토큰 확인 (브라우저 닫으면 삭제됨)
    const savedToken = sessionStorage.getItem('auth_token');
    if (savedToken) {
      // 저장된 토큰으로 서버에서 반드시 인증 확인
      fetch(`${API_BASE_URL}/api/auth/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'bypass-tunnel-reminder': 'true',
          'ngrok-skip-browser-warning': 'true',
        },
        body: `password=${encodeURIComponent(savedToken)}`,
      })
        .then((res) => {
          if (res.ok) {
            setAuthToken(savedToken);
          } else {
            sessionStorage.removeItem('auth_token');
          }
          setCheckingAuth(false);
        })
        .catch(() => {
          // 서버 연결 실패 시 재로그인 필요
          sessionStorage.removeItem('auth_token');
          setCheckingAuth(false);
        });
    } else {
      setCheckingAuth(false);
    }
  }, []);

  if (checkingAuth) {
    return (
      <div className="auth-checking">
        <p>인증 확인 중...</p>
      </div>
    );
  }

  if (!authToken) {
    return (
      <PasswordScreen
        onAuthenticated={setAuthToken}
        isDarkMode={isDarkMode}
        onToggleTheme={toggleDarkMode}
      />
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        {/* Main Route: AI Assistant Dashboard (음성 전용) */}
        <Route
          path="/"
          element={
            <AssistantMain
              isDarkMode={isDarkMode}
              onToggleTheme={toggleDarkMode}
            />
          }
        />

        {/* Agent Routes: 상담사 등록 및 이력 조회 */}
        <Route
          path="/agent/register"
          element={
            <AgentRegister
              isDarkMode={isDarkMode}
              onToggleTheme={toggleDarkMode}
            />
          }
        />
        <Route
          path="/agent/history"
          element={
            <AgentHistory
              isDarkMode={isDarkMode}
              onToggleTheme={toggleDarkMode}
            />
          }
        />

        {/* 404 Not Found */}
        <Route path="*" element={
          <div className="password-screen">
            <ThemeToggleButton isDarkMode={isDarkMode} onToggle={toggleDarkMode} />
            <div className="password-card">
              <h1>404 - Page Not Found</h1>
              <p className="subtitle">요청하신 페이지를 찾을 수 없습니다.</p>
              <Link to="/" className="submit-btn" style={{ display: 'block', textAlign: 'center', textDecoration: 'none' }}>
                AI 어시스턴트 대시보드
              </Link>
            </div>
          </div>
        } />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
