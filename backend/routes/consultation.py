"""상담 이력 조회 API 라우터.

고객 상담 세션, 전사, 분석 결과 조회 엔드포인트들을 제공합니다.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from modules import (
    get_session_repository,
    get_transcript_repository,
    get_agent_result_repository,
)
from .deps import verify_auth_header

router = APIRouter(prefix="/api/consultation", tags=["consultation"])


@router.get("/sessions/{customer_id}")
async def get_customer_sessions(
    customer_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    _: bool = Depends(verify_auth_header)
):
    """고객의 상담 세션 목록을 조회합니다.

    Args:
        customer_id: 고객 ID
        limit: 조회 개수 제한 (기본값: 10, 최대: 50)

    Returns:
        dict: 세션 목록
    """
    session_repo = get_session_repository()
    sessions = await session_repo.get_customer_sessions(customer_id, limit)

    # datetime 객체를 문자열로 변환
    for session in sessions:
        for key in ['started_at', 'ended_at', 'created_at']:
            if session.get(key):
                session[key] = str(session[key])

    return {"sessions": sessions, "count": len(sessions)}


@router.get("/session/{session_id}/transcripts")
async def get_session_transcripts(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: bool = Depends(verify_auth_header)
):
    """세션의 전사 목록을 조회합니다.

    Args:
        session_id: 세션 UUID
        limit: 조회 개수 제한 (기본값: 100)
        offset: 시작 위치 (기본값: 0)

    Returns:
        dict: 전사 목록
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    transcript_repo = get_transcript_repository()
    transcripts = await transcript_repo.get_session_transcripts(session_uuid, limit, offset)

    # timestamp를 문자열로 변환
    for transcript in transcripts:
        if transcript.get('timestamp'):
            transcript['timestamp'] = str(transcript['timestamp'])

    return {"transcripts": transcripts, "count": len(transcripts)}


@router.get("/session/{session_id}/results")
async def get_session_agent_results(
    session_id: str,
    result_type: str = Query(default=None, description="결과 타입 필터 (intent, sentiment, summary, rag, faq)"),
    _: bool = Depends(verify_auth_header)
):
    """세션의 에이전트 결과를 조회합니다.

    Args:
        session_id: 세션 UUID
        result_type: 결과 타입 필터 (선택)

    Returns:
        dict: 에이전트 결과 목록
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    result_repo = get_agent_result_repository()
    results = await result_repo.get_session_results(session_uuid, result_type)

    # datetime, UUID 객체를 문자열로 변환
    for result in results:
        if result.get('created_at'):
            result['created_at'] = str(result['created_at'])
        if result.get('result_id'):
            result['result_id'] = str(result['result_id'])
        if result.get('turn_id'):
            result['turn_id'] = str(result['turn_id'])

    return {"results": results, "count": len(results)}


@router.get("/history/{session_id}")
async def get_consultation_history_detail(
    session_id: str,
    _: bool = Depends(verify_auth_header)
):
    """상담 이력 상세 정보를 조회합니다.

    세션 기본 정보, 대화 내용, AI 분석 결과를 통합하여 반환합니다.

    Args:
        session_id: 세션 UUID

    Returns:
        dict: 상담 이력 상세 정보
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session ID format")

    # 세션 기본 정보 조회
    session_repo = get_session_repository()
    session_info = await session_repo.get_session(session_uuid)
    if not session_info:
        raise HTTPException(status_code=404, detail="Session not found")

    # 대화 내용 조회
    transcript_repo = get_transcript_repository()
    transcripts = await transcript_repo.get_session_transcripts(session_uuid, limit=200)

    # AI 분석 결과 조회
    result_repo = get_agent_result_repository()
    analysis_results = await result_repo.get_session_results(session_uuid)

    # 상담 시간 계산
    duration = None
    if session_info.get('started_at') and session_info.get('ended_at'):
        try:
            started = session_info['started_at']
            ended = session_info['ended_at']
            if hasattr(started, 'timestamp') and hasattr(ended, 'timestamp'):
                diff_seconds = int((ended - started).total_seconds())
                minutes = diff_seconds // 60
                seconds = diff_seconds % 60
                duration = f"{minutes}분 {seconds}초"
        except Exception:
            pass

    # datetime/UUID 변환
    for transcript in transcripts:
        if transcript.get('timestamp'):
            ts = transcript['timestamp']
            if hasattr(ts, 'strftime'):
                transcript['timestamp'] = ts.strftime('%H:%M:%S')
            else:
                transcript['timestamp'] = str(ts)
        # speaker_type -> speaker_role 통일
        if 'speaker_type' in transcript:
            transcript['speaker_role'] = transcript.pop('speaker_type')

    for result in analysis_results:
        if result.get('created_at'):
            result['created_at'] = str(result['created_at'])
        if result.get('result_id'):
            result['result_id'] = str(result['result_id'])

    return {
        "session_id": session_id,
        "consultation_date": str(session_info.get('started_at', ''))[:19].replace('T', ' ') if session_info.get('started_at') else None,
        "consultation_type": session_info.get('consultation_type'),
        "agent_name": session_info.get('agent_name'),
        "customer_name": session_info.get('customer_name'),
        "duration": duration,
        "final_summary": session_info.get('final_summary'),
        "status": session_info.get('status'),
        "transcripts": transcripts,
        "analysis_results": analysis_results
    }
