"use client";

/**
 * AssistantMain - Main dashboard for real-time consultation assistant
 *
 * Layout:
 * - Header: Call controls, status, timer, connection info
 * - Left Panel: Customer info, consultation history (agent only)
 * - Center Panel: AI insights (summary, sentiment, draft replies)
 * - Right Panel: Intent banner, RAG/FAQ recommendations (agent only)
 * - Floating: Chat transcript window
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { useWebRTCClient, useCallTimer } from '@/hooks';
import type { UserRole, CustomerInfo, ConsultationHistoryItem, SessionSaveResult } from '@/lib/types';
import { RoleSelection } from './RoleSelection';
import { ConnectionPanel } from './ConnectionPanel';
import { TranscriptPanel, CustomerInfoCard, ConsultationHistoryCard } from './TranscriptPanel';
import { InsightPanel, IntentBanner, AssistCards } from './InsightPanel';

// Assist card type
interface AssistCard {
  id: string;
  title: string;
  type: string;
  content?: string;
  collapsed: boolean;
  relevance?: number;
  metadata?: Record<string, unknown>;
  monthlyPrice?: number;
  briefInfo?: string;
  category?: string;
  cacheHit?: boolean;
  isNew?: boolean;
  ragGroupId?: string;
  ragIndex?: number;
}

export function AssistantMain() {
  // User role state
  const [userRole, setUserRole] = useState<UserRole>(null);

  // Panel visibility
  const [leftPanelVisible, setLeftPanelVisible] = useState(true);
  const [customerInfoCollapsed, setCustomerInfoCollapsed] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);

  // Floating chat
  const [floatingChatOpen, setFloatingChatOpen] = useState(false);
  const [unreadChatCount, setUnreadChatCount] = useState(0);
  const lastReadTranscriptCount = useRef(0);

  // Session save state
  const [isSavingSession, setIsSavingSession] = useState(false);
  const [saveSessionResult, setSaveSessionResult] = useState<SessionSaveResult | null>(null);

  // Assist cards
  const [assistCards, setAssistCards] = useState<AssistCard[]>([]);
  const [newCardIds, setNewCardIds] = useState<Set<string>>(new Set());

  // WebRTC hook
  const {
    isConnected,
    isInRoom,
    isCallActive,
    roomName,
    nickname,
    peerCount,
    connectionState,
    participants,
    error,
    transcripts,
    llmStatus,
    agentUpdates,
    latestTurnId,
    customerInfo,
    consultationHistory,
    remoteAudioRef,
    isAudioEnabled,
    connect,
    joinRoom,
    startCall,
    leaveRoom,
    endSession,
    toggleAudio,
    clearError,
  } = useWebRTCClient();

  // Call timer hook
  const callTimer = useCallTimer();

  // Get remote peer info
  const remotePeer = participants.length > 0 ? participants[0] : null;

  // Update unread count when chat is closed
  useEffect(() => {
    if (floatingChatOpen) {
      lastReadTranscriptCount.current = transcripts.length;
      setUnreadChatCount(0);
    } else {
      const newCount = transcripts.length - lastReadTranscriptCount.current;
      if (newCount > 0) {
        setUnreadChatCount(newCount);
      }
    }
  }, [transcripts, floatingChatOpen]);

  // Process RAG results into assist cards
  useEffect(() => {
    if (!latestTurnId) return;

    const bucket = agentUpdates[latestTurnId] || {};
    const ragData = bucket.rag_policy || {};
    const ragResult = (ragData as Record<string, unknown>).rag_policy_result || ragData;

    if ((ragResult as Record<string, unknown>).skipped) return;
    const recommendations = ((ragResult as Record<string, unknown>).recommendations || []) as Record<string, unknown>[];
    if (recommendations.length === 0) return;

    const cardId = `rag-${latestTurnId}`;

    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId || c.id.startsWith(`${cardId}-`))) return prev;

      const newCards: AssistCard[] = [];
      const newIds: string[] = [];

      recommendations.slice(0, 5).forEach((rec, idx) => {
        const metadata = (rec.metadata || {}) as Record<string, unknown>;
        const cardIdWithIdx = `${cardId}-rec-${idx}`;
        newIds.push(cardIdWithIdx);

        newCards.push({
          id: cardIdWithIdx,
          title: (rec.title as string) || 'Related Policy',
          type: 'rag',
          content: (rec.content as string) || '',
          metadata,
          relevance: rec.relevance_score as number,
          monthlyPrice: metadata.monthly_price as number,
          collapsed: idx > 0,
          isNew: true,
          ragGroupId: cardId,
          ragIndex: idx,
        });
      });

      setNewCardIds((prevIds) => {
        const updated = new Set(prevIds);
        newIds.forEach((id) => updated.add(id));
        return updated;
      });

      setTimeout(() => {
        setNewCardIds((prevIds) => {
          const updated = new Set(prevIds);
          newIds.forEach((id) => updated.delete(id));
          return updated;
        });
      }, 3000);

      return [...newCards, ...prev];
    });
  }, [latestTurnId, agentUpdates]);

  // Process FAQ results into assist cards
  useEffect(() => {
    if (!latestTurnId) return;

    const bucket = agentUpdates[latestTurnId] || {};
    const faqData = bucket.faq_search || {};
    const faqResult = (faqData as Record<string, unknown>).faq_result || faqData;
    const faqs = ((faqResult as Record<string, unknown>).faqs || []) as Record<string, unknown>[];

    if (faqs.length === 0) return;

    const cardId = `faq-${latestTurnId}`;

    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId || c.id.startsWith(`${cardId}-`))) return prev;

      const newCards: AssistCard[] = [];
      const newIds: string[] = [];

      faqs.slice(0, 3).forEach((faq, idx) => {
        const cardIdWithIdx = `${cardId}-faq-${idx}`;
        newIds.push(cardIdWithIdx);

        newCards.push({
          id: cardIdWithIdx,
          title: (faq.question as string) || 'FAQ',
          type: 'faq',
          content: (faq.answer as string) || '',
          category: faq.category as string,
          cacheHit: (faqResult as Record<string, unknown>).cache_hit as boolean,
          collapsed: idx > 0,
          isNew: true,
        });
      });

      setNewCardIds((prevIds) => {
        const updated = new Set(prevIds);
        newIds.forEach((id) => updated.add(id));
        return updated;
      });

      setTimeout(() => {
        setNewCardIds((prevIds) => {
          const updated = new Set(prevIds);
          newIds.forEach((id) => updated.delete(id));
          return updated;
        });
      }, 3000);

      return [...newCards, ...prev];
    });
  }, [latestTurnId, agentUpdates]);

  // Card actions
  const handleToggleCard = useCallback((cardId: string) => {
    setAssistCards((prev) =>
      prev.map((card) => (card.id === cardId ? { ...card, collapsed: !card.collapsed } : card))
    );
  }, []);

  const handleDismissCard = useCallback((cardId: string) => {
    setAssistCards((prev) => prev.filter((card) => card.id !== cardId));
  }, []);

  // Call controls
  const handleStartCall = async () => {
    try {
      await startCall();
      callTimer.start();
    } catch (err) {
      console.error('Failed to start call:', err);
    }
  };

  const handleEndCall = async () => {
    if (!isCallActive) return;

    // Customer leaves immediately
    if (userRole !== 'agent') {
      handleLeaveRoom();
      return;
    }

    // Agent: save session first
    setIsSavingSession(true);
    setSaveSessionResult(null);

    try {
      const result = await endSession();
      setSaveSessionResult(result);
    } catch (err) {
      setSaveSessionResult({
        success: false,
        message: err instanceof Error ? err.message : 'Failed to save session',
      });
    }
  };

  const handleLeaveRoom = () => {
    callTimer.stop();
    leaveRoom();
    setAssistCards([]);
    setIsSavingSession(false);
    setSaveSessionResult(null);
  };

  const handleConfirmSaveResult = () => {
    const shouldLeave = saveSessionResult?.success && userRole === 'agent';
    setIsSavingSession(false);
    setSaveSessionResult(null);
    if (shouldLeave) {
      handleLeaveRoom();
    }
  };

  // Role selection
  if (!userRole) {
    return <RoleSelection onSelectRole={setUserRole} />;
  }

  // Connection / Room setup
  if (!isConnected || !isInRoom) {
    return (
      <ConnectionPanel
        userRole={userRole}
        isConnected={isConnected}
        isInRoom={isInRoom}
        error={error}
        onConnect={connect}
        onJoinRoom={joinRoom}
        onResetRole={() => setUserRole(null)}
      />
    );
  }

  // Get current issue summary for header
  const bucket = latestTurnId ? agentUpdates[latestTurnId] || {} : {};
  const summaryRaw = bucket.summarize || {};
  const summaryData = (summaryRaw as Record<string, unknown>).summary_result || summaryRaw;
  const intentRaw = bucket.intent || {};
  const intentData = (intentRaw as Record<string, unknown>).intent_result || intentRaw;
  const currentIssueSummary = (summaryData as Record<string, unknown>).customer_issue ||
    (intentData as Record<string, unknown>).intent_label ||
    'Waiting...';

  // Main Dashboard
  return (
    <div className="flex h-screen flex-col bg-bg-primary">
      {/* Session saving overlay */}
      {isSavingSession && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="rounded-xl bg-bg-card p-8 text-center shadow-2xl">
            {!saveSessionResult ? (
              <>
                <div className="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
                <p className="text-text-primary">Saving consultation data...</p>
              </>
            ) : (
              <>
                <div className={`mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full ${
                  saveSessionResult.success ? 'bg-accent-green' : 'bg-accent-red'
                }`}>
                  {saveSessionResult.success ? (
                    <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : (
                    <svg className="h-6 w-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  )}
                </div>
                <p className="mb-2 text-text-primary">
                  {saveSessionResult.success ? 'Saved successfully!' : 'Save failed'}
                </p>
                {saveSessionResult.message && (
                  <p className="mb-4 text-sm text-text-secondary">{saveSessionResult.message}</p>
                )}
                <button
                  onClick={handleConfirmSaveResult}
                  className="rounded-lg bg-primary px-6 py-2 font-medium text-white hover:bg-primary/90"
                >
                  {saveSessionResult.success ? 'Confirm & Leave' : 'OK'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <header className="flex items-center justify-between border-b border-border-primary bg-bg-card px-4 py-3">
        {/* Left: Call controls */}
        <div className="flex items-center gap-3">
          {!isCallActive ? (
            <button
              onClick={handleStartCall}
              className="rounded-lg bg-accent-green px-4 py-2 font-medium text-white hover:bg-accent-green/90"
            >
              Start Call
            </button>
          ) : (
            <>
              <button
                onClick={toggleAudio}
                className={`rounded-lg px-3 py-2 font-medium ${
                  isAudioEnabled
                    ? 'bg-primary text-white'
                    : 'bg-bg-secondary text-text-secondary'
                }`}
              >
                {isAudioEnabled ? 'MIC ON' : 'MIC OFF'}
              </button>
              <button
                onClick={handleEndCall}
                disabled={isSavingSession}
                className="rounded-lg bg-accent-red px-4 py-2 font-medium text-white hover:bg-accent-red/90 disabled:opacity-50"
              >
                {userRole === 'agent' ? 'End & Save' : 'End Call'}
              </button>
            </>
          )}
          {!isCallActive && (
            <button
              onClick={handleLeaveRoom}
              className="rounded-lg border border-border-primary px-3 py-2 text-sm text-text-secondary hover:bg-bg-secondary"
            >
              Leave Room
            </button>
          )}

          {/* Status badge */}
          <div className={`flex items-center gap-2 rounded-full px-3 py-1 ${
            isCallActive ? 'bg-accent-green/10' : 'bg-bg-secondary'
          }`}>
            {isCallActive && (
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-green opacity-75"></span>
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-green"></span>
              </span>
            )}
            <span className={`text-sm font-medium ${isCallActive ? 'text-accent-green' : 'text-text-muted'}`}>
              {isCallActive ? 'Active' : 'Waiting'}
            </span>
          </div>

          {/* Timer */}
          {isCallActive && (
            <span className="font-mono text-lg font-semibold text-text-primary">
              {callTimer.formatted}
            </span>
          )}

          {/* Customer brief */}
          {userRole === 'agent' && remotePeer && (
            <div className="ml-2 flex items-center gap-2 text-sm">
              <span className="font-medium text-text-primary">{remotePeer.nickname}</span>
              {(() => {
                const grade = customerInfo && (customerInfo as CustomerInfo).membership_grade;
                if (!grade) return null;
                return (
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
                    {String(grade)}
                  </span>
                );
              })()}
            </div>
          )}
        </div>

        {/* Center: Issue summary */}
        <div className="flex-1 px-4 text-center">
          <span className="text-sm text-text-secondary">{String(currentIssueSummary)}</span>
        </div>

        {/* Right: Connection status */}
        <div className="flex items-center gap-3">
          <div className={`flex items-center gap-2 text-sm ${
            connectionState === 'connected' ? 'text-accent-green' : 'text-text-muted'
          }`}>
            <span className={`h-2 w-2 rounded-full ${
              connectionState === 'connected' ? 'bg-accent-green' : 'bg-text-muted'
            }`}></span>
            {connectionState || 'Disconnected'}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className={`flex flex-1 overflow-hidden ${userRole === 'customer' ? '' : ''}`}>
        {/* Left panel toggle */}
        {userRole === 'agent' && (
          <button
            onClick={() => setLeftPanelVisible(!leftPanelVisible)}
            className="absolute left-0 top-1/2 z-10 -translate-y-1/2 rounded-r-lg bg-bg-card px-1 py-4 text-text-muted shadow hover:bg-bg-secondary"
          >
            {leftPanelVisible ? '<' : '>'}
          </button>
        )}

        {/* Left panel: Customer info & history */}
        {userRole === 'agent' && leftPanelVisible && (
          <div className="w-80 flex-shrink-0 overflow-y-auto border-r border-border-primary bg-bg-secondary p-4 space-y-4">
            <CustomerInfoCard
              customerInfo={customerInfo as Record<string, unknown>}
              remotePeerName={remotePeer?.nickname || null}
              collapsed={customerInfoCollapsed}
              onToggle={() => setCustomerInfoCollapsed(!customerInfoCollapsed)}
            />
            <ConsultationHistoryCard
              history={consultationHistory as ConsultationHistoryItem[]}
              collapsed={historyCollapsed}
              onToggle={() => setHistoryCollapsed(!historyCollapsed)}
              onSelectHistory={(item) => {
                console.log('Selected history:', item);
                // TODO: Open history detail modal
              }}
            />
          </div>
        )}

        {/* Center panel: AI insights */}
        <div className="flex-1 overflow-y-auto p-4">
          <InsightPanel
            agentUpdates={agentUpdates}
            latestTurnId={latestTurnId}
            userRole={userRole}
          />
        </div>

        {/* Right panel: Intent & recommendations (agent only) */}
        {userRole === 'agent' && (
          <div className="w-96 flex-shrink-0 overflow-y-auto border-l border-border-primary bg-bg-secondary p-4 space-y-4">
            <IntentBanner agentUpdates={agentUpdates} latestTurnId={latestTurnId} />
            <div className="rounded-lg border border-border-primary bg-bg-card">
              <div className="px-4 py-3 border-b border-border-primary">
                <h3 className="font-semibold text-text-primary">AI Recommendations</h3>
              </div>
              <div className="p-4">
                <AssistCards
                  cards={assistCards}
                  newCardIds={newCardIds}
                  onToggle={handleToggleCard}
                  onDismiss={handleDismissCard}
                />
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Floating chat */}
      <TranscriptPanel
        transcripts={transcripts}
        isOpen={floatingChatOpen}
        onToggle={() => {
          setFloatingChatOpen(!floatingChatOpen);
          if (!floatingChatOpen) {
            lastReadTranscriptCount.current = transcripts.length;
            setUnreadChatCount(0);
          }
        }}
        unreadCount={unreadChatCount}
        callStartTime={callTimer.startTime}
      />

      {/* Hidden audio element */}
      <audio ref={remoteAudioRef} autoPlay playsInline />
    </div>
  );
}
