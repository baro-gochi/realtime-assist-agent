"""상담사 관리 API 라우터.

상담사 등록, 로그인, 세션 조회 엔드포인트들을 제공합니다.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from modules import get_agent_repository
from .deps import verify_auth_header

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRegisterRequest(BaseModel):
    """상담사 등록 요청 모델."""
    agent_code: str
    agent_name: str


class AgentLoginRequest(BaseModel):
    """상담사 로그인 요청 모델."""
    agent_code: str
    agent_name: str


@router.post("/register")
async def register_agent(
    request: AgentRegisterRequest,
    _: bool = Depends(verify_auth_header)
):
    """새로운 상담사를 등록합니다.

    Args:
        request: 상담사 등록 요청
            - agent_code: 상담사 코드 (사번)
            - agent_name: 상담사 이름

    Returns:
        dict: 등록 결과
    """
    if not request.agent_code or not request.agent_name:
        raise HTTPException(status_code=400, detail="상담사 코드와 이름을 모두 입력해주세요")

    agent_repo = get_agent_repository()
    agent_id = await agent_repo.register_agent(request.agent_code, request.agent_name)

    if agent_id is None:
        raise HTTPException(status_code=400, detail="이미 등록된 상담사 코드이거나 등록에 실패했습니다")

    return {
        "success": True,
        "agent_id": agent_id,
        "agent_code": request.agent_code,
        "agent_name": request.agent_name,
        "message": "상담사 등록이 완료되었습니다"
    }


@router.post("/login")
async def agent_login(
    request: AgentLoginRequest,
    _: bool = Depends(verify_auth_header)
):
    """상담사 로그인 (코드와 이름으로 조회).

    Args:
        request: 로그인 요청
            - agent_code: 상담사 코드 (사번)
            - agent_name: 상담사 이름

    Returns:
        dict: 상담사 정보
    """
    if not request.agent_code or not request.agent_name:
        raise HTTPException(status_code=400, detail="상담사 코드와 이름을 모두 입력해주세요")

    agent_repo = get_agent_repository()
    agent = await agent_repo.find_agent(request.agent_code, request.agent_name)

    if agent is None:
        raise HTTPException(status_code=404, detail="등록되지 않은 상담사이거나 정보가 일치하지 않습니다")

    # datetime 변환
    if agent.get('created_at'):
        agent['created_at'] = str(agent['created_at'])

    return {
        "success": True,
        "agent": agent
    }


@router.get("/{agent_id}/sessions")
async def get_agent_sessions(
    agent_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    _: bool = Depends(verify_auth_header)
):
    """상담사의 상담 세션 목록을 조회합니다.

    Args:
        agent_id: 상담사 DB ID
        limit: 조회 개수 제한 (기본값: 20, 최대: 100)

    Returns:
        dict: 세션 목록
    """
    agent_repo = get_agent_repository()

    # 상담사 존재 확인
    agent = await agent_repo.get_agent_by_id(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="상담사를 찾을 수 없습니다")

    sessions = await agent_repo.get_agent_sessions(agent_id, limit)

    return {
        "agent": {
            "agent_id": agent['agent_id'],
            "agent_code": agent['agent_code'],
            "agent_name": agent['agent_name']
        },
        "sessions": sessions,
        "count": len(sessions)
    }
