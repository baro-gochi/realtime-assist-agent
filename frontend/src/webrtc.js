/**
 * @fileoverview WebRTC 클라이언트 - 룸 기반 음성 통화 시스템
 *
 * @description
 * 이 파일은 WebRTC를 사용한 실시간 음성 통화 기능을 제공합니다.
 * 서버의 시그널링 서버와 통신하여 피어 간 연결을 설정하고 오디오를 주고받습니다.
 *
 * 연결 과정:
 * 1. WebSocket으로 시그널링 서버에 연결
 * 2. 룸(방)에 참가
 * 3. 마이크 권한 요청 및 로컬 오디오 획득
 * 4. RTCPeerConnection 생성 및 offer 전송
 * 5. 서버로부터 answer 수신
 * 6. ICE candidate 교환
 * 7. 오디오 스트림 송수신 시작
 *
 * @see {@link https://developer.mozilla.org/ko/docs/Web/API/WebRTC_API} WebRTC API 문서
 * @see {@link https://developer.mozilla.org/ko/docs/Web/API/WebSocket} WebSocket API 문서
 *
 * @example
 * // 기본 사용법
 * const client = new WebRTCClient('ws://localhost:8000/ws');
 *
 * // 이벤트 핸들러 등록
 * client.onRemoteStream = (stream) => {
 *   audioElement.srcObject = stream;
 * };
 *
 * // 연결 및 통화 시작
 * await client.connect();
 * await client.joinRoom('상담실1', '홍길동');
 * await client.startCall();
 */

import logger from './logger';

/**
 * WebRTC 클라이언트 클래스
 *
 * @class WebRTCClient
 * @description
 * 룸 기반 음성 통화를 위한 WebRTC 클라이언트입니다.
 * 시그널링 서버와 통신하여 다른 참가자들과 실시간으로 오디오를 주고받습니다.
 */

export class WebRTCClient {
  /**
   * WebRTCClient 생성자
   *
   * @constructor
   * @param {string} [signalingUrl='ws://localhost:8000/ws'] - 시그널링 서버의 WebSocket URL
   *
   * @description
   * WebRTC 클라이언트의 초기 상태를 설정합니다.
   * 모든 연결 관련 객체들을 null로 초기화하고, 이벤트 콜백 함수들을 준비합니다.
   *
   * @property {string} signalingUrl - 시그널링 서버 주소
   * @property {WebSocket|null} ws - WebSocket 연결 객체 (서버와 통신)
   * @property {RTCPeerConnection|null} pc - WebRTC 피어 연결 객체 (오디오 송수신)
   * @property {string|null} peerId - 서버가 할당한 고유 ID
   * @property {string|null} roomName - 현재 참가 중인 룸 이름
   * @property {string|null} nickname - 사용자 닉네임
   * @property {MediaStream|null} localStream - 내 마이크 스트림
   * @property {MediaStream} remoteStream - 상대방 마이크 스트림
   *
   * @property {Function|null} onPeerId - 피어 ID를 받았을 때 호출되는 콜백
   * @property {Function|null} onRoomJoined - 룸 참가 성공 시 호출되는 콜백
   * @property {Function|null} onUserJoined - 다른 사용자가 입장했을 때 호출되는 콜백
   * @property {Function|null} onUserLeft - 다른 사용자가 퇴장했을 때 호출되는 콜백
   * @property {Function|null} onRemoteStream - 상대방 미디어를 받았을 때 호출되는 콜백
   * @property {Function|null} onConnectionStateChange - 연결 상태 변경 시 호출되는 콜백
   * @property {Function|null} onError - 에러 발생 시 호출되는 콜백
   *
   * @example
   * // 기본 생성 (로컬 서버)
   * const client = new WebRTCClient();
   *
   * @example
   * // 다른 서버 주소 지정
   * const client = new WebRTCClient('wss://example.com/ws');
   *
   * @example
   * // 이벤트 핸들러 설정
   * const client = new WebRTCClient();
   * client.onPeerId = (id) => console.log('내 ID:', id);
   * client.onRemoteStream = (stream) => {
   *   document.getElementById('remoteAudio').srcObject = stream;
   * };
   */


  constructor(signalingUrl = 'ws://localhost:8000/ws', authToken = null) {
    this.signalingUrl = signalingUrl;
    this.authToken = authToken || sessionStorage.getItem('auth_token');
    this.ws = null;
    this.pc = null;
    this.peerId = null;
    this.roomName = null;
    this.nickname = null;
    this.localStream = null;
    this.remoteStream = new MediaStream();
    this.needsRenegotiation = false; // 재협상 필요 여부 플래그
    this.turnServers = null; // 캐시된 TURN 자격 증명

    // Event callbacks (이벤트가 발생했을 때 실행할 함수들)
    this.onPeerId = null;
    this.onRoomJoined = null;
    this.onUserJoined = null;
    this.onUserLeft = null;
    this.onRemoteStream = null;
    this.onConnectionStateChange = null;
    this.onError = null;
    this.onTranscript = null; // STT transcript 이벤트 콜백
    this.onLocalStream = null; // 로컬 스트림 획득 콜백
    this.onAgentConsultation = null; // 상담 가이드 결과
    this.onAgentStatus = null; // 상담 진행 상태
    this.onSessionEnded = null; // 세션 종료 결과 콜백

    // Prefetch TURN 자격 증명 on construction
    this.prefetchTurnCredentials();
  }

  /**
   * TURN 자격 증명을 백그라운드에서 미리 가져옵니다.
   *
   * @async
   * @description
   * TURN 서버 자격 증명을 가져옵니다. 백엔드에서 받아와 캐시합니다.
   * 백그라운드에서 동작하고 있어 createPeerConnection()에서 차단되지 않습니다.
   */
  async prefetchTurnCredentials() {
    try {
      // 환경변수 우선, 없으면 현재 호스트 사용
      const apiBase = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.host}`;
      const backendUrl = `${apiBase}/api/turn-credentials`;
      logger.debug('Prefetching TURN credentials from:', backendUrl);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const headers = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      if (this.authToken) {
        headers['Authorization'] = `Bearer ${this.authToken}`;
      }

      const response = await fetch(backendUrl, { signal: controller.signal, headers });
      clearTimeout(timeoutId);

      if (response.ok) {
        this.turnServers = await response.json();
        logger.debug('TURN credentials prefetched successfully');
      } else {
        logger.warn('Failed to prefetch TURN credentials, will use STUN only');
      }
    } catch (error) {
      logger.warn('Error prefetching TURN credentials:', error.message);
    }
  }

  /**
   * 시그널링을 위한 WebSocket 연결을 초기화합니다
   *
   * @async
   * @returns {Promise<void>} 연결 완료 시 resolve되는 Promise
   * @throws {Error} WebSocket 연결 실패 시 에러 발생
   *
   * @description
   * 시그널링 서버에 WebSocket으로 연결합니다.
   * 연결이 성공하면 서버로부터 메시지를 받을 수 있는 상태가 됩니다.
   *
   * WebSocket 이벤트 핸들러:
   * - onopen: 연결 성공
   * - onerror: 연결 오류
   * - onclose: 연결 종료
   * - onmessage: 서버로부터 메시지 수신
   *
   * @example
   * const client = new WebRTCClient();
   * try {
   *   await client.connect();
   *   console.log('서버에 연결되었습니다!');
   * } catch (error) {
   *   console.error('연결 실패:', error);
   * }
   *
   * @tutorial
   * 연결 순서:
   * 1. WebSocket 객체 생성
   * 2. 이벤트 핸들러 등록
   * 3. 연결 대기 (Promise)
   * 4. 연결 완료 또는 실패
   */
  async connect() {
    return new Promise((resolve, reject) => {
      // Append auth token to WebSocket URL if available
      let wsUrl = this.signalingUrl;
      if (this.authToken) {
        const separator = wsUrl.includes('?') ? '&' : '?';
        wsUrl = `${wsUrl}${separator}token=${encodeURIComponent(this.authToken)}`;
      }
      logger.debug('Attempting to connect to:', wsUrl);

      try {
        this.ws = new WebSocket(wsUrl);
      } catch (error) {
        logger.error('Failed to create WebSocket:', error);
        reject(new Error(`Failed to create WebSocket: ${error.message}`));
        return;
      }

      this.ws.onopen = () => {
        logger.info('WebSocket connected successfully');
        resolve();
      };

      this.ws.onerror = (error) => {
        logger.error('WebSocket error:', error);
        logger.debug('WebSocket readyState:', this.ws.readyState);
        if (this.onError) this.onError(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
        reject(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
      };

      this.ws.onclose = (event) => {
        logger.info('WebSocket closed');
        logger.debug('Close code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);

        // Handle authentication failure
        if (event.code === 4001) {
          logger.error('Authentication failed - unauthorized');
          sessionStorage.removeItem('auth_token');
          if (this.onError) this.onError(new Error('Unauthorized - please re-login'));
          window.location.reload();
        }
      };

      this.ws.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          await this.handleSignalingMessage(message);
        } catch (error) {
          logger.error('Error handling signaling message:', error);
          if (this.onError) this.onError(error);
        }
      };
    });
  }

  /**
   * 서버로부터 받은 시그널링 메시지를 처리합니다
   *
   * @async
   * @param {Object} message - 서버가 보낸 메시지 객체
   * @param {string} message.type - 메시지 타입 (예: 'peer_id', 'room_joined', 'answer' 등)
   * @param {Object} message.data - 메시지 데이터
   *
   * @description
   * 서버로부터 받은 메시지들을 처리합니다.
   * 각 메시지 타입에 따라 다른 동작을 수행합니다.
   *
   * 처리 메시지 타입:
   * - peer_id: 서버가 할당한 나의 고유 ID
   * - room_joined: 룸 참가 성공 알림
   * - user_joined: 다른 사용자 입장 알림
   * - user_left: 다른 사용자 퇴장 알림
   * - answer: WebRTC answer (연결 응답)
   * - error: 서버 에러 메시지
   *
   * @example
   * // 내부적으로 WebSocket의 onmessage에서 호출됨
   * ws.onmessage = async (event) => {
   *   const message = JSON.parse(event.data);
   *   await this.handleSignalingMessage(message);
   * };
   */
  async handleSignalingMessage(message) {
    const { type, data } = message;

    switch (type) {
      case 'peer_id':
        this.peerId = data.peer_id;
        logger.debug('Received peer ID:', this.peerId);
        if (this.onPeerId) this.onPeerId(this.peerId);
        break;

      case 'room_joined':
        logger.info('Joined room:', data.room_name);
        if (this.onRoomJoined) {
          this.onRoomJoined(data);
        }
        break;

      case 'user_joined':
        logger.info('User joined:', data.nickname);
        if (this.onUserJoined) {
          this.onUserJoined(data);
        }
        break;

      case 'user_left':
        logger.info('User left:', data.nickname);
        if (this.onUserLeft) {
          this.onUserLeft(data);
        }
        break;

      case 'answer':
        logger.debug('Received answer from server');
        await this.handleAnswer(data);
        break;

      case 'ice_candidate':
        logger.debug('Received ICE candidate from server');
        await this.handleIceCandidate(data);
        break;

      case 'renegotiation_needed':
        logger.debug('Renegotiation needed:', data.reason);
        // CRITICAL: Wait for connection to be established before renegotiating
        // Renegotiating too early causes ICE transport to close prematurely
        if (this.pc && this.pc.connectionState === 'connected') {
          logger.debug('Connection ready, renegotiating now');
          await this.renegotiate();
        } else {
          logger.debug('Deferring renegotiation - connection not ready (state:', this.pc?.connectionState || 'no pc', ')');
          this.needsRenegotiation = true;
        }
        break;

      case 'transcript':
        logger.debug('Transcript received');
        if (this.onTranscript) {
          this.onTranscript(data);
        }
        break;

      case 'agent_ready':
        logger.debug('Agent ready');
        if (this.onAgentReady) {
          this.onAgentReady(data);
        }
        break;

      case 'agent_update':
        logger.debug('Agent update - node:', message.node);
        if (this.onAgentUpdate) {
          this.onAgentUpdate({
            turnId: message.turn_id,
            node: message.node,
            data: message.data
          });
        }
        break;

      case 'agent_status':
        logger.debug('Agent status:', data.status);
        if (this.onAgentStatus) this.onAgentStatus(data);
        break;

      case 'agent_consultation':
        logger.debug('Agent consultation result received');
        if (this.onAgentConsultation) this.onAgentConsultation(data);
        break;

      case 'agent_error':
        logger.error('Agent error:', data);
        if (this.onAgentStatus) this.onAgentStatus({ task: data.task, status: 'error' });
        if (this.onError) this.onError(new Error(data.message || 'Agent error'));
        break;

      case 'session_ended':
        logger.info('Session ended');
        if (this.onSessionEnded) {
          this.onSessionEnded(data);
        }
        break;

      case 'error':
        logger.error('Server error:', data.message);
        if (this.onError) this.onError(new Error(data.message));
        break;

      default:
        logger.warn('Unknown message type:', type);
    }
  }

  /**
   * 특정 룸(방)에 참가합니다
   *
   * @async
   * @param {string} roomName - 참가할 룸의 이름
   * @param {string} nickname - 사용자 닉네임 (다른 참가자들에게 표시됨)
   * @throws {Error} WebSocket이 연결되지 않았으면 에러 발생
   *
   * @description
   * 지정된 이름의 룸에 참가 요청을 보냅니다.
   * 룸이 존재하지 않으면 자동으로 생성됩니다.
   * 같은 룸에 있는 다른 참가자들과 음성 통화를 할 수 있게 됩니다.
   *
   * @example
   * const client = new WebRTCClient();
   * await client.connect();
   * await client.joinRoom('상담실1', '홍길동');
   * // '상담실1'이라는 룸에 '홍길동'이라는 이름으로 입장
   *
   * @tutorial
   * 룸(Room)이란?
   * - 가상의 회의실 같은 개념
   * - 같은 룸에 있는 사람들끼리만 통화 가능
   * - 여러 룸을 동시에 운영 가능
   * - 빈 룸은 자동으로 삭제됨
   */
  async joinRoom(roomName, nickname, phoneNumber = null, agentCode = null) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    this.roomName = roomName;
    this.nickname = nickname;

    const joinData = {
      room_name: roomName,
      nickname: nickname
    };

    // 고객인 경우 전화번호 추가
    if (phoneNumber) {
      joinData.phone_number = phoneNumber;
    }

    // 상담사인 경우 상담사 코드 추가
    if (agentCode) {
      joinData.agent_code = agentCode;
    }

    logger.debug('[WebRTC] joinRoom data:', { room_name: roomName, nickname });
    this.sendMessage('join_room', joinData);

    logger.info(`Joining room '${roomName}' as '${nickname}'`);
  }

  /**
   * 로컬 오디오 스트림을 획득합니다 (마이크)
   *
   * @async
   * @returns {Promise<MediaStream>} 로컬 오디오 스트림
   * @throws {Error} 미디어 접근 권한이 없거나 기기가 없으면 에러 발생
   *
   * @description
   * 사용자의 마이크에 접근하여 오디오 스트림을 가져옵니다.
   * 처음 실행 시 브라우저가 권한을 요청합니다.
   *
   * 오디오 설정:
   *   - echoCancellation: 에코 제거 (내 소리가 다시 들리는 현상 방지)
   *   - noiseSuppression: 배경 소음 제거
   *   - autoGainControl: 음량 자동 조절
   *
   * @example
   * const client = new WebRTCClient();
   * try {
   *   const stream = await client.getLocalMedia();
   *   audioElement.srcObject = stream; // 오디오 요소에 연결
   * } catch (error) {
   *   if (error.name === 'NotAllowedError') {
   *     alert('마이크 권한이 필요합니다');
   *   }
   * }
   *
   * @tutorial
   * 주의사항:
   * - HTTPS 또는 localhost에서만 작동 (보안상의 이유)
   * - 사용자가 권한을 거부하면 에러 발생
   * - 마이크가 다른 앱에서 사용 중이면 실패할 수 있음
   */
  async getLocalMedia() {
    try {
      logger.debug('Requesting microphone permissions...');
      logger.debug('Secure context:', window.isSecureContext);

      this.localStream = await navigator.mediaDevices.getUserMedia({
        video: false,
        audio: {
          sampleRate: 48000,           // 48kHz 샘플레이트 (Opus 권장)
          channelCount: 1,             // 모노 (음성 통화)
          autoGainControl: true,       // 볼륨 자동 조절
          echoCancellation: false,     // 에코 제거 끄기
          noiseSuppression: false,     // 노이즈 제거 끄기
        }
      });
      logger.info('Local audio stream obtained');
      logger.debug('Audio tracks:', this.localStream.getAudioTracks().length);
      return this.localStream;
    } catch (error) {
      logger.error('Error getting local media:', error.name, error.message);

      // Show user-friendly error
      let userMessage = '마이크 접근 실패: ';
      if (error.name === 'NotAllowedError') {
        userMessage += '권한이 거부되었습니다. 마이크 접근을 허용해주세요.';
      } else if (error.name === 'NotFoundError') {
        userMessage += '마이크를 찾을 수 없습니다.';
      } else if (error.name === 'NotReadableError') {
        userMessage += '마이크가 다른 앱에서 사용 중입니다.';
      } else if (error.name === 'NotSecureError' || !window.isSecureContext) {
        userMessage += 'HTTPS 연결이 필요합니다.';
      } else {
        userMessage += error.message;
      }

      alert(userMessage);
      if (this.onError) this.onError(new Error(userMessage));
      throw error;
    }
  }

  /**
   * 피어 연결을 생성하고 offer를 서버에 전송합니다
   *
   * @async
   *
   * @description
   * WebRTC의 핵심인 RTCPeerConnection 객체를 생성합니다.
   * 이 연결을 통해 실제 오디오가 전송됩니다.
   *
   * 주요 작업:
   * 1. RTCPeerConnection 생성 (STUN 서버 설정)
   * 2. 로컬 미디어 트랙 추가
   * 3. 이벤트 핸들러 등록:
   *    - ontrack: 상대방 미디어 수신
   *    - onicecandidate: 네트워크 경로 정보 생성
   *    - onconnectionstatechange: 연결 상태 변경
   * 4. SDP Offer 생성 및 전송
   *
   * @example
   * await client.getLocalMedia(); // 먼저 로컬 미디어 획득
   * await client.createPeerConnection(); // 그 다음 피어 연결 생성
   *
   * @tutorial
   * STUN 서버란?
   * - 공인 IP 주소를 알려주는 서버
   * - Google의 무료 STUN 서버 사용
   * - NAT 뒤에 있는 컴퓨터들이 통신할 수 있게 도와줌
   *
   * SDP Offer란?
   * - "이런 미디어를 보낼 수 있어요"라는 제안
   * - 지원하는 코덱, 해상도 등의 정보 포함
   * - 상대방이 answer로 응답함
   */
  async createPeerConnection() {
    // Use prefetched TURN credentials from AWS coturn or fetch if not available
    let iceServers = [
      // Google STUN server
      { urls: 'stun:stun.l.google.com:19302' }
    ];

    // Use cached AWS coturn credentials if available
    if (this.turnServers) {
      iceServers = iceServers.concat(this.turnServers);
      logger.debug('Using prefetched AWS coturn credentials');
    } else {
      logger.warn('AWS coturn credentials not prefetched yet, using Google STUN only');
    }

    // Create RTCPeerConnection with fetched ICE servers
    // Use all available connection methods (STUN + TURN)
    this.pc = new RTCPeerConnection({iceServers});

    // Add local tracks to peer connection
    if (this.localStream) {
      this.localStream.getTracks().forEach(track => {
        this.pc.addTrack(track, this.localStream);
        logger.debug('Added local track:', track.kind);
      });
    }

    // Handle remote tracks
    this.pc.ontrack = (event) => {
      logger.debug('Received remote track:', event.track.kind);

      // 오디오 재생 지연 버퍼 설정 (패킷 손실/지터로 인한 끊김 방지)
      if (event.receiver && event.track.kind === 'audio') {
        event.receiver.playoutDelayHint = 0.05; // 50ms 재생 지연
        if ('jitterBufferTarget' in event.receiver) {
          event.receiver.jitterBufferTarget = 50;
        }
        logger.debug('Audio jitter buffer configured');
      }

      // Add only the received track (not all tracks from stream)
      const track = event.track;

      // 기존 같은 종류의 트랙이 있으면 제거
      const existingTracks = this.remoteStream.getTracks().filter(t => t.kind === track.kind);
      existingTracks.forEach(t => {
        this.remoteStream.removeTrack(t);
      });

      this.remoteStream.addTrack(track);
      logger.debug('Track added to remoteStream:', track.kind);

      // 오디오 트랙이 있으면 콜백 호출
      const hasAudio = this.remoteStream.getTracks().some(t => t.kind === 'audio');

      if (hasAudio && this.onRemoteStream) {
        logger.debug('Audio track received, calling onRemoteStream callback');
        this.onRemoteStream(this.remoteStream);
      }
    };

    // Handle ICE candidates
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        logger.debug('New ICE candidate');
        this.sendMessage('ice_candidate', {
          candidate: event.candidate.toJSON()
        });
      }
    };

    // Handle connection state changes
    this.pc.onconnectionstatechange = () => {
      const state = this.pc.connectionState;
      logger.info('Connection state:', state);

      if (this.onConnectionStateChange) {
        this.onConnectionStateChange(state);
      }

      // Execute deferred renegotiation when connection is established
      if (state === 'connected' && this.needsRenegotiation) {
        logger.debug('Executing deferred renegotiation');
        this.needsRenegotiation = false;
        this.renegotiate();
      }
    };

    // Create and send offer
    const offer = await this.pc.createOffer();

    // DTX(Discontinuous Transmission) 비활성화
    // 침묵 구간에서도 패킷을 계속 전송하여 jitter buffer 안정화
    offer.sdp = this.disableDTX(offer.sdp);

    await this.pc.setLocalDescription(offer);

    logger.debug('Sending offer to server');
    this.sendMessage('offer', {
      sdp: offer.sdp,
      type: offer.type
    });

    // NOTE: Don't process buffered candidates here!
    // They need to wait until remote description is set (after receiving answer)
  }

  /**
   * 서버로부터 받은 answer를 처리합니다
   *
   * @async
   * @param {Object} answer - WebRTC answer 객체
   * @param {string} answer.sdp - Session Description Protocol 데이터
   * @param {string} answer.type - "answer" 타입 지정
   *
   * @description
   * 서버가 보낸 answer를 받아서 원격 연결 정보를 설정합니다.
   * 이 과정이 완료되면 ICE candidate 교환이 시작되고,
   * 최종적으로 미디어 전송이 가능해집니다.
   *
   * @example
   * // 내부적으로 handleSignalingMessage에서 호출됨
   * case 'answer':
   *   await this.handleAnswer(data);
   *   break;
   *
   * @tutorial
   * SDP Answer란?
   * - Offer에 대한 응답
   * - "나는 이런 미디어를 받을 수 있어요"
   * - Offer-Answer 교환 후 실제 미디어 전송 시작
   */
  async handleAnswer(answer) {
    try {
      // Check if we have a peer connection
      if (!this.pc) {
        logger.warn('No peer connection exists, ignoring answer');
        return;
      }

      // Check current signaling state
      logger.debug('Current signaling state:', this.pc.signalingState);

      // Check if answer SDP contains ICE candidates
      const candidateCount = (answer.sdp.match(/a=candidate:/g) || []).length;
      logger.debug(`Answer SDP contains ${candidateCount} ICE candidates`);
      if (candidateCount === 0) {
        logger.warn('Answer SDP has NO ICE candidates! Backend ICE gathering may have failed.');
      }

      // Only set remote description if we're in the correct state
      // We should be in 'have-local-offer' state to receive an answer
      if (this.pc.signalingState === 'have-local-offer') {
        // Answer SDP에도 동일한 Opus 설정 적용 (bitrate 등)
        const modifiedAnswer = {
          type: answer.type,
          sdp: this.disableDTX(answer.sdp)
        };

        await this.pc.setRemoteDescription(
          new RTCSessionDescription(modifiedAnswer)
        );
        logger.debug('Remote description set, state:', this.pc.signalingState);

        // NOW process buffered ICE candidates (remote description is set)
        if (this.pendingCandidates && this.pendingCandidates.length > 0) {
          logger.debug(`Processing ${this.pendingCandidates.length} buffered ICE candidates`);
          for (const candidateData of this.pendingCandidates) {
            await this.handleIceCandidate(candidateData);
          }
          this.pendingCandidates = [];
        }
      } else if (this.pc.signalingState === 'stable') {
        logger.warn('Already in stable state, ignoring duplicate answer');
      } else {
        logger.warn(`Unexpected state ${this.pc.signalingState}, cannot set answer`);
      }
    } catch (error) {
      logger.error('Error setting remote description:', error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * 서버로부터 받은 ICE candidate를 처리합니다
   *
   * @async
   * @param {Object} candidateData - ICE candidate 객체
   *
   * @description
   * 서버가 중계한 다른 피어의 ICE candidate를 받아서
   * 로컬 RTCPeerConnection에 추가합니다.
   * ICE candidate는 네트워크 경로 정보를 담고 있으며,
   * 양쪽이 모두 교환해야 연결이 완료됩니다.
   *
   * @example
   * // 내부적으로 handleSignalingMessage에서 호출됨
   * case 'ice_candidate':
   *   await this.handleIceCandidate(data);
   *   break;
   */
  async handleIceCandidate(candidateData) {
    try {
      if (!candidateData.candidate) {
        logger.warn('Received empty ICE candidate, ignoring');
        return;
      }

      // If peer connection doesn't exist yet OR remote description not set, buffer the candidate
      if (!this.pc || !this.pc.remoteDescription) {
        logger.debug('Buffering ICE candidate (remote description not ready yet)');
        if (!this.pendingCandidates) {
          this.pendingCandidates = [];
        }
        this.pendingCandidates.push(candidateData);
        return;
      }

      // Create RTCIceCandidate from the data
      // Check if candidateData is nested (has .candidate property that is an object)
      const candidateInit = typeof candidateData.candidate === 'object'
        ? candidateData.candidate
        : candidateData;

      const iceCandidate = new RTCIceCandidate(candidateInit);

      await this.pc.addIceCandidate(iceCandidate);
      logger.debug('ICE candidate added');
    } catch (error) {
      logger.error('Error adding ICE candidate:', error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * 시그널링 서버에 메시지를 전송합니다
   *
   * @param {string|Object} typeOrMessage - 메시지 타입 문자열 또는 {type, data} 형태의 메시지 객체
   * @param {Object} [data] - 메시지 데이터 (첫 번째 인자가 문자열인 경우)
   *
   * @description
   * WebSocket을 통해 서버에 JSON 형식의 메시지를 보냅니다.
   * WebSocket이 열려있지 않으면 에러 로그만 출력하고 무시합니다.
   *
   * 두 가지 호출 방식을 지원합니다:
   * 1. sendMessage('type', { data }) - 기존 방식
   * 2. sendMessage({ type: 'type', data: { data } }) - 객체 방식
   *
   * @example
   * // 기존 방식
   * this.sendMessage('join_room', {
   *   room_name: '상담실1',
   *   nickname: '홍길동'
   * });
   *
   * @example
   * // 객체 방식
   * this.sendMessage({
   *   type: 'enable_dual_stt',
   *   data: { enabled: true }
   * });
   */
  sendMessage(typeOrMessage, data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      let message;
      if (typeof typeOrMessage === 'string') {
        // 기존 방식: sendMessage('type', { data })
        message = { type: typeOrMessage, data };
      } else {
        // 객체 방식: sendMessage({ type, data })
        message = typeOrMessage;
      }
      this.ws.send(JSON.stringify(message));
      logger.debug('Sent message:', message.type);
    } else {
      logger.warn('WebSocket not connected, cannot send message');
    }
  }

  /**
   * 상담 가이드 에이전트 태스크 요청을 전송합니다.
   * @param {string} roomName
   * @param {object} userOptions
   */
  sendConsultationTask(roomName, userOptions = {}) {
    this.sendMessage('agent_task', {
      task: 'consultation',
      room_name: roomName,
      user_options: userOptions
    });
  }

  /**
   * 상담 세션을 종료하고 데이터를 저장합니다.
   * @returns {Promise<{success: boolean, session_id: string|null, message: string}>}
   */
  endSession() {
    return new Promise((resolve) => {
      // Set up one-time handler for session_ended response
      const originalHandler = this.onSessionEnded;
      let timeoutId = null;

      this.onSessionEnded = (data) => {
        // Clear timeout to prevent race condition
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
        // Restore original handler
        this.onSessionEnded = originalHandler;
        if (originalHandler) originalHandler(data);
        resolve(data);
      };

      // Set timeout for response (30 seconds to allow LLM summary generation)
      timeoutId = setTimeout(() => {
        this.onSessionEnded = originalHandler;
        resolve({
          success: false,
          session_id: null,
          message: 'Session end request timed out'
        });
      }, 30000);

      // Send end_session message
      this.sendMessage('end_session', {});
    });
  }

  /**
   * 피어 연결을 재협상합니다 (새 피어가 입장했을 때)
   *
   * @async
   *
   * @description
   * 새로운 피어가 룸에 입장하면 기존 피어들이 새 피어의 트랙을 받기 위해
   * 재협상을 수행합니다. 새로운 offer를 생성하여 서버에 전송합니다.
   *
   * @example
   * // 서버로부터 renegotiation_needed 메시지를 받으면 자동 호출됨
   * case 'renegotiation_needed':
   *   await this.renegotiate();
   *   break;
   */
  async renegotiate() {
    try {
      if (!this.pc) {
        logger.warn('No peer connection to renegotiate');
        return;
      }

      logger.debug('Creating new offer for renegotiation');

      // Create new offer
      const offer = await this.pc.createOffer();

      // DTX 비활성화 적용
      offer.sdp = this.disableDTX(offer.sdp);

      await this.pc.setLocalDescription(offer);

      // Send new offer to server
      this.sendMessage('offer', {
        sdp: offer.sdp,
        type: offer.type
      });

      logger.debug('Renegotiation offer sent');
    } catch (error) {
      logger.error('Error during renegotiation:', error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * 통화를 시작합니다 (오디오 획득 + 피어 연결 생성)
   *
   * @async
   * @throws {Error} 오디오 획득 또는 연결 생성 실패 시 에러 발생
   *
   * @description
   * 음성 통화를 시작하기 위한 모든 과정을 순서대로 실행합니다.
   * 이 메서드 하나로 통화 준비를 완료할 수 있습니다.
   *
   * 실행 순서:
   * 1. getLocalMedia(): 마이크 권한 요청 및 스트림 획득
   * 2. createPeerConnection(): WebRTC 연결 생성 및 offer 전송
   *
   * @example
   * const client = new WebRTCClient();
   * await client.connect();
   * await client.joinRoom('상담실1', '홍길동');
   *
   * await client.startCall();
   */
  async startCall() {
    try {
      await this.getLocalMedia();
      await this.createPeerConnection();
    } catch (error) {
      logger.error('Error starting call:', error);
      if (this.onError) this.onError(error);
      throw error;
    }
  }

  /**
   * 현재 룸에서 퇴장합니다
   *
   * @description
   * 룸에서 나가고 통화를 종료합니다.
   * 서버에 퇴장 메시지를 보내고 로컬 리소스를 정리합니다.
   *
   * 정리 작업:
   * - 서버에 'leave_room' 메시지 전송
   * - stopCall() 호출 (미디어 및 연결 정리)
   * - 룸 정보 초기화
   *
   * @example
   * client.leaveRoom();
   * // 이제 다른 룸에 참가하거나 연결을 종료할 수 있음
   *
   * @see {stopCall} 미디어 및 연결 정리
   */
  leaveRoom() {
    if (this.roomName) {
      this.sendMessage('leave_room', {});
      this.stopCall();
      this.roomName = null;
      this.nickname = null;
    }
  }

  /**
   * 통화를 중단하고 모든 리소스를 정리합니다
   *
   * @description
   * 오디오 스트림과 WebRTC 연결을 모두 종료합니다.
   * 메모리 누수를 방지하기 위해 모든 리소스를 해제합니다.
   *
   * 정리 항목:
   * 1. 로컬 오디오 트랙 정지 (마이크 LED 꺼짐)
   * 2. 로컬 스트림 객체 제거
   * 3. RTCPeerConnection 종료
   * 4. 원격 스트림 정리
   *
   * @example
   * client.stopCall();
   * // 마이크가 꺼지고 통화가 완전히 종료됨
   */
  stopCall() {
    // Stop local tracks
    if (this.localStream) {
      this.localStream.getTracks().forEach(track => track.stop());
      this.localStream = null;
    }

    // Close peer connection
    if (this.pc) {
      this.pc.close();
      this.pc = null;
    }

    // Clear remote stream
    this.remoteStream.getTracks().forEach(track => track.stop());
    this.remoteStream = new MediaStream();

    logger.info('Call stopped');
  }

  /**
   * 시그널링 서버와의 연결을 끊습니다
   *
   * @description
   * WebSocket 연결을 종료하고 모든 리소스를 정리합니다.
   * 앱을 완전히 종료하거나 다시 시작할 때 사용합니다.
   *
   * 종료 순서:
   * 1. leaveRoom() - 룸 퇴장 및 통화 종료
   * 2. WebSocket 연결 종료
   * 3. 연결 객체 null로 초기화
   *
   * @example
   * // 앱 종료 또는 페이지 이탈 시
   * window.addEventListener('beforeunload', () => {
   *   client.disconnect();
   * });
   *
   * @example
   * // 사용자가 "나가기" 버튼 클릭 시
   * function handleExit() {
   *   client.disconnect();
   *   navigate('/'); // 메인 페이지로 이동
   * }
   */
  disconnect() {
    this.leaveRoom();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    logger.info('Disconnected');
  }

  /**
   * 로컬 오디오 스트림을 시작합니다 (마이크).
   *
   * @async
   * @param {Object} constraints - MediaStream 제약 조건
   * @param {boolean} [constraints.audio=true] - 오디오 활성화 여부
   * @returns {Promise<MediaStream>} 로컬 오디오 스트림
   */
  async startLocalStream(constraints = { audio: true, video: false }) {
    try {
      this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
      logger.debug('Local stream started:', this.localStream.getTracks().map(t => t.kind));

      // 로컬 스트림 콜백 호출
      if (this.onLocalStream) {
        this.onLocalStream(this.localStream);
      }

      // 이미 연결된 상태라면 트랙 추가 및 재협상
      if (this.pc && this.ws && this.roomName) {
        this.localStream.getTracks().forEach(track => {
          this.pc.addTrack(track, this.localStream);
        });
        // Offer 재전송
        await this.sendOffer();
      }

      return this.localStream;
    } catch (error) {
      logger.error('Failed to start local stream:', error);
      throw error;
    }
  }

  /**
   * 로컬 미디어 스트림을 중지합니다.
   */
  stopLocalStream() {
    if (this.localStream) {
      this.localStream.getTracks().forEach(track => {
        track.stop();
      });
      this.localStream = null;
      logger.debug('Local stream stopped');
    }
  }

  /**
   * 오디오 트랙을 토글합니다 (음소거/음소거 해제)
   *
   * @returns {boolean} 오디오 활성화 상태 (true: 켜짐, false: 꺼짐)
   */
  toggleAudio() {
    if (this.localStream) {
      const audioTracks = this.localStream.getAudioTracks();
      if (audioTracks.length > 0) {
        const enabled = !audioTracks[0].enabled;
        audioTracks.forEach(track => {
          track.enabled = enabled;
        });
        logger.debug(`Audio ${enabled ? 'enabled' : 'disabled'}`);
        return enabled;
      }
    }
    return false;
  }

  /**
   * 현재 오디오 활성화 상태를 반환합니다
   *
   * @returns {boolean} true: 오디오 켜짐, false: 오디오 꺼짐
   */
  isAudioEnabled() {
    if (this.localStream) {
      const audioTracks = this.localStream.getAudioTracks();
      return audioTracks.length > 0 && audioTracks[0].enabled;
    }
    return false;
  }

  /**
   * 오디오 송신 bitrate를 직접 설정합니다
   *
   * @async
   * @param {number} bitrate - 목표 bitrate (bps)
   *
   * @description
   * RTCRtpSender.setParameters()를 사용하여 인코더 bitrate를 직접 제어합니다.
   * SDP의 maxaveragebitrate는 수신측에 대한 힌트일 뿐이고,
   * 실제 송신 bitrate는 이 방법으로 설정해야 합니다.
   */
  async setAudioBitrate(bitrate) {
    if (!this.pc) {
      logger.warn('PeerConnection not available for bitrate setting');
      return;
    }

    const senders = this.pc.getSenders();
    const audioSender = senders.find(s => s.track?.kind === 'audio');

    if (!audioSender) {
      logger.warn('No audio sender found for bitrate setting');
      return;
    }

    try {
      const params = audioSender.getParameters();

      // encodings 배열이 없으면 생성
      if (!params.encodings || params.encodings.length === 0) {
        params.encodings = [{}];
      }

      // maxBitrate 설정 (bps 단위)
      params.encodings[0].maxBitrate = bitrate;

      await audioSender.setParameters(params);
      logger.debug(`Audio bitrate set to ${bitrate}bps`);
    } catch (error) {
      logger.error('Failed to set audio bitrate:', error);
    }
  }

  /**
   * SDP에서 Opus DTX(Discontinuous Transmission)를 비활성화합니다
   *
   * @param {string} sdp - 원본 SDP 문자열
   * @returns {string} DTX가 비활성화된 SDP 문자열
   *
   * @description
   * DTX가 활성화되면 침묵 구간에서 패킷 전송이 중단되어
   * 수신측 jitter buffer가 불안정해지고 로봇 소리가 발생할 수 있습니다.
   * usedtx=0을 설정하여 침묵 구간에서도 comfort noise 패킷을 전송합니다.
   *
   * @example
   * offer.sdp = this.disableDTX(offer.sdp);
   */
  disableDTX(sdp) {
    // Opus 코덱의 fmtp 라인을 찾아서 최적화 설정 추가
    // 로봇 소리 방지를 위한 설정:
    // - usedtx=0: DTX 비활성화 (침묵 시에도 패킷 전송)
    // - cbr=1: 고정 비트레이트 (jitter buffer 안정화)
    // - maxaveragebitrate=48000: 48kbps 고정 (품질 보장)
    // - ptime=20: 20ms 패킷 크기 (표준)
    const lines = sdp.split('\r\n');
    const modifiedLines = lines.map(line => {
      // Opus fmtp 라인 찾기 (보통 payload type 111)
      if (line.startsWith('a=fmtp:') && line.includes('minptime')) {
        // usedtx=0 (DTX 비활성화)
        if (line.includes('usedtx=')) {
          line = line.replace(/usedtx=\d/, 'usedtx=0');
        } else {
          line += ';usedtx=0';
        }

        // cbr=1 (고정 비트레이트 - jitter 감소)
        if (!line.includes('cbr=')) {
          line += ';cbr=1';
        }

        // maxaveragebitrate (48kbps - 음성 품질 향상)
        if (line.includes('maxaveragebitrate=')) {
          line = line.replace(/maxaveragebitrate=\d+/, 'maxaveragebitrate=48000');
        } else {
          line += ';maxaveragebitrate=48000';
        }

        // stereo 설정 (모노)
        if (!line.includes('stereo=')) {
          line += ';stereo=0;sprop-stereo=0';
        }

        logger.debug('Opus optimized in SDP');
      }

      // ptime 설정 (20ms 패킷 - 표준적이고 안정적)
      if (line.startsWith('a=ptime:')) {
        line = 'a=ptime:20';
      }

      return line;
    });
    return modifiedLines.join('\r\n');
  }
}
