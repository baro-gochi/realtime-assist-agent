/**
 * @fileoverview WebRTC 클라이언트 - 룸 기반 화상 통화 시스템
 *
 * @description
 * 이 파일은 WebRTC를 사용한 실시간 화상/음성 통화 기능을 제공합니다.
 * 서버의 시그널링 서버와 통신하여 피어 간 연결을 설정하고 미디어를 주고받습니다.
 *
 * 주요 개념 (초보자 필독):
 * - WebRTC: 웹 브라우저 간 실시간 통신 기술 (카메라, 마이크, 화면 공유 등)
 * - WebSocket: 서버와 실시간 양방향 통신을 위한 기술
 * - 시그널링: WebRTC 연결을 설정하기 위한 초기 정보 교환 과정
 * - SDP (Session Description Protocol): 연결 정보를 담은 데이터 형식
 * - ICE Candidate: 네트워크 경로 정보
 * - MediaStream: 카메라/마이크에서 오는 오디오/비디오 데이터 흐름
 *
 * 연결 과정 (순서대로):
 * 1. WebSocket으로 시그널링 서버에 연결
 * 2. 룸(방)에 참가
 * 3. 카메라/마이크 권한 요청 및 로컬 미디어 획득
 * 4. RTCPeerConnection 생성 및 offer 전송
 * 5. 서버로부터 answer 수신
 * 6. ICE candidate 교환
 * 7. 미디어 스트림 송수신 시작
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
 *   videoElement.srcObject = stream;
 * };
 *
 * // 연결 및 통화 시작
 * await client.connect();
 * await client.joinRoom('상담실1', '홍길동');
 * await client.startCall();
 */

/**
 * WebRTC 클라이언트 클래스
 *
 * @class WebRTCClient
 * @description
 * 룸 기반 화상 통화를 위한 WebRTC 클라이언트입니다.
 * 시그널링 서버와 통신하여 다른 참가자들과 실시간으로 오디오/비디오를 주고받습니다.
 *
 * @tutorial
 * WebRTC 연결 과정 이해하기:
 *
 * 1단계: 시그널링 (Signaling)
 *    - WebSocket으로 서버에 연결
 *    - 룸에 참가하여 다른 참가자들과 만남
 *    - 연결 정보(SDP)를 서버를 통해 교환
 *
 * 2단계: ICE (Interactive Connectivity Establishment)
 *    - 네트워크 경로를 찾는 과정
 *    - STUN 서버가 공인 IP를 찾아줌
 *    - 가능한 모든 연결 경로를 시도
 *
 * 3단계: 미디어 전송
 *    - P2P 연결이 완료되면 직접 미디어 전송
 *    - 서버는 더 이상 미디어 데이터를 중계하지 않음
 *    - 낮은 지연시간으로 실시간 통화 가능
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
   * @property {RTCPeerConnection|null} pc - WebRTC 피어 연결 객체 (미디어 송수신)
   * @property {string|null} peerId - 서버가 할당한 고유 ID
   * @property {string|null} roomName - 현재 참가 중인 룸 이름
   * @property {string|null} nickname - 사용자 닉네임
   * @property {MediaStream|null} localStream - 내 카메라/마이크 스트림
   * @property {MediaStream} remoteStream - 상대방 카메라/마이크 스트림
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
   *   document.getElementById('remoteVideo').srcObject = stream;
   * };
   */
  constructor(signalingUrl = 'ws://localhost:8000/ws') {
    this.signalingUrl = signalingUrl;
    this.ws = null;
    this.pc = null;
    this.peerId = null;
    this.roomName = null;
    this.nickname = null;
    this.localStream = null;
    this.remoteStream = new MediaStream();
    this.needsRenegotiation = false; // 재협상 필요 여부 플래그
    this.turnServers = null; // Cached TURN credentials

    // Event callbacks (이벤트가 발생했을 때 실행할 함수들)
    this.onPeerId = null;
    this.onRoomJoined = null;
    this.onUserJoined = null;
    this.onUserLeft = null;
    this.onRemoteStream = null;
    this.onConnectionStateChange = null;
    this.onError = null;
    this.onTranscript = null; // STT transcript 이벤트 콜백

    // Prefetch TURN credentials on construction
    this.prefetchTurnCredentials();
  }

  /**
   * Prefetch TURN credentials in the background
   *
   * @async
   * @description
   * Fetches TURN server credentials from backend and caches them.
   * This runs in background to avoid blocking createPeerConnection().
   */
  async prefetchTurnCredentials() {
    try {
      const backendUrl = `${window.location.protocol}//${window.location.host}/api/turn-credentials`;
      console.log('🔄 Prefetching TURN credentials from:', backendUrl);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);

      const response = await fetch(backendUrl, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (response.ok) {
        this.turnServers = await response.json();
        console.log('✅ TURN credentials prefetched successfully');
      } else {
        console.warn('⚠️ Failed to prefetch TURN credentials, will use STUN only');
      }
    } catch (error) {
      console.warn('⚠️ Error prefetching TURN credentials:', error.message);
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
      console.log('🔌 Attempting to connect to:', this.signalingUrl);

      try {
        this.ws = new WebSocket(this.signalingUrl);
      } catch (error) {
        console.error('🔌 Failed to create WebSocket:', error);
        reject(new Error(`Failed to create WebSocket: ${error.message}`));
        return;
      }

      this.ws.onopen = () => {
        console.log('🔌 WebSocket connected successfully');
        resolve();
      };

      this.ws.onerror = (error) => {
        console.error('🔌 WebSocket error:', error);
        console.error('🔌 WebSocket readyState:', this.ws.readyState);
        if (this.onError) this.onError(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
        reject(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
      };

      this.ws.onclose = (event) => {
        console.log('🔌 WebSocket closed');
        console.log('🔌 Close code:', event.code);
        console.log('🔌 Close reason:', event.reason);
        console.log('🔌 Was clean:', event.wasClean);
      };

      this.ws.onmessage = async (event) => {
        try {
          const message = JSON.parse(event.data);
          await this.handleSignalingMessage(message);
        } catch (error) {
          console.error('Error handling signaling message:', error);
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
   * 서버로부터 받은 여러 종류의 메시지를 처리합니다.
   * 각 메시지 타입에 따라 다른 동작을 수행합니다.
   *
   * 처리하는 메시지 타입:
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
        console.log('Received peer ID:', this.peerId);
        if (this.onPeerId) this.onPeerId(this.peerId);
        break;

      case 'room_joined':
        console.log('Joined room:', data.room_name);
        if (this.onRoomJoined) {
          this.onRoomJoined(data);
        }
        break;

      case 'user_joined':
        console.log('User joined:', data.nickname);
        if (this.onUserJoined) {
          this.onUserJoined(data);
        }
        break;

      case 'user_left':
        console.log('User left:', data.nickname);
        if (this.onUserLeft) {
          this.onUserLeft(data);
        }
        break;

      case 'answer':
        console.log('Received answer from server');
        await this.handleAnswer(data);
        break;

      case 'ice_candidate':
        console.log('Received ICE candidate from server');
        await this.handleIceCandidate(data);
        break;

      case 'renegotiation_needed':
        console.log('🔄 Renegotiation needed:', data.reason);
        // CRITICAL: Wait for connection to be established before renegotiating
        // Renegotiating too early causes ICE transport to close prematurely
        if (this.pc && this.pc.connectionState === 'connected') {
          console.log('✅ Connection ready, renegotiating now');
          await this.renegotiate();
        } else {
          console.log('🔄 Deferring renegotiation - connection not ready (state:', this.pc?.connectionState || 'no pc', ')');
          this.needsRenegotiation = true;
        }
        break;

      case 'transcript':
        console.log('💬 Transcript received:', data);
        if (this.onTranscript) {
          this.onTranscript(data);
        }
        break;

      case 'agent_ready':
        console.log('🤖 Agent ready:', data);
        if (this.onAgentReady) {
          this.onAgentReady(data);
        }
        break;

      case 'agent_update':
        console.log('🤖 Agent update received - full message:', message);
        console.log('🤖 Agent update - node:', message.node, 'data:', message.data);
        if (this.onAgentUpdate) {
          // node와 data를 모두 포함한 객체 전달
          this.onAgentUpdate({
            node: message.node,
            data: message.data
          });
        }
        break;

      case 'error':
        console.error('Server error:', data.message);
        if (this.onError) this.onError(new Error(data.message));
        break;

      default:
        console.warn('Unknown message type:', type);
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
   * 같은 룸에 있는 다른 참가자들과 화상 통화를 할 수 있게 됩니다.
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
  async joinRoom(roomName, nickname) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    this.roomName = roomName;
    this.nickname = nickname;

    this.sendMessage('join_room', {
      room_name: roomName,
      nickname: nickname
    });

    console.log(`Joining room '${roomName}' as '${nickname}'`);
  }

  /**
   * 로컬 미디어 스트림을 획득합니다 (카메라 + 마이크)
   *
   * @async
   * @returns {Promise<MediaStream>} 로컬 미디어 스트림
   * @throws {Error} 미디어 접근 권한이 없거나 기기가 없으면 에러 발생
   *
   * @description
   * 사용자의 카메라와 마이크에 접근하여 미디어 스트림을 가져옵니다.
   * 처음 실행 시 브라우저가 권한을 요청합니다.
   *
   * 미디어 설정:
   * - 비디오: 1280x720 해상도 (HD)
   * - 오디오:
   *   - echoCancellation: 에코 제거 (내 소리가 다시 들리는 현상 방지)
   *   - noiseSuppression: 배경 소음 제거
   *   - autoGainControl: 음량 자동 조절
   *
   * @example
   * const client = new WebRTCClient();
   * try {
   *   const stream = await client.getLocalMedia();
   *   videoElement.srcObject = stream; // 비디오 요소에 연결
   * } catch (error) {
   *   if (error.name === 'NotAllowedError') {
   *     alert('카메라/마이크 권한이 필요합니다');
   *   }
   * }
   *
   * @tutorial
   * 주의사항:
   * - HTTPS 또는 localhost에서만 작동 (보안상의 이유)
   * - 사용자가 권한을 거부하면 에러 발생
   * - 카메라/마이크가 다른 앱에서 사용 중이면 실패할 수 있음
   */
  async getLocalMedia() {
    try {
      console.log('🎥 Requesting camera/microphone permissions...');
      console.log('🔒 Current protocol:', window.location.protocol);
      console.log('🔒 Is secure context:', window.isSecureContext);

      this.localStream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      console.log('✅ Local media stream obtained');
      console.log('📹 Video tracks:', this.localStream.getVideoTracks().length);
      console.log('🎤 Audio tracks:', this.localStream.getAudioTracks().length);
      return this.localStream;
    } catch (error) {
      console.error('❌ Error getting local media:', error);
      console.error('❌ Error name:', error.name);
      console.error('❌ Error message:', error.message);

      // Show user-friendly error
      let userMessage = 'Failed to access camera/microphone: ';
      if (error.name === 'NotAllowedError') {
        userMessage += 'Permission denied. Please allow camera and microphone access.';
      } else if (error.name === 'NotFoundError') {
        userMessage += 'No camera or microphone found on this device.';
      } else if (error.name === 'NotReadableError') {
        userMessage += 'Camera/microphone is already in use by another application.';
      } else if (error.name === 'NotSecureError' || !window.isSecureContext) {
        userMessage += 'Camera/microphone requires HTTPS. Please use https:// URL.';
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
   * 이 연결을 통해 실제 미디어(오디오/비디오)가 전송됩니다.
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
    // Use prefetched TURN credentials or fetch if not available
    let iceServers = [
      // STUN servers (always available, no auth needed)
      { urls: 'stun:stun.l.google.com:19302' },
      { urls: 'stun:stun.relay.metered.ca:80' }
    ];

    // Use cached TURN credentials if available
    if (this.turnServers) {
      iceServers = iceServers.concat(this.turnServers);
      console.log('✅ Using prefetched TURN credentials');
    } else {
      console.warn('⚠️ TURN credentials not prefetched yet, using STUN only');
      console.warn('💡 TIP: Connection may fail behind strict NAT/firewall');
    }

    // Create RTCPeerConnection with fetched ICE servers
    // CRITICAL: Force relay mode to bypass localtunnel UDP limitations
    // All media traffic will go through TURN servers
    this.pc = new RTCPeerConnection({
      iceServers,
      iceTransportPolicy: 'relay'  // Force TURN relay, bypass P2P
    });

    // Add local tracks to peer connection
    if (this.localStream) {
      this.localStream.getTracks().forEach(track => {
        this.pc.addTrack(track, this.localStream);
        console.log('Added local track:', track.kind);
      });
    }

    // Handle remote tracks
    this.pc.ontrack = (event) => {
      console.log('🎥 Received remote track:', event.track.kind);
      console.log('🎥 Track ID:', event.track.id);
      console.log('🎥 Track state:', event.track.readyState);

      // Add only the received track (not all tracks from stream)
      const track = event.track;

      // 기존 같은 종류의 트랙이 있으면 제거
      const existingTracks = this.remoteStream.getTracks().filter(t => t.kind === track.kind);
      existingTracks.forEach(t => {
        console.log('🎥 Removing old track:', t.kind, t.id);
        this.remoteStream.removeTrack(t);
      });

      this.remoteStream.addTrack(track);
      console.log('🎥 Track added to remoteStream:', track.kind, track.id);

      const currentTracks = this.remoteStream.getTracks();
      console.log('🎥 Remote stream now has tracks:',
        currentTracks.map(t => `${t.kind}:${t.id}:${t.readyState}`));

      // onRemoteStream 콜백은 오디오+비디오 둘 다 있을 때만 호출
      const hasAudio = currentTracks.some(t => t.kind === 'audio');
      const hasVideo = currentTracks.some(t => t.kind === 'video');

      if (hasAudio && hasVideo && this.onRemoteStream) {
        console.log('🎥 Both audio and video tracks received, calling onRemoteStream callback');
        this.onRemoteStream(this.remoteStream);
      }
    };

    // Handle ICE candidates
    this.pc.onicecandidate = (event) => {
      if (event.candidate) {
        console.log('New ICE candidate:', event.candidate);
        this.sendMessage('ice_candidate', {
          candidate: event.candidate.toJSON()
        });
      }
    };

    // Handle connection state changes
    this.pc.onconnectionstatechange = () => {
      const state = this.pc.connectionState;
      console.log('Connection state:', state);

      if (this.onConnectionStateChange) {
        this.onConnectionStateChange(state);
      }

      // Execute deferred renegotiation when connection is established
      if (state === 'connected' && this.needsRenegotiation) {
        console.log('🔄 Executing deferred renegotiation');
        this.needsRenegotiation = false;
        this.renegotiate();
      }
    };

    // Create and send offer
    const offer = await this.pc.createOffer();
    await this.pc.setLocalDescription(offer);

    console.log('Sending offer to server');
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
        console.warn('⚠️ No peer connection exists, ignoring answer');
        return;
      }

      // Check current signaling state
      console.log('📡 Current signaling state:', this.pc.signalingState);

      // DEBUG: Check if answer SDP contains ICE candidates
      const candidateCount = (answer.sdp.match(/a=candidate:/g) || []).length;
      console.log(`📋 Answer SDP contains ${candidateCount} ICE candidates`);
      if (candidateCount === 0) {
        console.warn('⚠️ WARNING: Answer SDP has NO ICE candidates! Backend ICE gathering may have failed.');
      }

      // Only set remote description if we're in the correct state
      // We should be in 'have-local-offer' state to receive an answer
      if (this.pc.signalingState === 'have-local-offer') {
        await this.pc.setRemoteDescription(
          new RTCSessionDescription(answer)
        );
        console.log('✅ Remote description set, state:', this.pc.signalingState);

        // NOW process buffered ICE candidates (remote description is set)
        if (this.pendingCandidates && this.pendingCandidates.length > 0) {
          console.log(`📦 Processing ${this.pendingCandidates.length} buffered ICE candidates`);
          for (const candidateData of this.pendingCandidates) {
            await this.handleIceCandidate(candidateData);
          }
          this.pendingCandidates = [];
        }
      } else if (this.pc.signalingState === 'stable') {
        console.warn('⚠️ Already in stable state, ignoring duplicate answer');
      } else {
        console.warn(`⚠️ Unexpected state ${this.pc.signalingState}, cannot set answer`);
      }
    } catch (error) {
      console.error('❌ Error setting remote description:', error);
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
   *
   * @tutorial
   * ICE Candidate란?
   * - 네트워크 경로를 찾기 위한 정보
   * - 여러 개가 생성되며 모두 교환해야 함
   * - 최적의 경로를 자동으로 선택
   */
  async handleIceCandidate(candidateData) {
    try {
      // DEBUG: Log full structure
      console.log('📋 Raw candidate data:', candidateData);

      if (!candidateData.candidate) {
        console.warn('⚠️ Received empty ICE candidate, ignoring');
        return;
      }

      // If peer connection doesn't exist yet OR remote description not set, buffer the candidate
      if (!this.pc || !this.pc.remoteDescription) {
        console.log('📦 Buffering ICE candidate (remote description not ready yet)');
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

      console.log('📋 Candidate init:', candidateInit);

      const iceCandidate = new RTCIceCandidate(candidateInit);

      await this.pc.addIceCandidate(iceCandidate);
      console.log('✅ ICE candidate added');
    } catch (error) {
      console.error('❌ Error adding ICE candidate:', error);
      console.error('Candidate data:', candidateData);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * 시그널링 서버에 메시지를 전송합니다
   *
   * @param {string} type - 메시지 타입 (예: 'offer', 'ice_candidate', 'join_room')
   * @param {Object} data - 메시지 데이터
   *
   * @description
   * WebSocket을 통해 서버에 JSON 형식의 메시지를 보냅니다.
   * WebSocket이 열려있지 않으면 에러 로그만 출력하고 무시합니다.
   *
   * @example
   * this.sendMessage('join_room', {
   *   room_name: '상담실1',
   *   nickname: '홍길동'
   * });
   *
   * @example
   * this.sendMessage('offer', {
   *   sdp: offer.sdp,
   *   type: offer.type
   * });
   */
  sendMessage(type, data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, data }));
    } else {
      console.error('WebSocket is not open');
    }
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
   *
   * @tutorial
   * 재협상이 필요한 이유:
   * - WebRTC는 offer/answer 교환 시점의 트랙만 전송
   * - 새 피어가 입장하면 기존 피어는 새 트랙을 받을 수 없음
   * - 재협상을 통해 새로운 트랙 정보를 교환
   */
  async renegotiate() {
    try {
      if (!this.pc) {
        console.warn('No peer connection to renegotiate');
        return;
      }

      console.log('🔄 Creating new offer for renegotiation');

      // Create new offer
      const offer = await this.pc.createOffer();
      await this.pc.setLocalDescription(offer);

      // Send new offer to server
      this.sendMessage('offer', {
        sdp: offer.sdp,
        type: offer.type
      });

      console.log('🔄 Renegotiation offer sent');
    } catch (error) {
      console.error('Error during renegotiation:', error);
      if (this.onError) this.onError(error);
    }
  }

  /**
   * 통화를 시작합니다 (미디어 획득 + 피어 연결 생성)
   *
   * @async
   * @throws {Error} 미디어 획득 또는 연결 생성 실패 시 에러 발생
   *
   * @description
   * 화상 통화를 시작하기 위한 모든 과정을 순서대로 실행합니다.
   * 이 메서드 하나로 통화 준비를 완료할 수 있습니다.
   *
   * 실행 순서:
   * 1. getLocalMedia(): 카메라/마이크 권한 요청 및 스트림 획득
   * 2. createPeerConnection(): WebRTC 연결 생성 및 offer 전송
   *
   * @example
   * const client = new WebRTCClient();
   * await client.connect();
   * await client.joinRoom('상담실1', '홍길동');
   *
   * // 통화 시작!
   * await client.startCall();
   *
   * @tutorial
   * 통화 시작 전 체크리스트:
   * 1. ✅ WebSocket 연결 완료 (connect)
   * 2. ✅ 룸 참가 완료 (joinRoom)
   * 3. ✅ 카메라/마이크 권한 승인
   * 4. ✅ 네트워크 연결 상태 양호
   */
  async startCall() {
    try {
      await this.getLocalMedia();
      await this.createPeerConnection();
    } catch (error) {
      console.error('Error starting call:', error);
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
   * 미디어 스트림과 WebRTC 연결을 모두 종료합니다.
   * 메모리 누수를 방지하기 위해 모든 리소스를 해제합니다.
   *
   * 정리 항목:
   * 1. 로컬 미디어 트랙 정지 (카메라/마이크 LED 꺼짐)
   * 2. 로컬 스트림 객체 제거
   * 3. RTCPeerConnection 종료
   * 4. 원격 스트림 정리
   *
   * @example
   * client.stopCall();
   * // 카메라가 꺼지고 통화가 완전히 종료됨
   *
   * @tutorial
   * track.stop()이 중요한 이유:
   * - 카메라/마이크의 활성 LED가 꺼짐
   * - 다른 앱에서 카메라를 사용할 수 있게 됨
   * - 시스템 리소스 절약
   * - 배터리 수명 향상
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

    console.log('Call stopped');
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
   *
   * @tutorial
   * 언제 disconnect를 호출해야 할까요?
   * - 앱 종료 시
   * - 다른 페이지로 이동 시
   * - 로그아웃 시
   * - "연결 끊기" 버튼 클릭 시
   */
  disconnect() {
    this.leaveRoom();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    console.log('Disconnected');
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
        console.log(`🎤 Audio ${enabled ? 'enabled' : 'disabled'}`);
        return enabled;
      }
    }
    return false;
  }

  /**
   * 비디오 트랙을 토글합니다 (카메라 켜기/끄기)
   *
   * @returns {boolean} 비디오 활성화 상태 (true: 켜짐, false: 꺼짐)
   */
  toggleVideo() {
    if (this.localStream) {
      const videoTracks = this.localStream.getVideoTracks();
      if (videoTracks.length > 0) {
        const enabled = !videoTracks[0].enabled;
        videoTracks.forEach(track => {
          track.enabled = enabled;
        });
        console.log(`📹 Video ${enabled ? 'enabled' : 'disabled'}`);
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
   * 현재 비디오 활성화 상태를 반환합니다
   *
   * @returns {boolean} true: 비디오 켜짐, false: 비디오 꺼짐
   */
  isVideoEnabled() {
    if (this.localStream) {
      const videoTracks = this.localStream.getVideoTracks();
      return videoTracks.length > 0 && videoTracks[0].enabled;
    }
    return false;
  }
}
