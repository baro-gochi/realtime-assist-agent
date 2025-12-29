"""FastAPI WebRTC Signaling Server with Room Support.

이 모듈은 WebRTC 기반의 멀티룸 비디오/오디오 상담 시스템을 위한
시그널링 서버를 제공합니다. FastAPI와 WebSocket을 사용하여
실시간 peer-to-peer 연결을 관리합니다.

주요 기능:
    - 룸 기반 피어 관리 (다중 상담 세션 지원)
    - WebRTC offer/answer 교환
    - ICE candidate 처리
    - 실시간 참가자 입/퇴장 알림
    - CORS 설정을 통한 크로스 오리진 요청 지원

Architecture:
    - SFU (Selective Forwarding Unit) 패턴 사용
    - PeerConnectionManager: WebRTC 연결 관리
    - RoomManager: 룸 및 참가자 상태 관리
    - WebSocket: 실시간 시그널링 메시지 전송
"""
import logging
import asyncio
from contextlib import asynccontextmanager
import os
from typing import Optional, List
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from modules import (
    PeerConnectionManager, RoomManager, get_db_manager, get_redis_manager,
    DatabaseLogHandler
)
from modules.agent import remove_agent
from routes import (
    health_router, consultation_router, agent_router, logs_router, auth_router,
    signaling_router, init_signaling_managers,
    verify_auth_header
)
from dotenv import load_dotenv
from pathlib import Path

# Load 환경변수 로드 variables from config/.env
load_dotenv(Path(__file__).parent / "config" / ".env")


# 로그 설정
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/server_{__import__('datetime').datetime.now().strftime('%Y%m%d')}.log"

# 환경별 로그 레벨 설정 (환경변수로 제어)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENV = os.getenv("ENV", "development")

# 로그 보관 기간 (일) - 기본 60일 (2개월)
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "60"))


def cleanup_old_logs(log_dir: str = "logs", retention_days: int = LOG_RETENTION_DAYS) -> int:
    """오래된 로그 파일을 삭제합니다.

    Args:
        log_dir: 로그 디렉토리 경로
        retention_days: 보관 기간 (일)

    Returns:
        삭제된 파일 수
    """
    import glob
    from datetime import datetime, timedelta

    if not os.path.exists(log_dir):
        return 0

    cutoff_date = datetime.now() - timedelta(days=retention_days)
    deleted_count = 0

    # 삭제할 로그 패턴들 (server_*.log, frontend/frontend_*.log)
    log_patterns = [
        (os.path.join(log_dir, "server_*.log"), "server_", ".log"),
        (os.path.join(log_dir, "frontend", "frontend_*.log"), "frontend_", ".log"),
    ]

    for log_pattern, prefix, suffix in log_patterns:
        for log_file in glob.glob(log_pattern):
            try:
                filename = os.path.basename(log_file)
                date_str = filename.replace(prefix, "").replace(suffix, "")
                file_date = datetime.strptime(date_str, "%Y%m%d")

                if file_date < cutoff_date:
                    os.remove(log_file)
                    deleted_count += 1
            except (ValueError, OSError):
                continue

    return deleted_count

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),  # 콘솔 출력
        logging.FileHandler(log_filename, encoding="utf-8"),  # 파일 저장
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"로깅 초기화 완료: level={LOG_LEVEL}, env={ENV}")


# 글로벌 매니저 인스턴스
peer_manager = PeerConnectionManager()
room_manager = RoomManager()

# DB 매니저 및 Redis 매니저 초기화
db_manager = get_db_manager()
redis_manager = get_redis_manager()
db_log_handler: Optional[DatabaseLogHandler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 앱의 생명주기를 관리하는 컨텍스트 매니저.

    서버 시작 시 초기화 작업을 수행하고, 종료 시 정리 작업을 수행합니다.
    모든 활성 WebRTC 연결을 안전하게 종료하여 리소스 누수를 방지합니다.

    Args:
        app (FastAPI): FastAPI 애플리케이션 인스턴스

    Yields:
        None: 앱이 실행되는 동안 제어를 반환

    Note:
        - 시작: DB 초기화, 로그 핸들러 시작, 서버 시작
        - 종료: 로그 핸들러 정지, DB 연결 종료, 피어 연결 정리
    """
    global db_log_handler

    # 서버 시작
    logger.info("WebRTC 시그널링 서버 시작 중...")

    # 오래된 로그 파일 정리 (2개월 이상)
    deleted_logs = cleanup_old_logs()
    if deleted_logs > 0:
        logger.info(f"오래된 로그 파일 {deleted_logs}개 정리 완료 ({LOG_RETENTION_DAYS}일 이상)")

    # 데이터베이스 연결 초기화
    db_initialized = await db_manager.initialize()
    if db_initialized:
        logger.info("데이터베이스 연결 완료")

        # 데이터베이스 로그 핸들러 시작
        db_log_handler = DatabaseLogHandler(level=logging.INFO)
        logging.getLogger().addHandler(db_log_handler)
        await db_log_handler.start()
        logger.info("데이터베이스 로그 핸들러 시작됨")
    else:
        logger.warning("데이터베이스 사용 불가, DB 로깅 없이 실행")

    # Redis 연결 초기화
    redis_initialized = await redis_manager.initialize()
    if redis_initialized:
        logger.info("Redis 연결 완료")
    else:
        logger.warning("Redis 사용 불가, Redis 없이 실행")

    yield

    # 서버 종료
    logger.info("서버 종료 중...")

    # 데이터베이스 로그 핸들러 정지
    if db_log_handler:
        await db_log_handler.stop()
        logger.info("데이터베이스 로그 핸들러 정지됨")

    # Redis 연결 종료
    if redis_manager.is_initialized:
        await redis_manager.close()
        logger.info("Redis 연결 종료됨")

    # 데이터베이스 연결 종료
    if db_manager.is_initialized:
        await db_manager.close()
        logger.info("데이터베이스 연결 종료됨")

    # 피어 연결 정리
    await peer_manager.cleanup_all()


app = FastAPI(title="WebRTC Signaling Server with Rooms", lifespan=lifespan)

# CORS - 개발 환경에서는 모든 로컬 네트워크 허용
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|172\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+$|^https://.*\.loca\.lt$|^https://baro-gochi\.github\.io$|^https://.*\.ngrok(-free)?\.(app|dev|io)$|^https://.*\.trycloudflare\.com$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health_router)
app.include_router(consultation_router)
app.include_router(agent_router)
app.include_router(logs_router)
app.include_router(auth_router)
app.include_router(signaling_router)

# WebSocket 시그널링 라우터에 매니저 인스턴스 전달
init_signaling_managers(peer_manager, room_manager)


@app.get("/")
async def root():
    """서버 상태 확인 엔드포인트 (Health check).

    서버가 정상적으로 실행 중인지 확인하는 간단한 헬스체크 엔드포인트입니다.
    모니터링 및 로드 밸런서에서 서버 상태를 확인하는 데 사용됩니다.

    Returns:
        dict: 서버 상태 정보를 포함하는 딕셔너리
            - status (str): 서버 상태 ("ok" 또는 오류 상태)
            - service (str): 서비스 이름

    Examples:
        >>> response = await root()
        >>> print(response)
        {"status": "ok", "service": "WebRTC Signaling Server with Rooms"}
    """
    return {"status": "ok", "service": "WebRTC Signaling Server with Rooms"}

# STT 연동없이 택스트 시나리오로 에이전트 테스트용 API
class ScenarioTestRequest(BaseModel):
    """시나리오 테스트 요청 모델."""
    scenario: List[dict]  # [{"speaker": "고객", "text": "..."}, ...]
    customer_info: dict = {}

@app.post("/api/test/scenario")
async def test_scenario(request: ScenarioTestRequest):
    """시나리오를 실행하고 에이전트 응답을 반환합니다.

    STT 없이 텍스트 시나리오로 에이전트를 테스트합니다.

    Args:
        request: 시나리오 데이터와 고객 정보

    Returns:
        dict: 각 발화에 대한 에이전트 응답 리스트
    """
    from modules.agent.graph import create_agent_graph
    from langchain_openai import ChatOpenAI

    # LLM 초기화
    llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
    graph = create_agent_graph(llm)

    # 기본 고객 정보
    customer_info = request.customer_info or {
        "customer_name": "윤지현",
        "membership_grade": "Gold",
        "current_plan": "인기LTE 데이터ON - 비디오 플러스 69,000원",
        "monthly_fee": 69000,
    }

    # 초기 상태
    state = {
        "messages": [],
        "customer_info": customer_info,
        "conversation_history": [],
        "summary_result": None,
        "intent_result": None,
        "rag_policy_result": None,
        "sentiment_result": None,
        "risk_result": None,
        "draft_replies": None,
        "processed_turn_ids": set(),
        "last_customer_text": "",
    }

    results = []

    for i, turn in enumerate(request.scenario):
        speaker = turn.get("speaker", "")
        text = turn.get("text", "")

        # 대화 기록에 추가
        role = "고객" if speaker == "고객" else "상담사"
        state["conversation_history"].append({
            "role": role,
            "content": text,
            "timestamp": i
        })

        # 고객 발화일 때만 에이전트 실행
        if speaker == "고객":
            state["last_customer_text"] = text
            state["processed_turn_ids"] = set()  # 새 턴

            # 그래프 실행
            result = await graph.ainvoke(state)
            state = result

            # 결과 수집
            turn_result = {
                "turn": i + 1,
                "speaker": speaker,
                "text": text,
                "agent_response": {
                    "intent": result.get("intent_result"),
                    "rag_policy": None,
                    "sentiment": result.get("sentiment_result"),
                    "summary": result.get("summary_result"),
                }
            }

            # RAG 결과 정리
            if result.get("rag_policy_result"):
                rp = result["rag_policy_result"]
                recommendations = []
                for rec in (rp.get("recommendations") or [])[:3]:
                    meta = rec.get("metadata", {})
                    search_text = meta.get("search_text", "")
                    data_info = voice_info = ""
                    if search_text:
                        for p in search_text.split("|"):
                            p = p.strip()
                            if not data_info and p.startswith("데이터"):
                                data_info = p
                            elif not voice_info and p.startswith("음성"):
                                voice_info = p
                    recommendations.append({
                        "title": rec.get("title"),
                        "price": meta.get("monthly_price"),
                        "data": data_info,
                        "voice": voice_info,
                        "reason": rec.get("recommendation_reason"),
                    })
                turn_result["agent_response"]["rag_policy"] = {
                    "intent": rp.get("intent_label"),
                    "recommendations": recommendations,
                }

            results.append(turn_result)
        else:
            results.append({
                "turn": i + 1,
                "speaker": speaker,
                "text": text,
                "agent_response": None
            })

    return {"results": results, "final_summary": state.get("summary_result")}


@app.get("/api/rooms")
async def get_rooms_api(_: bool = Depends(verify_auth_header)):
    """활성화된 모든 룸의 목록을 조회합니다 (API 엔드포인트).

    /rooms와 동일한 기능을 제공하며, Vite 프록시 설정과 호환됩니다.
    프론트엔드에서 /api 경로를 통해 접근할 수 있습니다.

    Returns:
        dict: 룸 목록을 포함하는 딕셔너리
    """
    return {"rooms": room_manager.get_room_list()}


@app.get("/api/turn-credentials")
async def get_turn_credentials(_: bool = Depends(verify_auth_header)):
    """TURN 서버 credentials를 Frontend에 안전하게 제공합니다.

    AWS coturn 서버의 고정 credentials를 클라이언트에 전달합니다.
    이 엔드포인트는 Backend에서 credentials를 관리하여 Frontend에서 민감한 정보가
    노출되지 않도록 합니다.

    Returns:
        list: TURN 서버 ICE server 설정 리스트 또는 에러 메시지
            - 성공 시: ICE servers 배열 (STUN + TURN)
            - 실패 시: {"error": "에러 메시지"}

    Environment Variables:
        TURN_SERVER_URL: AWS coturn TURN 서버 URL
        TURN_USERNAME: AWS coturn 사용자명
        TURN_CREDENTIAL: AWS coturn 비밀번호
        STUN_SERVER_URL: AWS coturn STUN 서버 URL (선택)

    Security:
        - Credentials는 Backend 환경 변수에서만 관리
        - Frontend에 민감한 정보 직접 노출 방지

    Examples:
        성공 응답:
            [
                {
                    "urls": "stun:13.209.180.128:3478"
                },
                {
                    "urls": "turn:13.209.180.128:3478",
                    "username": "username1",
                    "credential": "password1"
                }
            ]

        에러 응답:
            {"error": "TURN service not configured"}
    """
    import os

    turn_server_url = os.getenv("TURN_SERVER_URL")
    turn_username = os.getenv("TURN_USERNAME")
    turn_credential = os.getenv("TURN_CREDENTIAL")
    stun_server_url = os.getenv("STUN_SERVER_URL")

    ice_servers = []

    # STUN 서버 추가 (커스텀 설정)
    if stun_server_url:
        ice_servers.append({"urls": stun_server_url})

    # Google STUN 서버 (fallback)
    ice_servers.append({"urls": "stun:stun.l.google.com:19302"})
    ice_servers.append({"urls": "stun:stun1.l.google.com:19302"})

    # TURN 서버 추가 (설정된 경우만)
    if turn_server_url and turn_username and turn_credential:
        ice_servers.append({
            "urls": turn_server_url,
            "username": turn_username,
            "credential": turn_credential
        })
        logger.info("ICE 서버 제공: STUN + TURN")
    else:
        logger.info("ICE 서버 제공: STUN만 (TURN 미설정)")

    return ice_servers


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
