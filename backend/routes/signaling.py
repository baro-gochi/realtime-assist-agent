"""WebRTC 시그널링 WebSocket 라우터.

WebRTC 시그널링을 위한 WebSocket 엔드포인트들을 제공합니다.
룸 참가/퇴장, WebRTC offer/answer 교환, ICE candidate 처리 등을 담당합니다.
"""

import logging
import uuid
import asyncio
import time
from collections import defaultdict
from typing import Optional, TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from modules import CustomerRepository, get_agent_repository
from modules.agent import get_or_create_agent, room_agents
from .deps import verify_ws_token

if TYPE_CHECKING:
    from modules import PeerConnectionManager, RoomManager

logger = logging.getLogger(__name__)

router = APIRouter()

# 글로벌 매니저 참조 (app.py에서 설정됨)
_peer_manager: Optional["PeerConnectionManager"] = None
_room_manager: Optional["RoomManager"] = None
_summary_counters: defaultdict[str, int] = defaultdict(int)


def init_managers(peer_manager: "PeerConnectionManager", room_manager: "RoomManager"):
    """매니저 인스턴스를 초기화합니다.

    app.py에서 호출하여 글로벌 매니저 참조를 설정합니다.

    Args:
        peer_manager: PeerConnectionManager 인스턴스
        room_manager: RoomManager 인스턴스
    """
    global _peer_manager, _room_manager
    _peer_manager = peer_manager
    _room_manager = room_manager
    logger.info("시그널링 라우터 매니저 초기화 완료")


def get_summary_counters() -> defaultdict[str, int]:
    """요약 카운터를 반환합니다."""
    return _summary_counters


async def broadcast_to_room(room_name: str, message: dict, exclude: list = None):
    """특정 룸의 모든 참가자에게 메시지를 브로드캐스트합니다.

    지정된 룸의 모든 피어에게 메시지를 전송하며, 선택적으로 특정 피어를
    제외할 수 있습니다. 메시지 전송 실패 시 해당 피어를 자동으로 정리합니다.

    Args:
        room_name: 메시지를 전송할 룸 이름
        message: 전송할 메시지 딕셔너리
        exclude: 메시지를 받지 않을 peer_id 리스트
    """
    if _room_manager is None or _peer_manager is None:
        logger.error("매니저가 초기화되지 않음")
        return

    exclude = exclude or []
    peers = _room_manager.get_room_peers(room_name)
    disconnected = []

    for peer in peers:
        if peer.peer_id not in exclude:
            try:
                await peer.websocket.send_json(message)
            except Exception as e:
                logger.error(f"피어 {peer.peer_id}에 브로드캐스트 중 오류: {e}")
                disconnected.append(peer.peer_id)

    # 연결 끊긴 피어 정리
    for peer_id in disconnected:
        _room_manager.leave_room(peer_id)
        await _peer_manager.close_peer_connection(peer_id)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = Query(None)):
    """WebRTC 시그널링을 위한 WebSocket 엔드포인트.

    클라이언트와의 WebSocket 연결을 통해 실시간 시그널링 메시지를 주고받습니다.

    처리하는 메시지 타입:
        - join_room: 특정 룸에 참가 (room_name, nickname 필요)
        - offer: WebRTC offer 전송 (sdp, type 포함)
        - ice_candidate: ICE candidate 정보 전송
        - leave_room: 현재 룸에서 퇴장
        - get_rooms: 활성 룸 목록 요청
        - end_session: 상담 세션 종료
        - text_input: 수동 텍스트 입력 (테스트용)

    Args:
        websocket: FastAPI WebSocket 연결 객체
        token: 인증 토큰 (쿼리 파라미터)
    """
    if _peer_manager is None or _room_manager is None:
        logger.error("매니저가 초기화되지 않음")
        await websocket.close(code=1011, reason="Server not ready")
        return

    # 연결 수락 전 토큰 검증
    if not verify_ws_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    peer_id = str(uuid.uuid4())
    current_room = None
    nickname = None

    logger.info(f"피어 {peer_id} 연결됨")

    # 클라이언트에 peer ID 전송
    await websocket.send_json({
        "type": "peer_id",
        "data": {"peer_id": peer_id}
    })

    # 트랙 수신 이벤트 콜백 등록
    async def on_track_received(source_peer_id: str, room_name: str, track_kind: str):
        """트랙 수신 시 호출되는 콜백 함수."""
        logger.info(f"트랙 수신 - 피어: {source_peer_id}, 종류: {track_kind}")
        await broadcast_to_room(
            room_name,
            {
                "type": "renegotiation_needed",
                "data": {
                    "reason": "track_received",
                    "source_peer_id": source_peer_id,
                    "track_kind": track_kind
                }
            },
            exclude=[source_peer_id]
        )

    _peer_manager.on_track_received_callback = on_track_received

    # ICE candidate 콜백 등록
    async def on_ice_candidate(source_peer_id: str, candidate):
        candidate_dict = {
            "candidate": candidate.candidate,
            "sdpMid": candidate.sdpMid,
            "sdpMLineIndex": candidate.sdpMLineIndex
        }

        logger.debug(f"변환된 candidate_dict: sdpMid={candidate_dict.get('sdpMid')}")

        room_name = _peer_manager.get_peer_room(source_peer_id)
        if room_name:
            logger.info(f"백엔드 ICE candidate 브로드캐스트 - 피어: {source_peer_id}, 방: '{room_name}'")
            await _room_manager.broadcast_to_room(
                room_name,
                {
                    "type": "ice_candidate",
                    "data": candidate_dict
                },
                exclude=[]
            )
        else:
            logger.warning(f"피어 {source_peer_id}의 방을 찾을 수 없음")
            await websocket.send_json({"type": "ice_candidate", "data": candidate_dict})

    _peer_manager.on_ice_candidate_callback = on_ice_candidate

    # STT 전사 결과 콜백 등록
    async def on_transcript(peer_id: str, room_name: str, transcript: str, source: str = "google", is_final: bool = True):
        """STT 인식 결과를 WebSocket을 통해 전송하고 에이전트를 실행하는 콜백 함수."""
        logger.info(f"[{source.upper()}] 전사 결과 - 피어: {peer_id}, 방: '{room_name}': {transcript}")

        peer_info = _room_manager.get_peer(peer_id)
        nickname = peer_info.nickname if peer_info else "Unknown"
        is_customer = peer_info.is_customer if peer_info else False

        current_time = time.time()
        if source == "google":
            _room_manager.add_transcript(peer_id, room_name, transcript, timestamp=current_time)

        await broadcast_to_room(
            room_name,
            {
                "type": "transcript",
                "data": {
                    "peer_id": peer_id,
                    "nickname": nickname,
                    "text": transcript,
                    "timestamp": current_time,
                    "source": source,
                    "is_final": is_final
                }
            }
        )

        # STT 비교 룸은 에이전트 실행 제외
        if room_name == "stt-comparison-room":
            logger.debug("STT 비교 룸에서는 에이전트 실행 생략")
            return

        # Google STT만 에이전트 실행
        if source != "google":
            logger.debug(f"{source} 소스는 에이전트 실행 생략")
            return

        try:
            agent = room_agents.get(room_name)
            if not agent:
                logger.warning(f"방 '{room_name}'의 에이전트를 찾을 수 없음")
                return

            should_run_summary = is_final
            if is_final:
                _summary_counters[room_name] += 1

            logger.info(f"방 '{room_name}' 에이전트 실행 (should_run_summary={should_run_summary})")

            turn_id = f"{room_name}-{int(current_time * 1000)}"

            async def handle_agent_update(chunk: dict):
                try:
                    await broadcast_to_room(
                        room_name,
                        {
                            "type": "agent_update",
                            "turn_id": chunk.get("turn_id"),
                            "node": chunk.get("node"),
                            "data": chunk.get("data"),
                        }
                    )
                except Exception as err:
                    logger.error(f"에이전트 업데이트 브로드캐스트 실패: {err}")

            result = await agent.on_new_transcript(
                peer_id,
                nickname,
                transcript,
                current_time,
                run_summary=should_run_summary,
                on_update=handle_agent_update,
                turn_id=turn_id,
                is_customer=is_customer
            )

            if "error" in result:
                logger.error(f"에이전트 에러 반환: {result['error']}")
                return

            if not should_run_summary:
                return

            summary_payload = result.get("summary_result", {}) or {}
            current_summary = result.get("current_summary", "")
            last_summarized_index = result.get("last_summarized_index", 0)

            logger.info(f"요약: {current_summary[:100]}...")

            await broadcast_to_room(
                room_name,
                {
                    "type": "agent_update",
                    "turn_id": turn_id,
                    "node": "summarize",
                    "data": {
                        "summary": summary_payload.get("summary", ""),
                        "customer_issue": summary_payload.get("customer_issue", ""),
                        "agent_action": summary_payload.get("agent_action", ""),
                        "last_summarized_index": last_summarized_index,
                        "raw": current_summary,
                    }
                }
            )

        except Exception as e:
            logger.error(f"에이전트 실행 실패: {e}", exc_info=True)

    _peer_manager.on_transcript_callback = on_transcript

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")

            if message_type == "join_room":
                await _handle_join_room(
                    websocket, peer_id, data, current_room, nickname,
                    on_transcript
                )
                join_data = data.get("data", {})
                current_room = join_data.get("room_name")
                nickname = join_data.get("nickname", "Anonymous")

            elif message_type == "offer":
                await _handle_offer(websocket, peer_id, current_room, data)

            elif message_type == "ice_candidate":
                await _handle_ice_candidate(websocket, peer_id, current_room, data)

            elif message_type == "end_session":
                await _handle_end_session(websocket, current_room)

            elif message_type == "leave_room":
                if current_room:
                    await _handle_leave_room(peer_id, current_room, nickname)
                    current_room = None

            elif message_type == "get_rooms":
                await websocket.send_json({
                    "type": "rooms_list",
                    "data": {"rooms": _room_manager.get_room_list()}
                })

            elif message_type == "text_input":
                if current_room:
                    text = data.get("data", {}).get("text", "").strip()
                    if text:
                        logger.info(f"[TEXT_INPUT] 피어 {peer_id}의 수동 텍스트 입력: {text}")
                        await on_transcript(peer_id, current_room, text, source="manual", is_final=True)

            else:
                logger.warning(f"알 수 없는 메시지 타입: {message_type}")

    except WebSocketDisconnect:
        logger.info(f"피어 {peer_id} 연결 끊김")
    except Exception as e:
        logger.error(f"피어 {peer_id}의 WebSocket 연결 중 오류: {e}")
    finally:
        if current_room:
            await broadcast_to_room(
                current_room,
                {
                    "type": "user_left",
                    "data": {
                        "peer_id": peer_id,
                        "nickname": nickname,
                        "peer_count": _room_manager.get_room_count(current_room) - 1
                    }
                },
                exclude=[peer_id]
            )
            _room_manager.leave_room(peer_id)
            if _room_manager.get_room_count(current_room) == 0:
                _summary_counters.pop(current_room, None)

        await _peer_manager.close_peer_connection(peer_id)
        logger.info(f"피어 {peer_id} 정리 완료")


async def _handle_join_room(
    websocket: WebSocket,
    peer_id: str,
    data: dict,
    current_room: Optional[str],
    nickname: Optional[str],
    on_transcript
):
    """방 입장 처리."""
    join_data = data.get("data", {})
    room_name = join_data.get("room_name")
    nickname = join_data.get("nickname", "Anonymous")
    phone_number = join_data.get("phone_number")
    agent_code = join_data.get("agent_code")

    logger.debug(f"[join_room] room={room_name}, nickname={nickname}, agent_code={agent_code}")

    if not room_name:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "Room name is required"}
        })
        return

    # 고객 정보 조회
    customer_info = None
    consultation_history = []
    if phone_number:
        customer_repo = CustomerRepository()
        logger.info(f"[고객조회] 시작 - name='{nickname}', phone='{phone_number}'")
        try:
            customer_info = await customer_repo.find_customer(nickname, phone_number)
            logger.info(f"[고객조회] 결과 - customer_info={customer_info is not None}")
        except Exception as e:
            logger.error(f"[고객조회] 예외 발생 - {e}")
            customer_info = None

        if customer_info:
            logger.info(f"고객 발견: '{nickname}' ({phone_number})")
            _room_manager.set_customer_info(room_name, customer_info, [])

            try:
                consultation_history = await customer_repo.get_consultation_history(
                    customer_info['customer_id']
                )
                logger.info(f"고객의 상담 이력 {len(consultation_history)}건 발견")
                if consultation_history:
                    _room_manager.set_customer_info(room_name, customer_info, consultation_history)
            except Exception as e:
                logger.error(f"상담 이력 조회 실패: {e}")

    # 상담사 정보 조회
    agent_info = None
    if agent_code:
        agent_repo = get_agent_repository()
        logger.info(f"상담사 조회: code='{agent_code}', name='{nickname}'")
        agent_info = await agent_repo.find_agent(agent_code, nickname)
        if agent_info:
            _room_manager.set_agent_info(room_name, agent_info)
            logger.info(f"상담사 식별 완료: '{nickname}' ({agent_code})")
        else:
            logger.warning(f"상담사를 찾을 수 없음: '{nickname}' ({agent_code})")
            await websocket.send_json({
                "type": "error",
                "data": {"message": f"등록되지 않은 상담사입니다: {agent_code}"}
            })
            return

    # 방 입장
    is_customer = phone_number is not None
    _room_manager.join_room(room_name, peer_id, nickname, websocket, is_customer=is_customer)

    # 에이전트 생성
    if room_name == "stt-comparison-room":
        agent = None
    else:
        logger.info(f"방 '{room_name}'의 에이전트 생성/조회 중")
        agent = get_or_create_agent(room_name)

    # 에이전트 준비 및 세션 시작
    if agent is not None:
        if agent_info:
            room_db_id = _room_manager.room_db_ids.get(room_name)
            if room_db_id is None:
                for _ in range(10):
                    await asyncio.sleep(0.1)
                    room_db_id = _room_manager.room_db_ids.get(room_name)
                    if room_db_id:
                        break

            session_customer_id = None
            session_customer_info, session_consultation_history = _room_manager.get_customer_info(room_name)
            if session_customer_info:
                session_customer_id = session_customer_info.get('customer_id')
                agent.set_customer_context(session_customer_info, session_consultation_history)
                logger.info(f"[세션] 기존 고객 정보 발견 - customer_id={session_customer_id}")

            session_id = await agent.start_session(
                agent_name=nickname,
                room_id=room_db_id,
                agent_id=str(agent_info.get('agent_id')),
                customer_id=session_customer_id
            )
            logger.info(f"Started consultation session: session_id={session_id}")

        await broadcast_to_room(
            room_name,
            {
                "type": "agent_ready",
                "data": {"llm_available": agent.llm_available}
            }
        )

    # 방의 다른 피어 조회
    other_peers = _room_manager.get_other_peers(room_name, peer_id)

    # 상담사인 경우 기존 고객 정보 조회
    existing_customer_info = None
    existing_consultation_history = []
    if not is_customer:
        existing_customer_info, existing_consultation_history = _room_manager.get_customer_info(room_name)

    # 방 입장 확인 전송
    room_joined_data = {
        "room_name": room_name,
        "peer_count": _room_manager.get_room_count(room_name),
        "other_peers": [
            {"peer_id": p.peer_id, "nickname": p.nickname}
            for p in other_peers
        ]
    }
    if existing_customer_info:
        room_joined_data["customer_info"] = existing_customer_info
    if existing_consultation_history:
        room_joined_data["consultation_history"] = existing_consultation_history

    await websocket.send_json({
        "type": "room_joined",
        "data": room_joined_data
    })

    # 다른 피어들에게 알림
    user_joined_data = {
        "peer_id": peer_id,
        "nickname": nickname,
        "peer_count": _room_manager.get_room_count(room_name)
    }
    if is_customer:
        user_joined_data["phone_number"] = phone_number
    if customer_info:
        user_joined_data["customer_info"] = customer_info
    if consultation_history:
        user_joined_data["consultation_history"] = consultation_history

    await broadcast_to_room(
        room_name,
        {"type": "user_joined", "data": user_joined_data},
        exclude=[peer_id]
    )

    # 에이전트에 고객 컨텍스트 설정
    if agent and customer_info:
        agent.set_customer_context(customer_info, consultation_history)
        if agent.session_id and customer_info.get('customer_id'):
            await agent.update_session_customer(customer_info['customer_id'])
            logger.info(f"[세션] 고객 연결 완료 - session={agent.session_id}")

    logger.info(f"피어 {nickname} ({peer_id})가 방 '{room_name}'에 입장함")


async def _handle_offer(websocket: WebSocket, peer_id: str, current_room: Optional[str], data: dict):
    """WebRTC offer 처리."""
    if not current_room:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "Not in a room"}
        })
        return

    offer = data.get("data")
    logger.info(f"피어 {peer_id}로부터 offer 수신")

    try:
        other_peers = _room_manager.get_other_peers(current_room, peer_id)
        other_peer_ids = [p.peer_id for p in other_peers]

        answer = await _peer_manager.handle_offer(
            peer_id, current_room, offer, other_peer_ids
        )

        await websocket.send_json({
            "type": "answer",
            "data": answer
        })
        logger.info(f"피어 {peer_id}에게 answer 전송 완료")
    except Exception as e:
        logger.error(f"피어 {peer_id}의 offer 처리 중 오류: {e}")
        await websocket.send_json({
            "type": "error",
            "data": {"message": str(e)}
        })


async def _handle_ice_candidate(websocket: WebSocket, peer_id: str, current_room: Optional[str], data: dict):
    """ICE candidate 처리."""
    if not current_room:
        await websocket.send_json({
            "type": "error",
            "data": {"message": "Not in a room"}
        })
        return

    candidate_data = data.get("data")
    logger.info(f"피어 {peer_id[:8]}로부터 ICE candidate 수신")

    pc = _peer_manager.get_peer_connection(peer_id)
    if pc and candidate_data:
        try:
            from aiortc.sdp import candidate_from_sdp

            inner_candidate = candidate_data.get("candidate", {})
            if isinstance(inner_candidate, dict):
                candidate_str = inner_candidate.get("candidate", "")
                sdp_mid = inner_candidate.get("sdpMid")
                sdp_mline_index = inner_candidate.get("sdpMLineIndex")
            else:
                candidate_str = candidate_data.get("candidate", "")
                sdp_mid = candidate_data.get("sdpMid")
                sdp_mline_index = candidate_data.get("sdpMLineIndex")

            if candidate_str.startswith("candidate:"):
                candidate_str = candidate_str[10:]

            ice_candidate = candidate_from_sdp(candidate_str)
            ice_candidate.sdpMid = sdp_mid
            ice_candidate.sdpMLineIndex = sdp_mline_index

            await pc.addIceCandidate(ice_candidate)
            logger.info(f"피어 {peer_id[:8]}에 ICE candidate 추가 완료")
        except Exception as e:
            logger.error(f"ICE candidate 추가 실패: {e}")

    await broadcast_to_room(
        current_room,
        {"type": "ice_candidate", "data": candidate_data},
        exclude=[peer_id]
    )


async def _handle_end_session(websocket: WebSocket, current_room: Optional[str]):
    """상담 세션 종료 처리."""
    if not current_room:
        await websocket.send_json({
            "type": "session_ended",
            "data": {
                "success": True,
                "session_id": None,
                "transcript_count": 0,
                "message": "상담 방에 참여하고 있지 않습니다"
            }
        })
        return

    logger.info(f"방 '{current_room}'의 세션 종료 처리 중")
    try:
        agent = room_agents.get(current_room)
        if agent and agent.session_id:
            conversation_history = agent.state.get("conversation_history", [])
            transcript_count = len(conversation_history)

            success = await agent.end_session()
            logger.info(f"방 '{current_room}' 세션 종료: success={success}")

            await websocket.send_json({
                "type": "session_ended",
                "data": {
                    "success": success,
                    "session_id": str(agent.session_id) if agent.session_id else None,
                    "transcript_count": transcript_count,
                    "message": f"상담 세션이 저장되었습니다 (대화 {transcript_count}턴)" if success else "세션 저장에 실패했습니다"
                }
            })
        else:
            await websocket.send_json({
                "type": "session_ended",
                "data": {
                    "success": True,
                    "session_id": None,
                    "transcript_count": 0,
                    "message": "저장할 세션이 없습니다"
                }
            })
    except Exception as e:
        logger.error(f"방 '{current_room}' 세션 종료 중 오류: {e}")
        await websocket.send_json({
            "type": "session_ended",
            "data": {
                "success": False,
                "session_id": None,
                "transcript_count": 0,
                "message": f"오류: {str(e)}"
            }
        })


async def _handle_leave_room(peer_id: str, current_room: str, nickname: Optional[str]):
    """방 퇴장 처리."""
    await broadcast_to_room(
        current_room,
        {
            "type": "user_left",
            "data": {
                "peer_id": peer_id,
                "nickname": nickname,
                "peer_count": _room_manager.get_room_count(current_room) - 1
            }
        },
        exclude=[peer_id]
    )

    _room_manager.leave_room(peer_id)
    await _peer_manager.close_peer_connection(peer_id)
    logger.info(f"피어 {nickname} ({peer_id})가 방 '{current_room}'에서 퇴장함")
