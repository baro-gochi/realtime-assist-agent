"""Room-based Agent Manager for Real-time Conversation Summarization.

이 모듈은 방(room)별로 LangGraph 에이전트 인스턴스를 관리합니다.

주요 기능:
    - 각 방마다 독립적인 에이전트 인스턴스 유지
    - 새로운 transcript 수신 시 에이전트 실행 (비스트리밍)
    - 증분 요약: last_summarized_index로 요약된 위치 추적
    - JSON 형식으로 구조화된 요약 반환
    - LLM 인스턴스를 한 번만 초기화하여 모든 에이전트가 공유

Architecture:
    - room_agents: {room_name: RoomAgent}
    - RoomAgent: 방 하나당 1개 인스턴스, State 유지
    - llm: 모든 에이전트가 공유하는 LLM 인스턴스 (성능 최적화)
    - 증분 요약: 기존 요약 + 새로운 transcript만 처리

Example:
    >>> from modules.agent import get_or_create_agent
    >>> agent = get_or_create_agent("상담실1")
    >>> result = await agent.on_new_transcript("고객", "김철수", "환불하고 싶어요")
    >>> print(result)  # {"current_summary": '{"summary": "...", ...}', "last_summarized_index": 1}
"""
import logging
import time
from typing import Dict, Any
from .graph import create_agent_graph, ConversationState
from .config import llm_config
from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)



class RoomAgent:
    """방 하나당 하나의 에이전트 인스턴스.

    각 상담 방마다 독립적인 대화 히스토리와 요약을 유지합니다.

    Attributes:
        room_name (str): 방 이름
        graph: 컴파일된 LangGraph 인스턴스
        state (ConversationState): 현재 대화 상태
    """

    def __init__(self, room_name: str):
        """RoomAgent 초기화.

        Args:
            room_name (str): 방 이름
        """
        # LLM 인스턴스 초기화 (클래스 생성 시 실행)
        logger.info(f"Initializing LLM: {llm_config.MODEL}")

        try:
            # TTFT 최적화: temperature=0 (Greedy Search)
            # - temperature=0: 가장 확률 높은 토큰만 선택하여 샘플링 시간 최소화
            # - max_completion_tokens=150: GPT-5에서는 max_tokens 대신 이걸 사용
            # - reasoning_effort="minimal": 간단한 요약에는 minimal reasoning으로 빠르게
            # - streaming=True: 첫 토큰 즉시 반환
            llm = init_chat_model(
                llm_config.MODEL,
                temperature=llm_config.TEMPERATURE,
                max_completion_tokens=llm_config.MAX_TOKENS,
                reasoning_effort=llm_config.REASONING_EFFORT or "minimal"
                # streaming=True
            )

            # 시스템 메시지 (Runtime Context로 전달할 내용) - JSON 출력 강제, 한 문장 요약 강조
            self.system_message = """
            # 역할
            고객 상담 대화를 요약하여 반드시 아래 JSON 형식으로만 출력하세요.
            다른 텍스트 없이 JSON만 출력하세요.

            # 중요 규칙
            - summary 필드는 반드시 한 문장이어야 합니다 (20자 이내)
            - 이전 요약을 참고하지 말고 현재 대화만 요약하세요

            {{"summary": "한 문장 요약 (20자 이내)", "customer_issue": "고객 문의 한 줄", "agent_action": "상담사 대응 한 줄"}}
            # 예시:
            {{"summary": "고객이 환불을 요청함", "customer_issue": "제품 불량으로 환불 요청", "agent_action": "환불 절차 안내"}}
            """

            logger.info("LLM initialized successfully")
        except Exception as e:
            logger.error(f"LLM initialization failed: {e}")
            llm = None
            self.system_message = None

        self.room_name = room_name
        self.llm_available = llm is not None

        if self.llm_available:
            self.graph = create_agent_graph(llm)
        else:
            self.graph = None
            logger.warning(f"RoomAgent for '{room_name}' created without LLM - summaries will not be generated")

        self.state: ConversationState = {
            "room_name": room_name,
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,  # 증분 요약용 인덱스 추적
            "messages": []  # MessagesState 필수 필드
        }

        logger.info(f"RoomAgent created for room: {room_name}")

    async def on_new_transcript(
        self,
        speaker_id: str,
        speaker_name: str,
        text: str,
        timestamp: float = None
    ) -> Dict[str, Any]:
        """새로운 transcript를 받아 에이전트를 실행합니다 (비스트리밍).

        Args:
            speaker_id (str): 발화자 ID (peer_id)
            speaker_name (str): 발화자 이름 (nickname)
            text (str): 전사된 텍스트
            timestamp (float, optional): 타임스탬프. None이면 현재 시간 사용

        Returns:
            Dict[str, Any]: {"current_summary": str (JSON), "last_summarized_index": int}
                           또는 에러 시 {"error": {"message": str}}

        Example:
            >>> result = await agent.on_new_transcript("peer123", "김철수", "환불하고 싶어요")
            >>> print(result)
            {"current_summary": '{"summary": "...", "customer_issue": "...", "agent_action": "..."}', ...}
        """
        if timestamp is None:
            timestamp = time.time()

        # State에 새 transcript 추가
        self.state["conversation_history"].append({
            "speaker_id": speaker_id,
            "speaker_name": speaker_name,
            "text": text,
            "timestamp": timestamp
        })

        logger.info(
            f"New transcript in room '{self.room_name}': "
            f"{speaker_name}: {text[:50]}..."
        )
        logger.info(f"Current conversation history count: {len(self.state['conversation_history'])}")

        # LLM 없으면 요약 생성 스킵 (transcript는 이미 추가됨)
        if not self.llm_available:
            logger.warning(f"LLM not available - skipping summary generation for room '{self.room_name}'")
            return {"error": {"message": "LLM not available"}}

        # LangGraph 비스트리밍 실행 (Runtime Context로 시스템 메시지 전달)
        logger.info(f"Starting graph.ainvoke for room '{self.room_name}'")

        try:
            # ainvoke로 한 번에 결과 받기 (비스트리밍)
            result = await self.graph.ainvoke(
                self.state,
                context={"system_message": self.system_message}  # Runtime Context 전달
            )

            # 결과에서 요약 및 인덱스 추출
            current_summary = result.get("current_summary", "")
            last_summarized_index = result.get("last_summarized_index", 0)

            # State 업데이트
            self.state["current_summary"] = current_summary
            self.state["last_summarized_index"] = last_summarized_index

            logger.info(f"Summary generated (JSON): {current_summary[:100]}...")
            logger.info(f"Last summarized index: {last_summarized_index}")

            return {
                "current_summary": current_summary,
                "last_summarized_index": last_summarized_index
            }

        except Exception as e:
            logger.error(f"Error in agent execution: {e}", exc_info=True)
            return {"error": {"message": str(e)}}

    def get_current_summary(self) -> str:
        """현재 대화 요약을 반환합니다.

        Returns:
            str: 현재까지의 대화 요약
        """
        return self.state.get("current_summary", "")

    def get_conversation_count(self) -> int:
        """대화 히스토리 개수를 반환합니다.

        Returns:
            int: 누적된 대화 개수
        """
        return len(self.state.get("conversation_history", []))

    def reset(self):
        """에이전트 상태를 초기화합니다.

        Note:
            방이 종료되거나 새로운 세션을 시작할 때 사용
        """
        logger.info(f"Resetting agent for room: {self.room_name}")
        self.state = {
            "room_name": self.room_name,
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,  # 증분 요약용 인덱스 초기화
            "messages": []  # MessagesState 필수 필드
        }


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
        logger.info(f"New agent created for room: {room_name}")
    else:
        logger.debug(f"Reusing existing agent for room: {room_name}")

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
        logger.info(f"Agent removed for room: {room_name}")
    else:
        logger.warning(f"No agent found for room: {room_name}")


def get_all_agents() -> Dict[str, RoomAgent]:
    """모든 활성 에이전트를 반환합니다.

    Returns:
        Dict[str, RoomAgent]: {room_name: RoomAgent}

    Note:
        모니터링 및 디버깅 목적
    """
    return room_agents.copy()
