/**
 * @fileoverview 상담사 이력 조회 페이지
 *
 * @description
 * 상담사가 자신의 코드(사번)와 이름을 입력하여 상담 이력을 조회하는 페이지입니다.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
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

function AgentHistory({ isDarkMode, onToggleTheme }) {
  const [agentCode, setAgentCode] = useState('');
  const [agentName, setAgentName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [agentInfo, setAgentInfo] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [expandedSessionId, setExpandedSessionId] = useState(null);
  const [sessionTranscripts, setSessionTranscripts] = useState({});
  const [sessionResults, setSessionResults] = useState({});
  const [loadingTranscripts, setLoadingTranscripts] = useState({});
  const [loadingResults, setLoadingResults] = useState({});

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!agentCode.trim() || !agentName.trim()) {
      setError('상담사 코드와 이름을 모두 입력해주세요');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const authToken = sessionStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/agent/login`, {
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
        setAgentInfo(data.agent);
        await fetchSessions(data.agent.agent_id);
      } else {
        setError(data.detail || '로그인 실패');
      }
    } catch (err) {
      setError('서버 연결 실패');
    } finally {
      setLoading(false);
    }
  };

  const fetchSessions = async (agentId) => {
    try {
      const authToken = sessionStorage.getItem('auth_token');
      const response = await fetch(`${API_BASE_URL}/api/agent/${agentId}/sessions`, {
        headers: {
          'Authorization': `Bearer ${authToken}`,
          'bypass-tunnel-reminder': 'true',
          'ngrok-skip-browser-warning': 'true',
        },
      });

      if (response.ok) {
        const data = await response.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const fetchTranscripts = async (sessionId) => {
    if (sessionTranscripts[sessionId]) return;

    setLoadingTranscripts((prev) => ({ ...prev, [sessionId]: true }));

    try {
      const authToken = sessionStorage.getItem('auth_token');
      const response = await fetch(
        `${API_BASE_URL}/api/consultation/session/${sessionId}/transcripts`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
            'bypass-tunnel-reminder': 'true',
            'ngrok-skip-browser-warning': 'true',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSessionTranscripts((prev) => ({
          ...prev,
          [sessionId]: data.transcripts || [],
        }));
      }
    } catch (err) {
      console.error('Failed to fetch transcripts:', err);
    } finally {
      setLoadingTranscripts((prev) => ({ ...prev, [sessionId]: false }));
    }
  };

  const fetchResults = async (sessionId) => {
    if (sessionResults[sessionId]) return;

    setLoadingResults((prev) => ({ ...prev, [sessionId]: true }));

    try {
      const authToken = sessionStorage.getItem('auth_token');
      const response = await fetch(
        `${API_BASE_URL}/api/consultation/session/${sessionId}/results`,
        {
          headers: {
            'Authorization': `Bearer ${authToken}`,
            'bypass-tunnel-reminder': 'true',
            'ngrok-skip-browser-warning': 'true',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSessionResults((prev) => ({
          ...prev,
          [sessionId]: data.results || [],
        }));
      }
    } catch (err) {
      console.error('Failed to fetch results:', err);
    } finally {
      setLoadingResults((prev) => ({ ...prev, [sessionId]: false }));
    }
  };

  const handleLogout = () => {
    setAgentInfo(null);
    setSessions([]);
    setExpandedSessionId(null);
    setSessionTranscripts({});
    setSessionResults({});
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '-';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}분 ${secs}초`;
  };

  /**
   * 노드 타입을 한글로 변환
   */
  const getResultTypeName = (resultType) => {
    const typeMap = {
      'summary': '실시간 요약',
      'summarize': '실시간 요약',
      'intent': '의도 분석',
      'sentiment': '감정 분석',
      'risk': '위험 감지',
      'rag': '정보 검색',
      'rag_policy': '정보 검색',
      'faq': 'FAQ 검색',
      'faq_search': 'FAQ 검색',
      'draft_reply': '응답 초안',
      'draft_replies': '응답 초안'
    };
    return typeMap[resultType] || resultType;
  };

  /**
   * 분석 결과 데이터를 파싱하여 보기 좋게 렌더링
   */
  const renderResultData = (resultType, resultData) => {
    // JSON 문자열이면 파싱
    let data = resultData;
    if (typeof resultData === 'string') {
      try {
        data = JSON.parse(resultData);
      } catch (e) {
        return <p>{resultData}</p>;
      }
    }

    if (!data || typeof data !== 'object') {
      return <p>{String(data || '-')}</p>;
    }

    // 스킵된 경우
    if (data.skipped) {
      return <p className="result-skipped">(스킵됨) {data.skip_reason || ''}</p>;
    }

    switch (resultType) {
      case 'summary':
      case 'summarize':
        return (
          <div className="result-parsed">
            {data.summary && <p><strong>요약:</strong> {data.summary}</p>}
            {data.customer_issue && <p><strong>고객 이슈:</strong> {data.customer_issue}</p>}
            {data.steps && data.steps.length > 0 && (
              <div>
                <strong>진행 과정:</strong>
                <ol>
                  {data.steps.map((step, idx) => (
                    <li key={idx}>{step.action || step}</li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        );

      case 'intent':
        return (
          <div className="result-parsed">
            <p><strong>의도:</strong> {data.intent_label || '-'}</p>
            {data.intent_confidence && (
              <p><strong>신뢰도:</strong> {Math.round(data.intent_confidence * 100)}%</p>
            )}
            {data.intent_explanation && (
              <p><strong>설명:</strong> {data.intent_explanation}</p>
            )}
          </div>
        );

      case 'sentiment':
        return (
          <div className="result-parsed">
            <p><strong>감정:</strong> {data.sentiment_label || '-'}</p>
            {data.sentiment_score && (
              <p><strong>점수:</strong> {Math.round(data.sentiment_score * 100)}%</p>
            )}
            {data.sentiment_explanation && (
              <p><strong>설명:</strong> {data.sentiment_explanation}</p>
            )}
          </div>
        );

      case 'risk':
        const flags = data.risk_flags || [];
        const validFlags = flags.filter(f => f && f.trim() !== '');
        return (
          <div className="result-parsed">
            <p><strong>위험 요소:</strong> {validFlags.length > 0 ? validFlags.join(', ') : '없음'}</p>
            {data.risk_explanation && (
              <p><strong>설명:</strong> {data.risk_explanation}</p>
            )}
          </div>
        );

      case 'rag':
      case 'rag_policy':
        const recommendations = data.recommendations || [];
        return (
          <div className="result-parsed">
            <p><strong>검색 결과:</strong> {recommendations.length}개</p>
            {recommendations.length > 0 && (
              <ul>
                {recommendations.map((rec, idx) => (
                  <li key={idx}>
                    {rec.plan_name || rec.title || '-'}
                    {rec.relevance_score && ` (${Math.round(rec.relevance_score * 100)}%)`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        );

      case 'faq':
      case 'faq_search':
        const faqs = data.faqs || data.results || [];
        return (
          <div className="result-parsed">
            <p>
              <strong>FAQ 결과:</strong> {faqs.length}개
              {data.cache_hit && <span className="cache-badge"> (캐시)</span>}
            </p>
            {faqs.length > 0 && (
              <ul>
                {faqs.map((faq, idx) => (
                  <li key={idx}>{faq.question || faq.title || '-'}</li>
                ))}
              </ul>
            )}
          </div>
        );

      case 'draft_reply':
      case 'draft_replies':
        return (
          <div className="result-parsed">
            {data.short_reply && <p><strong>짧은 응답:</strong> {data.short_reply}</p>}
            {data.detailed_reply && <p><strong>상세 응답:</strong> {data.detailed_reply}</p>}
            {data.draft_reply && <p><strong>응답:</strong> {data.draft_reply}</p>}
          </div>
        );

      default:
        // 알 수 없는 타입은 JSON으로 표시
        return <pre className="result-data-raw">{JSON.stringify(data, null, 2)}</pre>;
    }
  };

  // 로그인 전 화면
  if (!agentInfo) {
    return (
      <div className="agent-page">
        <ThemeToggleButton isDarkMode={isDarkMode} onToggle={onToggleTheme} />
        <div className="agent-container">
          <div className="agent-header">
            <h1>상담 이력 조회</h1>
            <p>상담사 정보를 입력하여 이력을 조회합니다</p>
          </div>

          <form onSubmit={handleLogin} className="agent-form">
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

            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? '조회 중...' : '조회하기'}
            </button>
          </form>

          <div className="agent-links">
            <Link to="/agent/register">상담사 등록</Link>
            <Link to="/">메인으로</Link>
          </div>
        </div>
      </div>
    );
  }

  // 로그인 후 화면
  return (
    <div className="agent-page">
      <ThemeToggleButton isDarkMode={isDarkMode} onToggle={onToggleTheme} />
      <div className="agent-container wide">
        <div className="agent-header">
          <div className="header-row">
            <div>
              <h1>상담 이력</h1>
              <p>
                {agentInfo.agent_name} ({agentInfo.agent_code}) 님의 상담 이력
              </p>
            </div>
            <button onClick={handleLogout} className="btn-secondary">
              로그아웃
            </button>
          </div>
        </div>

        <div className="sessions-list">
          {sessions.length === 0 ? (
            <div className="no-data">상담 이력이 없습니다</div>
          ) : (
            sessions.map((session) => (
              <div key={session.session_id} className="session-card">
                <div className="session-header">
                  <div className="session-info">
                    <span className="session-date">
                      {formatDate(session.started_at)}
                    </span>
                    <span className="session-customer">
                      {session.customer_name || '미확인 고객'}
                    </span>
                    <span className="session-type">
                      {session.consultation_type || '-'}
                    </span>
                  </div>
                  <div className="session-meta">
                    <span className="session-duration">
                      {formatDuration(session.duration_seconds)}
                    </span>
                    <span className="session-count">
                      {session.transcript_count || 0}개 대화
                    </span>
                  </div>
                </div>

                {session.final_summary && (
                  <div className="session-summary">{session.final_summary}</div>
                )}

                <div className="session-actions">
                  <button
                    className="btn-small"
                    onClick={() => {
                      if (expandedSessionId === session.session_id) {
                        setExpandedSessionId(null);
                      } else {
                        setExpandedSessionId(session.session_id);
                        fetchTranscripts(session.session_id);
                      }
                    }}
                  >
                    {expandedSessionId === session.session_id
                      ? '대화 숨기기'
                      : '대화 보기'}
                  </button>
                  <button
                    className="btn-small"
                    onClick={() => fetchResults(session.session_id)}
                    disabled={loadingResults[session.session_id]}
                  >
                    {loadingResults[session.session_id]
                      ? '로딩...'
                      : sessionResults[session.session_id]
                      ? '결과 새로고침'
                      : '분석 결과'}
                  </button>
                </div>

                {expandedSessionId === session.session_id && (
                  <div className="session-detail">
                    <h4>대화 내용</h4>
                    {loadingTranscripts[session.session_id] ? (
                      <div className="loading">로딩 중...</div>
                    ) : sessionTranscripts[session.session_id]?.length > 0 ? (
                      <div className="transcript-list">
                        {sessionTranscripts[session.session_id].map(
                          (transcript, idx) => (
                            <div
                              key={idx}
                              className={`transcript-item ${transcript.speaker_type}`}
                            >
                              <span className="speaker">
                                {transcript.speaker_name}
                              </span>
                              <span className="text">{transcript.text}</span>
                            </div>
                          )
                        )}
                      </div>
                    ) : (
                      <div className="no-data">대화 내용이 없습니다</div>
                    )}
                  </div>
                )}

                {sessionResults[session.session_id] && (
                  <div className="session-detail">
                    <h4>분석 결과</h4>
                    {sessionResults[session.session_id].length > 0 ? (
                      <div className="results-list">
                        {sessionResults[session.session_id].map(
                          (result, idx) => (
                            <div key={idx} className="result-item">
                              <span className="result-type">
                                {getResultTypeName(result.result_type)}
                              </span>
                              <div className="result-content">
                                {renderResultData(result.result_type, result.result_data)}
                              </div>
                            </div>
                          )
                        )}
                      </div>
                    ) : (
                      <div className="no-data">분석 결과가 없습니다</div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="agent-links">
          <Link to="/agent/register">상담사 등록</Link>
          <Link to="/">메인으로</Link>
        </div>
      </div>
    </div>
  );
}

export default AgentHistory;
