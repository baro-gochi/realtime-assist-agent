"""Shared Pydantic schemas for agent structured outputs."""
from typing import List
from pydantic import BaseModel, Field, ConfigDict


class AgentBaseModel(BaseModel):
    """Base model for structured outputs (forbid unknown fields)."""

    model_config = ConfigDict(extra="forbid")


class SummaryResult(AgentBaseModel):
    """실시간 대화 요약 결과."""

    summary: str = Field(default="", description="한 문장 핵심 요약")
    customer_issue: str = Field(default="", description="고객 문의 요약")
    agent_action: str = Field(default="", description="상담원 조치 요약")


class IntentResult(AgentBaseModel):
    """의도 분석 결과."""

    intent_label: str = Field(..., description="핵심 의도 라벨")
    intent_confidence: float = Field(default=0.0, description="의도 확신도 (0~1)")
    intent_explanation: str = Field(default="", description="의도 판단 근거")


class SentimentResult(AgentBaseModel):
    """감정 분석 결과."""

    sentiment_label: str = Field(..., description="감정 라벨")
    sentiment_score: float = Field(default=0.0, description="감정 강도 (0~1)")
    sentiment_explanation: str = Field(default="", description="감정 판단 근거")


class DraftReplyResult(AgentBaseModel):
    """응답 초안 생성 결과."""

    short_reply: str = Field(..., description="짧은 응답 초안 1-2문장")
    keywords: List[str] = Field(default_factory=list, description="응답에 포함할 키워드")


class RiskResult(AgentBaseModel):
    """위험 감지 결과."""

    risk_flags: List[str] = Field(default_factory=list, description="감지된 위험 플래그")
    risk_explanation: str = Field(default="", description="위험 판단 근거")


class FinalStep(AgentBaseModel):
    """최종 상담 요약의 단계별 진행 내용."""

    order: int = Field(..., description="순서 번호")
    action: str = Field(..., description="수행된 조치/진행 내용")


class FinalConsultationSummary(AgentBaseModel):
    """상담 종료 시 최종 구조화 요약."""

    consultation_type: str = Field(default="", description="상담 유형")
    customer_issue: str = Field(default="", description="고객 문의/이슈")
    steps: List[FinalStep] = Field(default_factory=list, description="상담 진행 과정")
    resolution: str = Field(default="", description="최종 해결 결과 또는 후속 조치")
    customer_sentiment: str = Field(default="", description="상담 종료 시 감정 상태")
