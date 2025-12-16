/**
 * @fileoverview AI 상담 어시스턴트 메인 대시보드
 *
 * @description
 * 상담사를 위한 AI 어시스턴트 대시보드 컴포넌트입니다.
 * 실시간 STT, 연결 정보, 대화 내역, AI 추천 답변 등을 표시합니다.
 *
 * 레이아웃 구조:
 * - 상단바: 통화 정보 / 타이머 / 감정 온도 / 위험 알림
 * - 좌측: 실시간 전사 (말풍선 UI)
 * - 중앙: 핵심 인사이트 (의도, 요약, 감정)
 * - 우측: 응답 초안 / AI 추천 정보
 */

import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { WebRTCClient } from './webrtc';
import './AssistantMain.css';

/**
 * subscription_date 기반 사용 기간 계산 (백엔드 필드 누락 시 프런트 보정)
 * @param {string} subscriptionDate ISO 날짜 문자열 (yyyy-mm-dd)
 * @returns {string|null} 사용 기간 문자열 (예: "2년 3개월 (총 780일)")
 */
function formatSubscriptionDuration(subscriptionDate) {
  if (!subscriptionDate) return null;
  try {
    const start = new Date(subscriptionDate);
    if (Number.isNaN(start.getTime())) return null;
    const today = new Date();
    if (start > today) return '0일';

    const diffMs = today - start;
    const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    const years = Math.floor(days / 365);
    const months = Math.floor((days % 365) / 30);

    const parts = [];
    if (years) parts.push(`${years}년`);
    if (months) parts.push(`${months}개월`);
    const main = parts.length ? parts.join(' ') : `${days}일`;
    return `${main} (총 ${days}일)`;
  } catch (e) {
    return null;
  }
}

/**
 * 고객 정보에 사용기간을 보정해서 반환
 * @param {object} info 고객 정보 객체
 * @returns {object} 보정된 고객 정보
 */
function enrichCustomerInfo(info) {
  if (!info) return info;
  if (info.subscription_duration || !info.subscription_date) return info;
  const duration = formatSubscriptionDuration(info.subscription_date);
  if (!duration) return info;
  return { ...info, subscription_duration: duration };
}

/**
 * FAQ 답변 텍스트를 파싱하여 구조화된 JSX로 변환
 * @param {string} content - FAQ 답변 텍스트
 * @returns {JSX.Element} 파싱된 FAQ 컨텐츠
 */
function renderFaqContent(content) {
  if (!content) return null;

  const lines = content.split('\n');
  const elements = [];
  let currentList = [];
  let listKey = 0;

  const flushList = () => {
    if (currentList.length > 0) {
      elements.push(
        <ul key={`list-${listKey++}`} className="faq-list">
          {currentList.map((item, idx) => (
            <li key={idx} className="faq-list-item">{item}</li>
          ))}
        </ul>
      );
      currentList = [];
    }
  };

  lines.forEach((line, idx) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushList();
      return;
    }

    // 섹션 헤더 (■ 로 시작)
    if (trimmed.startsWith('■')) {
      flushList();
      elements.push(
        <h4 key={`header-${idx}`} className="faq-section-header">
          {trimmed.substring(1).trim()}
        </h4>
      );
    }
    // 리스트 항목 (-, ㆍ, · 로 시작)
    else if (/^[-ㆍ·]\s*/.test(trimmed)) {
      currentList.push(trimmed.replace(/^[-ㆍ·]\s*/, ''));
    }
    // 일반 텍스트
    else {
      flushList();
      elements.push(
        <p key={`para-${idx}`} className="faq-paragraph">{trimmed}</p>
      );
    }
  });

  flushList();

  return <div className="faq-content-parsed">{elements}</div>;
}

function AssistantMain({ isDarkMode, onToggleTheme }) {
  const defaultAssistCards = () => [];

  // 역할 선택 ('agent' | 'customer' | null)
  const [userRole, setUserRole] = useState(null);

  // WebRTC 상태
  const [isConnected, setIsConnected] = useState(false);
  const [isInRoom, setIsInRoom] = useState(false);
  const [isCallActive, setIsCallActive] = useState(false);
  const [peerId, setPeerId] = useState('');
  const [roomName, setRoomName] = useState('');
  const [nickname, setNickname] = useState('');
  const [currentRoom, setCurrentRoom] = useState('');
  const [peerCount, setPeerCount] = useState(0);
  const [connectionState, setConnectionState] = useState('');
  const [participants, setParticipants] = useState([]);
  const [error, setError] = useState('');

  // 고객용 방 목록
  const [availableRooms, setAvailableRooms] = useState([]);
  const [loadingRooms, setLoadingRooms] = useState(false);

  // 통화 시간 타이머
  const [callDuration, setCallDuration] = useState(0);
  const [callStartTime, setCallStartTime] = useState(null);
  const callTimerRef = useRef(null);

  // STT 트랜스크립트
  const [transcripts, setTranscripts] = useState([]);
  const transcriptContainerRef = useRef(null);

  // AI 에이전트 요약 (JSON 파싱)
  const [parsedSummary, setParsedSummary] = useState(null);
  const [summaryTimestamp, setSummaryTimestamp] = useState(null);
  const [llmStatus, setLlmStatus] = useState('connecting');
  const [consultationStatus, setConsultationStatus] = useState('idle');
  const [consultationResult, setConsultationResult] = useState(null);
  const [consultationError, setConsultationError] = useState('');
  const [assistCards, setAssistCards] = useState(defaultAssistCards);
  const [agentUpdates, setAgentUpdates] = useState({});
  const [latestTurnId, setLatestTurnId] = useState(null);

  // 마지막 유효 데이터 (이전 결과 유지용)
  const [lastKnownSummary, setLastKnownSummary] = useState({});
  const [lastKnownIntent, setLastKnownIntent] = useState({});
  const [lastKnownSentiment, setLastKnownSentiment] = useState({});
  const [lastKnownDraft, setLastKnownDraft] = useState({});
  const [lastKnownRisk, setLastKnownRisk] = useState({});

  // WebRTC ref
  const webrtcClientRef = useRef(null);
  const remoteAudioRef = useRef(null);

  // 폼 입력값
  const [roomInput, setRoomInput] = useState('');
  const [nicknameInput, setNicknameInput] = useState('');
  const [phoneInput, setPhoneInput] = useState('');
  const [agentCodeInput, setAgentCodeInput] = useState('');

  // 고객 정보 (DB 조회 결과)
  const [customerInfo, setCustomerInfo] = useState(null);
  const [consultationHistory, setConsultationHistory] = useState([]);

  // 오디오 상태
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);

  // 세션 저장 상태
  const [isSavingSession, setIsSavingSession] = useState(false);
  const [saveSessionResult, setSaveSessionResult] = useState(null);
  const [pendingLeaveAfterSave, setPendingLeaveAfterSave] = useState(false);

  // 좌측 패널 카드 접기/펼치기 상태
  const [customerInfoCollapsed, setCustomerInfoCollapsed] = useState(false);
  const [conversationCollapsed, setConversationCollapsed] = useState(false);
  const [historyCollapsed, setHistoryCollapsed] = useState(true);

  // 상담 이력 팝업 상태
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [selectedHistory, setSelectedHistory] = useState(null);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);
  const [historyDetailData, setHistoryDetailData] = useState(null);

  // 좌측 패널 표시/숨김 상태
  const [leftPanelVisible, setLeftPanelVisible] = useState(true);

  // 플로팅 채팅 상태
  const [floatingChatOpen, setFloatingChatOpen] = useState(false);
  const [unreadChatCount, setUnreadChatCount] = useState(0);
  const floatingChatBodyRef = useRef(null);
  const lastReadTranscriptCount = useRef(0);

  // 중앙 패널 인사이트 카드 접기/펼치기 상태
  const [intentCardCollapsed, setIntentCardCollapsed] = useState(false);
  const [summaryCardCollapsed, setSummaryCardCollapsed] = useState(false);
  const [emotionCardCollapsed, setEmotionCardCollapsed] = useState(false);

  // RAG 카드 표시 상태: 처음 2개만 표시, "더 보기"로 확장
  const [ragCardVisibleCount, setRagCardVisibleCount] = useState(2);
  const [newRagCardIds, setNewRagCardIds] = useState(new Set());

  // Web Audio API (볼륨 증폭용)
  const audioContextRef = useRef(null);
  const gainNodeRef = useRef(null);

  /**
   * WebRTC 클라이언트 초기화
   */
  useEffect(() => {
    const wsUrl = import.meta.env.VITE_WS_URL ||
      `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`;

    console.log('WebSocket URL:', wsUrl);
    const client = new WebRTCClient(wsUrl);
    webrtcClientRef.current = client;

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
      // 고객이 먼저 입장한 경우 고객 정보 수신
      if (data.customer_info) {
        const enriched = enrichCustomerInfo(data.customer_info);
        setCustomerInfo(enriched);
        console.log('Customer info received (room_joined):', enriched);
      }
      if (data.consultation_history) {
        setConsultationHistory(data.consultation_history);
        console.log('Consultation history received (room_joined):', data.consultation_history);
      }
    };

    client.onUserJoined = (data) => {
      console.log('User joined:', data);
      setPeerCount(data.peer_count);
      setParticipants(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname
      }]);
      if (data.customer_info) {
        const enriched = enrichCustomerInfo(data.customer_info);
        setCustomerInfo(enriched);
        console.log('Customer info received:', enriched);
      }
      if (data.consultation_history) {
        setConsultationHistory(data.consultation_history);
        console.log('Consultation history received:', data.consultation_history);
      }
    };

    client.onUserLeft = (data) => {
      console.log('User left:', data);
      setPeerCount(data.peer_count);
      setParticipants(prev =>
        prev.filter(p => p.peer_id !== data.peer_id)
      );
    };

    client.onRemoteStream = (stream) => {
      console.log('Remote audio stream received');

      try {
        if (audioContextRef.current) {
          audioContextRef.current.close().catch(() => {});
        }

        const audioContext = new (window.AudioContext || window.webkitAudioContext)({
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

        console.log('Audio amplified with gain:', gainNode.gain.value);

        if (remoteAudioRef.current) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 0;
        }
      } catch (err) {
        console.error('Web Audio API failed, using fallback:', err);
        if (remoteAudioRef.current && remoteAudioRef.current.srcObject !== stream) {
          remoteAudioRef.current.srcObject = stream;
          remoteAudioRef.current.volume = 1.0;
          remoteAudioRef.current.play().catch(e => console.error('Remote audio play failed:', e));
        }
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

    client.onTranscript = (data) => {
      console.log('Transcript received:', data);
      setTranscripts(prev => [...prev, {
        peer_id: data.peer_id,
        nickname: data.nickname,
        text: data.text,
        timestamp: data.timestamp || Date.now(),
        receivedAt: Date.now()
      }]);
    };

    client.onAgentReady = (data) => {
      console.log('Agent ready:', data);
      if (data.llm_available) {
        setLlmStatus('ready');
        console.log('LLM available, ready for summarization');
      } else {
        setLlmStatus('failed');
        console.warn('LLM not available');
      }
    };

    client.onAgentUpdate = (data) => {
      console.log('Agent update received:', JSON.stringify(data, null, 2));

      if (!data) return;

      const turnId = data.turnId || data.turn_id || 'default';
      const node = data.node;
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

    client.onAgentStatus = (data) => {
      if (!data) return;
      if (data.status === 'processing') {
        setConsultationStatus('processing');
        setConsultationError('');
      } else if (data.status === 'error') {
        setConsultationStatus('error');
        setConsultationError(data.message || '에이전트 오류');
      }
    };

    client.onAgentConsultation = (data) => {
      console.log('Consultation result:', data);
      if (!data) return;
      setConsultationStatus('done');
      setConsultationError('');
      setConsultationResult({
        guide: data.guide || [],
        recommendations: data.recommendations || [],
        citations: data.citations || [],
        generated_at: data.generated_at || Date.now()
      });
    };

    const handleBeforeUnload = () => {
      console.log('beforeunload: Cleaning up WebRTC connection...');
      if (client) {
        client.leaveRoom();
        client.disconnect();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      if (client) {
        client.disconnect();
      }
    };
  }, []);

  /**
   * 트랜스크립트 자동 스크롤
   */
  useEffect(() => {
    if (transcriptContainerRef.current) {
      transcriptContainerRef.current.scrollTop = transcriptContainerRef.current.scrollHeight;
    }
  }, [transcripts]);

  /**
   * 플로팅 채팅 읽지 않은 메시지 카운트 및 자동 스크롤
   */
  useEffect(() => {
    if (floatingChatOpen) {
      // 채팅창이 열려있으면 읽음 처리
      lastReadTranscriptCount.current = transcripts.length;
      setUnreadChatCount(0);
      // 자동 스크롤
      if (floatingChatBodyRef.current) {
        floatingChatBodyRef.current.scrollTop = floatingChatBodyRef.current.scrollHeight;
      }
    } else {
      // 채팅창이 닫혀있으면 새 메시지 카운트
      const newCount = transcripts.length - lastReadTranscriptCount.current;
      if (newCount > 0) {
        setUnreadChatCount(newCount);
      }
    }
  }, [transcripts, floatingChatOpen]);

  /**
   * 상담 가이드 수신 시 우측 스택에 카드 추가
   */
  useEffect(() => {
    if (!consultationResult || !consultationResult.generated_at) return;
    const cardId = `guide-${consultationResult.generated_at}`;
    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId)) return prev;
      return [
        {
          id: cardId,
          title: '상담 가이드 업데이트',
          type: 'guide',
          content: consultationResult.guide?.[0] || '가이드가 도착했습니다.',
          collapsed: false,
        },
        ...prev,
      ];
    });
  }, [consultationResult]);

  /**
   * RAG 정책 검색 결과 수신 시 우측 스택에 카드 추가
   *
   * 백엔드 응답 구조:
   * rag_policy_result: {
   *   skipped: boolean,
   *   intent_label: string,
   *   query: string,
   *   searched_classifications: string[],
   *   search_context: string,
   *   recommendations: [{
   *     collection, title, content, relevance_score,
   *     metadata: { monthly_price, target_segment, search_text, ... },
   *     recommendation_reason
   *   }]
   * }
   */
  useEffect(() => {
    if (!latestTurnId) return;

    const bucket = agentUpdates[latestTurnId] || {};
    const ragData = bucket.rag_policy || {};

    // rag_policy_result에서 데이터 추출
    const ragResult = ragData.rag_policy_result || ragData;

    // skipped 상태이거나 추천이 없으면 무시
    if (ragResult.skipped || !ragResult.recommendations?.length) return;

    const recommendations = ragResult.recommendations || [];
    const cardId = `rag-${latestTurnId}`;

    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId || c.id.startsWith(`${cardId}-`))) return prev;

      const newCards = [];
      const newCardIds = [];

      // 상위 추천 문서 카드 추가 (최대 5개)
      recommendations.slice(0, 5).forEach((rec, idx) => {
        const metadata = rec.metadata || {};
        const planDetails = metadata.plan_details || {};
        const monthlyPrice = metadata.monthly_price;

        // plan_details에서 직접 데이터 추출 (백엔드에서 파싱된 구조화된 데이터)
        const dataAllowance = planDetails['데이터'] || '';
        const voiceBenefit = planDetails['음성'] || '';
        const contentBenefit = planDetails['콘텐츠'] || planDetails['필수팩'] || '';
        const membership = planDetails['멤버십'] || '';
        const smsInfo = planDetails['문자'] || '';

        // 카테고리 결정 (컬렉션명 기반)
        let category = 'POLICY';
        if (rec.collection) {
          if (rec.collection.includes('mobile')) category = 'MOBILE PLANS';
          else if (rec.collection.includes('internet')) category = 'INTERNET';
          else if (rec.collection.includes('tv')) category = 'TV';
          else if (rec.collection.includes('bundle')) category = 'BUNDLE';
          else if (rec.collection.includes('penalty')) category = 'PENALTY';
          else if (rec.collection.includes('membership')) category = 'MEMBERSHIP';
        }

        // 타겟 세그먼트
        const targetSegment = metadata.target_segment || '';

        // TIP 생성 (추천 이유)
        const tip = rec.recommendation_reason || '';

        // briefInfo (가격/데이터 요약)
        const priceStr = monthlyPrice ? `${monthlyPrice.toLocaleString()}원` : '';
        const briefInfo = [priceStr, dataAllowance].filter(Boolean).join(' / ');

        const cardIdWithIdx = `${cardId}-rec-${idx}`;
        newCardIds.push(cardIdWithIdx);

        newCards.push({
          id: cardIdWithIdx,
          title: rec.title || '관련 정책',
          type: 'rag',
          content: rec.content || '',
          metadata: {
            ...metadata,
            category: category,
            data_allowance: dataAllowance,
            voice_benefit: voiceBenefit,
            content_benefit: contentBenefit,
            membership: membership,
            sms_info: smsInfo,
            target_segment: targetSegment,
            tip: tip,
            plan_details: planDetails,
          },
          relevance: rec.relevance_score,
          collection: rec.collection,
          recommendationReason: tip,
          briefInfo: briefInfo,
          monthlyPrice: monthlyPrice,
          collapsed: idx > 0,
          isNew: true,
          ragGroupId: cardId,
          ragIndex: idx,
        });
      });

      // 새 카드 ID들을 하이라이트 상태에 추가
      setNewRagCardIds((prevIds) => {
        const updated = new Set(prevIds);
        newCardIds.forEach((id) => updated.add(id));
        return updated;
      });

      // 3초 후 하이라이트 제거
      setTimeout(() => {
        setNewRagCardIds((prevIds) => {
          const updated = new Set(prevIds);
          newCardIds.forEach((id) => updated.delete(id));
          return updated;
        });
      }, 3000);

      // RAG 카드 표시 개수 초기화 (새 그룹이 도착하면 2개만 표시)
      setRagCardVisibleCount(2);

      return [...newCards, ...prev];
    });
  }, [latestTurnId, agentUpdates]);

  /**
   * FAQ 검색 결과 수신 시 우측 스택에 카드 추가
   *
   * 백엔드 응답 구조:
   * faq_result: {
   *   query: string,
   *   faqs: [{question, answer, category, id}],
   *   cache_hit: boolean,
   *   similarity_score: float,
   *   cached_query: string,
   *   search_time_ms: float
   * }
   */
  useEffect(() => {
    if (!latestTurnId) return;

    const bucket = agentUpdates[latestTurnId] || {};
    const faqData = bucket.faq_search || {};

    // faq_result에서 데이터 추출
    const faqResult = faqData.faq_result || faqData;

    // FAQ가 없으면 무시
    if (!faqResult.faqs?.length) return;

    const faqs = faqResult.faqs || [];
    const cardId = `faq-${latestTurnId}`;
    const cacheHit = faqResult.cache_hit;

    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId || c.id.startsWith(`${cardId}-`))) return prev;

      const newCards = [];
      const newCardIds = [];

      // FAQ 카드 추가 (최대 3개)
      faqs.slice(0, 3).forEach((faq, idx) => {
        const cardIdWithIdx = `${cardId}-faq-${idx}`;
        newCardIds.push(cardIdWithIdx);

        newCards.push({
          id: cardIdWithIdx,
          title: faq.question || 'FAQ',
          type: 'faq',
          content: faq.answer || '',
          category: faq.category || '',
          faqId: faq.id || '',
          cacheHit: cacheHit,
          collapsed: idx > 0,  // 첫 번째만 펼침
          isNew: true,
          faqGroupId: cardId,
          faqIndex: idx,
        });
      });

      // 새 카드 ID들을 하이라이트 상태에 추가
      setNewRagCardIds((prevIds) => {
        const updated = new Set(prevIds);
        newCardIds.forEach((id) => updated.add(id));
        return updated;
      });

      // 3초 후 하이라이트 제거
      setTimeout(() => {
        setNewRagCardIds((prevIds) => {
          const updated = new Set(prevIds);
          newCardIds.forEach((id) => updated.delete(id));
          return updated;
        });
      }, 3000);

      return [...newCards, ...prev];
    });
  }, [latestTurnId, agentUpdates]);

  /**
   * 리스크 감지 시 AI 추천 정보 스택에 카드 추가
   */
  useEffect(() => {
    if (!latestTurnId) return;

    const bucket = agentUpdates[latestTurnId] || {};
    const riskRaw = bucket.risk || {};
    const riskData = riskRaw.risk_result || riskRaw;
    const riskFlags = riskData.risk_flags || [];

    // 리스크가 없으면 무시
    if (!riskFlags.length) return;

    const cardId = `risk-${latestTurnId}`;

    setAssistCards((prev) => {
      if (prev.some((c) => c.id === cardId)) return prev;
      return [
        {
          id: cardId,
          title: `리스크 감지: ${riskFlags.join(', ')}`,
          type: 'risk',
          content: riskData.risk_explanation || '위험 요소가 감지되었습니다.',
          collapsed: false,
        },
        ...prev,
      ];
    });
  }, [latestTurnId, agentUpdates]);

  /**
   * 마지막 유효 데이터 업데이트 (이전 결과 유지)
   */
  useEffect(() => {
    if (!latestTurnId) return;
    const bucket = agentUpdates[latestTurnId] || {};

    // Summary
    const summaryRaw = bucket.summarize || {};
    const summaryData = summaryRaw.summary_result || summaryRaw;
    if (summaryData.summary || summaryData.customer_issue) {
      setLastKnownSummary(summaryData);
    }

    // Intent
    const intentRaw = bucket.intent || {};
    const intentData = intentRaw.intent_result || intentRaw;
    if (intentData.intent_label) {
      setLastKnownIntent(intentData);
    }

    // Sentiment
    const sentimentRaw = bucket.sentiment || {};
    const sentimentData = sentimentRaw.sentiment_result || sentimentRaw;
    if (sentimentData.sentiment_label) {
      setLastKnownSentiment(sentimentData);
    }

    // Draft
    const draftRaw = bucket.draft_reply || bucket.draft_replies || {};
    const draftData = draftRaw.draft_replies || draftRaw;
    if (draftData.short_reply) {
      setLastKnownDraft(draftData);
    }

    // Risk
    const riskRaw = bucket.risk || {};
    const riskData = riskRaw.risk_result || riskRaw;
    if (riskData.risk_flags?.length > 0) {
      setLastKnownRisk(riskData);
    }
  }, [latestTurnId, agentUpdates]);

  /**
   * 고객 선택 시 자동으로 방 목록 가져오기
   */
  useEffect(() => {
    if (userRole === 'customer' && isConnected) {
      fetchRooms();
    }
  }, [userRole, isConnected]);

  /**
   * 통화 시간 타이머
   */
  useEffect(() => {
    if (isCallActive) {
      setCallDuration(0);
      callTimerRef.current = setInterval(() => {
        setCallDuration(prev => prev + 1);
      }, 1000);
    } else {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
        callTimerRef.current = null;
      }
    }

    return () => {
      if (callTimerRef.current) {
        clearInterval(callTimerRef.current);
      }
    };
  }, [isCallActive]);

  /**
   * 통화 시간 포맷 (MM:SS)
   */
  const formatDuration = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  /**
   * 경과 시간 계산 (밀리초 → 초)
   */
  const getElapsedSeconds = (timestamp) => {
    if (!callStartTime || !timestamp) return 0;
    return Math.floor((timestamp - callStartTime) / 1000);
  };

  /**
   * 서버 연결
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
   * 방 목록 가져오기 (고객용)
   */
  const fetchRooms = async () => {
    const apiBase = import.meta.env.VITE_API_URL || '';
    const apiUrl = `${apiBase}/api/rooms`;

    console.log('Fetching rooms from:', apiUrl);
    setLoadingRooms(true);
    setError('');
    try {
      const headers = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      const authToken = sessionStorage.getItem('auth_token');
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const response = await fetch(apiUrl, { headers });
      console.log('Response status:', response.status);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('Received rooms data:', data);
      setAvailableRooms(data.rooms || []);
      console.log('Rooms loaded successfully:', data.rooms?.length || 0);
    } catch (err) {
      console.error('Failed to fetch rooms:', err);
      setError(`방 목록을 불러오는데 실패했습니다: ${err.message}`);
    } finally {
      setLoadingRooms(false);
      console.log('Fetch rooms completed');
    }
  };

  /**
   * 고객이 방 선택
   */
  const handleJoinRoomAsCustomer = async (room) => {
    if (!nicknameInput.trim()) {
      setError('이름을 입력해주세요');
      return;
    }
    if (!phoneInput.trim()) {
      setError('휴대전화 번호를 입력해주세요');
      return;
    }

    try {
      setError('');
      setTranscripts([]);
      setParsedSummary(null);
      setLlmStatus('connecting');
      setCustomerInfo(null);
      setConsultationHistory([]);
      await webrtcClientRef.current.joinRoom(room.room_name, nicknameInput.trim(), phoneInput.trim());
      setRoomName(room.room_name);
      setNickname(nicknameInput.trim());
      setCurrentRoom(room.room_name);
      setIsInRoom(true);
      setPeerCount(room.peer_count || 0);
      setParticipants(room.peers || []);
    } catch (err) {
      setError(`Failed to join room: ${err.message}`);
    }
  };

  /**
   * 상담사가 방 생성
   */
  const handleCreateRoomAsAgent = async (e) => {
    e.preventDefault();
    if (!roomInput.trim() || !nicknameInput.trim()) {
      setError('방 이름과 이름을 모두 입력해주세요');
      return;
    }

    try {
      setError('');
      setTranscripts([]);
      setParsedSummary(null);
      setLlmStatus('connecting');
      await webrtcClientRef.current.joinRoom(roomInput.trim(), nicknameInput.trim(), null, agentCodeInput.trim());
      setRoomName(roomInput.trim());
      setNickname(nicknameInput.trim());
      setCurrentRoom(roomInput.trim());
      setIsInRoom(true);
      setPeerCount(1);
    } catch (err) {
      setError(`Failed to create room: ${err.message}`);
    }
  };

  /**
   * 통화 시작
   */
  const handleStartCall = async () => {
    try {
      setError('');
      await webrtcClientRef.current.startCall();
      setCallStartTime(Date.now());
      setIsCallActive(true);
    } catch (err) {
      console.error('Start call error:', err);
      setError(`Failed to start call: ${err.message}`);
      alert(`Failed to start call: ${err.message}`);
    }
  };

  /**
   * 통화 종료 (세션 저장 후 방 나가기)
   */
  const handleEndCall = async () => {
    if (!isCallActive) return;

    // 고객은 저장 없이 바로 나가기
    if (userRole !== 'agent') {
      handleLeaveRoom();
      return;
    }

    // 상담사: 저장 플로우
    setIsSavingSession(true);
    setSaveSessionResult(null);
    setPendingLeaveAfterSave(false);

    try {
      // 세션 저장 요청
      const result = await webrtcClientRef.current.endSession();
      setSaveSessionResult(result);
      setPendingLeaveAfterSave(Boolean(result?.success ?? true));
    } catch (error) {
      console.error('Session save error:', error);
      setSaveSessionResult({
        success: false,
        message: error.message || 'Failed to save session'
      });
      setPendingLeaveAfterSave(false);
    }
  };

  /**
   * 룸 퇴장 (저장 없이 바로 나가기)
   */
  const handleLeaveRoom = () => {
    webrtcClientRef.current.leaveRoom();

    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }

    if (remoteAudioRef.current) remoteAudioRef.current.srcObject = null;

    setIsInRoom(false);
    setIsCallActive(false);
    setCurrentRoom('');
    setRoomName('');
    setNickname('');
    setPeerCount(0);
    setParticipants([]);
    setTranscripts([]);
    setParsedSummary(null);
    setSummaryTimestamp(null);
    setConnectionState('');
    setRoomInput('');
    setNicknameInput('');
    setAgentCodeInput('');
    setLlmStatus('connecting');
    setCallStartTime(null);
    setConsultationStatus('idle');
    setConsultationResult(null);
    setConsultationError('');
    setAssistCards(defaultAssistCards());
    setAgentUpdates({});
    setLatestTurnId(null);
    setIsSavingSession(false);
    setSaveSessionResult(null);
  };

  /**
   * 세션 저장 결과 확인 후 정리
   */
  const handleConfirmSaveResult = () => {
    const shouldLeave = pendingLeaveAfterSave && userRole === 'agent';
    setIsSavingSession(false);
    setSaveSessionResult(null);
    setPendingLeaveAfterSave(false);
    if (shouldLeave) {
      handleLeaveRoom();
    }
  };

  /**
   * 우측 카드 스택: 접기/삭제
   */
  const handleToggleCard = (cardId) => {
    setAssistCards((prev) =>
      prev.map((card) => (card.id === cardId ? { ...card, collapsed: !card.collapsed } : card)),
    );
  };

  const handleDismissCard = (cardId) => {
    setAssistCards((prev) => prev.filter((card) => card.id !== cardId));
  };

  /**
   * 오디오 토글
   */
  const handleToggleAudio = () => {
    const enabled = webrtcClientRef.current.toggleAudio();
    setIsAudioEnabled(enabled);
  };

  /**
   * 결과 타입 한글 이름 매핑
   */
  const getResultTypeName = (resultType) => {
    const typeMap = {
      'summary': '요약',
      'summarize': '요약',
      'intent': '의도',
      'sentiment': '감정',
      'risk': '위험',
      'rag': '검색',
      'rag_policy': '검색',
      'faq': 'FAQ',
      'faq_search': 'FAQ',
      'draft_reply': '응답',
      'draft_replies': '응답'
    };
    return typeMap[resultType] || resultType;
  };

  /**
   * 분석 결과 요약 포맷팅
   */
  const formatResultSummary = (resultType, resultData) => {
    let data = resultData;
    if (typeof resultData === 'string') {
      try {
        data = JSON.parse(resultData);
      } catch {
        return resultData;
      }
    }
    if (!data) return '-';

    switch (resultType) {
      case 'intent':
        return data.intent_label || data.intent || '-';
      case 'sentiment':
        return `${data.emotion_label || data.sentiment || '-'} (${data.intensity || '-'})`;
      case 'risk':
        if (data.risk_flags && data.risk_flags.length > 0) {
          return data.risk_flags.join(', ');
        }
        return data.risk_detected ? '위험 감지됨' : '정상';
      case 'summary':
      case 'summarize':
        return data.current_summary || data.summary || '-';
      case 'rag':
      case 'rag_policy':
        return `${data.count || (data.results?.length || 0)}건 검색됨`;
      case 'faq':
      case 'faq_search':
        return `${data.count || (data.faqs?.length || 0)}건 검색됨`;
      case 'draft_reply':
      case 'draft_replies':
        if (data.draft_replies && data.draft_replies.length > 0) {
          return data.draft_replies[0].text?.substring(0, 50) + '...';
        }
        return '-';
      default:
        return JSON.stringify(data).substring(0, 50) + '...';
    }
  };

  /**
   * 상담 이력 상세 조회
   */
  const handleHistoryClick = async (history) => {
    setSelectedHistory(history);
    setShowHistoryModal(true);
    setHistoryDetailLoading(true);
    setHistoryDetailData(null);

    try {
      const apiBase = import.meta.env.VITE_API_URL || '';
      const headers = {
        'bypass-tunnel-reminder': 'true',
        'ngrok-skip-browser-warning': 'true',
      };
      const authToken = sessionStorage.getItem('auth_token');
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const response = await fetch(`${apiBase}/api/consultation/history/${history.session_id}`, { headers });

      if (response.ok) {
        const data = await response.json();
        setHistoryDetailData(data);
      } else {
        console.error('Failed to fetch history detail:', response.status);
      }
    } catch (err) {
      console.error('Failed to fetch history detail:', err);
    } finally {
      setHistoryDetailLoading(false);
    }
  };

  /**
   * 이력 모달 닫기
   */
  const handleCloseHistoryModal = () => {
    setShowHistoryModal(false);
    setSelectedHistory(null);
    setHistoryDetailData(null);
  };

  /**
   * 연결된 상대방 정보 가져오기
   */
  const getRemotePeer = () => {
    return participants.length > 0 ? participants[0] : null;
  };

  /**
   * 감정 상태 결정
   */
  const getEmotionState = (sentimentLabel) => {
    if (!sentimentLabel) return 'stable';
    const label = sentimentLabel.toLowerCase();
    if (label.includes('angry') || label.includes('분노')) return 'angry';
    if (label.includes('anxious') || label.includes('불안')) return 'anxious';
    if (label.includes('confused') || label.includes('혼란')) return 'confused';
    return 'stable';
  };

  // Step 1: 역할 선택
  if (!userRole) {
    return (
      <div className="assistant-welcome">
        <button className="theme-toggle welcome-theme-toggle" onClick={onToggleTheme} title={isDarkMode ? '라이트 모드' : '다크 모드'}>
          {isDarkMode ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
          )}
        </button>
        <div className="welcome-card">
          <h2>역할 선택</h2>
          <p>상담사 또는 고객을 선택하세요</p>
          <div className="role-selection">
            <button
              onClick={() => setUserRole('agent')}
              className="btn btn-primary btn-large"
            >
              상담사
            </button>
            <button
              onClick={() => setUserRole('customer')}
              className="btn btn-success btn-large"
            >
              고객
            </button>
          </div>
          <div className="agent-links">
            <Link to="/agent/register">상담사 등록</Link>
            <Link to="/agent/history">상담 이력 조회</Link>
            <Link to="/">메인으로</Link>
          </div>
        </div>
      </div>
    );
  }

  // Step 2: 서버 연결
  if (!isConnected) {
    return (
      <div className="assistant-welcome">
        <div className="welcome-card">
          <h2>{userRole === 'agent' ? '상담사 연결' : '고객 연결'}</h2>
          <p>서버에 연결하여 시작하세요</p>
          <button onClick={handleConnect} className="btn btn-primary">
            서버 연결
          </button>
          {error && <div className="error-message">{error}</div>}
          <button
            onClick={() => setUserRole(null)}
            className="btn btn-secondary mt-2"
          >
            역할 다시 선택
          </button>
          <div className="agent-links">
            {userRole === 'agent' && (
              <>
                <Link to="/agent/register">상담사 등록</Link>
                <Link to="/agent/history">상담 이력 조회</Link>
              </>
            )}
            <Link to="/">메인으로</Link>
          </div>
        </div>
      </div>
    );
  }

  // Step 3: 방 선택/생성
  if (!isInRoom) {
    if (userRole === 'agent') {
      return (
        <div className="assistant-welcome">
          <div className="welcome-card">
            <h2>상담 룸 생성</h2>
            <form onSubmit={handleCreateRoomAsAgent} className="join-form">
              <div className="form-group">
                <label>상담실 이름</label>
                <input
                  type="text"
                  placeholder="예: 상담실1"
                  value={roomInput}
                  onChange={(e) => setRoomInput(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label>상담사 이름</label>
                <input
                  type="text"
                  placeholder="이름을 입력하세요"
                  value={nicknameInput}
                  onChange={(e) => setNicknameInput(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>상담사 코드 (사번)</label>
                <input
                  type="text"
                  placeholder="예: A001"
                  value={agentCodeInput}
                  onChange={(e) => setAgentCodeInput(e.target.value)}
                />
              </div>
              <button type="submit" className="btn btn-success">
                상담실 생성
              </button>
            </form>
            {error && <div className="error-message">{error}</div>}
            <div className="agent-links">
              <Link to="/agent/register">상담사 등록</Link>
              <Link to="/agent/history">상담 이력 조회</Link>
              <Link to="/">메인으로</Link>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="assistant-welcome">
        <div className="welcome-card wide">
          <h2>상담 대기 중인 상담실</h2>

          <div className="form-group">
            <label>고객 이름</label>
            <input
              type="text"
              placeholder="이름을 입력하세요"
              value={nicknameInput}
              onChange={(e) => setNicknameInput(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>휴대전화 번호</label>
            <input
              type="tel"
              placeholder="010-1234-5678"
              value={phoneInput}
              onChange={(e) => setPhoneInput(e.target.value)}
            />
          </div>

          <button
            onClick={fetchRooms}
            className="btn btn-primary mb-3"
            disabled={loadingRooms}
          >
            {loadingRooms ? '불러오는 중...' : '상담실 목록 새로고침'}
          </button>

          {availableRooms.length === 0 ? (
            <p className="no-rooms">현재 대기 중인 상담실이 없습니다.</p>
          ) : (
            <div className="room-grid">
              {availableRooms.map((room, index) => (
                <div key={index} className="room-card" onClick={() => handleJoinRoomAsCustomer(room)}>
                  <div className="room-header">
                    <h3>{room.room_name}</h3>
                    <span className="room-count">{room.peer_count}명</span>
                  </div>
                  <div className="room-info">
                    <div className="room-agent">
                      상담사: {room.peers.length > 0 ? room.peers[0].nickname : '알 수 없음'}
                    </div>
                    <div className="room-status">
                      <span className="status-dot"></span>
                      대기 중
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {error && <div className="error-message">{error}</div>}
          <div className="agent-links">
            <Link to="/">메인으로</Link>
          </div>
        </div>
      </div>
    );
  }

  // Main Dashboard
  const remotePeer = getRemotePeer();
  const latestUpdateBucket = latestTurnId ? agentUpdates[latestTurnId] || {} : {};

  // 노드별 데이터 추출 (백엔드에서 {node_result: {...}, last_xxx_index: N} 형식으로 전송)
  const summaryRaw = latestUpdateBucket.summarize || {};
  const intentRaw = latestUpdateBucket.intent || {};
  const sentimentRaw = latestUpdateBucket.sentiment || {};
  const draftRaw = latestUpdateBucket.draft_reply || latestUpdateBucket.draft_replies || {};
  const riskRaw = latestUpdateBucket.risk || {};
  const ragPolicyData = latestUpdateBucket.rag_policy || {};

  // 중첩 구조 평탄화 + 마지막 유효값 fallback (이전 결과 유지)
  const currentSummary = summaryRaw.summary_result || summaryRaw;
  const currentIntent = intentRaw.intent_result || intentRaw;
  const currentSentiment = sentimentRaw.sentiment_result || sentimentRaw;
  const currentDraft = draftRaw.draft_replies || draftRaw;
  const currentRisk = riskRaw.risk_result || riskRaw;

  // 유효한 데이터가 있으면 현재값, 없으면 마지막 유효값 사용
  const summaryData = currentSummary.summary ? currentSummary : lastKnownSummary;
  const intentData = currentIntent.intent_label ? currentIntent : lastKnownIntent;
  const sentimentData = currentSentiment.sentiment_label ? currentSentiment : lastKnownSentiment;
  const draftData = currentDraft.short_reply ? currentDraft : lastKnownDraft;
  const riskData = currentRisk.risk_flags?.length > 0 ? currentRisk : lastKnownRisk;

  const emotionState = getEmotionState(sentimentData.sentiment_label);
  const riskFlags = riskData.risk_flags || [];
  const currentIssueSummary = summaryData.customer_issue || intentData.intent_label || '대기 중';

  return (
    <div className="assistant-dashboard">
      {/* 세션 저장 로딩 오버레이 */}
      {isSavingSession && (
        <div className="session-saving-overlay">
          <div className="session-saving-content">
            {!saveSessionResult ? (
              <>
                <div className="saving-spinner"></div>
                <p className="saving-text">상담 내역을 저장하고 있습니다...</p>
              </>
            ) : (
              <>
                <div className={`saving-result-icon ${saveSessionResult.success ? 'success' : 'error'}`}>
                  {saveSessionResult.success ? (
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  ) : (
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"></line>
                      <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                  )}
                </div>
                <p className="saving-text">
                  {saveSessionResult.success ? '저장이 완료되었습니다!' : '저장에 실패했습니다'}
                </p>
                {saveSessionResult.message && (
                  <p className="saving-detail">{saveSessionResult.message}</p>
                )}
                {saveSessionResult.session_id && (
                  <p className="saving-session-id">Session ID: {saveSessionResult.session_id.slice(0, 8)}...</p>
                )}
                <button
                  className="btn btn-primary btn-save-confirm"
                  onClick={handleConfirmSaveResult}
                >
                  {saveSessionResult.success ? '확인 후 나가기' : '확인'}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* Top Header Bar */}
      <header className="dashboard-header">
        <div className="header-content">
          {/* 좌측: 통화 컨트롤 + 통화 상태 + 타이머 + 고객 정보 */}
          <div className="header-left">
            {/* 통화 컨트롤 버튼 */}
            <div className="header-call-controls">
              {!isCallActive ? (
                <button onClick={handleStartCall} className="btn btn-success btn-call">
                  통화 시작
                </button>
              ) : (
                <>
                  <button
                    onClick={handleToggleAudio}
                    className={`btn btn-call ${isAudioEnabled ? 'btn-primary' : 'btn-ghost'}`}
                  >
                    {isAudioEnabled ? 'MIC ON' : 'MIC OFF'}
                  </button>
                  <button
                    onClick={handleEndCall}
                    className="btn btn-call btn-danger"
                    disabled={isSavingSession}
                  >
                    {userRole === 'agent' ? '통화 종료 및 저장' : '통화 종료'}
                  </button>
                  <button
                    onClick={handleLeaveRoom}
                    className="btn btn-call btn-outline-secondary"
                    disabled={isSavingSession}
                  >
                    {userRole === 'agent' ? '저장 없이 나가기' : '방 나가기'}
                  </button>
                </>
              )}
              {/* 방 나가기 버튼 - 통화 중이 아닐 때만 표시 */}
              {!isCallActive && (
                <button onClick={handleLeaveRoom} className="btn btn-call btn-secondary">
                  방 나가기
                </button>
              )}
            </div>

            <div className={`call-status-badge ${isCallActive ? 'active' : 'waiting'}`}>
              {isCallActive ? (
                <>
                  <span className="status-indicator">
                    <span className="ping"></span>
                    <span className="dot"></span>
                  </span>
                  <span>통화 중</span>
                </>
              ) : (
                <span>대기 중</span>
              )}
            </div>
            {isCallActive && (
              <span className="call-timer">{formatDuration(callDuration)}</span>
            )}
            {userRole === 'agent' && remotePeer && (
              <div className="customer-brief">
                <span className="customer-name">{remotePeer.nickname}</span>
                {customerInfo?.membership_grade && (
                  <span className="customer-grade">{customerInfo.membership_grade}</span>
                )}
                {customerInfo?.age && (
                  <span>{customerInfo.age}세</span>
                )}
              </div>
            )}
          </div>

          {/* 중앙: 핵심 이슈 요약 */}
          <div className="header-center">
            <span className="issue-summary">{currentIssueSummary}</span>
          </div>

          {/* 우측: 연결상태 + 테마토글 */}
          <div className="header-right">
            {/* 연결 상태 */}
            <div className={`connection-status ${connectionState || 'disconnected'}`}>
              <span className="connection-dot"></span>
              <span>{connectionState || '미연결'}</span>
            </div>

            <button className="theme-toggle" onClick={onToggleTheme} title={isDarkMode ? '라이트 모드' : '다크 모드'}>
              {isDarkMode ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5"></circle>
                  <line x1="12" y1="1" x2="12" y2="3"></line>
                  <line x1="12" y1="21" x2="12" y2="23"></line>
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
                  <line x1="1" y1="12" x2="3" y2="12"></line>
                  <line x1="21" y1="12" x2="23" y2="12"></line>
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                </svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* 좌측 패널 토글 버튼 */}
      <button
        className={`panel-toggle-btn ${!leftPanelVisible ? 'panel-hidden' : ''}`}
        onClick={() => setLeftPanelVisible(!leftPanelVisible)}
        title={leftPanelVisible ? '좌측 패널 숨기기' : '좌측 패널 표시'}
      >
        {leftPanelVisible ? '<' : '>'}
      </button>

      {/* Main Content - 3분할 */}
      <main className={`dashboard-main ${userRole === 'customer' ? 'customer-view' : ''} ${!leftPanelVisible ? 'left-panel-hidden' : ''}`}>
        {/* 좌측 패널: 실시간 대화 */}
        <div className="panel panel-left">
          {/* 고객 정보 카드 - 상담사 전용 */}
          {userRole === 'agent' && (
            <div className={`card collapsible-card ${customerInfoCollapsed ? 'collapsed' : ''}`}>
              <div
                className="card-header clickable"
                onClick={() => setCustomerInfoCollapsed(!customerInfoCollapsed)}
              >
                <h3 className="card-title">고객 정보</h3>
                <button className="collapse-btn">
                  {customerInfoCollapsed ? '+' : '-'}
                </button>
              </div>
              {!customerInfoCollapsed && (
                <div className="card-body">
                  {customerInfo ? (
                    <div className="customer-info-grid">
                      <div className="customer-info-row">
                        <span className="customer-info-label">고객 식별자</span>
                        <span className="customer-info-value">{customerInfo.customer_id || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">고객명</span>
                        <span className="customer-info-value">{remotePeer?.nickname || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">휴대번호</span>
                        <span className="customer-info-value">{customerInfo.phone_number || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">등급</span>
                        <span className="customer-info-value highlight">{customerInfo.membership_grade || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">나이/성별</span>
                        <span className="customer-info-value">
                          {customerInfo.age ? `${customerInfo.age}세` : '-'} / {customerInfo.gender || '-'}
                        </span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">요금제</span>
                        <span className="customer-info-value highlight">{customerInfo.current_plan || customerInfo.plan_name || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">월 요금</span>
                        <span className="customer-info-value">
                          {customerInfo.monthly_fee ? `${customerInfo.monthly_fee.toLocaleString()}원` : '-'}
                        </span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">약정상태</span>
                        <span className="customer-info-value">{customerInfo.contract_status || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">결합정보</span>
                        <span className="customer-info-value">{customerInfo.bundle_info || '없음'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">데이터</span>
                        <span className="customer-info-value">{customerInfo.data_allowance || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">가입일</span>
                        <span className="customer-info-value">{customerInfo.subscription_date || '-'}</span>
                      </div>
                      <div className="customer-info-row">
                        <span className="customer-info-label">사용기간</span>
                        <span className="customer-info-value">{customerInfo.subscription_duration || '-'}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="no-connection">
                      <p>고객 연결 대기 중...</p>
                      <p className="wait-message">고객이 입장하면 정보가 표시됩니다.</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 과거 상담 이력 - 상담사만 */}
          {userRole === 'agent' && (
            <div className={`card collapsible-card ${historyCollapsed ? 'collapsed' : ''}`}>
              <div
                className="card-header clickable"
                onClick={() => setHistoryCollapsed(!historyCollapsed)}
              >
                <h3 className="card-title">
                  과거 상담 이력 {consultationHistory.length > 0 && `(${consultationHistory.length}건)`}
                </h3>
                <button className="collapse-btn">
                  {historyCollapsed ? '+' : '-'}
                </button>
              </div>
              {!historyCollapsed && (
                <div className="card-body">
                  <div className="history-list">
                    {consultationHistory.length > 0 ? (
                      consultationHistory.map((history, index) => {
                        const metaParts = [
                          history.consultation_date,
                          history.consultation_type || '상담',
                          history.agent_name ? `담당 ${history.agent_name}` : null,
                        ].filter(Boolean);
                        const metaLine = metaParts.join(' · ');
                        const summaryText = history.final_summary || '요약 없음';
                        const shortSummary =
                          summaryText.length > 80
                            ? `${summaryText.slice(0, 80)}…`
                            : summaryText;

                        return (
                          <div
                            key={index}
                            className="history-item clickable"
                            onClick={() => handleHistoryClick(history)}
                          >
                            <div className="history-header compact">
                              <span className="history-date">{metaLine}</span>
                              <span className="history-view-detail">상세 보기</span>
                            </div>
                            <p className={`history-summary ${history.final_summary ? '' : 'history-no-summary'}`}>
                              {shortSummary}
                            </p>
                          </div>
                        );
                      })
                    ) : (
                      <p className="no-history">상담 이력이 없습니다.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 중앙 패널: 핵심 인사이트 */}
        <div className="panel panel-center">
          {/* 응답 초안 카드 */}
          {userRole === 'agent' && (
            <div className="card">
              <div className="card-header">
                <h3 className="card-title">응답 초안 추천</h3>
              </div>
              <div className="card-body">
                {draftData.keywords && draftData.keywords.length > 0 && (
                  <div className="response-keywords">
                    {draftData.keywords.map((keyword, idx) => (
                      <span key={idx} className="keyword-tag">{keyword}</span>
                    ))}
                  </div>
                )}
                <div className="response-content">
                  {draftData.short_reply || '응답 초안 대기 중...'}
                </div>
                <p className="copy-hint">클릭하여 복사</p>
              </div>
            </div>
          )}

          {/* 자동 요약 카드 */}
          <div className={`insight-card collapsible-card ${summaryCardCollapsed ? 'collapsed' : ''}`}>
            <div
              className="insight-card-header clickable"
              onClick={() => setSummaryCardCollapsed(!summaryCardCollapsed)}
            >
              <span className="insight-card-title">자동 문제 요약</span>
              <button className="collapse-btn">{summaryCardCollapsed ? '+' : '-'}</button>
            </div>
            {!summaryCardCollapsed && (
              <div className="insight-card-body">
                <div className="summary-content">
                  <div className="summary-item">
                    <div className="summary-label">요약</div>
                    <div className="summary-value">{summaryData.summary || '대기 중'}</div>
                  </div>
                  <div className="summary-item">
                    <div className="summary-label">고객 문의</div>
                    <div className="summary-value">{summaryData.customer_issue || '대기 중'}</div>
                  </div>
                  <div className="summary-item">
                    <div className="summary-label">상담사 대응</div>
                    <div className="summary-value">{summaryData.agent_action || '대기 중'}</div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* 감정 분석 카드 */}
          <div className={`insight-card collapsible-card ${emotionCardCollapsed ? 'collapsed' : ''}`}>
            <div
              className="insight-card-header clickable"
              onClick={() => setEmotionCardCollapsed(!emotionCardCollapsed)}
            >
              <span className="insight-card-title emotion-title-row">
                <span className="emotion-label-prefix">감정 상태</span>
                <span className={`emotion-label-badge ${emotionState}`}>
                  {sentimentData.sentiment_label || '안정'}
                </span>
              </span>
              <button className="collapse-btn">{emotionCardCollapsed ? '+' : '-'}</button>
            </div>
            {!emotionCardCollapsed && (
              <div className="insight-card-body">
                <div className="emotion-content">
                  <div className="emotion-indicators">
                    <div className="emotion-indicator">
                      <div className="emotion-indicator-label">강도</div>
                      <div className="emotion-indicator-value">
                        {sentimentData.sentiment_score ?? '-'}
                      </div>
                    </div>
                    <div className="emotion-indicator">
                      <div className="emotion-indicator-label">해지 리스크</div>
                      <div className={`emotion-indicator-value ${riskFlags.includes('해지') ? 'high' : 'low'}`}>
                        {riskFlags.includes('해지') ? '높음' : '낮음'}
                      </div>
                    </div>
                  </div>
                  {sentimentData.sentiment_explanation && (
                    <div className="emotion-advice">
                      {sentimentData.sentiment_explanation}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>


        </div>

        {/* 우측 패널: 고객 의도 + RAG - 상담사만 */}
        {userRole === 'agent' && (
          <div className="panel panel-right">
            {/* 고객 의도 헤더 - 크고 눈에 띄게 */}
            <div className="intent-header-banner">
              <span className="intent-header-title">고객 의도: {intentData.intent_label || '분석 대기 중'}</span>
              {intentData.intent_explanation && (
                <span className="intent-header-detail">{intentData.intent_explanation}</span>
              )}
            </div>

            {/* AI 추천 정보 카드 스택 */}
            <div className="card card-flex">
              <div className="card-header">
                <h3 className="card-title">AI 추천 정보</h3>
              </div>
              <div className="card-body">
                {(() => {
                  // RAG 카드와 기타 카드 분리
                  const ragCards = assistCards.filter((c) => c.type === 'rag');
                  const otherCards = assistCards.filter((c) => c.type !== 'rag');

                  // 최신 RAG 그룹 찾기 (가장 최근 턴의 카드들)
                  const latestRagGroupId = ragCards.length > 0 ? ragCards[0].ragGroupId : null;
                  const latestRagCards = ragCards.filter((c) => c.ragGroupId === latestRagGroupId);
                  const olderRagCards = ragCards.filter((c) => c.ragGroupId !== latestRagGroupId);

                  // 최신 RAG 그룹에서 표시할 카드 (ragCardVisibleCount 개)
                  const visibleLatestRagCards = latestRagCards.slice(0, ragCardVisibleCount);
                  const hiddenLatestRagCount = latestRagCards.length - ragCardVisibleCount;

                  // 전체 표시할 카드: 최신 RAG (제한) + 이전 RAG + 기타
                  const allVisibleCards = [...visibleLatestRagCards, ...olderRagCards, ...otherCards];

                  if (allVisibleCards.length === 0) {
                    return <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>표시할 카드가 없습니다.</p>;
                  }

                  return (
                    <div className="stack-list">
                      {allVisibleCards.map((card, cardIndex) => {
                        const isHighlighted = newRagCardIds.has(card.id);
                        const isLatestGroup = card.ragGroupId === latestRagGroupId;
                        const showLoadMore = isLatestGroup && card.ragIndex === ragCardVisibleCount - 1 && hiddenLatestRagCount > 0;

                        return (
                          <React.Fragment key={card.id}>
                            <div
                              className={`stack-card ${card.collapsed ? 'collapsed' : ''} ${card.type === 'rag' ? 'rag-card' : ''} ${card.type === 'faq' ? 'faq-card' : ''} ${isHighlighted ? 'rag-card-highlight' : ''}`}
                            >
                              <div className="stack-card-header" onClick={() => handleToggleCard(card.id)}>
                                <div className="stack-card-meta">
                                  <span className={`pill pill-${card.type || 'default'}`}>
                                    {card.type === 'reply' && '응답'}
                                    {card.type === 'policy' && '정책'}
                                    {card.type === 'risk' && '위험'}
                                    {card.type === 'guide' && '가이드'}
                                    {card.type === 'rag' && 'RAG'}
                                    {card.type === 'faq' && 'FAQ'}
                                    {!card.type && '알림'}
                                  </span>
                                  <span className="stack-card-title">{card.title}</span>
                                  {card.relevance && (
                                    <span className="relevance-badge" title="관련도">
                                      {Math.round(card.relevance * 100)}%
                                    </span>
                                  )}
                                  {isHighlighted && <span className="new-badge">NEW</span>}
                                </div>
                                <div className="stack-card-actions">
                                  <button
                                    className="icon-btn"
                                    title={card.collapsed ? '펼치기' : '접기'}
                                  >
                                    {card.collapsed ? '+' : '-'}
                                  </button>
                                  <button
                                    className="icon-btn"
                                    onClick={(e) => { e.stopPropagation(); handleDismissCard(card.id); }}
                                    title="닫기"
                                  >
                                    x
                                  </button>
                                </div>
                              </div>
                              {!card.collapsed && (
                                <div className="stack-card-body">
                                  {/* FAQ 카드: 카테고리 및 캐시 정보 */}
                                  {card.type === 'faq' && card.category && (
                                    <div className="card-faq-category">
                                      <span className="faq-category-label">{card.category}</span>
                                      {card.cacheHit && <span className="faq-cache-badge">Cached</span>}
                                    </div>
                                  )}
                                  {/* RAG 카드: 상세 정보 레이아웃 */}
                                  {card.type === 'rag' && (
                                    <div className="rag-detail-layout">
                                      {/* 가격 및 데이터 박스 */}
                                      <div className="rag-price-data-box">
                                        {card.monthlyPrice && (
                                          <div className="rag-price-section">
                                            <span className="rag-price-label">월 요금</span>
                                            <span className="rag-price-value">{card.monthlyPrice.toLocaleString()}원</span>
                                          </div>
                                        )}
                                        {card.metadata?.data_allowance && (
                                          <div className="rag-data-section">
                                            <span className="rag-data-label">데이터</span>
                                            <span className="rag-data-value">{card.metadata.data_allowance}</span>
                                          </div>
                                        )}
                                      </div>
                                      {/* 통화/콘텐츠/멤버십 특징 목록 */}
                                      {(card.metadata?.voice_benefit || card.metadata?.content_benefit || card.metadata?.membership) && (
                                        <div className="rag-features-list">
                                          {card.metadata?.voice_benefit && (
                                            <div className="rag-feature-item">
                                              <span className="rag-feature-icon voice">V</span>
                                              <span className="rag-feature-label">통화</span>
                                              <span className="rag-feature-value">{card.metadata.voice_benefit}</span>
                                            </div>
                                          )}
                                          {card.metadata?.content_benefit && (
                                            <div className="rag-feature-item">
                                              <span className="rag-feature-icon content">*</span>
                                              <span className="rag-feature-label">콘텐츠</span>
                                              <span className="rag-feature-value">{card.metadata.content_benefit}</span>
                                            </div>
                                          )}
                                          {card.metadata?.membership && (
                                            <div className="rag-feature-item">
                                              <span className="rag-feature-icon membership">M</span>
                                              <span className="rag-feature-label">멤버십</span>
                                              <span className="rag-feature-value">{card.metadata.membership}</span>
                                            </div>
                                          )}
                                        </div>
                                      )}
                                      {/* 타겟 세그먼트 */}
                                      {card.metadata?.target_segment && (
                                        <div className="rag-target-segment">
                                          <span className="rag-target-label">타겟:</span>
                                          <span className="rag-target-value">{card.metadata.target_segment}</span>
                                        </div>
                                      )}
                                      {/* TIP */}
                                      {card.metadata?.tip && (
                                        <div className="rag-tip-box">
                                          <span className="rag-tip-label">TIP</span>
                                          <span className="rag-tip-value">{card.metadata.tip}</span>
                                        </div>
                                      )}
                                      {/* 기존 briefInfo 폴백 */}
                                      {card.briefInfo && !card.metadata?.data_allowance && (
                                        <div className="card-brief-info">{card.briefInfo}</div>
                                      )}
                                    </div>
                                  )}
                                  {card.content && card.type !== 'rag' && (
                                    card.type === 'faq'
                                      ? renderFaqContent(card.content)
                                      : <p className="stack-card-text">{card.content}</p>
                                  )}
                                  {/* RAG 카드: 추천 이유는 TIP에 표시됨 */}
                                  {/* 기존 policy 카드 호환 (metadata.monthly_price) */}
                                  {card.type !== 'rag' && card.metadata && card.metadata.monthly_price && (
                                    <div className="card-price-info">
                                      <span className="price-label">월정액:</span>
                                      <span className="price-value">{card.metadata.monthly_price}</span>
                                    </div>
                                  )}
                                  {card.checklist && (
                                    <ul className="checklist">
                                      {card.checklist.map((item, idx) => (
                                        <li key={idx} className="checklist-item">
                                          <span className="checklist-bullet"></span>
                                          {item}
                                        </li>
                                      ))}
                                    </ul>
                                  )}
                                </div>
                              )}
                            </div>
                            {/* 더 보기 버튼 */}
                            {showLoadMore && (
                              <button
                                className="load-more-btn"
                                onClick={() => setRagCardVisibleCount((prev) => Math.min(prev + 3, 5))}
                              >
                                + {hiddenLatestRagCount}개 더 보기
                              </button>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* 플로팅 채팅 버튼 */}
      <button
        className={`floating-chat-btn ${floatingChatOpen ? 'active' : ''}`}
        onClick={() => {
          setFloatingChatOpen(!floatingChatOpen);
          if (!floatingChatOpen) {
            lastReadTranscriptCount.current = transcripts.length;
            setUnreadChatCount(0);
          }
        }}
        title={floatingChatOpen ? '채팅 닫기' : '실시간 대화'}
      >
        {floatingChatOpen ? (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
        )}
        {unreadChatCount > 0 && !floatingChatOpen && (
          <span className="chat-badge">{unreadChatCount > 99 ? '99+' : unreadChatCount}</span>
        )}
      </button>

      {/* 플로팅 채팅창 */}
      {floatingChatOpen && (
        <div className="floating-chat-window">
          <div className="floating-chat-header">
            <h4>실시간 대화</h4>
            <span className="chat-count">{transcripts.length}개 메시지</span>
          </div>
          <div className="floating-chat-body" ref={floatingChatBodyRef}>
            {transcripts.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
                대화 내용이 여기에 표시됩니다...
              </p>
            ) : (
              transcripts.map((transcript, index) => {
                const isOwnMessage = transcript.peer_id === peerId;
                const isCustomerMessage = userRole === 'agent' ? !isOwnMessage : isOwnMessage;
                const role = isCustomerMessage ? '고객' : '상담사';
                const elapsedTime = getElapsedSeconds(transcript.receivedAt);
                return (
                  <div
                    key={index}
                    className={`message-bubble ${isCustomerMessage ? 'customer' : 'agent'}`}
                  >
                    <div className="message-header">
                      <span className="message-sender">{role}</span>
                      <span className="message-time">{formatDuration(elapsedTime)}</span>
                    </div>
                    <div className="message-text">{transcript.text}</div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Hidden Audio Element for Remote Stream */}
      <audio ref={remoteAudioRef} autoPlay />

      {/* 상담 이력 상세 모달 */}
      {showHistoryModal && (
        <div className="history-modal-overlay" onClick={handleCloseHistoryModal}>
          <div className="history-modal" onClick={(e) => e.stopPropagation()}>
            <div className="history-modal-header">
              <h3>상담 이력 상세</h3>
              <button className="modal-close-btn" onClick={handleCloseHistoryModal}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
            <div className="history-modal-body">
              {historyDetailLoading ? (
                <div className="modal-loading">
                  <div className="loading-spinner"></div>
                  <p>상담 이력을 불러오는 중...</p>
                </div>
              ) : (
                <>
                  {/* 기본 정보 */}
                  <div className="modal-section">
                    <h4>기본 정보</h4>
                    <div className="modal-info-grid">
                      <div className="modal-info-row">
                        <span className="modal-info-label">상담 일시</span>
                        <span className="modal-info-value">{selectedHistory?.consultation_date || '-'}</span>
                      </div>
                      <div className="modal-info-row">
                        <span className="modal-info-label">상담 유형</span>
                        <span className="modal-info-value">
                          {selectedHistory?.consultation_type ? (
                            <span className="history-type-badge">{selectedHistory.consultation_type}</span>
                          ) : '-'}
                        </span>
                      </div>
                      <div className="modal-info-row">
                        <span className="modal-info-label">담당 상담사</span>
                        <span className="modal-info-value">{selectedHistory?.agent_name || '-'}</span>
                      </div>
                      {historyDetailData?.duration && (
                        <div className="modal-info-row">
                          <span className="modal-info-label">상담 시간</span>
                          <span className="modal-info-value">{historyDetailData.duration}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 상담 요약 */}
                  {(selectedHistory?.final_summary || historyDetailData?.final_summary) && (
                    <div className="modal-section">
                      <h4>상담 요약</h4>
                      <div className="modal-summary-content">
                        {historyDetailData?.final_summary || selectedHistory?.final_summary}
                      </div>
                    </div>
                  )}

                  {/* 대화 내용 */}
                  {historyDetailData?.transcripts && historyDetailData.transcripts.length > 0 && (
                    <div className="modal-section">
                      <h4>대화 내용 ({historyDetailData.transcripts.length}건)</h4>
                      <div className="modal-transcripts">
                        {historyDetailData.transcripts.map((transcript, idx) => (
                          <div
                            key={idx}
                            className={`modal-transcript-item ${transcript.speaker_role === 'customer' ? 'customer' : 'agent'}`}
                          >
                            <div className="transcript-header">
                              <span className="transcript-speaker">
                                {transcript.speaker_role === 'customer' ? '고객' : '상담사'}
                              </span>
                              {transcript.timestamp && (
                                <span className="transcript-time">{transcript.timestamp}</span>
                              )}
                            </div>
                            <p className="transcript-text">{transcript.text}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 분석 결과 */}
                  {historyDetailData?.analysis_results && historyDetailData.analysis_results.length > 0 && (
                    <div className="modal-section">
                      <h4>AI 분석 결과</h4>
                      <div className="modal-analysis-list">
                        {historyDetailData.analysis_results.map((result, idx) => (
                          <div key={idx} className="modal-analysis-item">
                            <span className="analysis-type">{getResultTypeName(result.result_type)}</span>
                            <span className="analysis-summary">{formatResultSummary(result.result_type, result.result_data)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 데이터 없음 */}
                  {!historyDetailData && !historyDetailLoading && (
                    <div className="modal-no-detail">
                      <p>상세 정보를 불러올 수 없습니다.</p>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AssistantMain;
