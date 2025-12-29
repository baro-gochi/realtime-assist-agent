/**
 * @fileoverview Library exports
 *
 * 프로젝트 전역에서 사용되는 유틸리티 및 클라이언트 라이브러리
 */

// Logger
export { default as logger } from './logger';
export type { Logger, LogLevel } from './logger';

// WebRTC Client
export { WebRTCClient } from './webrtc';
export type {
  IceServer,
  SignalingMessage,
  RoomJoinedData,
  ParticipantInfo,
  UserEventData,
  TranscriptData,
  AgentUpdateData,
  AgentStatusData,
  AgentConsultationData,
  SessionEndedData,
  IceCandidateData,
  SdpAnswerData,
  ConnectionState,
  OnPeerIdCallback,
  OnRoomJoinedCallback,
  OnUserJoinedCallback,
  OnUserLeftCallback,
  OnRemoteStreamCallback,
  OnLocalStreamCallback,
  OnConnectionStateChangeCallback,
  OnErrorCallback,
  OnTranscriptCallback,
  OnAgentReadyCallback,
  OnAgentUpdateCallback,
  OnAgentStatusCallback,
  OnAgentConsultationCallback,
  OnSessionEndedCallback,
} from './webrtc';
