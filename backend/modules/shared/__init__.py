"""Shared DTOs and type definitions used across services.

Only lightweight, common data models should live here. Do not place
service-specific logic or heavy dependencies (e.g., pgvector, LangGraph)
in this package.
"""

from .dto import SummaryResult

__all__ = [
    "SummaryResult",
]
