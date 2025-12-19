"""
graph_experimental.py 구조 변경 테스트 스크립트

DB 연결 없이 그래프 구조만 테스트합니다.
RAG/FAQ 노드는 모킹 처리됩니다.

사용법 (backend 디렉토리에서 실행):
    # 시나리오 모드 (기본)
    uv run python test/test_graph_experimental.py --scenario

    # 시나리오 타입 선택
    uv run python test/test_graph_experimental.py --scenario -t pass
    uv run python test/test_graph_experimental.py --scenario -t cancel

    # 대화형 모드
    uv run python test/test_graph_experimental.py

    # 딜레이 없이 빠른 실행
    uv run python test/test_graph_experimental.py --scenario --no-delay
"""

import asyncio
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import patch, AsyncMock

# backend 모듈 import를 위한 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from backend.modules.agent.agents import create_agent_graph, ContextSchema
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def format_message(msg: BaseMessage) -> str:
    """메시지 객체를 읽기 쉬운 문자열로 변환"""
    msg_type = type(msg).__name__
    content = msg.content
    if len(content) > 100:
        content = content[:100] + "..."
    return f"[{msg_type}] {content}"


def print_messages(messages: List[BaseMessage], title: str = "Messages"):
    """MessagesState의 messages 리스트 출력"""
    print(f"\n\033[96m[{title}] ({len(messages)}개)\033[0m")
    if not messages:
        print("  (비어있음)")
        return
    for i, msg in enumerate(messages):
        msg_type = type(msg).__name__
        # 색상 지정
        if isinstance(msg, SystemMessage):
            color = "\033[90m"  # 회색
        elif isinstance(msg, HumanMessage):
            color = "\033[92m"  # 초록
        elif isinstance(msg, AIMessage):
            color = "\033[94m"  # 파랑
        else:
            color = "\033[0m"
        reset = "\033[0m"

        content = msg.content
        if len(content) > 80:
            content = content[:80] + "..."
        print(f"  {color}[{i+1}] {msg_type}: {content}{reset}")


# 기본 테스트 시나리오 (요금 관련)
DEFAULT_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요, KT 고객센터입니다. 무엇을 도와드릴까요?"},
    {"speaker": "고객", "text": "이번 달 요금이 평소보다 많이 나온 것 같아서요. 문자에 89000원이라고 찍혔는데 왜 이 가격이죠?"},
    {"speaker": "상담사", "text": "네, 요금 관련해서 확인해드리겠습니다. 혹시 지금 사용하고 계신 요금제가 어떤 건지 아시나요?"},
    {"speaker": "고객", "text": "5G 슈퍼플랜 베이직인 것 같은데... 원래 7만원대였거든요. 근데 갑자기 왜 올랐죠?"},
]

# PASS 앱 관련 시나리오
PASS_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요, KT 고객센터입니다. 무엇을 도와드릴까요?"},
    {"speaker": "고객", "text": "PASS 앱에서 이상한 알림이 왔는데요"},
    {"speaker": "상담사", "text": "네, 어떤 알림인지 말씀해주시겠어요?"},
    {"speaker": "고객", "text": "본인확인 요청이라고 뜨는데 제가 요청한 적이 없어서 해킹당한건 아닌지 너무 걱정돼요."},
]

# 해지/위약금 관련 시나리오
CANCELLATION_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요, 해지하고 싶어서 전화했어요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요. 해지 관련 문의시네요. 혹시 어떤 이유로 해지를 원하시는지 여쭤봐도 될까요?"},
    {"speaker": "고객", "text": "다른 통신사가 더 저렴해서요. 지금 얼마나 위약금이 나오나요?"},
]

SCENARIO_MAP = {
    "default": DEFAULT_SCENARIO,
    "billing": DEFAULT_SCENARIO,
    "pass": PASS_SCENARIO,
    "cancel": CANCELLATION_SCENARIO,
    "cancellation": CANCELLATION_SCENARIO,
}


def calculate_delay(text: str) -> float:
    """발화 길이에 따른 딜레이 계산 (초)"""
    length = len(text)
    if length < 20:
        return 0.5
    elif length < 50:
        return 1.0
    elif length < 100:
        return 1.5
    else:
        return 2.0


def print_divider(char: str = "=", width: int = 60):
    print(char * width)


def print_node_result(node_name: str, data: Dict[str, Any], elapsed_ms: int = 0):
    """노드 결과를 보기 좋게 출력"""
    color_codes = {
        "summarize": "\033[94m",   # 파랑
        "intent": "\033[92m",      # 초록
        "sentiment": "\033[93m",   # 노랑
        "draft_reply": "\033[95m", # 보라
        "risk": "\033[91m",        # 빨강
        "rag_policy": "\033[96m",  # 시안
        "faq_search": "\033[90m",  # 회색
    }
    reset = "\033[0m"
    color = color_codes.get(node_name, "")

    print(f"\n{color}[{node_name}] ({elapsed_ms}ms){reset}")

    if data is None:
        return

    if node_name == "summarize":
        sr = data.get("summary_result", {})
        if sr:
            print(f"  요약: {sr.get('summary', '-')}")
            print(f"  고객문의: {sr.get('customer_issue', '-')}")
            print(f"  상담사대응: {sr.get('agent_action', '-')}")

    elif node_name == "intent":
        ir = data.get("intent_result", {})
        if ir:
            print(f"  의도: {ir.get('intent_label', '-')}")
            print(f"  확신도: {ir.get('intent_confidence', '-')}")
            print(f"  근거: {ir.get('intent_explanation', '-')}")

    elif node_name == "rag_policy":
        rp = data.get("rag_policy_result", {})
        if rp:
            skipped = rp.get("skipped", False)
            if skipped:
                print(f"  [SKIPPED] 의도: {rp.get('intent_label', '-')}")
                print(f"  스킵 사유: {rp.get('skip_reason', '-')}")
            else:
                print(f"  [MOCKED] 의도: {rp.get('intent_label', '-')}")
                print(f"  (DB 없이 테스트 중 - RAG 검색 모킹됨)")

    elif node_name == "faq_search":
        fq = data.get("faq_result", {})
        if fq:
            skipped = fq.get("skipped", False)
            if skipped:
                print(f"  [SKIPPED] 쿼리: {fq.get('query', '-')[:30]}...")
                print(f"  스킵 사유: {fq.get('skip_reason', '-')}")
            else:
                print(f"  [MOCKED] (DB 없이 테스트 중 - FAQ 검색 모킹됨)")

    elif node_name == "sentiment":
        sr = data.get("sentiment_result", {})
        if sr:
            print(f"  감정: {sr.get('sentiment_label', '-')}")
            print(f"  강도: {sr.get('sentiment_score', '-')}")
            print(f"  근거: {sr.get('sentiment_explanation', '-')}")

    elif node_name == "draft_reply":
        dr = data.get("draft_replies", {})
        if dr:
            print(f"  짧은응답: {dr.get('short_reply', '-')}")
            keywords = dr.get('keywords', [])
            print(f"  키워드: {', '.join(keywords) if keywords else '-'}")

    elif node_name == "risk":
        rr = data.get("risk_result", {})
        if rr:
            flags = rr.get("risk_flags", [])
            print(f"  위험플래그: {flags if flags else '없음'}")
            if rr.get("risk_explanation"):
                print(f"  설명: {rr.get('risk_explanation', '-')}")


# RAG/FAQ 모킹용 함수
async def mock_rag_policy_search(*args, **kwargs):
    """RAG 정책 검색 모킹"""
    from dataclasses import dataclass

    @dataclass
    class MockRAGResult:
        intent_label: str = "모킹된 의도"
        query: str = ""
        searched_classifications: list = None
        recommendations: list = None
        search_context: str = ""

        def __post_init__(self):
            if self.searched_classifications is None:
                self.searched_classifications = []
            if self.recommendations is None:
                self.recommendations = []

        def to_dict(self):
            return {
                "intent_label": self.intent_label,
                "query": self.query,
                "searched_classifications": self.searched_classifications,
                "recommendations": self.recommendations,
                "search_context": self.search_context,
            }

    return MockRAGResult(
        intent_label=kwargs.get("intent_label", "테스트"),
        query=kwargs.get("customer_query", ""),
    )


class MockFAQService:
    """FAQ 서비스 모킹"""
    is_initialized = True

    async def initialize(self):
        pass

    async def semantic_search(self, query: str, **kwargs):
        from dataclasses import dataclass

        @dataclass
        class MockFAQResult:
            cache_hit: bool = False
            similarity_score: float = 0.0
            cached_query: str = ""
            search_time_ms: int = 0
            faqs: list = None

            def __post_init__(self):
                if self.faqs is None:
                    self.faqs = []

        return MockFAQResult()


class GraphExperimentalTester:
    """graph_experimental.py 테스트 클래스 (DB 연결 없음)"""

    def __init__(self, model: str = "gpt-4o-mini", output_file: Optional[str] = None):
        print(f"LLM 초기화 중... (model: {model})")
        self.output_file = output_file
        self.results_log: List[Dict[str, Any]] = []

        self.llm = ChatOpenAI(model=model, temperature=0)
        self.graph = create_agent_graph(self.llm)

        # 정적 시스템 프롬프트
        static_system_prefix = """## 고객 정보
- 고객명: 테스트 고객
- 요금제: KT 5G 프리미어
- 등급: VIP
- 가입기간: 3년

## 상담 이력
- 최근 상담 없음"""

        self.context = ContextSchema(static_system_prefix=static_system_prefix)

        # 테스트용 고객 정보
        test_customer_info = {
            "customer_name": "테스트 고객",
            "phone_number": "010-1234-5678",
            "age": 35,
            "gender": "남",
            "residence": "서울시 강남구",
            "membership_grade": "Gold",
            "current_plan": "5G 슈퍼플랜 베이직",
            "monthly_fee": 69000,
            "current_data_gb": 11,
            "contract_status": "약정 4개월 남음",
            "bundle_info": "없음",
        }

        # 상태 초기화 (MessagesState의 messages 포함)
        self.state = {
            "messages": [],  # MessagesState의 messages 필드
            "room_name": "test_experimental",
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,
            "summary_result": None,
            "customer_info": test_customer_info,
            "consultation_history": [],
            "intent_result": None,
            "sentiment_result": None,
            "draft_replies": None,
            "risk_result": None,
            "rag_policy_result": None,
            "faq_result": None,
            "has_new_customer_turn": False,
            "last_intent_index": 0,
            "last_sentiment_index": 0,
            "last_draft_index": 0,
            "last_risk_index": 0,
            "last_rag_index": 0,
            "last_faq_index": 0,
            "last_rag_intent": "",
            "last_faq_query": "",
        }

        print("그래프 초기화 완료!")
        print(f"테스트 고객: {test_customer_info['customer_name']}, "
              f"요금제: {test_customer_info['current_plan']}\n")

    def add_utterance(self, speaker: str, text: str):
        """대화에 발화 추가"""
        is_customer = speaker in ["고객", "customer", "user"]
        self.state["conversation_history"].append({
            "speaker_name": speaker,
            "speaker_id": "customer" if is_customer else "agent",
            "text": text,
            "timestamp": time.time(),
            "is_customer": is_customer,
        })
        if is_customer:
            self.state["has_new_customer_turn"] = True

    async def run_graph(self, utterance_info: Optional[Dict] = None):
        """그래프 실행 (RAG/FAQ 모킹)"""
        print_divider("-", 60)
        print("그래프 실행 중...")

        results = {}
        node_timings = {}
        graph_start = time.perf_counter()

        # RAG/FAQ 모킹 패치
        with patch("modules.agent.graph_experimental.create_rag_policy_node") as mock_rag, \
             patch("modules.agent.graph_experimental.create_faq_search_node") as mock_faq:

            # RAG 노드 모킹
            async def mocked_rag_node(state, runtime):
                intent_result = state.get("intent_result", {})
                intent_label = intent_result.get("intent_label", "")
                return {
                    "rag_policy_result": {
                        "skipped": True,
                        "skip_reason": "DB 없이 테스트 중 (모킹됨)",
                        "intent_label": intent_label,
                    },
                    "last_rag_index": len(state.get("conversation_history", [])),
                }

            # FAQ 노드 모킹
            async def mocked_faq_node(state, runtime):
                return {
                    "faq_result": {
                        "skipped": True,
                        "skip_reason": "DB 없이 테스트 중 (모킹됨)",
                        "query": "",
                    },
                    "last_faq_index": len(state.get("conversation_history", [])),
                }

            mock_rag.return_value = mocked_rag_node
            mock_faq.return_value = mocked_faq_node

            # 그래프 재생성 (모킹된 노드 사용)
            graph = create_agent_graph(self.llm)

            async for update in graph.astream(
                self.state,
                context=self.context,
                stream_mode="updates"
            ):
                for node_name, data in update.items():
                    now = time.perf_counter()
                    if node_name not in node_timings:
                        node_timings[node_name] = now - graph_start
                    elapsed_ms = int(node_timings[node_name] * 1000)

                    results[node_name] = data
                    print_node_result(node_name, data, elapsed_ms)

                    # 상태 업데이트
                    self._update_state(node_name, data)

        # messages 상태 출력
        if self.state.get("messages"):
            print_messages(self.state["messages"], "MessagesState.messages")

        print_divider("-", 60)
        self.state["has_new_customer_turn"] = False

        # 결과 로그에 추가
        if self.output_file and utterance_info:
            log_entry = {
                "utterance": utterance_info,
                "results": {
                    "summarize": results.get("summarize", {}).get("summary_result"),
                    "intent": results.get("intent", {}).get("intent_result"),
                    "sentiment": results.get("sentiment", {}).get("sentiment_result"),
                    "draft_reply": results.get("draft_reply", {}).get("draft_replies"),
                    "risk": results.get("risk", {}).get("risk_result"),
                    "rag_policy": results.get("rag_policy", {}).get("rag_policy_result"),
                    "faq_search": results.get("faq_search", {}).get("faq_result"),
                },
                "messages_count": len(self.state.get("messages", [])),
            }
            self.results_log.append(log_entry)

        return results

    def _update_state(self, node_name: str, data: Dict[str, Any]):
        """노드 결과로 상태 업데이트"""
        # messages 업데이트 (MessagesState)
        if "messages" in data:
            # messages는 append 방식으로 업데이트될 수 있음
            if isinstance(data["messages"], list):
                self.state["messages"] = data["messages"]

        if node_name == "summarize":
            if "summary_result" in data:
                self.state["summary_result"] = data["summary_result"]
            if "current_summary" in data:
                self.state["current_summary"] = data["current_summary"]
            if "last_summarized_index" in data:
                self.state["last_summarized_index"] = data["last_summarized_index"]

        elif node_name == "intent":
            if "intent_result" in data:
                self.state["intent_result"] = data["intent_result"]
            if "last_intent_index" in data:
                self.state["last_intent_index"] = data["last_intent_index"]

        elif node_name == "sentiment":
            if "sentiment_result" in data:
                self.state["sentiment_result"] = data["sentiment_result"]
            if "last_sentiment_index" in data:
                self.state["last_sentiment_index"] = data["last_sentiment_index"]

        elif node_name == "draft_reply":
            if "draft_replies" in data:
                self.state["draft_replies"] = data["draft_replies"]
            if "last_draft_index" in data:
                self.state["last_draft_index"] = data["last_draft_index"]

        elif node_name == "risk":
            if "risk_result" in data:
                self.state["risk_result"] = data["risk_result"]
            if "last_risk_index" in data:
                self.state["last_risk_index"] = data["last_risk_index"]

        elif node_name == "rag_policy":
            if "rag_policy_result" in data:
                self.state["rag_policy_result"] = data["rag_policy_result"]
            if "last_rag_index" in data:
                self.state["last_rag_index"] = data["last_rag_index"]

        elif node_name == "faq_search":
            if "faq_result" in data:
                self.state["faq_result"] = data["faq_result"]
            if "last_faq_index" in data:
                self.state["last_faq_index"] = data["last_faq_index"]

    async def run_scenario(self, scenario: List[Dict[str, str]], auto_delay: bool = True):
        """시나리오 모드 실행"""
        print_divider()
        print("시나리오 모드 시작 (graph_experimental.py)")
        print(f"총 {len(scenario)}개의 발화")
        print_divider()

        for i, utterance in enumerate(scenario):
            speaker = utterance["speaker"]
            text = utterance["text"]

            print(f"\n[{i+1}/{len(scenario)}] {speaker}: {text}")

            self.add_utterance(speaker, text)

            if auto_delay:
                delay = calculate_delay(text)
                print(f"  (대기 {delay}초...)")
                await asyncio.sleep(delay)

            utterance_info = {"index": i + 1, "speaker": speaker, "text": text}
            await self.run_graph(utterance_info)

            print_divider()

        print("\n시나리오 완료!")

        # 결과 파일 저장
        if self.output_file:
            self.save_results()

    def save_results(self):
        """결과를 TXT 파일로 저장"""
        output_path = Path(self.output_file)

        lines = []
        lines.append("=" * 80)
        lines.append("graph_experimental.py 테스트 결과")
        lines.append("=" * 80)
        lines.append(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"총 발화 수: {len(self.results_log)}")
        lines.append("=" * 80)
        lines.append("")

        for entry in self.results_log:
            utt = entry.get("utterance", {})
            results = entry.get("results", {})
            msg_count = entry.get("messages_count", 0)

            lines.append("-" * 80)
            lines.append(f"[{utt.get('index', '?')}] {utt.get('speaker', '?')}: {utt.get('text', '')}")
            lines.append(f"  (messages: {msg_count}개)")
            lines.append("-" * 80)

            # 요약
            summ = results.get("summarize") or {}
            lines.append(f"[요약]")
            lines.append(f"  요약: {summ.get('summary', '-')}")
            lines.append(f"  고객문의: {summ.get('customer_issue', '-')}")
            lines.append(f"  상담사대응: {summ.get('agent_action', '-')}")
            lines.append("")

            # 의도
            intent = results.get("intent") or {}
            lines.append(f"[의도]")
            lines.append(f"  의도: {intent.get('intent_label', '-')}")
            lines.append(f"  확신도: {intent.get('intent_confidence', '-')}")
            lines.append(f"  근거: {intent.get('intent_explanation', '-')}")
            lines.append("")

            # 감정
            sent = results.get("sentiment") or {}
            lines.append(f"[감정]")
            lines.append(f"  감정: {sent.get('sentiment_label', '-')}")
            lines.append(f"  강도: {sent.get('sentiment_score', '-')}")
            lines.append(f"  근거: {sent.get('sentiment_explanation', '-')}")
            lines.append("")

            # 응답 초안
            draft = results.get("draft_reply") or {}
            lines.append(f"[응답 초안]")
            lines.append(f"  짧은응답: {draft.get('short_reply', '-')}")
            keywords = draft.get('keywords', [])
            lines.append(f"  키워드: {', '.join(keywords) if keywords else '-'}")
            lines.append("")

            # 위험
            risk = results.get("risk") or {}
            flags = risk.get("risk_flags", [])
            lines.append(f"[위험]")
            lines.append(f"  위험플래그: {flags if flags else '없음'}")
            if risk.get("risk_explanation"):
                lines.append(f"  설명: {risk.get('risk_explanation', '-')}")
            lines.append("")

            # RAG
            rag = results.get("rag_policy") or {}
            lines.append(f"[RAG 정책]")
            if rag.get("skipped"):
                lines.append(f"  상태: SKIPPED")
                lines.append(f"  스킵 사유: {rag.get('skip_reason', '-')}")
            else:
                lines.append(f"  의도: {rag.get('intent_label', '-')}")
            lines.append("")

            # FAQ
            faq = results.get("faq_search") or {}
            lines.append(f"[FAQ]")
            if faq.get("skipped"):
                lines.append(f"  상태: SKIPPED")
                lines.append(f"  스킵 사유: {faq.get('skip_reason', '-')}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("테스트 완료")
        lines.append("=" * 80)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"\n결과 저장 완료: {output_path}")

    async def run_interactive(self):
        """대화형 모드"""
        print_divider()
        print("대화형 모드 시작 (graph_experimental.py)")
        print("명령어:")
        print("  /고객 <텍스트>  - 고객 발화 추가")
        print("  /상담사 <텍스트> - 상담사 발화 추가")
        print("  /history       - 현재 대화 히스토리 보기")
        print("  /messages      - MessagesState의 messages 보기")
        print("  /state         - 현재 상태 요약 보기")
        print("  /reset         - 대화 초기화")
        print("  /quit          - 종료")
        print_divider()

        while True:
            try:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                if user_input == "/quit":
                    print("종료합니다.")
                    break

                if user_input == "/history":
                    print("\n현재 대화 히스토리:")
                    for i, entry in enumerate(self.state["conversation_history"]):
                        print(f"  [{i+1}] {entry['speaker_name']}: {entry['text']}")
                    continue

                if user_input == "/messages":
                    print_messages(self.state.get("messages", []), "MessagesState.messages")
                    continue

                if user_input == "/state":
                    print("\n현재 상태:")
                    print(f"  대화 수: {len(self.state['conversation_history'])}")
                    print(f"  messages 수: {len(self.state.get('messages', []))}")
                    if self.state.get("intent_result"):
                        print(f"  의도: {self.state['intent_result'].get('intent_label', '-')}")
                    if self.state.get("sentiment_result"):
                        print(f"  감정: {self.state['sentiment_result'].get('sentiment_label', '-')}")
                    if self.state.get("summary_result"):
                        print(f"  요약: {self.state['summary_result'].get('summary', '-')[:50]}...")
                    continue

                if user_input == "/reset":
                    self.state["messages"] = []  # MessagesState 초기화
                    self.state["conversation_history"] = []
                    self.state["current_summary"] = ""
                    self.state["last_summarized_index"] = 0
                    self.state["summary_result"] = None
                    self.state["intent_result"] = None
                    self.state["sentiment_result"] = None
                    self.state["draft_replies"] = None
                    self.state["risk_result"] = None
                    self.state["rag_policy_result"] = None
                    self.state["faq_result"] = None
                    self.state["has_new_customer_turn"] = False
                    self.state["last_intent_index"] = 0
                    self.state["last_sentiment_index"] = 0
                    self.state["last_draft_index"] = 0
                    self.state["last_risk_index"] = 0
                    self.state["last_rag_index"] = 0
                    self.state["last_faq_index"] = 0
                    print("대화가 초기화되었습니다.")
                    continue

                if user_input.startswith("/고객 "):
                    text = user_input[4:].strip()
                    self.add_utterance("고객", text)
                    print(f"  추가됨: 고객: {text}")
                    await self.run_graph()
                    continue

                if user_input.startswith("/상담사 "):
                    text = user_input[5:].strip()
                    self.add_utterance("상담사", text)
                    print(f"  추가됨: 상담사: {text}")
                    await self.run_graph()
                    continue

                # 기본: 고객 발화로 처리
                self.add_utterance("고객", user_input)
                print(f"  추가됨: 고객: {user_input}")
                await self.run_graph()

            except KeyboardInterrupt:
                print("\n종료합니다.")
                break
            except Exception as e:
                print(f"오류 발생: {e}")
                import traceback
                traceback.print_exc()


def get_default_output_path() -> str:
    """기본 출력 파일 경로 생성"""
    test_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(test_dir / f"experimental_result_{timestamp}.txt")


async def main():
    parser = argparse.ArgumentParser(description="graph_experimental.py 테스트")
    parser.add_argument("--scenario", action="store_true", help="시나리오 모드 실행")
    parser.add_argument("--scenario-type", "-t", type=str, default="default",
                        choices=list(SCENARIO_MAP.keys()),
                        help="시나리오 타입 (default/billing, pass, cancel)")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="사용할 LLM 모델")
    parser.add_argument("--no-delay", action="store_true", help="딜레이 없이 실행")
    parser.add_argument("--output", "-o", type=str, help="결과 저장 파일 경로")
    parser.add_argument("--no-output", action="store_true", help="결과 파일 저장 안함")

    args = parser.parse_args()

    scenario = SCENARIO_MAP.get(args.scenario_type, DEFAULT_SCENARIO)

    # 출력 파일 설정
    output_file = None
    if not args.no_output and args.scenario:
        output_file = args.output if args.output else get_default_output_path()

    tester = GraphExperimentalTester(model=args.model, output_file=output_file)

    if args.scenario:
        print(f"시나리오 타입: {args.scenario_type}")
        await tester.run_scenario(scenario, auto_delay=not args.no_delay)
    else:
        await tester.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
