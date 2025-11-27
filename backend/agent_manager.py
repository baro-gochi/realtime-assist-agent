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
LLM_MODEL = "openai:gpt-5-nano"



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
            # TTFT 최적화: temperature=0 (Greedy Search)
            # - temperature=0: 가장 확률 높은 토큰만 선택하여 샘플링 시간 최소화
            # - max_completion_tokens=150: GPT-5에서는 max_tokens 대신 이걸 사용
            # - reasoning_effort="minimal": 간단한 요약에는 minimal reasoning으로 빠르게
            # - streaming=True: 첫 토큰 즉시 반환
            llm = init_chat_model(
                LLM_MODEL,
                temperature=0,
                max_completion_tokens=150,
                reasoning_effort="minimal",
                streaming=True
            )

            # 시스템 메시지 (Runtime Context로 전달할 내용)
            self.system_message = """고객 상담 대화를 1문장으로 개조식으로 매우 간단하게 요약하세요.
예시: 고객이 환불을 요청함.
고객의 주요 문의사항과 상담사의 대응을 포함하세요."""

            logger.info("✅ LLM initialized successfully")
        except Exception as e:
            logger.error(f"❌ LLM initialization failed: {e}")
            llm = None
            self.system_message = None

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
            "current_summary": "",
            "messages": []  # MessagesState 필수 필드
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

        # LangGraph 스트리밍 실행 (Runtime Context로 시스템 메시지 전달)
        # stream_mode="messages": LLM의 각 토큰을 실시간으로 스트리밍
        logger.info(f"🚀 Starting graph.astream for room '{self.room_name}'")
        summary_chunks = []  # 요약 청크를 누적

        try:
            async for chunk in self.graph.astream(
                self.state,
                stream_mode="messages",  # LLM 메시지 스트리밍
                context={"system_message": self.system_message}  # Runtime Context 전달
            ):
                # chunk는 (message, metadata) 튜플 형태
                message, metadata = chunk
                logger.debug(f"📤 Message chunk received: {message}")

                # AIMessage의 content만 추출
                if hasattr(message, 'content') and message.content:
                    content = message.content
                    summary_chunks.append(content)

                    # 현재까지 누적된 요약을 State에 반영
                    current_summary = "".join(summary_chunks)
                    self.state["current_summary"] = current_summary

                    # 각 청크를 즉시 yield (프론트엔드로 스트리밍)
                    yield {
                        "summarize": {
                            "current_summary": current_summary,
                            "is_streaming": True  # 스트리밍 중임을 표시
                        }
                    }

            # 스트리밍 완료 표시
            if summary_chunks:
                final_summary = "".join(summary_chunks)
                self.state["current_summary"] = final_summary
                yield {
                    "summarize": {
                        "current_summary": final_summary,
                        "is_streaming": False  # 스트리밍 완료
                    }
                }

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
            "current_summary": "",
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
