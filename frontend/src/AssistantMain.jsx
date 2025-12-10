/**
 * @fileoverview AI 상담 어시스턴트 메인 대시보드
 *
 * @description
 * 상담사를 위한 AI 어시스턴트 대시보드 컴포넌트입니다.
 * 실시간 STT, 연결 정보, 대화 내역, AI 추천 답변 등을 표시합니다.
 *
 * 주요 기능:
 * 1. 상담사/고객 역할 선택
 * 2. 상담사: 방 생성, 고객: 방 목록에서 선택
 * 3. 실시간 음성 인식 및 대화 표시
 * 4. 연결된 상대방 정보 표시
 * 5. AI 추천 답변 (RAG 기반)
 */

import { useState, useEffect, useRef } from 'react';
import { WebRTCClient } from './webrtc';
import './AssistantMain.css';

function AssistantMain() {
  // 역할 선택 ('agent' | 'customer' | null)
  const [userRole, setUserRole] = useState(null);

  // WebRTC 상태
  const [isConnected, setIsConnected] = useState(false);
  const [isInRoom, setIsInRoom] = useState(false);
  const [isCallActive, setIsCallActive] = useState(false);
  const [peerId, setPeerId] = useState('');
  const [roomName, setRoomName] = useState('');
  const [nickname, setNickname] = useState('');
  const [currentRoom, setCurrentRoom] = useState('');
  const [peerCount, setPeerCount] = useState(0);
  const [connectionState, setConnectionState] = useState('');
  const [participants, setParticipants] = useState([]);
  const [error, setError] = useState('');

  // 고객용 방 목록
  const [availableRooms, setAvailableRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(false);

  // 통화 시간 타이머
  const [callDuration, setCallDuration] = useState(0);
  const [callStartTime, setCallStartTime] = useState(null); // 통화 시작 시간 (timestamp)
  const callTimerRef = useRef(null);

  // STT 트랜스크립트
  const [transcripts, setTranscripts] = useState([]);
  const transcriptContainerRef = useRef(null);

  // AI 에이전트 요약 (JSON 파싱)
  const [parsedSummary, setParsedSummary] = useState(null); // {summary, customer_issue, agent_action}
  const [summaryTimestamp, setSummaryTimestamp] = useState(null); // 요약 수신 시간
  const [llmStatus, setLlmStatus] = useState('connecting'); // 'connecting' | 'ready' | 'connected' | 'failed'
  const [consultationStatus, setConsultationStatus] = useState('idle'); // idle | processing | done | error
  const [consultationResult, setConsultationResult] = useState(null); // {guide, recommendations, citations}
  const [consultationError, setConsultationError] = useState('');

  // WebRTC ref
  const webrtcClientRef = useRef(null);
  const remoteAudioRef = useRef(null);

  // 폼 입력값
  const [roomInput, setRoomInput] = useState('');
  const [nicknameInput, setNicknameInput] = useState('');

  // 오디오 상태
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);

  // Web Audio API (볼륨 증폭용)
  const audioContextRef = useRef(null);
  const gainNodeRef = useRef(null);

  /**
   * WebRTC 클라이언트 초기화
   */
  useEffect(() => {
    // 환경변수 우선, 없으면 현재 호스트 기반 URL 사용
    const wsUrl = import.meta.env.VITE_WS_URL ||
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

    console.log('🔗 WebSocket URL:', wsUrl);
    const client = new WebRTCClient(wsUrl);
    webrtcClientRef.current = client;

    // 이벤트 핸들러 설정
    client.onPeerId = (id) => {
      setPeerId(id);
      console.log('Peer ID set:', id);
    };

    client.onRoomJoined = (data) => {
      console.log('Room joined:', data);
      setCurrentRoom(data.room_name);
      setPeerCount(data.peer_count);
      setIsInRoom(true);
      setParticipants(data.other_peers || []);
    };

    client.onUserJoined = (data) => {
      console.log('User joined:', data);
      setPeerCount(data.peer_count);
      setParticipants(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname
      }]);
    };

    client.onUserLeft = (data) => {
      console.log('User left:', data);
      setPeerCount(data.peer_count);
      setParticipants(prev =>
        prev.filter(p => p.peer_id !== data.peer_id)
      );
    };

    client.onRemoteStream = (stream) => {
      console.log('🎤 Remote audio stream received');

      // Web Audio API를 사용하여 볼륨 증폭
      try {
        // 기존 AudioContext 정리
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
        }

        // 새 AudioContext 생성
        const audioContext = new (window.AudioContext || window.webkitAudioContext)({
          latencyHint: 'interactive',  // 낮은 지연 모드
          sampleRate: 48000            // 48kHz 샘플레이트
        });
        audioContextRef.current = audioContext;

        // 스트림을 AudioContext에 연결
        const source = audioContext.createMediaStreamSource(stream);

        // GainNode로 볼륨 증폭 (2.5배)
        const gainNode = audioContext.createGain();
        gainNode.gain.value = 2.5;
        gainNodeRef.current = gainNode;

        // 연결: source → gain → destination (스피커)
        source.connect(gainNode);
        gainNode.connect(audioContext.destination);

        console.log('🔊 Audio amplified with gain:', gainNode.gain.value);

        // 숨겨진 audio 요소에도 연결 (폴백용)
        if (remoteAudioRef.current) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 0; // Web Audio API 사용하므로 0으로
        }
      } catch (err) {
        console.error('❌ Web Audio API failed, using fallback:', err);
        // 폴백: 일반 audio 요소 사용
        if (remoteAudioRef.current && remoteAudioRef.current.srcObject !== stream) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 1.0;
          remoteAudioRef.current.play().catch(e => console.error('Remote audio play failed:', e));
        }
      }
    };

    client.onConnectionStateChange = (state) => {
      setConnectionState(state);
      console.log('Connection state changed:', state);
    };

    client.onError = (err) => {
      setError(err.message);
      console.error('WebRTC error:', err);
    };

    // STT transcript 이벤트 핸들러
    client.onTranscript = (data) => {
      console.log('💬 Transcript received:', data);
      setTranscripts(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname,
        text: data.text,
        timestamp: data.timestamp || Date.now(),
        receivedAt: Date.now() // 수신 시간 (UI 표시용)
      }]);
    };

    // AI 에이전트 준비 완료 이벤트 핸들러
    client.onAgentReady = (data) => {
      console.log('🤖 Agent ready:', data);
      if (data.llm_available) {
        setLlmStatus('ready');
        console.log('✅ LLM available, ready for summarization');
      } else {
        setLlmStatus('failed');
        console.warn('⚠️ LLM not available');
      }
    };

    // AI 에이전트 업데이트 이벤트 핸들러 (JSON 파싱)
    client.onAgentUpdate = (data) => {
      console.log('🤖 Agent update received:', JSON.stringify(data, null, 2));

      if (!data || data.node !== 'summarize') {
        return;
      }

      const summaryData = data.data || {};
      const parsed = {
        summary: summaryData.summary || '',
        customer_issue: summaryData.customer_issue || '',
        agent_action: summaryData.agent_action || ''
      };

      // raw가 JSON 문자열일 경우만 파싱 시도 (호환성)
      if ((!parsed.summary || !parsed.customer_issue || !parsed.agent_action) && summaryData.raw) {
        try {
          const json = JSON.parse(summaryData.raw);
          parsed.summary = parsed.summary || json.summary || '';
          parsed.customer_issue = parsed.customer_issue || json.customer_issue || '';
          parsed.agent_action = parsed.agent_action || json.agent_action || '';
        } catch (e) {
          console.warn('⚠️ Failed to parse raw summary JSON:', e.message);
        }
      }

      setLlmStatus('connected');
      setSummaryTimestamp(Date.now());
      setParsedSummary(parsed);
    };

    // 상담 가이드 상태 업데이트
    client.onAgentStatus = (data) => {
      if (!data) return;
      if (data.status === 'processing') {
        setConsultationStatus('processing');
        setConsultationError('');
      } else if (data.status === 'error') {
        setConsultationStatus('error');
        setConsultationError(data.message || '에이전트 오류');
      }
    };

    // 상담 가이드 결과 수신
    client.onAgentConsultation = (data) => {
      console.log('📑 Consultation result:', data);
      if (!data) return;
      setConsultationStatus('done');
      setConsultationError('');
      setConsultationResult({
        guide: data.guide || [],
        recommendations: data.recommendations || [],
        citations: data.citations || [],
        generated_at: data.generated_at || Date.now()
      });
    };

    // 브라우저 종료/새로고침 시 즉시 정리 (beforeunload)
    const handleBeforeUnload = () => {
      console.log('🔴 beforeunload: Cleaning up WebRTC connection...');
      if (client) {
        // leaveRoom을 호출하여 서버에 즉시 알림
        client.leaveRoom();
        client.disconnect();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (client) {
        client.disconnect();
      }
    };
  }, []);

  /**
   * 트랜스크립트 자동 스크롤
   */
  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop = transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  /**
   * 고객 선택 시 자동으로 방 목록 가져오기
   */
  useEffect(() => {
    if (userRole === 'customer' && isConnected) {
      fetchRooms();
    }
  }, [userRole, isConnected]);

  /**
   * 통화 시간 타이머
   */
  useEffect(() => {
    if (isCallActive) {
      setCallDuration(0);
      callTimerRef.current = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    } else {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
        callTimerRef.current = null;
      }
    }

    return () => {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
      }
    };
  }, [isCallActive]);

  /**
   * 통화 시간 포맷 (MM:SS)
   */
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  /**
   * 경과 시간 계산 (밀리초 → 초)
   */
  const getElapsedSeconds = (timestamp) => {
    if (!callStartTime || !timestamp) return 0;
    return Math.floor((timestamp - callStartTime) / 1000);
  };

  /**
   * 서버 연결
   */
  const handleConnect = async () => {
    try {
      setError('');
      await webrtcClientRef.current.connect();
      setIsConnected(true);
    } catch (err) {
      setError(`Connection failed: ${err.message}`);
    }
  };

  /**
   * 방 목록 가져오기 (고객용)
   */
  const fetchRooms = async () => {
    // 환경변수 우선, 없으면 현재 호스트 사용
    const apiBase = import.meta.env.VITE_API_URL || '';
    const apiUrl = `${apiBase}/api/rooms`;

    console.log('🔄 Fetching rooms from:', apiUrl);
    setLoadingRooms(true);
    setError(''); // 이전 에러 초기화
    try {
      const headers = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      const authToken = sessionStorage.getItem('auth_token');
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const response = await fetch(apiUrl, { headers });
      console.log('📡 Response status:', response.status);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('📦 Received rooms data:', data);
      setAvailableRooms(data.rooms || []);
      console.log('✅ Rooms loaded successfully:', data.rooms?.length || 0);
    } catch (err) {
      console.error('❌ Failed to fetch rooms:', err);
      setError(`방 목록을 불러오는데 실패했습니다: ${err.message}`);
    } finally {
      setLoadingRooms(false);
      console.log('🏁 Fetch rooms completed');
    }
  };

  /**
   * 고객이 방 선택
   */
  const handleJoinRoomAsCustomer = async (room) => {
    if (!nicknameInput.trim()) {
      setError('이름을 입력해주세요');
      return;
    }

    try {
      setError('');
      setTranscripts([]);
      setParsedSummary(null);
      setLlmStatus('connecting');
      await webrtcClientRef.current.joinRoom(room.room_name, nicknameInput.trim());
      setRoomName(room.room_name);
      setNickname(nicknameInput.trim());
      // Fallback: 서버 room_joined 이벤트 지연 시에도 화면 전환
      setCurrentRoom(room.room_name);
      setIsInRoom(true);
      setPeerCount(room.peer_count || 0);
      setParticipants(room.peers || []);
    } catch (err) {
      setError(`Failed to join room: ${err.message}`);
    }
  };

  /**
   * 상담사가 방 생성
   */
  const handleCreateRoomAsAgent = async (e) => {
    e.preventDefault();
    if (!roomInput.trim() || !nicknameInput.trim()) {
      setError('방 이름과 이름을 모두 입력해주세요');
      return;
    }

    try {
      setError('');
      setTranscripts([]);
      setParsedSummary(null);
      setLlmStatus('connecting');
      await webrtcClientRef.current.joinRoom(roomInput.trim(), nicknameInput.trim());
      setRoomName(roomInput.trim());
      setNickname(nicknameInput.trim());
      // Fallback: 서버 room_joined 이벤트 지연 시에도 화면 전환
      setCurrentRoom(roomInput.trim());
      setIsInRoom(true);
      setPeerCount(1);
    } catch (err) {
      setError(`Failed to create room: ${err.message}`);
    }
  };

  /**
   * 통화 시작
   */
  const handleStartCall = async () => {
    try {
      setError('');
      await webrtcClientRef.current.startCall();
      setCallStartTime(Date.now()); // 통화 시작 시간 기록
      setIsCallActive(true);
    } catch (err) {
      console.error('Start call error:', err);
      setError(`Failed to start call: ${err.message}`);
      alert(`Failed to start call: ${err.message}`);
    }
  };

  /**
   * 룸 퇴장
   */
  const handleLeaveRoom = () => {
    webrtcClientRef.current.leaveRoom();

    // AudioContext 정리
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    if (remoteAudioRef.current) remoteAudioRef.current.srcObject = null;

    setIsInRoom(false);
    setIsCallActive(false);
    setCurrentRoom('');
    setRoomName('');
    setNickname('');
    setPeerCount(0);
    setParticipants([]);
    setTranscripts([]);
    setParsedSummary(null);
    setSummaryTimestamp(null);
    setConnectionState('');
    setRoomInput('');
    setNicknameInput('');
    setLlmStatus('connecting');
    setCallStartTime(null); // 통화 시작 시간 초기화
    setConsultationStatus('idle');
    setConsultationResult(null);
    setConsultationError('');
  };

  /**
   * 오디오 토글
   */
  const handleToggleAudio = () => {
    const enabled = webrtcClientRef.current.toggleAudio();
    setIsAudioEnabled(enabled);
  };

  /**
   * 연결된 상대방 정보 가져오기
   */
  const getRemotePeer = () => {
    return participants.length > 0 ? participants[0] : null;
  };

  /**
   * 상담 가이드 생성 요청
   */
  const handleConsultationRequest = () => {
    if (!currentRoom) {
      setConsultationError('룸 정보가 없습니다.');
      return;
    }
    setConsultationStatus('processing');
    setConsultationError('');
    setConsultationResult(null);
    try {
      webrtcClientRef.current.sendConsultationTask(currentRoom, {});
    } catch (e) {
      setConsultationStatus('error');
      setConsultationError(e.message || '요청 실패');
    }
  };

  // Step 1: 역할 선택
  if (!userRole) {
    return (
      <div className="assistant-welcome">
        <div className="welcome-card">
          <h2>역할 선택</h2>
          <p>상담사 또는 고객을 선택하세요</p>
          <div className="role-selection">
            <button
              onClick={() => setUserRole('agent')}
              className="btn btn-primary btn-large"
            >
              👨‍💼 상담사
            </button>
            <button
              onClick={() => setUserRole('customer')}
              className="btn btn-success btn-large"
            >
              👤 고객
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Step 2: 서버 연결
  if (!isConnected) {
    return (
      <div className="assistant-welcome">
        <div className="welcome-card">
          <h2>{userRole === 'agent' ? '상담사 연결' : '고객 연결'}</h2>
          <p>서버에 연결하여 시작하세요</p>
          <button onClick={handleConnect} className="btn btn-primary">
            서버 연결
          </button>
          {error && <div className="error-message">⚠️ {error}</div>}
          <button
            onClick={() => setUserRole(null)}
            className="btn btn-secondary mt-2"
          >
            역할 다시 선택
          </button>
        </div>
      </div>
    );
  }

  // Step 3: 방 선택/생성
  if (!isInRoom) {
    // 상담사: 방 생성
    if (userRole === 'agent') {
      return (
        <div className="assistant-welcome">
          <div className="welcome-card">
            <h2>상담 룸 생성</h2>
            <form onSubmit={handleCreateRoomAsAgent} className="join-form">
              <div className="form-group">
                <label>상담실 이름</label>
                <input
                  type="text"
                  placeholder="예: 상담실1"
                  value={roomInput}
                  onChange={(e) => setRoomInput(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>상담사 이름</label>
                <input
                  type="text"
                  placeholder="이름을 입력하세요"
                  value={nicknameInput}
                  onChange={(e) => setNicknameInput(e.target.value)}
                />
              </div>
              <button type="submit" className="btn btn-success">
                상담실 생성
              </button>
            </form>
            {error && <div className="error-message">⚠️ {error}</div>}
          </div>
        </div>
      );
    }

    // 고객: 방 목록에서 선택
    return (
      <div className="assistant-welcome">
        <div className="welcome-card wide">
          <h2>상담 대기 중인 상담실</h2>

          <div className="form-group">
            <label>고객 이름</label>
            <input
              type="text"
              placeholder="이름을 입력하세요"
              value={nicknameInput}
              onChange={(e) => setNicknameInput(e.target.value)}
            />
          </div>

          <button
            onClick={fetchRooms}
            className="btn btn-primary mb-3"
            disabled={loadingRooms}
          >
            {loadingRooms ? '불러오는 중...' : '상담실 목록 새로고침'}
          </button>

          {availableRooms.length === 0 ? (
            <p className="no-rooms">현재 대기 중인 상담실이 없습니다.</p>
          ) : (
            <div className="room-grid">
              {availableRooms.map((room, index) => (
                <div key={index} className="room-card" onClick={() => handleJoinRoomAsCustomer(room)}>
                  <div className="room-header">
                    <h3>{room.room_name}</h3>
                    <span className="room-count">{room.peer_count}명</span>
                  </div>
                  <div className="room-info">
                    <div className="room-agent">
                      상담사: {room.peers.length > 0 ? room.peers[0].nickname : '알 수 없음'}
                    </div>
                    <div className="room-status">
                      <span className="status-dot"></span>
                      대기 중
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && <div className="error-message">⚠️ {error}</div>}
        </div>
      </div>
    );
  }

  // Main Dashboard
  const remotePeer = getRemotePeer();

  return (
    <div className="assistant-dashboard">
      {/* Header */}
      <header className="dashboard-header">
        <div className="header-content">
          <h1>AI 상담 어시스턴트 (v1.0)</h1>
          <div className="header-info">
            <div className="header-user-info">
              <span className="user-role">{userRole === 'agent' ? '상담사' : '고객'}</span>
              <span className="user-name">{nickname}</span>
              <span className="user-room">룸: {currentRoom}</span>
              <span className="user-peer">ID: {peerId.substring(0, 8)}...</span>
            </div>
            <div className="call-status">
              {isCallActive && (
                <>
                  <span className="status-indicator">
                    <span className="ping"></span>
                    <span className="dot"></span>
                  </span>
                  <span>통화 중 ({formatDuration(callDuration)})</span>
                </>
              )}
              {!isCallActive && <span className="status-waiting">대기 중</span>}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="dashboard-main">
        {/* Left Sidebar: Connection Info */}
        <aside className="sidebar-left">
          {/* Connection Info Card */}
          <div className="card">
            <h2 className="card-title">연결 정보</h2>
            <div className="info-grid">
              {remotePeer ? (
                <>
                  <div className="info-row">
                    <span className="info-label">{userRole === 'agent' ? '고객명' : '상담사'}</span>
                    <span className="info-value">{remotePeer.nickname}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Peer ID</span>
                    <span className="info-value small">{remotePeer.peer_id.substring(0, 8)}...</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">연결 상태</span>
                    <span className={`info-value status-${connectionState}`}>
                      {connectionState || '미연결'}
                    </span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">참가자 수</span>
                    <span className="info-value">{peerCount}명</span>
                  </div>
                </>
              ) : (
                <div className="no-connection">
                  <p>연결된 사용자가 없습니다.</p>
                  <p className="wait-message">상대방이 입장할 때까지 기다려주세요...</p>
                </div>
              )}
            </div>

            {/* Call Controls */}
            <div className="call-controls">
              {!isCallActive ? (
                <button onClick={handleStartCall} className="btn btn-success btn-block">
                  🎤 통화 시작
                </button>
              ) : (
                <>
                  <div className="control-buttons">
                    <button
                      onClick={handleToggleAudio}
                      className={`btn btn-sm ${isAudioEnabled ? 'btn-primary' : 'btn-secondary'}`}
                      title={isAudioEnabled ? '음소거' : '음소거 해제'}
                    >
                      {isAudioEnabled ? '🎤' : '🔇'}
                    </button>
                  </div>
                  <button onClick={handleLeaveRoom} className="btn btn-danger btn-block mt-2">
                    통화 종료
                  </button>
                </>
              )}
            </div>
          </div>

          {/* Past Consultation History - 상담사만 표시 */}
          {userRole === 'agent' && (
            <div className="card card-flex">
              <h2 className="card-title">과거 상담 이력 (총 3건)</h2>
              <div className="history-list">
                <div className="history-item">
                  <p className="history-title">2025-11-03: 배송 지연 문의</p>
                  <p className="history-content">"상품이 아직 도착하지 않았습니다."</p>
                  <p className="history-agent">담당: 박상담</p>
                </div>
                <hr />
                <div className="history-item">
                  <p className="history-title">2025-10-20: 결제 오류</p>
                  <p className="history-content">"카드로하려 하는데 결제가 안돼요."</p>
                  <p className="history-agent">담당: 김상담</p>
                </div>
                <hr />
                <div className="history-item">
                  <p className="history-title">2025-09-15: 회원가입 문의</p>
                  <p className="history-content">"아이디가 기억나지 않습니다."</p>
                  <p className="history-agent">담당: 김상담</p>
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* Center: Conversation */}
        <section className="conversation-section">
          {/* Summary Card */}
          <div className="card summary-card">
            <h2 className="card-title summary-card-title">🤖 AI 실시간 통화 요약</h2>
            {summaryTimestamp && (
              <div className="summary-timestamp">
                {formatDuration(getElapsedSeconds(summaryTimestamp))}
              </div>
            )}
            <div className="summary-content">
              {llmStatus === 'connecting' && <p className="summary-text">LLM 연결 중...</p>}
              {llmStatus === 'ready' && <p className="summary-text">✅ 요약 대기 중 (대화 시작 시 실시간 요약 생성)</p>}
              {llmStatus === 'connected' && parsedSummary && (
                <div className="summary-json">
                  <div className="summary-field">
                    <span className="summary-label">📝 요약:</span>
                    <span className="summary-value">{parsedSummary.summary || '없음'}</span>
                  </div>
                  <div className="summary-field">
                    <span className="summary-label">❓ 고객 문의:</span>
                    <span className="summary-value">{parsedSummary.customer_issue || '없음'}</span>
                  </div>
                  <div className="summary-field">
                    <span className="summary-label">💡 상담사 대응:</span>
                    <span className="summary-value">{parsedSummary.agent_action || '없음'}</span>
                  </div>
                </div>
              )}
              {llmStatus === 'connected' && !parsedSummary && <p className="summary-text">요약 수신 대기 중...</p>}
              {llmStatus === 'failed' && <p className="summary-text error">❌ LLM 연결 실패: 요약 기능을 사용할 수 없습니다. (STT는 정상 동작)</p>}
            </div>
          </div>

          {/* Real-time Conversation */}
          <div className="card card-flex">
            <h2 className="card-title">실시간 대화</h2>
            <div className="conversation-list" ref={transcriptContainerRef}>
              {transcripts.length === 0 ? (
                <p className="no-conversation">대화 내용이 여기에 표시됩니다...</p>
              ) : (
                transcripts.map((transcript, index) => {
                  const isOwnMessage = transcript.peer_id === peerId;
                  const role = isOwnMessage
                    ? (userRole === 'agent' ? '상담사' : '고객')
                    : (userRole === 'agent' ? '고객' : '상담사');
                  const elapsedTime = getElapsedSeconds(transcript.receivedAt);

                  return (
                    <div key={index} className="conversation-item">
                      <div className="conversation-header">
                        <span className={`speaker ${isOwnMessage ? 'agent' : 'customer'}`}>
                          [{role}]
                        </span>
                        <span className="conversation-time">
                          {formatDuration(elapsedTime)}
                        </span>
                      </div>
                      <div className="conversation-text">
                        {transcript.text}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>

        {/* Right Sidebar: AI Assistance - 상담사만 표시 */}
        {userRole === 'agent' && (
          <aside className="sidebar-right">
            {/* 상담 가이드 생성 */}
            <div className="card ai-recommendation">
              <h2 className="card-title">상담 가이드 생성</h2>
              <p className="info-text">실시간 요약은 자동, 버튼을 눌러 가이드를 요청하세요.</p>
              <button
                className="btn btn-primary btn-block"
                onClick={handleConsultationRequest}
                disabled={consultationStatus === 'processing' || !isInRoom}
              >
                {consultationStatus === 'processing' ? '생성 중...' : '상담 가이드 생성'}
              </button>
              {consultationStatus === 'processing' && (
                <p className="status-text">가이드를 생성하는 중입니다...</p>
              )}
              {consultationStatus === 'error' && consultationError && (
                <p className="error-message">⚠️ {consultationError}</p>
              )}
              {consultationResult && (
                <div className="consultation-result">
                  <h3>가이드</h3>
                  {consultationResult.guide.length === 0 ? (
                    <p className="info-text">가이드가 비어 있습니다.</p>
                  ) : (
                    <ul>
                      {consultationResult.guide.map((item, idx) => (
                        <li key={idx}>{item}</li>
                      ))}
                    </ul>
                  )}
                  {consultationResult.recommendations?.length > 0 && (
                    <>
                      <h4>추천</h4>
                      <ul>
                        {consultationResult.recommendations.map((rec, idx) => (
                          <li key={idx}>{rec}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </div>
          </aside>
        )}
      </main>

      {/* Hidden Audio Element for Remote Stream */}
      <audio ref={remoteAudioRef} autoPlay />
    </div>
  );
}

export default AssistantMain;
