"use client";

/**
 * TranscriptPanel - Real-time transcript display (floating chat)
 */

import { useRef, useEffect } from 'react';
import type { TranscriptEntry } from '@/lib/types';

interface TranscriptPanelProps {
  transcripts: TranscriptEntry[];
  isOpen: boolean;
  onToggle: () => void;
  unreadCount: number;
  callStartTime: number | null;
}

function formatElapsedTime(timestamp: number, callStartTime: number | null): string {
  if (!callStartTime) return '';
  const elapsed = Math.floor((timestamp - callStartTime) / 1000);
  const mins = Math.floor(elapsed / 60);
  const secs = elapsed % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

export function TranscriptPanel({
  transcripts,
  isOpen,
  onToggle,
  unreadCount,
  callStartTime,
}: TranscriptPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when transcripts update and panel is open
  useEffect(() => {
    if (isOpen && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [transcripts, isOpen]);

  return (
    <>
      {/* Floating chat button */}
      <button
        onClick={onToggle}
        className={`fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full shadow-lg transition-all ${
          isOpen
            ? 'bg-primary text-white'
            : 'bg-bg-card text-text-primary hover:bg-bg-secondary'
        }`}
      >
        {isOpen ? (
          <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <>
            <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            {unreadCount > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-accent-red text-xs font-bold text-white">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </>
        )}
      </button>

      {/* Floating chat panel */}
      {isOpen && (
        <div className="fixed bottom-24 right-6 z-40 flex h-96 w-80 flex-col rounded-xl border border-border-primary bg-bg-card shadow-2xl">
          <div className="flex items-center justify-between border-b border-border-primary px-4 py-3">
            <h3 className="font-semibold text-text-primary">Conversation</h3>
            <span className="text-xs text-text-muted">
              {transcripts.length} messages
            </span>
          </div>
          <div
            ref={containerRef}
            className="flex-1 overflow-y-auto p-4 space-y-3"
          >
            {transcripts.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-text-muted">No messages yet</p>
              </div>
            ) : (
              transcripts.map((transcript, index) => (
                <div key={index} className="group">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium text-primary">
                      {transcript.nickname}
                    </span>
                    <span className="text-xs text-text-muted">
                      {formatElapsedTime(transcript.timestamp, callStartTime)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-text-primary leading-relaxed">
                    {transcript.text}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </>
  );
}

/**
 * CustomerInfoCard - Customer information display (agent only)
 */
interface CustomerInfoCardProps {
  customerInfo: Record<string, unknown> | null;
  remotePeerName: string | null;
  collapsed: boolean;
  onToggle: () => void;
}

export function CustomerInfoCard({
  customerInfo,
  remotePeerName,
  collapsed,
  onToggle,
}: CustomerInfoCardProps) {
  const infoRows = [
    { label: 'Customer ID', key: 'customer_id' },
    { label: 'Name', value: remotePeerName },
    { label: 'Phone', key: 'phone_number' },
    { label: 'Grade', key: 'membership_grade', highlight: true },
    { label: 'Age/Gender', compute: () => {
      const age = customerInfo?.age;
      const gender = customerInfo?.gender;
      return `${age ? `${age}yo` : '-'} / ${gender || '-'}`;
    }},
    { label: 'Plan', key: 'current_plan', altKey: 'plan_name', highlight: true },
    { label: 'Monthly Fee', key: 'monthly_fee', format: (v: number) => `${v.toLocaleString()} KRW` },
    { label: 'Contract', key: 'contract_status' },
    { label: 'Bundle', key: 'bundle_info', default: 'None' },
    { label: 'Data', key: 'data_allowance' },
    { label: 'Join Date', key: 'subscription_date' },
    { label: 'Duration', key: 'subscription_duration' },
  ];

  const getValue = (row: typeof infoRows[0]) => {
    if (row.value !== undefined) return row.value || '-';
    if (row.compute) return row.compute();

    const val = (row.key && customerInfo?.[row.key]) ||
                (row.altKey && customerInfo?.[row.altKey]) ||
                row.default;

    if (val === undefined || val === null) return '-';
    if (row.format && typeof val === 'number') return row.format(val);
    return String(val);
  };

  return (
    <div className={`rounded-lg border border-border-primary bg-bg-card overflow-hidden ${collapsed ? '' : ''}`}>
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/50"
      >
        <h3 className="font-semibold text-text-primary">Customer Info</h3>
        <span className="text-text-muted">{collapsed ? '+' : '-'}</span>
      </button>
      {!collapsed && (
        <div className="border-t border-border-primary px-4 py-3">
          {customerInfo ? (
            <div className="grid gap-2">
              {infoRows.map((row, idx) => (
                <div key={idx} className="flex justify-between text-sm">
                  <span className="text-text-muted">{row.label}</span>
                  <span className={row.highlight ? 'font-medium text-primary' : 'text-text-primary'}>
                    {getValue(row)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-4 text-center">
              <p className="text-sm text-text-muted">Waiting for customer...</p>
              <p className="mt-1 text-xs text-text-muted">
                Info will appear when customer joins
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * ConsultationHistoryCard - Past consultation history (agent only)
 */
interface HistoryItem {
  session_id: string;
  consultation_date?: string;
  consultation_type?: string;
  agent_name?: string;
  final_summary?: string;
}

interface ConsultationHistoryCardProps {
  history: HistoryItem[];
  collapsed: boolean;
  onToggle: () => void;
  onSelectHistory: (item: HistoryItem) => void;
}

export function ConsultationHistoryCard({
  history,
  collapsed,
  onToggle,
  onSelectHistory,
}: ConsultationHistoryCardProps) {
  return (
    <div className="rounded-lg border border-border-primary bg-bg-card overflow-hidden">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/50"
      >
        <h3 className="font-semibold text-text-primary">
          Past Consultations {history.length > 0 && `(${history.length})`}
        </h3>
        <span className="text-text-muted">{collapsed ? '+' : '-'}</span>
      </button>
      {!collapsed && (
        <div className="border-t border-border-primary px-4 py-3">
          {history.length > 0 ? (
            <div className="space-y-3">
              {history.map((item, index) => {
                const meta = [
                  item.consultation_date,
                  item.consultation_type || 'Consultation',
                  item.agent_name ? `Agent: ${item.agent_name}` : null,
                ].filter(Boolean).join(' / ');

                const summary = item.final_summary || 'No summary';
                const shortSummary = summary.length > 60 ? `${summary.slice(0, 60)}...` : summary;

                return (
                  <button
                    key={index}
                    onClick={() => onSelectHistory(item)}
                    className="w-full rounded-lg border border-border-primary bg-bg-secondary p-3 text-left transition-colors hover:border-primary"
                  >
                    <div className="flex items-center justify-between text-xs text-text-muted">
                      <span>{meta}</span>
                      <span className="text-primary">View</span>
                    </div>
                    <p className="mt-1 text-sm text-text-primary">{shortSummary}</p>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="py-2 text-center text-sm text-text-muted">
              No consultation history
            </p>
          )}
        </div>
      )}
    </div>
  );
}
