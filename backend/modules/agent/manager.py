"""Room-based Agent Manager for Real-time Conversation Summarization.

이 모듈은 방(room)별로 LangGraph 에이전트 인스턴스를 관리합니다.

주요 기능:
    - 각 방마다 독립적인 에이전트 인스턴스 유지
    - 새로운 transcript 수신 시 에이전트 실행 (비스트리밍)
    - 증분 요약: last_summarized_index로 요약된 위치 추적
    - JSON 형식으로 구조화된 요약 반환
    - LLM 인스턴스를 한 번만 초기화하여 모든 에이전트가 공유
    - Redis 캐싱을 통한 Rate Limit 방어 및 지연 시간 단축
    - OpenAI Implicit Caching을 위한 정적 컨텍스트 분리
    - 상담 세션/전사/에이전트 결과 DB 저장

Architecture:
    - room_agents: {room_name: RoomAgent}
    - RoomAgent: 방 하나당 1개 인스턴스, State 유지
    - llm: 모든 에이전트가 공유하는 LLM 인스턴스 (성능 최적화)
    - 증분 요약: 기존 요약 + 새로운 transcript만 처리

Caching Strategy:
    1. OpenAI Implicit Caching: 정적 시스템 메시지를 동일하게 유지하여 TTFT 감소
    2. Redis LangChain Cache: 유사/동일 프롬프트에 대한 API 호출 자체를 줄임

Example:
    >>> from modules.agent import get_or_create_agent
    >>> agent = get_or_create_agent("상담실1")
    >>> result = await agent.on_new_transcript("고객", "김철수", "환불하고 싶어요")
    >>> print(result)  # {"current_summary": '{"summary": "...", ...}', "last_summarized_index": 1}
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from .graph import (
    create_agent_graph,
    ConversationState,
    FINAL_SUMMARY_SCHEMA,
    FINAL_SUMMARY_SYSTEM_PROMPT,
)
from langchain_core.messages import SystemMessage, HumanMessage
import json
from .config import llm_config, summary_llm_config
from .cache import setup_global_llm_cache, get_cache_stats
from langchain.chat_models import init_chat_model

# Database repositories (lazy import to avoid circular dependencies)
_session_repo = None
_transcript_repo = None
_agent_result_repo = None


def _get_repositories():
    """Repository 싱글톤 인스턴스들을 반환합니다 (lazy initialization)."""
    global _session_repo, _transcript_repo, _agent_result_repo
    if _session_repo is None:
        from modules.database import (
            get_session_repository,
            get_transcript_repository,
            get_agent_result_repository,
        )
        _session_repo = get_session_repository()
        _transcript_repo = get_transcript_repository()
        _agent_result_repo = get_agent_result_repository()
    return _session_repo, _transcript_repo, _agent_result_repo

logger = logging.getLogger(__name__)

# 애플리케이션 시작 시 전역 LLM 캐시 설정
_cache_setup_done = False



def _ensure_cache_setup():
    """전역 LLM 캐시가 설정되어 있는지 확인하고, 필요시 설정합니다."""
    global _cache_setup_done
    if not _cache_setup_done:
        _cache_setup_done = True
        if setup_global_llm_cache():
            stats = get_cache_stats()
            logger.info(f"[캐시] LLM 캐시 설정 완료: {stats}")
        else:
            logger.info("[캐시] LLM 캐시 비활성화 또는 설정 실패")


class RoomAgent:
    """방 하나당 하나의 에이전트 인스턴스.

    각 상담 방마다 독립적인 대화 히스토리와 요약을 유지합니다.

    Attributes:
        room_name (str): 방 이름
        graph: 컴파일된 LangGraph 인스턴스
        state (ConversationState): 현재 대화 상태
        static_system_prefix (str): OpenAI Implicit Caching용 정적 시스템 메시지
        session_id (UUID | None): 현재 상담 세션 ID (DB 저장용)
        save_to_db (bool): DB 저장 활성화 여부
    """

    def __init__(self, room_name: str, save_to_db: bool = True):
        """RoomAgent 초기화.

        Args:
            room_name (str): 방 이름
            save_to_db (bool): DB 저장 활성화 여부 (기본값: True)
        """
        # 전역 LLM 캐시 설정 확인
        _ensure_cache_setup()

        # LLM 인스턴스 초기화 (클래스 생성 시 실행)
        logger.info(f"[에이전트] LLM 초기화 중: {llm_config.MODEL}")

        try:
            llm = init_chat_model(
                llm_config.MODEL,
                temperature=llm_config.TEMPERATURE,
                # max_completion_tokens=llm_config.MAX_TOKENS,
                reasoning_effort=llm_config.REASONING_EFFORT or "minimal"
                # streaming=True
            )

            # 정적 시스템 메시지 (OpenAI Implicit Caching 대상)
            # 모든 노드에서 동일하게 사용되어야 캐시 효과 극대화
            self._base_system_message = """고객 상담 대화를 분석하여 요약하세요."""

            # 현재 활성화된 정적 접두사 (고객 컨텍스트 포함)
            self.static_system_prefix = self._base_system_message

            # 하위 호환성을 위한 system_message 유지
            self.system_message = self.static_system_prefix

            # logger.info("LLM 초기화 성공")
        except Exception as e:
            logger.error(f"[에이전트] LLM 초기화 실패: {e}")
            llm = None
            self._base_system_message = None
            self.static_system_prefix = None
            self.system_message = None

        # 최종 요약 전용 LLM 초기화
        summary_llm = None
        try:
            logger.info(f"[에이전트] 요약 LLM 초기화 중: {summary_llm_config.MODEL}")
            summary_llm = init_chat_model(
                summary_llm_config.MODEL,
                temperature=summary_llm_config.TEMPERATURE,
            )
            logger.info("[에이전트] 요약 LLM 초기화 성공")
        except Exception as e:
            logger.error(f"[에이전트] 요약 LLM 초기화 실패: {e}")
            summary_llm = None

        self.room_name = room_name
        self.llm = llm  # 실시간 분석용 LLM
        self.summary_llm = summary_llm  # 최종 요약 전용 LLM
        self.llm_available = llm is not None
        self.save_to_db = save_to_db
        self.session_id: Optional[UUID] = None
        self._turn_index = 0  # 전사 순서 인덱스

        if self.llm_available:
            self.graph = create_agent_graph(llm)
        else:
            self.graph = None
            logger.warning(f"[에이전트] RoomAgent 생성됨 (LLM 없음): {room_name}")

        self.state: ConversationState = {
            "room_name": room_name,
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,
            "summary_result": {},
            "messages": [],
            "customer_info": None,
            "consultation_history": [],
            "intent_result": None,
            "sentiment_result": None,
            "draft_replies": None,
            "risk_result": None,
            "rag_policy_result": None,
            "faq_result": None,
            "has_new_customer_turn": False,
            "last_intent_index": 0,
            "last_sentiment_index": 0,
            "last_draft_index": 0,
            "last_risk_index": 0,
            "last_rag_index": 0,
            "last_faq_index": 0,
            "last_rag_intent": "",
            "last_faq_query": "",
        }

        logger.info(f"[에이전트] RoomAgent 생성: {room_name}")

    async def on_new_transcript(
        self,
        speaker_id: str,
        speaker_name: str,
        text: str,
        timestamp: float = None,
        run_summary: bool = True,
        on_update=None,
        turn_id: Optional[str] = None,
        is_customer: bool = False,
    ) -> Dict[str, Any]:
        """새로운 transcript를 받아 에이전트를 실행합니다 (비스트리밍).

        Args:
            speaker_id (str): 발화자 ID (peer_id)
            speaker_name (str): 발화자 이름 (nickname)
            text (str): 전사된 텍스트
            timestamp (float, optional): 타임스탬프. None이면 현재 시간 사용
            run_summary (bool): True일 때만 요약 실행 (False면 히스토리만 기록)
            on_update (Callable): 그래프 노드별 업데이트 콜백 (stream_mode="updates"에서 사용)
            turn_id (str | None): 이 요약 실행을 식별하기 위한 ID (없으면 자동 생성)
            is_customer (bool): 고객 발화 여부 (True면 의도 분석 노드 활성화)

        Returns:
            Dict[str, Any]: {"summary_result": dict, "last_summarized_index": int}
                           또는 에러 시 {"error": {"message": str}}

        Example:
            >>> result = await agent.on_new_transcript("peer123", "김철수", "환불하고 싶어요", is_customer=True)
            >>> print(result)
            {"summary_result": {...}, ...}
        """
        if timestamp is None:
            timestamp = time.time()

        # State에 새 transcript 추가 (is_customer 플래그 포함)
        self.state["conversation_history"].append({
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "text": text,
            "timestamp": timestamp,
            "is_customer": is_customer,
        })

        # 고객 발화인 경우 플래그 설정
        if is_customer:
            self.state["has_new_customer_turn"] = True

        logger.info(
            f"[에이전트] 새 전사: {self.room_name} - "
            f"{speaker_name}: {text[:50]}..."
        )
        logger.info(f"[에이전트] 대화 이력 수: {len(self.state['conversation_history'])}")

        # DB에 전사 저장
        await self._save_transcript(
            speaker_type="customer" if is_customer else "agent",
            speaker_name=speaker_name,
            text=text,
            timestamp=datetime.fromtimestamp(timestamp)
        )

        # 요약 생략 요청 시 히스토리만 기록
        if not run_summary:
            return {
                "summary_result": self.state.get("summary_result", {}),
                "current_summary": self.state.get("current_summary", ""),
                "last_summarized_index": self.state.get("last_summarized_index", 0),
                "intent_result": self.state.get("intent_result", None),
                "sentiment_result": self.state.get("sentiment_result", None),
                "draft_replies": self.state.get("draft_replies", None),
                "risk_result": self.state.get("risk_result", None),
                "rag_policy_result": self.state.get("rag_policy_result", None),
                "faq_result": self.state.get("faq_result", None),
            }

        # LLM 없으면 요약 생성 스킵 (transcript는 이미 추가됨)
        if not self.llm_available:
            logger.warning(f"[에이전트] LLM 없음: {self.room_name}")
            return {"error": {"message": "LLM not available"}}

        # LangGraph 스트리밍 실행 (stream_mode="updates"로 노드별 업데이트 전달)
        logger.info(f"[에이전트] 그래프 스트리밍 시작: {self.room_name}")
        stream_turn_id = turn_id or f"{self.room_name}-{int(time.time() * 1000)}"

        try:
            latest_updates: Dict[str, Any] = {}

            # Runtime Context를 context= 파라미터로 전달
            # LangGraph는 context_schema에 맞는 dict를 context=로 전달받아
            # 각 노드의 runtime.context에 주입함
            async for update in self.graph.astream(
                {**self.state},
                stream_mode="updates",
                context={
                    "static_system_prefix": self.static_system_prefix,
                    "system_message": self.system_message,
                },
            ):
                if not update:
                    continue

                for node_name, payload in update.items():
                    if not payload:
                        continue

                    # 실시간 콜백으로 WebSocket 브로드캐스트
                    if callable(on_update):
                        await on_update({
                            "turn_id": stream_turn_id,
                            "node": node_name,
                            "data": payload,
                        })

                    # 마지막 결과 저장 (노드별 최신값)
                    latest_updates.update(payload)

            # 그래프 실행 후 상태 적용
            if latest_updates:
                self.state.update(latest_updates)

            summary_result = latest_updates.get("summary_result", self.state.get("summary_result", {}))
            current_summary = latest_updates.get("current_summary", self.state.get("current_summary", ""))
            last_summarized_index = latest_updates.get("last_summarized_index", self.state.get("last_summarized_index", 0))

            intent_result = latest_updates.get("intent_result", self.state.get("intent_result"))
            sentiment_result = latest_updates.get("sentiment_result", self.state.get("sentiment_result"))
            draft_replies = latest_updates.get("draft_replies", self.state.get("draft_replies"))
            risk_result = latest_updates.get("risk_result", self.state.get("risk_result"))
            rag_policy_result = latest_updates.get("rag_policy_result", self.state.get("rag_policy_result"))
            faq_result = latest_updates.get("faq_result", self.state.get("faq_result"))

            # State 업데이트 (보존 필드 포함)
            self.state["summary_result"] = summary_result
            self.state["current_summary"] = current_summary
            self.state["last_summarized_index"] = last_summarized_index
            self.state["intent_result"] = intent_result
            self.state["sentiment_result"] = sentiment_result
            self.state["draft_replies"] = draft_replies
            self.state["risk_result"] = risk_result
            self.state["rag_policy_result"] = rag_policy_result
            self.state["faq_result"] = faq_result

            # 그래프 실행 완료 후 고객 발화 플래그 리셋
            self.state["has_new_customer_turn"] = False

            # 인덱스 및 쿼리 업데이트 (그래프에서 반환한 값 사용)
            for idx_key in ["last_intent_index", "last_sentiment_index", "last_draft_index", "last_risk_index", "last_rag_index", "last_faq_index", "last_rag_intent", "last_faq_query"]:
                if idx_key in latest_updates:
                    self.state[idx_key] = latest_updates[idx_key]

            logger.info(f"[에이전트] 요약 생성: {current_summary[:100]}...")
            logger.info(f"[에이전트] 요약 인덱스: {last_summarized_index}")
            logger.info(f"[에이전트] 의도: {intent_result}, 감정: {sentiment_result}, 위험: {risk_result}")
            if rag_policy_result:
                logger.info(f"[RAG] 정책 결과: {len(rag_policy_result.get('recommendations', []))}개 추천")
            if faq_result:
                logger.info(f"[FAQ] 결과: {len(faq_result.get('faqs', []))}개, 캐시={faq_result.get('cache_hit')}")

            # DB에 에이전트 결과 저장
            await self._save_agent_results(
                turn_id=stream_turn_id,
                intent_result=intent_result,
                sentiment_result=sentiment_result,
                summary_result=summary_result,
                rag_result=rag_policy_result,
                faq_result=faq_result,
                risk_result=risk_result
            )

            return {
                "summary_result": summary_result,
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index,
                "intent_result": intent_result,
                "sentiment_result": sentiment_result,
                "draft_replies": draft_replies,
                "risk_result": risk_result,
                "rag_policy_result": rag_policy_result,
                "faq_result": faq_result,
            }

        except Exception as e:
            logger.error(f"[에이전트] 실행 오류: {e}", exc_info=True)
            return {"error": {"message": str(e)}}
    

    def reset(self):
        """에이전트 상태를 초기화합니다.

        Note:
            방이 종료되거나 새로운 세션을 시작할 때 사용
        """
        logger.info(f"[에이전트] 상태 초기화: {self.room_name}")
        self.state = {
            "room_name": self.room_name,
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,
            "summary_result": {},
            "messages": [],  # MessagesState 필수 필드
            "customer_info": None,
            "consultation_history": [],
            "intent_result": None,
            "sentiment_result": None,
            "draft_replies": None,
            "risk_result": None,
            "rag_policy_result": None,
            "faq_result": None,
            "has_new_customer_turn": False,
            "last_intent_index": 0,
            "last_sentiment_index": 0,
            "last_draft_index": 0,
            "last_risk_index": 0,
            "last_rag_index": 0,
            "last_faq_index": 0,
            "last_rag_intent": "",
            "last_faq_query": "",
        }
        # 정적 시스템 메시지 초기화 (캐싱 일관성 유지)
        self.static_system_prefix = self._base_system_message
        self.system_message = self._base_system_message
        # 세션 정보 초기화
        self.session_id = None
        self._turn_index = 0

    async def start_session(
        self,
        agent_name: str,
        room_id: UUID = None,
        customer_id: int = None,
        agent_id: str = None,
        channel: str = "call",
        metadata: dict = None
    ) -> Optional[UUID]:
        """새로운 상담 세션을 시작합니다.

        Args:
            agent_name: 상담사 이름
            room_id: WebRTC 룸 ID (선택)
            customer_id: 고객 ID (선택)
            agent_id: 상담사 ID (선택)
            channel: 채널 (call, chat)
            metadata: 추가 메타데이터

        Returns:
            생성된 세션 UUID 또는 None
        """
        logger.info(f"[에이전트] 세션 시작 요청 - room={self.room_name}, agent={agent_name}, room_id={room_id} (type={type(room_id).__name__})")

        if not self.save_to_db:
            logger.warning(f"[에이전트] 세션 생성 스킵: save_to_db=False (room={self.room_name})")
            return None

        session_repo, _, _ = _get_repositories()
        logger.debug(f"[에이전트] 세션 레포지토리 획득 완료")

        logger.info(f"[에이전트] 세션 생성 호출 중 - agent={agent_name}, room_id={room_id}, agent_id={agent_id}")
        self.session_id = await session_repo.create_session(
            agent_name=agent_name,
            room_id=room_id,
            customer_id=customer_id,
            agent_id=agent_id,
            channel=channel,
            metadata=metadata or {"room_name": self.room_name}
        )

        if self.session_id:
            self._turn_index = 0
            logger.info(f"[에이전트] 세션 시작 성공 - session_id={self.session_id}, room={self.room_name}")
        else:
            logger.error(f"[에이전트] 세션 시작 실패 - room={self.room_name}, room_id={room_id}")

        return self.session_id

    async def generate_final_summary(self) -> Dict[str, Any]:
        """전체 대화를 기반으로 구조화된 최종 요약을 생성합니다.

        Returns:
            구조화된 최종 요약 딕셔너리:
            {
                "consultation_type": str,
                "customer_issue": str,
                "steps": [{"order": int, "action": str}, ...],
                "resolution": str,
                "customer_sentiment": str
            }
        """
        # 요약 전용 LLM 사용, 없으면 기본 LLM 폴백
        llm_to_use = self.summary_llm or self.llm
        if not llm_to_use:
            logger.warning("[에이전트] 최종 요약 LLM 없음")
            return {}

        conversation_history = self.state.get("conversation_history", [])
        if not conversation_history:
            logger.warning("[에이전트] 대화 이력 없음, 최종 요약 불가")
            return {}

        # 대화 내역을 텍스트로 변환
        conversation_text = "\n".join([
            f"[{entry.get('speaker_id', 'unknown')}] {entry.get('speaker_name', '')}: {entry.get('text', '')}"
            for entry in conversation_history
        ])

        try:
            # Structured Output으로 LLM 호출
            structured_llm = llm_to_use.with_structured_output(
                FINAL_SUMMARY_SCHEMA,
                method="json_schema",
                strict=True
            )

            messages = [
                SystemMessage(content=FINAL_SUMMARY_SYSTEM_PROMPT),
                HumanMessage(content=f"## 전체 상담 대화\n\n{conversation_text}")
            ]

            logger.info(f"[에이전트] 최종 요약 생성 중: {len(conversation_history)}개 턴")
            start_time = time.time()

            result = await structured_llm.ainvoke(messages)

            elapsed = time.time() - start_time
            logger.info(f"[에이전트] 최종 요약 완료: {elapsed:.2f}s")

            # LLM 반환값 확인
            logger.debug(f"generate_final_summary result type: {type(result).__name__}")
            logger.debug(f"consultation_type: {result.get('consultation_type') if isinstance(result, dict) else 'N/A'}")

            return result if isinstance(result, dict) else {}

        except Exception as e:
            logger.error(f"[에이전트] 최종 요약 실패: {e}")
            return {}

    def _format_final_summary_text(self, summary_data: Dict[str, Any]) -> str:
        """구조화된 요약 데이터를 텍스트 형식으로 변환합니다."""
        if not summary_data:
            return ""

        lines = []

        # 상담 유형
        if summary_data.get("consultation_type"):
            lines.append(f"[상담 유형] {summary_data['consultation_type']}")

        # 고객 문의
        if summary_data.get("customer_issue"):
            lines.append(f"[고객 문의] {summary_data['customer_issue']}")

        # 진행 과정
        steps = summary_data.get("steps", [])
        if steps:
            lines.append("[진행 과정]")
            for step in steps:
                order = step.get("order", 0)
                action = step.get("action", "")
                lines.append(f"  {order}. {action}")

        # 해결 결과
        if summary_data.get("resolution"):
            lines.append(f"[해결 결과] {summary_data['resolution']}")

        # 고객 감정
        if summary_data.get("customer_sentiment"):
            lines.append(f"[고객 상태] {summary_data['customer_sentiment']}")

        return "\n".join(lines)

    async def end_session(
        self,
        final_summary: str = None,
        consultation_type: str = None
    ) -> bool:
        """상담 세션을 종료합니다.

        Args:
            final_summary: 최종 요약 (없으면 LLM으로 구조화된 요약 생성)
            consultation_type: 상담 유형

        Returns:
            성공 여부
        """
        logger.info(f"[에이전트] 세션 종료 요청 - room={self.room_name}, session_id={self.session_id}")

        if not self.save_to_db:
            logger.warning(f"[에이전트] 세션 종료 스킵: save_to_db=False")
            return False

        if not self.session_id:
            logger.warning(f"[에이전트] 세션 종료 스킵: session_id가 None (room={self.room_name})")
            return False

        session_repo, _, _ = _get_repositories()

        # 최종 요약이 없으면 LLM으로 구조화된 요약 생성
        if not final_summary:
            logger.info(f"[에이전트] 최종 요약 생성 중...")
            summary_data = await self.generate_final_summary()
            logger.debug(f"summary_data keys: {list(summary_data.keys()) if summary_data else 'None'}")
            if summary_data:
                final_summary = self._format_final_summary_text(summary_data)
                # 상담 유형도 자동 추출
                if not consultation_type:
                    consultation_type = summary_data.get("consultation_type", "")
                logger.debug(f"extracted consultation_type: '{consultation_type}'")
                logger.info(f"[에이전트] 최종 요약 생성 완료 - type={consultation_type}")
            else:
                # 폴백: 기존 실시간 요약 사용
                final_summary = self.state.get("current_summary", "")
                logger.warning(f"[에이전트] 최종 요약 생성 실패, 기존 요약 사용")

        logger.info(f"[에이전트] 세션 종료 DB 저장 중 - session={self.session_id}")
        logger.debug(f"end_session params: consultation_type='{consultation_type}', summary_len={len(final_summary) if final_summary else 0}")
        success = await session_repo.end_session(
            session_id=self.session_id,
            final_summary=final_summary,
            consultation_type=consultation_type
        )

        if success:
            logger.info(f"[에이전트] 세션 종료 성공 - session_id={self.session_id}")
        else:
            logger.error(f"[에이전트] 세션 종료 실패 - session_id={self.session_id}")

        return success

    async def update_session_customer(self, customer_id: int) -> bool:
        """세션에 고객 정보를 연결합니다.

        Args:
            customer_id: 고객 ID

        Returns:
            성공 여부
        """
        if not self.save_to_db or not self.session_id:
            return False

        session_repo, _, _ = _get_repositories()
        return await session_repo.update_customer(self.session_id, customer_id)

    async def _save_transcript(
        self,
        speaker_type: str,
        speaker_name: str,
        text: str,
        timestamp: datetime,
        confidence: float = None
    ) -> bool:
        """전사 내용을 DB에 저장합니다.

        Args:
            speaker_type: 발화자 타입 (agent, customer)
            speaker_name: 발화자 이름
            text: 발화 내용
            timestamp: 발화 시간
            confidence: STT 신뢰도

        Returns:
            성공 여부
        """
        logger.debug(f"[에이전트] 전사 저장 시도 - save_to_db={self.save_to_db}, session_id={self.session_id}")

        if not self.save_to_db:
            logger.debug("[에이전트] 전사 저장 스킵: save_to_db=False")
            return False

        if not self.session_id:
            logger.warning(f"[에이전트] 전사 저장 스킵: session_id가 None (room={self.room_name})")
            return False

        _, transcript_repo, _ = _get_repositories()

        self._turn_index += 1
        logger.info(f"[에이전트] 전사 저장 중 - session={self.session_id}, turn={self._turn_index}, speaker={speaker_name}")

        result = await transcript_repo.add_transcript(
            session_id=self.session_id,
            turn_index=self._turn_index,
            speaker_type=speaker_type,
            speaker_name=speaker_name,
            text=text,
            timestamp=timestamp,
            confidence=confidence
        )

        if result:
            logger.info(f"[에이전트] 전사 저장 완료 - turn={self._turn_index}")
        else:
            logger.error(f"[에이전트] 전사 저장 실패 - turn={self._turn_index}")

        return result

    async def _save_agent_results(
        self,
        turn_id: str,
        intent_result: dict = None,
        sentiment_result: dict = None,
        summary_result: dict = None,
        rag_result: dict = None,
        faq_result: dict = None,
        risk_result: dict = None
    ):
        """에이전트 분석 결과를 DB에 저장합니다.

        Args:
            turn_id: 연관된 turn ID
            intent_result: 의도 분석 결과
            sentiment_result: 감정 분석 결과
            summary_result: 요약 결과
            rag_result: RAG 검색 결과
            faq_result: FAQ 검색 결과
            risk_result: 리스크 분석 결과
        """
        result_types = []
        if intent_result:
            result_types.append("intent")
        if sentiment_result:
            result_types.append("sentiment")
        if summary_result:
            result_types.append("summary")
        if rag_result:
            result_types.append("rag")
        if faq_result:
            result_types.append("faq")
        if risk_result:
            result_types.append("risk")

        logger.debug(f"[에이전트] 결과 저장 시도 - save_to_db={self.save_to_db}, session_id={self.session_id}, types={result_types}")

        if not self.save_to_db:
            logger.debug("[에이전트] 결과 저장 스킵: save_to_db=False")
            return

        if not self.session_id:
            logger.warning(f"[에이전트] 결과 저장 스킵: session_id가 None (room={self.room_name})")
            return

        logger.info(f"[에이전트] 결과 저장 시작 - session={self.session_id}, types={result_types}")

        _, _, agent_result_repo = _get_repositories()

        # Intent 저장
        if intent_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="intent",
                result_data=intent_result,
                turn_id=turn_id
            )

        # Sentiment 저장
        if sentiment_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="sentiment",
                result_data=sentiment_result,
                turn_id=turn_id
            )

        # Summary 저장
        if summary_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="summary",
                result_data=summary_result,
                turn_id=turn_id
            )

        # RAG 저장
        if rag_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="rag",
                result_data=rag_result,
                turn_id=turn_id
            )

        # FAQ 저장
        if faq_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="faq",
                result_data=faq_result,
                turn_id=turn_id
            )

        # Risk 저장
        if risk_result:
            await agent_result_repo.save_result(
                session_id=self.session_id,
                result_type="risk",
                result_data=risk_result,
                turn_id=turn_id
            )

    def set_customer_context(self, customer_info: dict, consultation_history: list):
        """고객 정보를 에이전트 컨텍스트에 설정합니다.

        OpenAI Implicit Caching 최적화:
        - 고객 정보가 변경될 때만 static_system_prefix를 업데이트
        - 동일한 고객 정보면 캐시가 유지됨

        Args:
            customer_info (dict): DB에서 조회한 고객 정보
            consultation_history (list): 고객의 과거 상담 이력
        """
        self.state["customer_info"] = customer_info
        self.state["consultation_history"] = consultation_history

        # 정적 시스템 메시지에 고객 컨텍스트 추가 (캐싱 대상)
        if customer_info and self._base_system_message:
            customer_context = self._generate_customer_context(customer_info, consultation_history)

            # 정적 접두사 업데이트 (OpenAI Implicit Caching 대상)
            self.static_system_prefix = self._base_system_message + customer_context
            self.system_message = self.static_system_prefix

            logger.info(
                f"[캐시] 정적 컨텍스트 업데이트: {self.room_name} - "
                f"{customer_info.get('customer_name')} ({len(self.static_system_prefix)}자)"
            )

    def _generate_customer_context(self, customer_info: dict, consultation_history: list) -> str:
        """고객 컨텍스트 문자열을 생성합니다.

        Note:
            이 문자열은 OpenAI Implicit Caching의 키로 사용되므로,
            동일한 고객 정보에 대해 정확히 동일한 문자열이 생성되어야 합니다.

        Args:
            customer_info (dict): 고객 정보
            consultation_history (list): 상담 이력

        Returns:
            str: 고객 컨텍스트 문자열
        """
        customer_context = f"""

현재 상담 고객 정보:
- 이름: {customer_info.get('customer_name', '알 수 없음')}
- 등급: {customer_info.get('membership_grade', '알 수 없음')}
- 요금제: {customer_info.get('current_plan', '알 수 없음')}
- 월정액: {customer_info.get('monthly_fee', 0):,}원
- 약정상태: {customer_info.get('contract_status', '알 수 없음')}
- 결합정보: {customer_info.get('bundle_info', '없음')}
"""
        if consultation_history:
            customer_context += "\n최근 상담 이력:\n"
            for idx, history in enumerate(consultation_history[:3], 1):
                date = history.get('consultation_date', '')
                ctype = history.get('consultation_type', '')
                detail = history.get('detail', {})
                summary = detail.get('summary', '') if isinstance(detail, dict) else str(detail)
                customer_context += f"  {idx}. [{date}] {ctype}: {summary}\n"

        return customer_context


# 글로벌 에이전트 저장소
# {room_name: RoomAgent}
room_agents: Dict[str, RoomAgent] = {}


def get_or_create_agent(room_name: str) -> RoomAgent:
    """방 이름에 해당하는 에이전트를 반환하거나 새로 생성합니다.

    Args:
        room_name (str): 방 이름

    Returns:
        RoomAgent: 해당 방의 에이전트 인스턴스

    Note:
        - 방 입장 시 자동으로 에이전트 생성
        - 이미 존재하면 기존 인스턴스 재사용
    """
    if room_name not in room_agents:
        agent = RoomAgent(room_name)
        room_agents[room_name] = agent
        logger.info(f"[에이전트] 새 에이전트 생성: {room_name}")
    else:
        logger.debug(f"[에이전트] 기존 에이전트 재사용: {room_name}")

    return room_agents[room_name]


def remove_agent(room_name: str):
    """방의 에이전트를 제거합니다.

    Args:
        room_name (str): 방 이름

    Note:
        - 방이 완전히 종료될 때 호출
        - 메모리 정리 목적
    """
    if room_name in room_agents:
        del room_agents[room_name]
        logger.info(f"[에이전트] 에이전트 제거: {room_name}")
    else:
        logger.warning(f"[에이전트] 에이전트 없음: {room_name}")
