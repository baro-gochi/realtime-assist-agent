"""Lightweight shared DTOs for cross-service communication."""

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    """Structured summary output used by the real-time summarization agent."""

    summary: str = Field(default="", description="한 문장 핵심 요약")
    customer_issue: str = Field(default="", description="고객 문의 요약")
    agent_action: str = Field(default="", description="상담원 조치 요약")
