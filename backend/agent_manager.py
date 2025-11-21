"""Room-based Agent Manager for Real-time Conversation Summarization.

이 모듈은 방(room)별로 LangGraph 에이전트 인스턴스를 관리합니다.

주요 기능:
    - 각 방마다 독립적인 에이전트 인스턴스 유지
    - 새로운 transcript 수신 시 에이전트 실행
    - 스트리밍 모드로 실시간 업데이트 반환
    - LLM 인스턴스를 한 번만 초기화하여 모든 에이전트가 공유

Architecture:
    - room_agents: {room_name: RoomAgent}
    - RoomAgent: 방 하나당 1개 인스턴스, State 유지
    - llm: 모든 에이전트가 공유하는 LLM 인스턴스 (성능 최적화)

Example:
    >>> agent = get_or_create_agent("상담실1")
    >>> async for chunk in agent.on_new_transcript("고객", "김철수", "환불하고 싶어요"):
    ...     print(chunk)  # {"summarize": {"current_summary": "..."}}
"""
import os
import logging
import time
from typing import Dict, AsyncIterator, Any
from agent import create_agent_graph, ConversationState
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# LLM 모델 설정 (모든 에이전트가 공유)
LLM_MODEL = "openai:gpt-5-mini"



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
        logger.info(f"🤖 Initializing LLM: {LLM_MODEL}")

        try:
            # LLM 초기화 with 시스템 프롬프트 (한 번만 설정, 이후 재사용)
            base_llm = init_chat_model(LLM_MODEL)

            # 시스템 프롬프트를 LLM에 bind (매 호출마다 자동 포함)
            system_message = {
                "role": "system",
                "content": """고객 상담 대화를 1-3문장으로 간결하게 요약하세요.
예시: 고객이 환불을 요청함.
고객의 주요 문의사항과 상담사의 대응을 포함하세요."""
            }

            # bind를 사용하여 시스템 프롬프트를 LLM에 고정
            llm = base_llm.bind(system=[system_message])

            logger.info("✅ LLM initialized with system prompt binding")
        except Exception as e:
            logger.error(f"❌ LLM initialization failed: {e}")
            logger.warning("⚠️ Server will start without LLM - room connections and STT will work, but summaries will fail")
            llm = None
            
        self.room_name = room_name
        self.llm_available = llm is not None

        if self.llm_available:
            self.graph = create_agent_graph(llm)
        else:
            self.graph = None
            logger.warning(f"⚠️ RoomAgent for '{room_name}' created without LLM - summaries will not be generated")

        self.state: ConversationState = {
            "room_name": room_name,
            "conversation_history": [],
            "current_summary": ""
        }

        logger.info(f"🤖 RoomAgent created for room: {room_name}")

    async def on_new_transcript(
        self,
        speaker_id: str,
        speaker_name: str,
        text: str,
        timestamp: float = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """새로운 transcript를 받아 에이전트를 실행합니다.

        Args:
            speaker_id (str): 발화자 ID (peer_id)
            speaker_name (str): 발화자 이름 (nickname)
            text (str): 전사된 텍스트
            timestamp (float, optional): 타임스탬프. None이면 현재 시간 사용

        Yields:
            Dict[str, Any]: {"node_name": {업데이트된 State 부분}}

        Example:
            >>> async for chunk in agent.on_new_transcript("peer123", "김철수", "환불하고 싶어요"):
            ...     print(chunk)
            {"summarize": {"current_summary": "고객이 환불을 요청했습니다."}}
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
            f"📝 New transcript in room '{self.room_name}': "
            f"{speaker_name}: {text[:50]}..."
        )
        logger.info(f"📊 Current conversation history count: {len(self.state['conversation_history'])}")

        # LLM 없으면 요약 생성 스킵 (transcript는 이미 추가됨)
        if not self.llm_available:
            logger.warning(f"⚠️ LLM not available - skipping summary generation for room '{self.room_name}'")
            return

        # LangGraph 스트리밍 실행
        logger.info(f"🚀 Starting graph.astream for room '{self.room_name}'")
        try:
            async for chunk in self.graph.astream(
                self.state,
                stream_mode="updates"  # 변경된 부분만 스트리밍
            ):
                logger.info(f"📤 Agent stream chunk received: {list(chunk.keys())}")
                logger.info(f"📦 Chunk content: {chunk}")

                # State 동기화 (업데이트된 내용을 State에 반영)
                for node_name, node_output in chunk.items():
                    for key, value in node_output.items():
                        self.state[key] = value
                        logger.debug(f"  ✅ State updated: {key} = {str(value)[:100]}...")

                # 업데이트 yield
                yield chunk

        except Exception as e:
            logger.error(f"❌ Error in agent execution: {e}", exc_info=True)
            # 에러 발생 시에도 빈 업데이트 반환 (클라이언트가 멈추지 않도록)
            yield {"error": {"message": str(e)}}

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
        logger.info(f"🔄 Resetting agent for room: {self.room_name}")
        self.state = {
            "room_name": self.room_name,
            "conversation_history": [],
            "current_summary": ""
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
        logger.info(f"✅ New agent created for room: {room_name}")
    else:
        logger.debug(f"♻️ Reusing existing agent for room: {room_name}")

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
        logger.info(f"🗑️ Agent removed for room: {room_name}")
    else:
        logger.warning(f"⚠️ No agent found for room: {room_name}")


def get_all_agents() -> Dict[str, RoomAgent]:
    """모든 활성 에이전트를 반환합니다.

    Returns:
        Dict[str, RoomAgent]: {room_name: RoomAgent}

    Note:
        모니터링 및 디버깅 목적
    """
    return room_agents.copy()
