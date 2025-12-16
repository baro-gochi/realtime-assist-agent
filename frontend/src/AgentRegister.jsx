/**
 * @fileoverview 상담사 등록 페이지
 *
 * @description
 * 상담사가 자신의 코드(사번)와 이름을 입력하여 등록하는 페이지입니다.
 */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import './AgentPages.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * 테마 토글 버튼 컴포넌트
 */
function ThemeToggleButton({ isDarkMode, onToggle }) {
  return (
    <button
      className="page-theme-toggle"
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

function AgentRegister({ isDarkMode, onToggleTheme }) {
  const navigate = useNavigate();
  const [agentCode, setAgentCode] = useState('');
  const [agentName, setAgentName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!agentCode.trim() || !agentName.trim()) {
      setError('상담사 코드와 이름을 모두 입력해주세요');
      return;
    }

    setLoading(true);
    setError('');
    setSuccess('');

    try {
      const authToken = sessionStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/agent/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`,
          'bypass-tunnel-reminder': 'true',
          'ngrok-skip-browser-warning': 'true',
        },
        body: JSON.stringify({
          agent_code: agentCode.trim(),
          agent_name: agentName.trim(),
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setSuccess(`등록 완료! 상담사 ID: ${data.agent_id}`);
        setAgentCode('');
        setAgentName('');
      } else {
        setError(data.detail || '등록 실패');
      }
    } catch (err) {
      setError('서버 연결 실패');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="agent-page">
      <ThemeToggleButton isDarkMode={isDarkMode} onToggle={onToggleTheme} />
      <div className="agent-container">
        <div className="agent-header">
          <h1>상담사 등록</h1>
          <p>새로운 상담사 정보를 등록합니다</p>
        </div>

        <form onSubmit={handleSubmit} className="agent-form">
          <div className="form-group">
            <label htmlFor="agentCode">상담사 코드 (사번)</label>
            <input
              type="text"
              id="agentCode"
              value={agentCode}
              onChange={(e) => setAgentCode(e.target.value)}
              placeholder="예: A001"
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="agentName">상담사 이름</label>
            <input
              type="text"
              id="agentName"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="이름을 입력하세요"
            />
          </div>

          {error && <div className="message error">{error}</div>}
          {success && <div className="message success">{success}</div>}

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? '등록 중...' : '등록하기'}
          </button>
        </form>

        <div className="agent-links">
          <Link to="/agent/history">이력 조회</Link>
          <Link to="/">메인으로</Link>
        </div>
      </div>
    </div>
  );
}

export default AgentRegister;
