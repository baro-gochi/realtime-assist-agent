"use client";

/**
 * InsightPanel - AI insights display (summary, intent, sentiment, drafts)
 */

import { useState } from 'react';
import type { AgentUpdates } from '@/lib/types';

// Types for agent data
interface SummaryData {
  summary?: string;
  customer_issue?: string;
  agent_action?: string;
}

interface IntentData {
  intent_label?: string;
  intent_explanation?: string;
}

interface SentimentData {
  sentiment_label?: string;
  sentiment_score?: number;
  sentiment_explanation?: string;
}

interface DraftData {
  short_reply?: string;
  keywords?: string[];
}

interface RiskData {
  risk_flags?: string[];
  risk_explanation?: string;
}

interface InsightPanelProps {
  agentUpdates: AgentUpdates;
  latestTurnId: string | null;
  userRole: 'agent' | 'customer' | null;
}

// Extract data from agent updates with fallback
function extractNodeData<T>(
  bucket: Record<string, Record<string, unknown>>,
  nodeKey: string,
  resultKey: string
): T | Record<string, never> {
  const raw = bucket[nodeKey] || {};
  return (raw[resultKey] || raw) as T || {};
}

export function InsightPanel({
  agentUpdates,
  latestTurnId,
  userRole,
}: InsightPanelProps) {
  const [summaryCollapsed, setSummaryCollapsed] = useState(false);
  const [emotionCollapsed, setEmotionCollapsed] = useState(false);

  // Get latest bucket
  const bucket = latestTurnId ? agentUpdates[latestTurnId] || {} : {};

  // Extract data from each node
  const summaryData = extractNodeData<SummaryData>(bucket, 'summarize', 'summary_result');
  const intentData = extractNodeData<IntentData>(bucket, 'intent', 'intent_result');
  const sentimentData = extractNodeData<SentimentData>(bucket, 'sentiment', 'sentiment_result');
  const draftRaw = bucket.draft_reply || bucket.draft_replies || {};
  const draftData = ((draftRaw as Record<string, unknown>).draft_replies || draftRaw) as DraftData;
  const riskRaw = bucket.risk || {};
  const riskData = ((riskRaw as Record<string, unknown>).risk_result || riskRaw) as RiskData;

  const riskFlags = riskData.risk_flags || [];

  // Emotion state mapping
  const getEmotionState = (label?: string): string => {
    if (!label) return 'stable';
    const l = label.toLowerCase();
    if (l.includes('angry') || l.includes('anger')) return 'angry';
    if (l.includes('anxious') || l.includes('anxiety')) return 'anxious';
    if (l.includes('confused') || l.includes('confusion')) return 'confused';
    return 'stable';
  };

  const emotionState = getEmotionState(sentimentData.sentiment_label);
  const emotionColors: Record<string, string> = {
    stable: 'bg-accent-green/10 text-accent-green',
    anxious: 'bg-accent-orange/10 text-accent-orange',
    confused: 'bg-accent-orange/10 text-accent-orange',
    angry: 'bg-accent-red/10 text-accent-red',
  };

  return (
    <div className="space-y-4">
      {/* Draft Reply Card - Agent only */}
      {userRole === 'agent' && (
        <div className="rounded-lg border border-border-primary bg-bg-card">
          <div className="px-4 py-3 border-b border-border-primary">
            <h3 className="font-semibold text-text-primary">Response Draft</h3>
          </div>
          <div className="p-4">
            {draftData.keywords && draftData.keywords.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-2">
                {draftData.keywords.map((keyword, idx) => (
                  <span
                    key={idx}
                    className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            )}
            <p className="text-sm text-text-primary leading-relaxed">
              {draftData.short_reply || 'Waiting for response draft...'}
            </p>
            <p className="mt-2 text-xs text-text-muted">Click to copy</p>
          </div>
        </div>
      )}

      {/* Summary Card */}
      <div className="rounded-lg border border-border-primary bg-bg-card overflow-hidden">
        <button
          onClick={() => setSummaryCollapsed(!summaryCollapsed)}
          className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/50"
        >
          <h3 className="font-semibold text-text-primary">Auto Summary</h3>
          <span className="text-text-muted">{summaryCollapsed ? '+' : '-'}</span>
        </button>
        {!summaryCollapsed && (
          <div className="border-t border-border-primary p-4 space-y-3">
            <div>
              <div className="text-xs font-medium text-text-muted uppercase mb-1">Summary</div>
              <p className="text-sm text-text-primary">{summaryData.summary || 'Waiting...'}</p>
            </div>
            <div>
              <div className="text-xs font-medium text-text-muted uppercase mb-1">Customer Issue</div>
              <p className="text-sm text-text-primary">{summaryData.customer_issue || 'Waiting...'}</p>
            </div>
            <div>
              <div className="text-xs font-medium text-text-muted uppercase mb-1">Agent Action</div>
              <p className="text-sm text-text-primary">{summaryData.agent_action || 'Waiting...'}</p>
            </div>
          </div>
        )}
      </div>

      {/* Emotion Card */}
      <div className="rounded-lg border border-border-primary bg-bg-card overflow-hidden">
        <button
          onClick={() => setEmotionCollapsed(!emotionCollapsed)}
          className="flex w-full items-center justify-between px-4 py-3 text-left hover:bg-bg-secondary/50"
        >
          <div className="flex items-center gap-2">
            <span className="font-semibold text-text-primary">Emotion</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${emotionColors[emotionState]}`}>
              {sentimentData.sentiment_label || 'Stable'}
            </span>
          </div>
          <span className="text-text-muted">{emotionCollapsed ? '+' : '-'}</span>
        </button>
        {!emotionCollapsed && (
          <div className="border-t border-border-primary p-4">
            <div className="flex gap-4 mb-3">
              <div className="flex-1 rounded-lg bg-bg-secondary p-3 text-center">
                <div className="text-xs text-text-muted mb-1">Intensity</div>
                <div className="text-lg font-semibold text-text-primary">
                  {sentimentData.sentiment_score ?? '-'}
                </div>
              </div>
              <div className="flex-1 rounded-lg bg-bg-secondary p-3 text-center">
                <div className="text-xs text-text-muted mb-1">Churn Risk</div>
                <div className={`text-lg font-semibold ${riskFlags.includes('churn') || riskFlags.includes('cancellation') ? 'text-accent-red' : 'text-accent-green'}`}>
                  {riskFlags.includes('churn') || riskFlags.includes('cancellation') ? 'High' : 'Low'}
                </div>
              </div>
            </div>
            {sentimentData.sentiment_explanation && (
              <p className="text-sm text-text-secondary bg-bg-secondary rounded-lg p-3">
                {sentimentData.sentiment_explanation}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * IntentBanner - Customer intent header banner
 */
interface IntentBannerProps {
  agentUpdates: AgentUpdates;
  latestTurnId: string | null;
}

export function IntentBanner({ agentUpdates, latestTurnId }: IntentBannerProps) {
  const bucket = latestTurnId ? agentUpdates[latestTurnId] || {} : {};
  const intentRaw = bucket.intent || {};
  const intentData = ((intentRaw as Record<string, unknown>).intent_result || intentRaw) as {
    intent_label?: string;
    intent_explanation?: string;
  };

  return (
    <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
      <div className="text-sm font-medium text-primary">
        Customer Intent: {intentData.intent_label || 'Analyzing...'}
      </div>
      {intentData.intent_explanation && (
        <p className="mt-1 text-xs text-text-secondary">
          {intentData.intent_explanation}
        </p>
      )}
    </div>
  );
}

/**
 * AssistCard - AI recommendation card
 */
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
}

interface AssistCardsProps {
  cards: AssistCard[];
  newCardIds: Set<string>;
  onToggle: (id: string) => void;
  onDismiss: (id: string) => void;
}

export function AssistCards({
  cards,
  newCardIds,
  onToggle,
  onDismiss,
}: AssistCardsProps) {
  const typeLabels: Record<string, string> = {
    reply: 'Reply',
    policy: 'Policy',
    risk: 'Risk',
    guide: 'Guide',
    rag: 'RAG',
    faq: 'FAQ',
  };

  const typeColors: Record<string, string> = {
    reply: 'bg-primary/10 text-primary',
    policy: 'bg-accent-blue/10 text-accent-blue',
    risk: 'bg-accent-red/10 text-accent-red',
    guide: 'bg-accent-green/10 text-accent-green',
    rag: 'bg-accent-purple/10 text-accent-purple',
    faq: 'bg-accent-orange/10 text-accent-orange',
  };

  if (cards.length === 0) {
    return (
      <p className="text-sm text-text-muted">No recommendations yet.</p>
    );
  }

  return (
    <div className="space-y-3">
      {cards.map((card) => {
        const isHighlighted = newCardIds.has(card.id);

        return (
          <div
            key={card.id}
            className={`rounded-lg border bg-bg-card overflow-hidden transition-all ${
              isHighlighted ? 'border-primary ring-2 ring-primary/20' : 'border-border-primary'
            }`}
          >
            <div
              onClick={() => onToggle(card.id)}
              className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-bg-secondary/50"
            >
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${typeColors[card.type] || 'bg-bg-secondary text-text-secondary'}`}>
                  {typeLabels[card.type] || 'Info'}
                </span>
                <span className="text-sm font-medium text-text-primary truncate">
                  {card.title}
                </span>
                {card.relevance && (
                  <span className="text-xs text-text-muted">
                    {Math.round(card.relevance * 100)}%
                  </span>
                )}
                {isHighlighted && (
                  <span className="rounded-full bg-accent-green px-2 py-0.5 text-xs font-bold text-white">
                    NEW
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 ml-2">
                <span className="text-text-muted">{card.collapsed ? '+' : '-'}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); onDismiss(card.id); }}
                  className="ml-1 text-text-muted hover:text-text-primary"
                >
                  x
                </button>
              </div>
            </div>
            {!card.collapsed && (
              <div className="border-t border-border-primary p-4">
                {/* FAQ card */}
                {card.type === 'faq' && card.category && (
                  <div className="mb-2 flex items-center gap-2 text-xs">
                    <span className="text-text-muted">{card.category}</span>
                    {card.cacheHit && (
                      <span className="rounded bg-accent-blue/10 px-1.5 py-0.5 text-accent-blue">
                        Cached
                      </span>
                    )}
                  </div>
                )}
                {/* RAG card details */}
                {card.type === 'rag' && (
                  <div className="space-y-2">
                    {card.monthlyPrice != null && (
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Monthly</span>
                        <span className="font-medium text-primary">
                          {card.monthlyPrice.toLocaleString()} KRW
                        </span>
                      </div>
                    )}
                    {card.metadata && card.metadata.data_allowance != null && (
                      <div className="flex justify-between text-sm">
                        <span className="text-text-muted">Data</span>
                        <span className="text-text-primary">{String(card.metadata.data_allowance)}</span>
                      </div>
                    )}
                    {card.metadata && card.metadata.tip != null && (
                      <div className="mt-2 rounded-lg bg-accent-orange/10 p-2">
                        <span className="text-xs font-medium text-accent-orange">TIP: </span>
                        <span className="text-xs text-text-secondary">{String(card.metadata.tip)}</span>
                      </div>
                    )}
                  </div>
                )}
                {/* Content */}
                {card.content && card.type !== 'rag' && (
                  <p className="text-sm text-text-primary whitespace-pre-wrap">
                    {card.content}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
