/**
 * @fileoverview WebRTC 클라이언트 - 룸 기반 음성 통화 시스템 (TypeScript)
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
 * @example
 * import { WebRTCClient } from '@/lib/webrtc';
 *
 * const client = new WebRTCClient('ws://localhost:8000/ws');
 * client.onRemoteStream = (stream) => {
 *   audioElement.srcObject = stream;
 * };
 *
 * await client.connect();
 * await client.joinRoom('상담실1', '홍길동');
 * await client.startCall();
 */

import logger from './logger';

// =============================================================================
// Types and Interfaces
// =============================================================================

/** ICE 서버 설정 */
export interface IceServer {
  urls: string | string[];
  username?: string;
  credential?: string;
}

/** 시그널링 메시지 기본 구조 */
export interface SignalingMessage {
  type: string;
  data?: Record<string, unknown>;
  node?: string;
  turn_id?: string;
}

/** 룸 참가 데이터 */
export interface RoomJoinedData {
  room_name: string;
  participants?: ParticipantInfo[];
  [key: string]: unknown;
}

/** 참가자 정보 */
export interface ParticipantInfo {
  peer_id: string;
  nickname: string;
  [key: string]: unknown;
}

/** 사용자 참가/퇴장 데이터 */
export interface UserEventData {
  peer_id: string;
  nickname: string;
  [key: string]: unknown;
}

/** 트랜스크립트 데이터 */
export interface TranscriptData {
  text: string;
  speaker?: string;
  is_final?: boolean;
  timestamp?: string;
  [key: string]: unknown;
}

/** 에이전트 업데이트 데이터 */
export interface AgentUpdateData {
  turnId?: string;
  node?: string;
  data?: Record<string, unknown>;
}

/** 에이전트 상태 데이터 */
export interface AgentStatusData {
  task?: string;
  status: string;
  [key: string]: unknown;
}

/** 에이전트 상담 결과 데이터 */
export interface AgentConsultationData {
  result?: string;
  recommendations?: string[];
  [key: string]: unknown;
}

/** 세션 종료 결과 */
export interface SessionEndedData {
  success: boolean;
  session_id: string | null;
  message?: string;
  [key: string]: unknown;
}

/** ICE Candidate 데이터 */
export interface IceCandidateData {
  candidate?: RTCIceCandidateInit | string;
  sdpMid?: string | null;
  sdpMLineIndex?: number | null;
  [key: string]: unknown;
}

/** SDP Answer 데이터 */
export interface SdpAnswerData {
  sdp: string;
  type: RTCSdpType;
}

/** 연결 상태 타입 */
export type ConnectionState = RTCPeerConnectionState;

// =============================================================================
// Callback Types
// =============================================================================

export type OnPeerIdCallback = (peerId: string) => void;
export type OnRoomJoinedCallback = (data: RoomJoinedData) => void;
export type OnUserJoinedCallback = (data: UserEventData) => void;
export type OnUserLeftCallback = (data: UserEventData) => void;
export type OnRemoteStreamCallback = (stream: MediaStream) => void;
export type OnLocalStreamCallback = (stream: MediaStream) => void;
export type OnConnectionStateChangeCallback = (state: ConnectionState) => void;
export type OnErrorCallback = (error: Error) => void;
export type OnTranscriptCallback = (data: TranscriptData) => void;
export type OnAgentReadyCallback = (data: Record<string, unknown>) => void;
export type OnAgentUpdateCallback = (data: AgentUpdateData) => void;
export type OnAgentStatusCallback = (data: AgentStatusData) => void;
export type OnAgentConsultationCallback = (data: AgentConsultationData) => void;
export type OnSessionEndedCallback = (data: SessionEndedData) => void;

// =============================================================================
// WebRTC Client Class
// =============================================================================

/**
 * WebRTC 클라이언트 클래스
 *
 * 룸 기반 음성 통화를 위한 WebRTC 클라이언트입니다.
 * 시그널링 서버와 통신하여 다른 참가자들과 실시간으로 오디오를 주고받습니다.
 */
export class WebRTCClient {
  // Connection properties
  private signalingUrl: string;
  private authToken: string | null;
  private ws: WebSocket | null = null;
  private pc: RTCPeerConnection | null = null;
  private peerId: string | null = null;
  private roomName: string | null = null;
  private nickname: string | null = null;
  private localStream: MediaStream | null = null;
  private remoteStream: MediaStream;
  private needsRenegotiation = false;
  private turnServers: IceServer[] | null = null;
  private pendingCandidates: IceCandidateData[] = [];

  // Event callbacks
  public onPeerId: OnPeerIdCallback | null = null;
  public onRoomJoined: OnRoomJoinedCallback | null = null;
  public onUserJoined: OnUserJoinedCallback | null = null;
  public onUserLeft: OnUserLeftCallback | null = null;
  public onRemoteStream: OnRemoteStreamCallback | null = null;
  public onLocalStream: OnLocalStreamCallback | null = null;
  public onConnectionStateChange: OnConnectionStateChangeCallback | null = null;
  public onError: OnErrorCallback | null = null;
  public onTranscript: OnTranscriptCallback | null = null;
  public onAgentReady: OnAgentReadyCallback | null = null;
  public onAgentUpdate: OnAgentUpdateCallback | null = null;
  public onAgentStatus: OnAgentStatusCallback | null = null;
  public onAgentConsultation: OnAgentConsultationCallback | null = null;
  public onSessionEnded: OnSessionEndedCallback | null = null;

  /**
   * WebRTCClient 생성자
   *
   * @param signalingUrl - 시그널링 서버의 WebSocket URL
   * @param authToken - 인증 토큰 (옵션)
   */
  constructor(signalingUrl = 'ws://localhost:8000/ws', authToken: string | null = null) {
    this.signalingUrl = signalingUrl;
    this.authToken = authToken || (typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('auth_token') : null);
    this.remoteStream = new MediaStream();

    // Prefetch TURN 자격 증명
    this.prefetchTurnCredentials();
  }

  /**
   * TURN 자격 증명을 백그라운드에서 미리 가져옵니다.
   */
  private async prefetchTurnCredentials(): Promise<void> {
    try {
      // 환경변수 우선, 없으면 현재 호스트 사용
      const apiBase = process.env.NEXT_PUBLIC_API_URL ||
        (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.host}` : '');
      const backendUrl = `${apiBase}/api/turn-credentials`;
      logger.debug('Prefetching TURN credentials from:', backendUrl);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 10000);

      const headers: HeadersInit = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      if (this.authToken) {
        (headers as Record<string, string>)['Authorization'] = `Bearer ${this.authToken}`;
      }

      const response = await fetch(backendUrl, { signal: controller.signal, headers });
      clearTimeout(timeoutId);

      if (response.ok) {
        const data = await response.json();
        if (Array.isArray(data)) {
          this.turnServers = data as IceServer[];
          logger.debug('ICE servers prefetched:', data.length, 'servers');
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      logger.warn('Error prefetching TURN credentials:', message);
    }
  }

  /**
   * 시그널링을 위한 WebSocket 연결을 초기화합니다
   */
  async connect(): Promise<void> {
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
        const err = error instanceof Error ? error : new Error(String(error));
        logger.error('Failed to create WebSocket:', err);
        reject(new Error(`Failed to create WebSocket: ${err.message}`));
        return;
      }

      this.ws.onopen = () => {
        logger.info('WebSocket connected successfully');
        resolve();
      };

      this.ws.onerror = (event) => {
        logger.error('WebSocket error:', event);
        logger.debug('WebSocket readyState:', this.ws?.readyState);
        if (this.onError) this.onError(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
        reject(new Error(`WebSocket connection failed to ${this.signalingUrl}`));
      };

      this.ws.onclose = (event: CloseEvent) => {
        logger.info('WebSocket closed');
        logger.debug('Close code:', event.code, 'reason:', event.reason, 'wasClean:', event.wasClean);

        // Handle authentication failure
        if (event.code === 4001) {
          logger.error('Authentication failed - unauthorized');
          if (typeof sessionStorage !== 'undefined') {
            sessionStorage.removeItem('auth_token');
          }
          if (this.onError) this.onError(new Error('Unauthorized - please re-login'));
          if (typeof window !== 'undefined') {
            window.location.reload();
          }
        }
      };

      this.ws.onmessage = async (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data as string) as SignalingMessage;
          await this.handleSignalingMessage(message);
        } catch (error) {
          const err = error instanceof Error ? error : new Error(String(error));
          logger.error('Error handling signaling message:', err);
          if (this.onError) this.onError(err);
        }
      };
    });
  }

  /**
   * 서버로부터 받은 시그널링 메시지를 처리합니다
   */
  private async handleSignalingMessage(message: SignalingMessage): Promise<void> {
    const { type, data } = message;

    switch (type) {
      case 'peer_id':
        this.peerId = (data as { peer_id: string }).peer_id;
        logger.debug('Received peer ID:', this.peerId);
        if (this.onPeerId) this.onPeerId(this.peerId);
        break;

      case 'room_joined':
        logger.info('Joined room:', (data as RoomJoinedData).room_name);
        if (this.onRoomJoined) {
          this.onRoomJoined(data as RoomJoinedData);
        }
        break;

      case 'user_joined':
        logger.info('User joined:', (data as UserEventData).nickname);
        if (this.onUserJoined) {
          this.onUserJoined(data as UserEventData);
        }
        break;

      case 'user_left':
        logger.info('User left:', (data as UserEventData).nickname);
        if (this.onUserLeft) {
          this.onUserLeft(data as UserEventData);
        }
        break;

      case 'answer':
        logger.debug('Received answer from server');
        await this.handleAnswer(data as unknown as SdpAnswerData);
        break;

      case 'ice_candidate':
        logger.debug('Received ICE candidate from server');
        await this.handleIceCandidate(data as IceCandidateData);
        break;

      case 'renegotiation_needed':
        logger.debug('Renegotiation needed:', (data as { reason?: string }).reason);
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
          this.onTranscript(data as TranscriptData);
        }
        break;

      case 'agent_ready':
        logger.debug('Agent ready');
        if (this.onAgentReady) {
          this.onAgentReady(data as Record<string, unknown>);
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
        logger.debug('Agent status:', (data as AgentStatusData).status);
        if (this.onAgentStatus) this.onAgentStatus(data as AgentStatusData);
        break;

      case 'agent_consultation':
        logger.debug('Agent consultation result received');
        if (this.onAgentConsultation) this.onAgentConsultation(data as AgentConsultationData);
        break;

      case 'agent_error':
        logger.error('Agent error:', data);
        if (this.onAgentStatus) this.onAgentStatus({ task: (data as { task?: string }).task, status: 'error' });
        if (this.onError) this.onError(new Error((data as { message?: string }).message || 'Agent error'));
        break;

      case 'session_ended':
        logger.info('Session ended');
        if (this.onSessionEnded) {
          this.onSessionEnded(data as SessionEndedData);
        }
        break;

      case 'error':
        logger.error('Server error:', (data as { message?: string }).message);
        if (this.onError) this.onError(new Error((data as { message?: string }).message || 'Server error'));
        break;

      default:
        logger.warn('Unknown message type:', type);
    }
  }

  /**
   * 특정 룸(방)에 참가합니다
   */
  async joinRoom(
    roomName: string,
    nickname: string,
    phoneNumber: string | null = null,
    agentCode: string | null = null
  ): Promise<void> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }

    this.roomName = roomName;
    this.nickname = nickname;

    const joinData: Record<string, string> = {
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
   */
  async getLocalMedia(): Promise<MediaStream> {
    try {
      logger.debug('Requesting microphone permissions...');
      logger.debug('Secure context:', typeof window !== 'undefined' ? window.isSecureContext : 'N/A');

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
      const err = error as DOMException;
      logger.error('Error getting local media:', err.name, err.message);

      // Show user-friendly error
      let userMessage = '마이크 접근 실패: ';
      if (err.name === 'NotAllowedError') {
        userMessage += '권한이 거부되었습니다. 마이크 접근을 허용해주세요.';
      } else if (err.name === 'NotFoundError') {
        userMessage += '마이크를 찾을 수 없습니다.';
      } else if (err.name === 'NotReadableError') {
        userMessage += '마이크가 다른 앱에서 사용 중입니다.';
      } else if (err.name === 'NotSecureError' || (typeof window !== 'undefined' && !window.isSecureContext)) {
        userMessage += 'HTTPS 연결이 필요합니다.';
      } else {
        userMessage += err.message;
      }

      if (typeof alert !== 'undefined') {
        alert(userMessage);
      }
      if (this.onError) this.onError(new Error(userMessage));
      throw error;
    }
  }

  /**
   * 피어 연결을 생성하고 offer를 서버에 전송합니다
   */
  async createPeerConnection(): Promise<void> {
    // Use prefetched TURN credentials from AWS coturn or fetch if not available
    let iceServers: IceServer[] = [
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
    this.pc = new RTCPeerConnection({ iceServers });

    // Add local tracks to peer connection
    if (this.localStream) {
      this.localStream.getTracks().forEach(track => {
        this.pc!.addTrack(track, this.localStream!);
        logger.debug('Added local track:', track.kind);
      });
    }

    // Handle remote tracks
    this.pc.ontrack = (event: RTCTrackEvent) => {
      logger.debug('Received remote track:', event.track.kind);

      // 오디오 재생 지연 버퍼 설정
      if (event.receiver && event.track.kind === 'audio') {
        (event.receiver as RTCRtpReceiver & { playoutDelayHint?: number }).playoutDelayHint = 0.05;
        if ('jitterBufferTarget' in event.receiver) {
          (event.receiver as RTCRtpReceiver & { jitterBufferTarget?: number }).jitterBufferTarget = 50;
        }
        logger.debug('Audio jitter buffer configured');
      }

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
    this.pc.onicecandidate = (event: RTCPeerConnectionIceEvent) => {
      if (event.candidate) {
        logger.debug('New ICE candidate');
        this.sendMessage('ice_candidate', {
          candidate: event.candidate.toJSON()
        });
      }
    };

    // Handle connection state changes
    this.pc.onconnectionstatechange = () => {
      const state = this.pc!.connectionState;
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
    offer.sdp = this.disableDTX(offer.sdp || '');

    await this.pc.setLocalDescription(offer);

    logger.debug('Sending offer to server');
    this.sendMessage('offer', {
      sdp: offer.sdp,
      type: offer.type
    });
  }

  /**
   * 서버로부터 받은 answer를 처리합니다
   */
  private async handleAnswer(answer: SdpAnswerData): Promise<void> {
    try {
      if (!this.pc) {
        logger.warn('No peer connection exists, ignoring answer');
        return;
      }

      logger.debug('Current signaling state:', this.pc.signalingState);

      // Check if answer SDP contains ICE candidates
      const candidateCount = (answer.sdp.match(/a=candidate:/g) || []).length;
      logger.debug(`Answer SDP contains ${candidateCount} ICE candidates`);
      if (candidateCount === 0) {
        logger.warn('Answer SDP has NO ICE candidates! Backend ICE gathering may have failed.');
      }

      if (this.pc.signalingState === 'have-local-offer') {
        const modifiedAnswer: RTCSessionDescriptionInit = {
          type: answer.type,
          sdp: this.disableDTX(answer.sdp)
        };

        await this.pc.setRemoteDescription(new RTCSessionDescription(modifiedAnswer));
        logger.debug('Remote description set, state:', this.pc.signalingState);

        // Process buffered ICE candidates
        if (this.pendingCandidates.length > 0) {
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
      const err = error instanceof Error ? error : new Error(String(error));
      logger.error('Error setting remote description:', err);
      if (this.onError) this.onError(err);
    }
  }

  /**
   * 서버로부터 받은 ICE candidate를 처리합니다
   */
  private async handleIceCandidate(candidateData: IceCandidateData): Promise<void> {
    try {
      if (!candidateData.candidate) {
        logger.warn('Received empty ICE candidate, ignoring');
        return;
      }

      // If peer connection doesn't exist yet OR remote description not set, buffer
      if (!this.pc || !this.pc.remoteDescription) {
        logger.debug('Buffering ICE candidate (remote description not ready yet)');
        this.pendingCandidates.push(candidateData);
        return;
      }

      // Create RTCIceCandidate from the data
      const candidateInit = typeof candidateData.candidate === 'object'
        ? candidateData.candidate as RTCIceCandidateInit
        : { candidate: candidateData.candidate as string };

      const iceCandidate = new RTCIceCandidate(candidateInit);

      await this.pc.addIceCandidate(iceCandidate);
      logger.debug('ICE candidate added');
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      logger.error('Error adding ICE candidate:', err);
      if (this.onError) this.onError(err);
    }
  }

  /**
   * 시그널링 서버에 메시지를 전송합니다
   */
  sendMessage(typeOrMessage: string | SignalingMessage, data?: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      let message: SignalingMessage;
      if (typeof typeOrMessage === 'string') {
        message = { type: typeOrMessage, data };
      } else {
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
   */
  sendConsultationTask(roomName: string, userOptions: Record<string, unknown> = {}): void {
    this.sendMessage('agent_task', {
      task: 'consultation',
      room_name: roomName,
      user_options: userOptions
    });
  }

  /**
   * 상담 세션을 종료하고 데이터를 저장합니다.
   */
  endSession(): Promise<SessionEndedData> {
    return new Promise((resolve) => {
      const originalHandler = this.onSessionEnded;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;

      this.onSessionEnded = (data: SessionEndedData) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
          timeoutId = null;
        }
        this.onSessionEnded = originalHandler;
        if (originalHandler) originalHandler(data);
        resolve(data);
      };

      timeoutId = setTimeout(() => {
        this.onSessionEnded = originalHandler;
        resolve({
          success: false,
          session_id: null,
          message: 'Session end request timed out'
        });
      }, 30000);

      this.sendMessage('end_session', {});
    });
  }

  /**
   * 피어 연결을 재협상합니다 (새 피어가 입장했을 때)
   */
  async renegotiate(): Promise<void> {
    try {
      if (!this.pc) {
        logger.warn('No peer connection to renegotiate');
        return;
      }

      logger.debug('Creating new offer for renegotiation');

      const offer = await this.pc.createOffer();
      offer.sdp = this.disableDTX(offer.sdp || '');

      await this.pc.setLocalDescription(offer);

      this.sendMessage('offer', {
        sdp: offer.sdp,
        type: offer.type
      });

      logger.debug('Renegotiation offer sent');
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      logger.error('Error during renegotiation:', err);
      if (this.onError) this.onError(err);
    }
  }

  /**
   * 통화를 시작합니다 (오디오 획득 + 피어 연결 생성)
   */
  async startCall(): Promise<void> {
    try {
      await this.getLocalMedia();
      await this.createPeerConnection();
    } catch (error) {
      const err = error instanceof Error ? error : new Error(String(error));
      logger.error('Error starting call:', err);
      if (this.onError) this.onError(err);
      throw error;
    }
  }

  /**
   * 현재 룸에서 퇴장합니다
   */
  leaveRoom(): void {
    if (this.roomName) {
      this.sendMessage('leave_room', {});
      this.stopCall();
      this.roomName = null;
      this.nickname = null;
    }
  }

  /**
   * 통화를 중단하고 모든 리소스를 정리합니다
   */
  stopCall(): void {
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
   */
  disconnect(): void {
    this.leaveRoom();

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    logger.info('Disconnected');
  }

  /**
   * 로컬 오디오 스트림을 시작합니다 (마이크).
   */
  async startLocalStream(constraints: MediaStreamConstraints = { audio: true, video: false }): Promise<MediaStream> {
    try {
      this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
      logger.debug('Local stream started:', this.localStream.getTracks().map(t => t.kind));

      if (this.onLocalStream) {
        this.onLocalStream(this.localStream);
      }

      // 이미 연결된 상태라면 트랙 추가 및 재협상
      if (this.pc && this.ws && this.roomName) {
        this.localStream.getTracks().forEach(track => {
          this.pc!.addTrack(track, this.localStream!);
        });
        await this.renegotiate();
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
  stopLocalStream(): void {
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
   */
  toggleAudio(): boolean {
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
   */
  isAudioEnabled(): boolean {
    if (this.localStream) {
      const audioTracks = this.localStream.getAudioTracks();
      return audioTracks.length > 0 && audioTracks[0].enabled;
    }
    return false;
  }

  /**
   * 오디오 송신 bitrate를 직접 설정합니다
   */
  async setAudioBitrate(bitrate: number): Promise<void> {
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

      if (!params.encodings || params.encodings.length === 0) {
        params.encodings = [{}];
      }

      params.encodings[0].maxBitrate = bitrate;

      await audioSender.setParameters(params);
      logger.debug(`Audio bitrate set to ${bitrate}bps`);
    } catch (error) {
      logger.error('Failed to set audio bitrate:', error);
    }
  }

  /**
   * SDP에서 Opus DTX(Discontinuous Transmission)를 비활성화합니다
   */
  private disableDTX(sdp: string): string {
    const lines = sdp.split('\r\n');
    const modifiedLines = lines.map(line => {
      if (line.startsWith('a=fmtp:') && line.includes('minptime')) {
        // usedtx=0 (DTX 비활성화)
        if (line.includes('usedtx=')) {
          line = line.replace(/usedtx=\d/, 'usedtx=0');
        } else {
          line += ';usedtx=0';
        }

        // cbr=1 (고정 비트레이트)
        if (!line.includes('cbr=')) {
          line += ';cbr=1';
        }

        // maxaveragebitrate (48kbps)
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

      // ptime 설정 (20ms 패킷)
      if (line.startsWith('a=ptime:')) {
        line = 'a=ptime:20';
      }

      return line;
    });
    return modifiedLines.join('\r\n');
  }

  // Getters for read-only access
  getPeerId(): string | null {
    return this.peerId;
  }

  getRoomName(): string | null {
    return this.roomName;
  }

  getNickname(): string | null {
    return this.nickname;
  }

  getLocalStream(): MediaStream | null {
    return this.localStream;
  }

  getRemoteStream(): MediaStream {
    return this.remoteStream;
  }

  getConnectionState(): ConnectionState | null {
    return this.pc?.connectionState ?? null;
  }
}

export default WebRTCClient;
