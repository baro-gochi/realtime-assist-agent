"use client";

/**
 * @fileoverview WebRTC 클라이언트 커스텀 훅
 *
 * WebRTC 연결, 룸 관리, 통화 상태를 관리하는 훅
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { WebRTCClient, type TranscriptData, type AgentUpdateData, type AgentStatusData, type SessionEndedData } from '@/lib/webrtc';
import { enrichCustomerInfo, type CustomerInfo, type ConsultationHistoryItem, type TranscriptEntry, type ParticipantInfo, type LLMStatus, type ConsultationStatus, type AgentUpdates } from '@/lib/types';
import logger from '@/lib/logger';

interface UseWebRTCClientOptions {
  wsUrl?: string;
}

interface UseWebRTCClientReturn {
  // Connection state
  isConnected: boolean;
  isInRoom: boolean;
  isCallActive: boolean;
  peerId: string;
  roomName: string;
  nickname: string;
  peerCount: number;
  connectionState: string;
  participants: ParticipantInfo[];
  error: string;

  // Transcripts
  transcripts: TranscriptEntry[];

  // Agent state
  llmStatus: LLMStatus;
  consultationStatus: ConsultationStatus;
  agentUpdates: AgentUpdates;
  latestTurnId: string | null;

  // Customer data
  customerInfo: CustomerInfo | null;
  consultationHistory: ConsultationHistoryItem[];

  // Audio
  remoteAudioRef: React.RefObject<HTMLAudioElement | null>;
  isAudioEnabled: boolean;

  // Actions
  connect: () => Promise<void>;
  joinRoom: (roomName: string, nickname: string, phoneNumber?: string, agentCode?: string) => Promise<void>;
  startCall: () => Promise<void>;
  leaveRoom: () => void;
  endSession: () => Promise<SessionEndedData>;
  toggleAudio: () => boolean;
  clearError: () => void;
  clearTranscripts: () => void;
}

export function useWebRTCClient(options: UseWebRTCClientOptions = {}): UseWebRTCClientReturn {
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [isInRoom, setIsInRoom] = useState(false);
  const [isCallActive, setIsCallActive] = useState(false);
  const [peerId, setPeerId] = useState('');
  const [roomName, setRoomName] = useState('');
  const [nickname, setNickname] = useState('');
  const [peerCount, setPeerCount] = useState(0);
  const [connectionState, setConnectionState] = useState('');
  const [participants, setParticipants] = useState<ParticipantInfo[]>([]);
  const [error, setError] = useState('');

  // Transcripts
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([]);

  // Agent state
  const [llmStatus, setLlmStatus] = useState<LLMStatus>('connecting');
  const [consultationStatus, setConsultationStatus] = useState<ConsultationStatus>('idle');
  const [agentUpdates, setAgentUpdates] = useState<AgentUpdates>({});
  const [latestTurnId, setLatestTurnId] = useState<string | null>(null);

  // Customer data
  const [customerInfo, setCustomerInfo] = useState<CustomerInfo | null>(null);
  const [consultationHistory, setConsultationHistory] = useState<ConsultationHistoryItem[]>([]);

  // Audio
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);

  // Refs
  const clientRef = useRef<WebRTCClient | null>(null);
  const remoteAudioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const gainNodeRef = useRef<GainNode | null>(null);

  // Initialize WebRTC client
  useEffect(() => {
    const wsUrl = options.wsUrl ||
      process.env.NEXT_PUBLIC_WS_URL ||
      (typeof window !== 'undefined'
        ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
        : 'ws://localhost:8000/ws');

    logger.debug('WebSocket URL:', wsUrl);
    const client = new WebRTCClient(wsUrl);
    clientRef.current = client;

    // Set up event handlers
    client.onPeerId = (id: string) => {
      setPeerId(id);
      logger.debug('Peer ID set:', id);
    };

    client.onRoomJoined = (data) => {
      logger.debug('Room joined:', data);
      setRoomName(data.room_name);
      setPeerCount((data as { peer_count?: number }).peer_count || 0);
      setIsInRoom(true);
      setParticipants((data as { other_peers?: ParticipantInfo[] }).other_peers || []);

      // Customer info from room join
      const roomData = data as { customer_info?: CustomerInfo; consultation_history?: ConsultationHistoryItem[] };
      if (roomData.customer_info) {
        const enriched = enrichCustomerInfo(roomData.customer_info);
        setCustomerInfo(enriched);
        logger.debug('Customer info received:', enriched);
      }
      if (roomData.consultation_history) {
        setConsultationHistory(roomData.consultation_history);
        logger.debug('Consultation history received:', roomData.consultation_history);
      }
    };

    client.onUserJoined = (data) => {
      logger.debug('User joined:', data);
      setPeerCount((data as { peer_count?: number }).peer_count || 0);
      setParticipants(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname
      }]);

      const userData = data as { customer_info?: CustomerInfo; consultation_history?: ConsultationHistoryItem[] };
      if (userData.customer_info) {
        const enriched = enrichCustomerInfo(userData.customer_info);
        setCustomerInfo(enriched);
      }
      if (userData.consultation_history) {
        setConsultationHistory(userData.consultation_history);
      }
    };

    client.onUserLeft = (data) => {
      logger.debug('User left:', data);
      setPeerCount((data as { peer_count?: number }).peer_count || 0);
      setParticipants(prev => prev.filter(p => p.peer_id !== data.peer_id));
    };

    client.onRemoteStream = (stream: MediaStream) => {
      logger.debug('Remote audio stream received');

      try {
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
        }

        const audioContext = new (window.AudioContext || (window as typeof window & { webkitAudioContext: typeof AudioContext }).webkitAudioContext)({
          latencyHint: 'interactive',
          sampleRate: 48000
        });
        audioContextRef.current = audioContext;

        const source = audioContext.createMediaStreamSource(stream);
        const gainNode = audioContext.createGain();
        gainNode.gain.value = 2.5;
        gainNodeRef.current = gainNode;

        source.connect(gainNode);
        gainNode.connect(audioContext.destination);

        logger.debug('Audio amplified with gain:', gainNode.gain.value);

        if (remoteAudioRef.current) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 0;
        }
      } catch (err) {
        logger.error('Web Audio API failed, using fallback:', err);
        if (remoteAudioRef.current && remoteAudioRef.current.srcObject !== stream) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 1.0;
          remoteAudioRef.current.play().catch(e => logger.error('Remote audio play failed:', e));
        }
      }
    };

    client.onConnectionStateChange = (state) => {
      setConnectionState(state);
      logger.debug('Connection state changed:', state);
    };

    client.onError = (err: Error) => {
      setError(err.message);
      logger.error('WebRTC error:', err);
    };

    client.onTranscript = (data: TranscriptData) => {
      logger.debug('Transcript received:', data);
      setTranscripts(prev => [...prev, {
        peer_id: (data as { peer_id?: string }).peer_id || '',
        nickname: (data as { nickname?: string }).nickname || '',
        text: data.text,
        timestamp: Number(data.timestamp) || Date.now(),
        receivedAt: Date.now()
      }]);
    };

    client.onAgentReady = (data: Record<string, unknown>) => {
      logger.debug('Agent ready:', data);
      if (data.llm_available) {
        setLlmStatus('ready');
      } else {
        setLlmStatus('failed');
      }
    };

    client.onAgentUpdate = (data: AgentUpdateData) => {
      logger.debug('Agent update received:', data);

      if (!data) return;

      const turnId = data.turnId || 'default';
      const node = data.node || 'unknown';
      const payload = data.data || {};

      setAgentUpdates((prev) => {
        const turnBucket = prev[turnId] || {};
        return {
          ...prev,
          [turnId]: {
            ...turnBucket,
            [node]: payload,
          },
        };
      });

      setLatestTurnId(turnId);
      setLlmStatus('connected');
    };

    client.onAgentStatus = (data: AgentStatusData) => {
      if (!data) return;
      if (data.status === 'processing') {
        setConsultationStatus('processing');
      } else if (data.status === 'error') {
        setConsultationStatus('error');
      }
    };

    // Cleanup
    return () => {
      if (clientRef.current) {
        clientRef.current.disconnect();
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
    };
  }, [options.wsUrl]);

  // Actions
  const connect = useCallback(async () => {
    if (!clientRef.current) return;
    try {
      setError('');
      await clientRef.current.connect();
      setIsConnected(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Connection failed: ${message}`);
      throw err;
    }
  }, []);

  const joinRoom = useCallback(async (
    newRoomName: string,
    newNickname: string,
    phoneNumber?: string,
    agentCode?: string
  ) => {
    if (!clientRef.current) return;
    try {
      setError('');
      setTranscripts([]);
      setLlmStatus('connecting');
      setCustomerInfo(null);
      setConsultationHistory([]);
      await clientRef.current.joinRoom(newRoomName, newNickname, phoneNumber || null, agentCode || null);
      setRoomName(newRoomName);
      setNickname(newNickname);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to join room: ${message}`);
      throw err;
    }
  }, []);

  const startCall = useCallback(async () => {
    if (!clientRef.current) return;
    try {
      setError('');
      await clientRef.current.startCall();
      setIsCallActive(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(`Failed to start call: ${message}`);
      throw err;
    }
  }, []);

  const leaveRoom = useCallback(() => {
    if (!clientRef.current) return;
    clientRef.current.leaveRoom();
    setIsInRoom(false);
    setIsCallActive(false);
    setRoomName('');
    setNickname('');
    setPeerCount(0);
    setParticipants([]);
    setCustomerInfo(null);
    setConsultationHistory([]);
  }, []);

  const endSession = useCallback(async (): Promise<SessionEndedData> => {
    if (!clientRef.current) {
      return { success: false, session_id: null, message: 'No client' };
    }
    return clientRef.current.endSession();
  }, []);

  const toggleAudio = useCallback((): boolean => {
    if (!clientRef.current) return false;
    const enabled = clientRef.current.toggleAudio();
    setIsAudioEnabled(enabled);
    return enabled;
  }, []);

  const clearError = useCallback(() => setError(''), []);
  const clearTranscripts = useCallback(() => setTranscripts([]), []);

  return {
    // Connection state
    isConnected,
    isInRoom,
    isCallActive,
    peerId,
    roomName,
    nickname,
    peerCount,
    connectionState,
    participants,
    error,

    // Transcripts
    transcripts,

    // Agent state
    llmStatus,
    consultationStatus,
    agentUpdates,
    latestTurnId,

    // Customer data
    customerInfo,
    consultationHistory,

    // Audio
    remoteAudioRef,
    isAudioEnabled,

    // Actions
    connect,
    joinRoom,
    startCall,
    leaveRoom,
    endSession,
    toggleAudio,
    clearError,
    clearTranscripts,
  };
}
