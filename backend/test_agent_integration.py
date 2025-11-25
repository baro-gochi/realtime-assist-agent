"""Runtime Context 패턴이 적용된 agent.py와 agent_manager.py 통합 테스트

이 테스트는:
1. RoomAgent 생성 (시스템 메시지는 한 번만 설정)
2. 새로운 transcript 추가 시 요약 생성
3. Runtime Context가 올바르게 동작하는지 검증
"""
import asyncio
import logging

from agent_manager import RoomAgent

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,  # INFO → DEBUG로 변경
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_room_agent():
    """RoomAgent 통합 테스트"""
    # 1. RoomAgent 생성 (시스템 메시지는 여기서 한 번만 설정)
    logger.info("\n1️⃣ RoomAgent 생성 중...")
    agent = RoomAgent("테스트실")

    logger.info(f"✅ RoomAgent 생성 완료: {agent.room_name}")
    logger.info(f"📝 시스템 메시지: {agent.system_message[:50]}...")

    # 2. 첫 번째 transcript 추가
    logger.info("\n2️⃣ 첫 번째 transcript 추가...")
    logger.info("=" * 80)

    async for chunk in agent.on_new_transcript(
        speaker_id="customer1",
        speaker_name="고객",
        text="환불하고 싶어요"
    ):
        logger.info(f"📦 Chunk: {chunk}")

    logger.info(f"\n✅ 현재 요약: {agent.get_current_summary()}")

    # 3. 두 번째 transcript 추가
    logger.info("\n3️⃣ 두 번째 transcript 추가...")
    logger.info("=" * 80)

    async for chunk in agent.on_new_transcript(
        speaker_id="agent1",
        speaker_name="상담사",
        text="어떤 제품을 환불하시나요?"
    ):
        logger.info(f"📦 Chunk: {chunk}")

    logger.info(f"\n✅ 현재 요약: {agent.get_current_summary()}")

    # 4. 세 번째 transcript 추가
    logger.info("\n4️⃣ 세 번째 transcript 추가...")
    logger.info("=" * 80)

    async for chunk in agent.on_new_transcript(
        speaker_id="customer1",
        speaker_name="고객",
        text="어제 산 노트북이요. 화면이 켜지지 않아요."
    ):
        logger.info(f"📦 Chunk: {chunk}")

    logger.info(f"\n✅ 현재 요약: {agent.get_current_summary()}")

    # 5. 최종 상태 확인
    logger.info("\n" + "=" * 80)
    logger.info("📊 최종 상태")
    logger.info("=" * 80)
    logger.info(f"방 이름: {agent.room_name}")
    logger.info(f"대화 개수: {agent.get_conversation_count()}")
    logger.info(f"최종 요약: {agent.get_current_summary()}")
    logger.info(f"메시지 히스토리 개수: {len(agent.state.get('messages', []))}")

if __name__ == "__main__":
    asyncio.run(test_room_agent())
