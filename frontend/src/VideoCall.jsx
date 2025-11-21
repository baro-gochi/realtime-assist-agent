/**
 * @fileoverview React 메인 앱 컴포넌트 - 룸 기반 화상 통화 UI
 *
 * @description
 * WebRTC 화상 통화 애플리케이션의 메인 컴포넌트입니다.
 * 사용자 인터페이스를 제공하고 WebRTCClient와 상호작용합니다.
 *
 * 주요 기능:
 * 1. 서버 연결 관리
 * 2. 룸 참가/퇴장
 * 3. 화상 통화 시작/종료
 * 4. 참가자 목록 표시
 * 5. 비디오 스트림 표시
 *
 * 화면 구성:
 * - 연결 전: 서버 연결 버튼
 * - 연결 후: 룸 참가 폼
 * - 룸 참가 후: 비디오 화면 + 컨트롤
 *
 * @see {WebRTCClient} WebRTC 클라이언트 클래스
 */

import { useState, useEffect, useRef } from 'react';
import { WebRTCClient } from './webrtc';
import './App.css';

/**
 * 화상 통화 메인 컴포넌트
 *
 * @component
 * @returns {JSX.Element} App 컴포넌트
 *
 * @description
 * WebRTC 화상 통화의 전체 UI를 관리하는 최상위 컴포넌트입니다.
 * React hooks를 사용하여 상태를 관리하고 사용자 인터랙션을 처리합니다.
 *
 * @example
 * // main.jsx에서 사용
 * import App from './App';
 * ReactDOM.createRoot(document.getElementById('root')).render(<App />);
 *
 * @tutorial
 * React Hooks 사용법:
 * - useState: 상태 값 저장 (예: 연결 상태, 룸 이름)
 * - useEffect: 컴포넌트 마운트 시 실행 (WebRTC 클라이언트 초기화)
 * - useRef: DOM 참조 저장 (비디오 엘리먼트) 또는 값 유지 (WebRTC 클라이언트)
 */
function VideoCall() {
  // 연결 상태 관리
  // @type {boolean} - 서버 연결 여부
  const [isConnected, setIsConnected] = useState(false);
  // @type {boolean} - 룸 참가 여부
  const [isInRoom, setIsInRoom] = useState(false);
  // @type {boolean} - 통화 활성화 여부
  const [isCallActive, setIsCallActive] = useState(false);

  // 룸 정보
  // @type {string} - 서버가 할당한 피어 ID
  const [peerId, setPeerId] = useState('');
  // @type {string} - 현재 룸 이름
  const [roomName, setRoomName] = useState('');
  // @type {string} - 사용자 닉네임
  const [nickname, setNickname] = useState('');
  // @type {string} - 현재 참가 중인 룸 이름 (실시간 업데이트)
  const [currentRoom, setCurrentRoom] = useState('');
  // @type {number} - 현재 룸의 참가자 수
  const [peerCount, setPeerCount] = useState(0);

  // 폼 입력값
  // @type {string} - 룸 이름 입력 필드
  const [roomInput, setRoomInput] = useState('');
  // @type {string} - 닉네임 입력 필드
  const [nicknameInput, setNicknameInput] = useState('');

  // 상태 정보
  // @type {string} - WebRTC 연결 상태 (new, connecting, connected, disconnected)
  const [connectionState, setConnectionState] = useState('');
  // @type {string} - 에러 메시지
  const [error, setError] = useState('');
  // @type {Array<{peer_id: string, nickname: string}>} - 참가자 목록
  const [participants, setParticipants] = useState([]);
  // @type {string} - 디버그 정보 (모바일에서 확인용)
  const [debugInfo, setDebugInfo] = useState('');
  // @type {boolean} - 오디오 활성화 상태
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);
  // @type {boolean} - 비디오 활성화 상태
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);
  // @type {Array<{peer_id: string, nickname: string, text: string, timestamp: number}>} - STT 인식 결과 목록
  const [transcripts, setTranscripts] = useState([]);

  // Ref 객체 (DOM 참조 및 인스턴스 유지)
  // @type {React.RefObject<HTMLVideoElement>} - 내 비디오 엘리먼트
  const localVideoRef = useRef(null);
  // @type {React.RefObject<HTMLVideoElement>} - 상대방 비디오 엘리먼트
  const remoteVideoRef = useRef(null);
  // @type {React.RefObject<HTMLDivElement>} - 트랜스크립트 컨테이너 (자동 스크롤용)
  const transcriptContainerRef = useRef(null);
  // @type {React.RefObject<WebRTCClient>} - WebRTC 클라이언트 인스턴스
  const webrtcClientRef = useRef(null);

  /**
   * 컴포넌트 마운트 시 WebRTC 클라이언트를 초기화합니다
   *
   * @description
   * useEffect 훅을 사용하여 컴포넌트가 처음 렌더링될 때 한 번만 실행됩니다.
   * WebRTC 클라이언트를 생성하고 모든 이벤트 핸들러를 등록합니다.
   *
   * 초기화 작업:
   * 1. WebRTCClient 인스턴스 생성
   * 2. 이벤트 핸들러 등록 (onPeerId, onRoomJoined 등)
   * 3. cleanup 함수 등록 (컴포넌트 언마운트 시 실행)
   *
   * @tutorial
   * useEffect의 dependency array가 빈 배열([])이면:
   * - 컴포넌트 마운트 시 한 번만 실행
   * - 컴포넌트 언마운트 시 cleanup 함수 실행
   * - 상태 변경 시 재실행되지 않음
   */
  useEffect(() => {
    // WebRTC 클라이언트 초기화
    // WebSocket URL을 동적으로 생성 (localtunnel 지원)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = window.location.hostname;
    const port = window.location.port;

    const locationInfo = {
      protocol: window.location.protocol,
      hostname: hostname,
      port: port,
      href: window.location.href
    };
    console.log('🔗 Location info:', locationInfo);

    // WebSocket URL 동적 생성
    // 터널 사용 시 (localtunnel/ngrok): wss://my-domain.loca.lt/ws
    // 로컬 개발: ws://localhost:8000/ws
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

    console.log('🔗 WebSocket URL:', wsUrl);
    setDebugInfo(`Host: ${hostname}\nWS URL: ${wsUrl}\nProtocol: ${window.location.protocol}`);
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
      console.log('📺 Remote stream received in App');
      console.log('📺 Stream tracks:', stream.getTracks().map(t => `${t.kind}:${t.id}:${t.readyState}`));

      if (remoteVideoRef.current) {
        // srcObject가 이미 같은 stream이면 재설정하지 않음
        if (remoteVideoRef.current.srcObject !== stream) {
          console.log('📺 Setting remote video srcObject');
          remoteVideoRef.current.srcObject = stream;

          // 비디오 엘리먼트 이벤트 리스너 추가 (디버깅용)
          remoteVideoRef.current.onloadedmetadata = () => {
            console.log('📺 Remote video metadata loaded');

            // 라이브 스트림 모드: 항상 최신 프레임 재생
            const video = remoteVideoRef.current;
            if (video.buffered.length > 0) {
              // 버퍼의 끝으로 이동 (최신 프레임)
              video.currentTime = video.buffered.end(video.buffered.length - 1);
            }

            // 명시적으로 play 호출
            video.play()
              .then(() => console.log('📺 Remote video play() succeeded'))
              .catch(err => console.error('📺 Remote video play() failed:', err));
          };
          remoteVideoRef.current.onplay = () => {
            console.log('📺 Remote video playing');
          };
          remoteVideoRef.current.onerror = (e) => {
            console.error('📺 Remote video error:', e);
          };
        } else {
          console.log('📺 srcObject already set, skipping');
        }
      } else {
        console.error('📺 remoteVideoRef.current is null!');
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
      console.log(`✅ STT 도착! "${data.text}" (${data.nickname})`);

      setTranscripts(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname,
        text: data.text,
        timestamp: data.timestamp || Date.now()
      }]);
    };

    // Cleanup on unmount
    return () => {
      if (client) {
        client.disconnect();
      }
    };
  }, []);

  /**
   * 트랜스크립트 추가 시 자동 스크롤
   */
  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop = transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  /**
   * 서버 연결 버튼 클릭 핸들러
   *
   * @async
   * @function handleConnect
   *
   * @description
   * 시그널링 서버에 WebSocket 연결을 시도합니다.
   * 연결 성공 시 isConnected 상태를 true로 변경하여 룸 참가 화면을 표시합니다.
   *
   * 실행 순서:
   * 1. 에러 메시지 초기화
   * 2. WebRTC 클라이언트의 connect() 호출
   * 3. 연결 성공 시 isConnected = true
   * 4. 실패 시 에러 메시지 표시
   *
   * @example
   * <button onClick={handleConnect}>서버에 연결</button>
   *
   * @tutorial
   * async/await 사용법:
   * - async 함수는 Promise를 반환
   * - await은 Promise가 완료될 때까지 대기
   * - try-catch로 에러 처리
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
   * 룸 참가 폼 제출 핸들러
   *
   * @async
   * @function handleJoinRoom
   * @param {Event} e - 폼 제출 이벤트
   *
   * @description
   * 사용자가 입력한 룸 이름과 닉네임으로 룸에 참가합니다.
   * 빈 값 체크 후 서버에 참가 요청을 보냅니다.
   *
   * 검증:
   * - 룸 이름과 닉네임이 비어있지 않아야 함
   * - 앞뒤 공백은 자동으로 제거 (trim)
   *
   * 실행 순서:
   * 1. 기본 폼 제출 동작 방지 (페이지 새로고침 방지)
   * 2. 입력값 검증
   * 3. WebRTC 클라이언트의 joinRoom() 호출
   * 4. 성공 시 roomName과 nickname 상태 업데이트
   *
   * @example
   * <form onSubmit={handleJoinRoom}>
   *   <input value={roomInput} onChange={...} />
   *   <button type="submit">참가</button>
   * </form>
   *
   * @tutorial
   * e.preventDefault()를 사용하는 이유:
   * - 폼 제출 시 페이지가 새로고침되는 것을 방지
   * - SPA(Single Page Application)에서 필수
   */
  const handleJoinRoom = async (e) => {
    e.preventDefault(); // 페이지 새로고침 방지

    // 입력값 검증
    if (!roomInput.trim() || !nicknameInput.trim()) {
      setError('Please enter both room name and nickname');
      return;
    }

    try {
      setError('');
      setTranscripts([]);  // 새 방에 입장하면 대화 내용 초기화
      await webrtcClientRef.current.joinRoom(roomInput.trim(), nicknameInput.trim());
      setRoomName(roomInput.trim());
      setNickname(nicknameInput.trim());
    } catch (err) {
      setError(`Failed to join room: ${err.message}`);
    }
  };

  /**
   * 통화 시작 버튼 클릭 핸들러
   *
   * @async
   * @function handleStartCall
   *
   * @description
   * 카메라/마이크 권한을 요청하고 화상 통화를 시작합니다.
   * 로컬 비디오를 화면에 표시하고 WebRTC 연결을 생성합니다.
   *
   * 실행 순서:
   * 1. WebRTC 클라이언트의 startCall() 호출
   *    - 카메라/마이크 권한 요청
   *    - 로컬 미디어 스트림 획득
   *    - RTCPeerConnection 생성
   *    - Offer 전송
   * 2. 로컬 비디오 엘리먼트에 스트림 연결
   * 3. isCallActive 상태를 true로 변경
   *
   * @example
   * <button onClick={handleStartCall}>통화 시작</button>
   *
   * @tutorial
   * video.srcObject란?
   * - HTMLVideoElement의 속성
   * - MediaStream을 비디오 엘리먼트에 연결
   * - 실시간 스트림을 화면에 표시
   */
  const handleStartCall = async () => {
    try {
      setError('');
      console.log('🎬 Start Call button clicked');

      // WebRTC 클라이언트 확인
      if (!webrtcClientRef.current) {
        throw new Error('WebRTC client not initialized');
      }

      console.log('📱 Requesting camera/microphone permissions...');

      // 카메라/마이크 권한 요청 및 WebRTC 연결 생성
      await webrtcClientRef.current.startCall();

      console.log('✅ Call started successfully');

      // 내 비디오를 화면에 표시
      if (localVideoRef.current && webrtcClientRef.current.localStream) {
        localVideoRef.current.srcObject = webrtcClientRef.current.localStream;
        console.log('📹 Local video attached');
      }

      setIsCallActive(true);
    } catch (err) {
      console.error('❌ Start call error:', err);
      const errorMsg = `Failed to start call: ${err.message}`;
      setError(errorMsg);
      alert(errorMsg); // 모바일에서 바로 볼 수 있도록 alert 추가
    }
  };

  /**
   * 룸 퇴장 버튼 클릭 핸들러
   *
   * @function handleLeaveRoom
   *
   * @description
   * 현재 룸에서 나가고 모든 관련 상태를 초기화합니다.
   * 비디오 스트림을 정지하고 UI를 초기 상태로 되돌립니다.
   *
   * 정리 작업:
   * 1. WebRTC 클라이언트의 leaveRoom() 호출
   *    - 서버에 퇴장 알림
   *    - 카메라/마이크 정지
   *    - WebRTC 연결 종료
   * 2. 비디오 엘리먼트 초기화
   * 3. 모든 룸 관련 상태 초기화
   *
   * @example
   * <button onClick={handleLeaveRoom}>룸 나가기</button>
   *
   * @tutorial
   * 상태 초기화가 중요한 이유:
   * - 다음 룸 참가를 위한 깨끗한 상태 준비
   * - 메모리 누수 방지
   * - UI 일관성 유지
   */
  const handleLeaveRoom = () => {
    // 룸 퇴장 및 통화 종료
    webrtcClientRef.current.leaveRoom();

    // 비디오 화면 초기화
    if (localVideoRef.current) {
      localVideoRef.current.srcObject = null;
    }
    if (remoteVideoRef.current) {
      remoteVideoRef.current.srcObject = null;
    }

    // 모든 룸 관련 상태 초기화
    setIsInRoom(false);
    setIsCallActive(false);
    setCurrentRoom('');
    setRoomName('');
    setNickname('');
    setPeerCount(0);
    setParticipants([]);
    setConnectionState('');
    setRoomInput('');
    setNicknameInput('');
  };

  /**
   * 서버 연결 끊기 버튼 클릭 핸들러
   *
   * @function handleDisconnect
   *
   * @description
   * 서버와의 연결을 완전히 끊고 앱을 초기 상태로 되돌립니다.
   * 모든 통화와 룸 참가 상태를 정리하고 연결 화면으로 돌아갑니다.
   *
   * 정리 작업:
   * 1. WebRTC 클라이언트의 disconnect() 호출
   *    - 룸 퇴장 (leaveRoom 포함)
   *    - WebSocket 연결 종료
   * 2. 비디오 엘리먼트 초기화
   * 3. 모든 상태를 초기값으로 리셋
   *
   * @example
   * <button onClick={handleDisconnect}>연결 끊기</button>
   *
   * @tutorial
   * disconnect vs leaveRoom 차이:
   * - leaveRoom: 룸만 나가고 서버 연결은 유지 (다른 룸 참가 가능)
   * - disconnect: 서버 연결까지 끊음 (완전 종료, 재연결 필요)
   */
  const handleDisconnect = () => {
    // 서버 연결 완전 종료
    webrtcClientRef.current.disconnect();

    // 비디오 화면 초기화
    if (localVideoRef.current) {
      localVideoRef.current.srcObject = null;
    }
    if (remoteVideoRef.current) {
      remoteVideoRef.current.srcObject = null;
    }

    // 모든 상태 완전 초기화 (연결 전 상태로)
    setIsConnected(false);
    setIsInRoom(false);
    setIsCallActive(false);
    setPeerId('');
    setCurrentRoom('');
    setRoomName('');
    setNickname('');
    setPeerCount(0);
    setParticipants([]);
    setTranscripts([]);  // 대화 내용 초기화
    setConnectionState('');
    setIsAudioEnabled(true);
    setIsVideoEnabled(true);
  };

  /**
   * 오디오 토글 핸들러
   */
  const handleToggleAudio = () => {
    const enabled = webrtcClientRef.current.toggleAudio();
    setIsAudioEnabled(enabled);
  };

  /**
   * 비디오 토글 핸들러
   */
  const handleToggleVideo = () => {
    const enabled = webrtcClientRef.current.toggleVideo();
    setIsVideoEnabled(enabled);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>WebRTC Video Call - Room Based</h1>
        {peerId && (
          <div className="peer-info">
            <span>Peer ID: {peerId}</span>
            {currentRoom && (
              <>
                <span> | Room: {currentRoom}</span>
                <span> | Participants: {peerCount}</span>
              </>
            )}
            {connectionState && (
              <span className="connection-state"> | Connection: {connectionState}</span>
            )}
          </div>
        )}
      </header>

      {debugInfo && (
        <div style={{
          background: '#f0f0f0',
          padding: '10px',
          margin: '10px',
          fontSize: '12px',
          fontFamily: 'monospace',
          whiteSpace: 'pre-wrap',
          border: '1px solid #ccc'
        }}>
          🐛 Debug Info:
          {debugInfo}
        </div>
      )}

      {error && (
        <div className="error-message">
          ⚠️ {error}
        </div>
      )}

      {/* Welcome Screen: Connect + Join Room */}
      {!isConnected && (
        <div className="welcome-screen">
          <div className="welcome-card">
            <h2>Welcome to Video Call</h2>
            <p>Connect to the signaling server to get started</p>
            <button onClick={handleConnect} className="btn btn-primary btn-large">
              Connect to Server
            </button>
          </div>
        </div>
      )}

      {/* Room Join Screen */}
      {isConnected && !isInRoom && (
        <div className="welcome-screen">
          <div className="welcome-card">
            <h2>Join a Room</h2>
            <form onSubmit={handleJoinRoom} className="join-form">
              <div className="form-group">
                <label htmlFor="room">Room Name</label>
                <input
                  id="room"
                  type="text"
                  placeholder="Enter room name"
                  value={roomInput}
                  onChange={(e) => setRoomInput(e.target.value)}
                  className="form-input"
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label htmlFor="nickname">Your Nickname</label>
                <input
                  id="nickname"
                  type="text"
                  placeholder="Enter your nickname"
                  value={nicknameInput}
                  onChange={(e) => setNicknameInput(e.target.value)}
                  className="form-input"
                />
              </div>
              <button type="submit" className="btn btn-success btn-large">
                Join Room
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Room View: Video Call */}
      {isInRoom && (
        <>
          <div className="room-info">
            <h3>Room: {currentRoom}</h3>
            <p>You are: {nickname}</p>
            {participants.length > 0 && (
              <div className="participants">
                <strong>Other participants:</strong>
                {participants.map(p => (
                  <span key={p.peer_id} className="participant-badge">
                    {p.nickname}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="video-container">
            <div className="video-box">
              <h3>Your Video</h3>
              <video
                ref={localVideoRef}
                autoPlay
                playsInline
                muted
                className="video-element"
              />
            </div>

            <div className="video-box">
              <h3>Remote Video</h3>
              <video
                ref={remoteVideoRef}
                autoPlay
                playsInline
                className="video-element"
                style={{ objectFit: 'cover' }}
              />
            </div>
          </div>

          {/* STT Transcript Section */}
          <div className="transcript-section">
            <h3>💬 Real-time Transcripts</h3>
            <div className="transcript-container" ref={transcriptContainerRef}>
              {transcripts.length === 0 ? (
                <p className="no-transcripts">음성 인식 결과가 여기에 표시됩니다...</p>
              ) : (
                transcripts.map((transcript, index) => (
                  <div key={index} className={`transcript-item ${transcript.peer_id === peerId ? 'own' : 'other'}`}>
                    <div className="transcript-header">
                      <span className="transcript-nickname">{transcript.nickname}</span>
                      <span className="transcript-time">
                        {new Date(transcript.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="transcript-text">{transcript.text}</div>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="controls">
            {!isCallActive ? (
              <button onClick={handleStartCall} className="btn btn-success">
                Start Call
              </button>
            ) : (
              <>
                <button onClick={handleToggleAudio} className={`btn ${isAudioEnabled ? 'btn-primary' : 'btn-secondary'}`}>
                  {isAudioEnabled ? '🎤 Mute' : '🔇 Unmute'}
                </button>
                <button onClick={handleToggleVideo} className={`btn ${isVideoEnabled ? 'btn-primary' : 'btn-secondary'}`}>
                  {isVideoEnabled ? '📹 Camera Off' : '📷 Camera On'}
                </button>
                <button onClick={handleLeaveRoom} className="btn btn-warning">
                  Leave Room
                </button>
              </>
            )}
            <button onClick={handleDisconnect} className="btn btn-danger">
              Disconnect
            </button>
          </div>

          <div className="info">
            <h3>Instructions</h3>
            <ol>
              <li>Click "Start Call" to begin video call (camera and microphone will be requested)</li>
              <li>Open this page in another tab/window with the same room name</li>
              <li>The server relays audio and video between peers in the same room</li>
            </ol>
          </div>
        </>
      )}
    </div>
  );
}

export default VideoCall;
