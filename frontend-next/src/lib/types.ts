/**
 * @fileoverview 공통 타입 정의
 */

// =============================================================================
// User Role Types
// =============================================================================

export type UserRole = 'agent' | 'customer' | null;

// =============================================================================
// Customer Information
// =============================================================================

export interface CustomerInfo {
  phone_number?: string;
  name?: string;
  subscription_date?: string;
  subscription_duration?: string;
  plan?: string;
  status?: string;
  [key: string]: unknown;
}

// =============================================================================
// Consultation History
// =============================================================================

export interface ConsultationHistoryItem {
  session_id: string;
  date: string;
  summary?: string;
  agent_name?: string;
  duration?: number;
  [key: string]: unknown;
}

// =============================================================================
// Transcript Types
// =============================================================================

export interface TranscriptEntry {
  peer_id: string;
  nickname: string;
  text: string;
  timestamp: number;
  receivedAt: number;
}

// =============================================================================
// AI Agent Types
// =============================================================================

export type LLMStatus = 'connecting' | 'connected' | 'ready' | 'failed';
export type ConsultationStatus = 'idle' | 'processing' | 'done' | 'error';

export interface AgentUpdate {
  [node: string]: Record<string, unknown>;
}

export interface AgentUpdates {
  [turnId: string]: AgentUpdate;
}

export interface ConsultationResult {
  guide: string[];
  recommendations: string[];
  citations: string[];
  [key: string]: unknown;
}

// =============================================================================
// Room Types
// =============================================================================

export interface RoomInfo {
  room_name: string;
  peer_count: number;
  peers?: ParticipantInfo[];
  created_at?: string;
}

export interface ParticipantInfo {
  peer_id: string;
  nickname: string;
}

// =============================================================================
// Session Types
// =============================================================================

export interface SessionSaveResult {
  success: boolean;
  session_id?: string | null;
  message?: string;
}

// =============================================================================
// Panel State Types
// =============================================================================

export interface PanelVisibility {
  leftPanel: boolean;
  customerInfo: boolean;
  conversation: boolean;
  history: boolean;
  intent: boolean;
  summary: boolean;
  emotion: boolean;
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * subscription_date 기반 사용 기간 계산
 */
export function formatSubscriptionDuration(subscriptionDate: string | undefined): string | null {
  if (!subscriptionDate) return null;
  try {
    const start = new Date(subscriptionDate);
    if (Number.isNaN(start.getTime())) return null;
    const today = new Date();
    if (start > today) return '0일';

    const diffMs = today.getTime() - start.getTime();
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);

    const parts: string[] = [];
    if (years) parts.push(`${years}년`);
    if (months) parts.push(`${months}개월`);
    const main = parts.length ? parts.join(' ') : `${days}일`;
    return `${main} (총 ${days}일)`;
  } catch {
    return null;
  }
}

/**
 * 고객 정보에 사용기간을 보정해서 반환
 */
export function enrichCustomerInfo(info: CustomerInfo | null): CustomerInfo | null {
  if (!info) return info;
  if (info.subscription_duration || !info.subscription_date) return info;
  const duration = formatSubscriptionDuration(info.subscription_date);
  if (!duration) return info;
  return { ...info, subscription_duration: duration };
}

/**
 * 통화 시간 포맷팅
 */
export function formatCallDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
