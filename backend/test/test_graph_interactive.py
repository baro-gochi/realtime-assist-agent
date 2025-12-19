"""
LangGraph 텍스트 기반 테스트 스크립트

사용법 (backend 디렉토리에서 실행):
    # 시나리오 모드 (기본 시나리오 - 요금 관련)
    uv run python test/test_graph_interactive.py --scenario

    # 시나리오 타입 선택 (billing/pass/cancel)
    uv run python test/test_graph_interactive.py --scenario -t pass
    uv run python test/test_graph_interactive.py --scenario -t cancel

    # 대화형 모드 (직접 입력)
    uv run python test/test_graph_interactive.py

    # 시나리오 파일 지정
    uv run python test/test_graph_interactive.py --scenario --file scenarios/pass_inquiry.json

    # 딜레이 없이 빠른 실행
    uv run python test/test_graph_interactive.py --scenario --no-delay

시나리오 타입:
    - default/billing: 요금 문의, 데이터 초과, 요금제 변경, 가족결합 할인
    - pass: PASS 앱 본인인증 알림, 보안 관련 문의
    - cancel/cancellation: 해지 문의, 위약금 확인
"""

import asyncio
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from io import StringIO

# backend 모듈 import를 위한 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / "config" / ".env")

from modules.agent.graph import create_agent_graph, ContextSchema
from modules.agent.cache import setup_global_llm_cache, get_cache_stats
from modules.agent.manager import RoomAgent
from modules.database import get_db_manager
from modules.database.repository import CustomerRepository
from modules.database.consultation_repository import AgentRepository, get_agent_repository
from langchain_openai import ChatOpenAI


# 기본 테스트 시나리오 (요금 관련 - RAG 검색 테스트용)
DEFAULT_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요, KT 고객센터입니다. 무엇을 도와드릴까요?"},
    {"speaker": "고객", "text": "이번 달 요금이 평소보다 많이 나온 것 같아서요. 문자에 89000원이라고 찍혔는데 왜 이 가격이죠?"},
    {"speaker": "상담사", "text": "네, 요금 관련해서 확인해드리겠습니다. 혹시 지금 사용하고 계신 요금제가 어떤 건지 아시나요?"},
    {"speaker": "고객", "text": "5G 슈퍼플랜 베이직인 것 같은데... 원래 7만원대였거든요. 근데 갑자기 왜 올랐죠?"},
    {"speaker": "상담사", "text": "확인해보니 데이터 초과 사용분이 있네요. 기본 제공량 초과시 추가 요금이 발생합니다."},
    {"speaker": "고객", "text": "아 그래요? 그럼 요금제를 바꾸면 더 저렴해질 수 있나요? 데이터 무제한 요금제로요"},
    {"speaker": "상담사", "text": "네, 5G 슈퍼플랜 프리미엄이나 다이렉트 플랜을 추천드릴 수 있습니다."},
    {"speaker": "고객", "text": "가족결합 할인도 받을 수 있나요? 인터넷이랑 TV도 KT 쓰고 있거든요"},
]

# PASS 앱 관련 시나리오
PASS_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요, KT 고객센터입니다. 무엇을 도와드릴까요?"},
    {"speaker": "고객", "text": "PASS 앱에서 이상한 알림이 왔는데요"},
    {"speaker": "상담사", "text": "네, 어떤 알림인지 말씀해주시겠어요?"},
    {"speaker": "고객", "text": "본인확인 요청이라고 뜨는데 제가 요청한 적이 없어서 해킹당한건 아닌지 너무 걱정돼요. 혹시 제 개인정보가 유출된 건 아닐까요?"},
    {"speaker": "상담사", "text": "고객님 걱정되셨겠네요. 확인해드릴게요. 혹시 최근에 은행이나 다른 사이트에서 본인인증을 하신 적 있으신가요?"},
    {"speaker": "고객", "text": "아 잠깐만요... 아까 은행 앱에서 뭔가 했던 것 같기도 하고... 근데 그게 이거랑 관련이 있나요?"},
    {"speaker": "상담사", "text": "네 맞습니다. 은행 앱에서 본인인증을 하시면 PASS 앱으로 알림이 가는 게 정상입니다."},
    {"speaker": "고객", "text": "아 그렇구나... 그러면 해킹은 아닌거죠? 진짜 걱정했어요"},
]

# 해지/위약금 관련 시나리오
CANCELLATION_SCENARIO = [
    {"speaker": "고객", "text": "안녕하세요, 해지하고 싶어서 전화했어요"},
    {"speaker": "상담사", "text": "네 고객님 안녕하세요. 해지 관련 문의시네요. 혹시 어떤 이유로 해지를 원하시는지 여쭤봐도 될까요?"},
    {"speaker": "고객", "text": "다른 통신사가 더 저렴해서요. 지금 얼마나 위약금이 나오나요?"},
    {"speaker": "상담사", "text": "네, 현재 약정 상태를 확인해드리겠습니다."},
    {"speaker": "고객", "text": "약정 끝나려면 얼마나 남았어요? 위약금 너무 많이 나오면 그냥 기다릴게요"},
]


def calculate_delay(text: str) -> float:
    """발화 길이에 따른 딜레이 계산 (초)"""
    length = len(text)
    if length < 20:
        return 1.0
    elif length < 50:
        return 2.0
    elif length < 100:
        return 3.0
    else:
        return 4.0


def print_divider(char: str = "=", width: int = 60):
    print(char * width)


def print_node_result(node_name: str, data: Dict[str, Any], elapsed_ms: int = 0):
    """노드 결과를 보기 좋게 출력"""
    timing = elapsed_ms

    color_codes = {
        "summarize": "\033[94m",  # 파랑
        "intent": "\033[92m",     # 초록
        "sentiment": "\033[93m",  # 노랑
        "draft_reply": "\033[95m", # 보라
        "risk": "\033[91m",       # 빨강
        "rag_policy": "\033[96m", # 시안
    }
    reset = "\033[0m"
    color = color_codes.get(node_name, "")

    print(f"\n{color}[{node_name}] ({timing}ms){reset}")

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
                print(f"  [RAG SKIPPED] 의도: {rp.get('intent_label', '-')}")
                print(f"  스킵 사유: {rp.get('skip_reason', '-')}")
            else:
                print(f"  [RAG CALLED] 의도: {rp.get('intent_label', '-')}")
                query = rp.get('query', '-')
                print(f"  검색 쿼리: {query[:60]}..." if len(query) > 60 else f"  검색 쿼리: {query}")

                # 검색 컨텍스트 (고객 정보 기반)
                search_context = rp.get('search_context', '')
                if search_context:
                    print(f"  검색 컨텍스트: {search_context}")

                print(f"  검색 분류: {rp.get('searched_classifications', [])}")

                recommendations = rp.get("recommendations", [])
                if recommendations:
                    print(f"  추천 요금제 ({len(recommendations)}건):")
                    for i, rec in enumerate(recommendations[:3]):
                        title = rec.get('title', '제목없음')
                        metadata = rec.get('metadata', {})
                        price = metadata.get('monthly_price', '-')
                        reason = rec.get('recommendation_reason', '')
                        search_text = metadata.get('search_text', '')
                        data_info = voice_info = ""
                        if search_text:
                            for p in search_text.split('|'):
                                p = p.strip()
                                if not data_info and p.startswith("데이터"):
                                    data_info = p
                                elif not voice_info and p.startswith("음성"):
                                    voice_info = p
                        print(f"    [{i+1}] {title} ({price})")
                        if data_info or voice_info:
                            print(f"        {data_info} | {voice_info}" if voice_info else f"        {data_info}")
                        if reason:
                            print(f"        추천: {reason}")
                else:
                    print(f"  추천 요금제: 없음")

            if rp.get("error"):
                print(f"  오류: {rp.get('error')}")

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



class GraphTester:
    def __init__(self, model: str = "gpt-5-mini", output_file: Optional[str] = None):
        print(f"LLM 초기화 중... (model: {model})")
        self._db_initialized = False

        # Redis LLM 캐시 설정 (Rate Limit 방어 및 지연 시간 단축)
        cache_enabled = setup_global_llm_cache()
        if cache_enabled:
            cache_stats = get_cache_stats()
            print(f"Redis LLM 캐시 활성화: type={cache_stats['type']}, ttl={cache_stats['ttl_seconds']}s")
        else:
            print("Redis LLM 캐시 비활성화 (연결 실패 또는 설정 OFF)")

        self.llm = ChatOpenAI(model=model, temperature=0, reasoning_effort="minimal")
        self.graph = create_agent_graph(self.llm)

        # OpenAI Prompt Caching 최적화를 위한 정적 시스템 프롬프트
        # 노드별 프롬프트(SUMMARIZE_SYSTEM_PROMPT 등)와 함께 사용되어 캐싱 효과 극대화
        static_system_prefix = """## 고객 정보
- 고객명: 테스트 고객
- 요금제: KT 5G 프리미어
- 등급: VIP
- 가입기간: 3년

## 상담 이력
- 최근 상담 없음"""

        self.context = ContextSchema(static_system_prefix=static_system_prefix)
        self.output_file = output_file
        self.results_log: List[Dict[str, Any]] = []

        # 테스트용 고객 정보 (스마트 RAG 검색용)
        # 이 고객은 월 89,000원 5G 슈퍼플랜 스페셜 사용 중, VIP 등급
        test_customer_info = {
            "customer_name": "테스트 고객",
            "phone_number": "010-1234-5678",
            "age": 35,
            "gender": "남",
            "residence": "서울시 강남구",
            "membership_grade": "Gold",
            "current_plan": "인기LTE 데이터ON - 비디오 플러스 69,000원",
            "monthly_fee": 69000,
            "current_data_gb": 11,  # 현재 요금제 데이터량 (GB), 0=무제한
            "contract_status": "약정 4개월 남음",
            "bundle_info": "없음 (단독 회선)",
        }

        # 상태 초기화
        self.state = {
            "room_name": "test_room",
            "conversation_history": [],
            "current_summary": "",
            "last_summarized_index": 0,
            "summary_result": None,
            "customer_info": test_customer_info,  # 스마트 RAG 검색용 고객 정보
            "consultation_history": [],
            "intent_result": None,
            "sentiment_result": None,
            "draft_replies": None,
            "risk_result": None,
            # RAG 정책 검색 결과
            "rag_policy_result": None,
            # 고객 발화 기반 노드 인덱스 (고객 발화 시에만 LLM 호출)
            "last_intent_index": 0,
            "last_sentiment_index": 0,
            "last_draft_index": 0,
            "last_risk_index": 0,
            "last_rag_index": 0,
        }
        print("그래프 초기화 완료!")
        print(f"테스트 고객: {test_customer_info['customer_name']}, "
              f"요금제: {test_customer_info['current_plan']}, "
              f"월 요금: {test_customer_info['monthly_fee']:,}원\n")

    async def ensure_db_initialized(self):
        """DB 초기화 (RAG 검색을 위해 필요)"""
        if not self._db_initialized:
            db = get_db_manager()
            await db.initialize()
            self._db_initialized = True
            print("DB 연결 초기화 완료")

    def add_utterance(self, speaker: str, text: str):
        """대화에 발화 추가"""
        self.state["conversation_history"].append({
            "speaker_name": speaker,
            "text": text,
            "timestamp": time.time()
        })

    async def run_graph(self, utterance_info: Optional[Dict] = None):
        """그래프 실행 및 결과 스트리밍"""
        await self.ensure_db_initialized()
        print_divider("-", 60)
        print("그래프 실행 중...")

        results = {}
        node_timings = {}
        graph_start = time.perf_counter()

        async for update in self.graph.astream(
            self.state,
            context=self.context,
            stream_mode="updates"
        ):
            for node_name, data in update.items():
                # 노드별 시간 측정
                now = time.perf_counter()
                if node_name not in node_timings:
                    node_timings[node_name] = now - graph_start
                elapsed_ms = int(node_timings[node_name] * 1000)

                results[node_name] = data
                results[f"{node_name}_ms"] = elapsed_ms
                print_node_result(node_name, data, elapsed_ms)

                # 상태 업데이트
                if node_name == "summarize":
                    if "summary_result" in data:
                        self.state["summary_result"] = data["summary_result"]
                    if "current_summary" in data:
                        self.state["current_summary"] = data["current_summary"]
                    if "last_summarized_index" in data:
                        self.state["last_summarized_index"] = data["last_summarized_index"]
                elif node_name == "intent" and "intent_result" in data:
                    self.state["intent_result"] = data["intent_result"]
                    if "last_intent_index" in data:
                        self.state["last_intent_index"] = data["last_intent_index"]
                elif node_name == "rag_policy":
                    if "rag_policy_result" in data:
                        self.state["rag_policy_result"] = data["rag_policy_result"]
                    if "last_rag_index" in data:
                        self.state["last_rag_index"] = data["last_rag_index"]
                elif node_name == "sentiment" and "sentiment_result" in data:
                    self.state["sentiment_result"] = data["sentiment_result"]
                elif node_name == "draft_reply" and "draft_replies" in data:
                    self.state["draft_replies"] = data["draft_replies"]
                elif node_name == "risk" and "risk_result" in data:
                    self.state["risk_result"] = data["risk_result"]

        print_divider("-", 60)

        # 결과 로그에 추가
        if self.output_file:
            log_entry = {
                "utterance": utterance_info,
                "results": {
                    "summarize": {
                        "data": results.get("summarize", {}).get("summary_result"),
                        "time_ms": results.get("summarize_ms", 0)
                    },
                    "intent": {
                        "data": results.get("intent", {}).get("intent_result"),
                        "time_ms": results.get("intent_ms", 0)
                    },
                    "sentiment": {
                        "data": results.get("sentiment", {}).get("sentiment_result"),
                        "time_ms": results.get("sentiment_ms", 0)
                    },
                    "draft_reply": {
                        "data": results.get("draft_reply", {}).get("draft_replies"),
                        "time_ms": results.get("draft_reply_ms", 0)
                    },
                    "risk": {
                        "data": results.get("risk", {}).get("risk_result"),
                        "time_ms": results.get("risk_ms", 0)
                    },
                    "rag_policy": {
                        "data": results.get("rag_policy", {}).get("rag_policy_result"),
                        "time_ms": results.get("rag_policy_ms", 0)
                    }
                }
            }
            self.results_log.append(log_entry)

        return results

    async def run_scenario(self, scenario: List[Dict[str, str]], auto_delay: bool = True):
        """시나리오 모드: 미리 정의된 대화 자동 재생"""
        print_divider()
        print("시나리오 모드 시작")
        print(f"총 {len(scenario)}개의 발화")
        print_divider()

        for i, utterance in enumerate(scenario):
            speaker = utterance["speaker"]
            text = utterance["text"]

            # 발화 출력
            print(f"\n[{i+1}/{len(scenario)}] {speaker}: {text}")

            # 대화에 추가
            self.add_utterance(speaker, text)

            # 딜레이 (실제 발화 시간 시뮬레이션)
            if auto_delay:
                delay = calculate_delay(text)
                print(f"  (대기 {delay}초...)")
                await asyncio.sleep(delay)

            # 그래프 실행
            utterance_info = {"index": i + 1, "speaker": speaker, "text": text}
            await self.run_graph(utterance_info)

            print_divider()

        print("\n시나리오 완료!")

        # 결과 파일 저장
        if self.output_file:
            self.save_results()

    def save_results(self):
        """결과를 TXT 파일로 저장 (읽기 쉬운 형식)"""
        output_path = Path(self.output_file)

        lines = []
        lines.append("=" * 80)
        lines.append("LangGraph 테스트 결과")
        lines.append("=" * 80)
        lines.append(f"실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"모델: {self.llm.model_name}")
        lines.append(f"총 발화 수: {len(self.results_log)}")
        lines.append("=" * 80)
        lines.append("")

        for entry in self.results_log:
            utt = entry.get("utterance", {})
            results = entry.get("results", {})

            lines.append("-" * 80)
            lines.append(f"[{utt.get('index', '?')}] {utt.get('speaker', '?')}: {utt.get('text', '')}")
            lines.append("-" * 80)

            # 요약
            summ = results.get("summarize", {})
            summ_data = summ.get("data") or {}
            lines.append(f"[요약] ({summ.get('time_ms', 0)}ms)")
            lines.append(f"  요약: {summ_data.get('summary', '-')}")
            lines.append(f"  고객문의: {summ_data.get('customer_issue', '-')}")
            lines.append(f"  상담사대응: {summ_data.get('agent_action', '-')}")
            lines.append("")

            # 의도
            intent = results.get("intent", {})
            intent_data = intent.get("data") or {}
            lines.append(f"[의도] ({intent.get('time_ms', 0)}ms)")
            lines.append(f"  의도: {intent_data.get('intent_label', '-')}")
            lines.append(f"  확신도: {intent_data.get('intent_confidence', '-')}")
            lines.append(f"  근거: {intent_data.get('intent_explanation', '-')}")
            lines.append("")

            # 감정
            sent = results.get("sentiment", {})
            sent_data = sent.get("data") or {}
            lines.append(f"[감정] ({sent.get('time_ms', 0)}ms)")
            lines.append(f"  감정: {sent_data.get('sentiment_label', '-')}")
            lines.append(f"  강도: {sent_data.get('sentiment_score', '-')}")
            lines.append(f"  근거: {sent_data.get('sentiment_explanation', '-')}")
            lines.append("")

            # 응답 초안
            draft = results.get("draft_reply", {})
            draft_data = draft.get("data") or {}
            lines.append(f"[응답 초안] ({draft.get('time_ms', 0)}ms)")
            lines.append(f"  짧은응답: {draft_data.get('short_reply', '-')}")
            keywords = draft_data.get('keywords', [])
            lines.append(f"  키워드: {', '.join(keywords) if keywords else '-'}")
            lines.append("")

            # 위험
            risk = results.get("risk", {})
            risk_data = risk.get("data") or {}
            flags = risk_data.get("risk_flags", [])
            lines.append(f"[위험] ({risk.get('time_ms', 0)}ms)")
            lines.append(f"  위험플래그: {flags if flags else '없음'}")
            if risk_data.get("risk_explanation"):
                lines.append(f"  설명: {risk_data.get('risk_explanation', '-')}")
            lines.append("")

            # RAG 정책 검색
            rag = results.get("rag_policy", {})
            rag_data = rag.get("data") or {}
            skipped = rag_data.get("skipped", False)

            lines.append(f"[RAG 정책] ({rag.get('time_ms', 0)}ms)")

            if skipped:
                lines.append(f"  상태: SKIPPED")
                lines.append(f"  의도: {rag_data.get('intent_label', '-')}")
                lines.append(f"  스킵 사유: {rag_data.get('skip_reason', '-')}")
            else:
                lines.append(f"  상태: CALLED")
                lines.append(f"  의도: {rag_data.get('intent_label', '-')}")
                query = rag_data.get('query', '-')
                lines.append(f"  검색 쿼리: {query[:80]}..." if len(query) > 80 else f"  검색 쿼리: {query}")

                # 검색 컨텍스트 (고객 정보 기반)
                search_context = rag_data.get('search_context', '')
                if search_context:
                    lines.append(f"  검색 컨텍스트: {search_context}")

                lines.append(f"  검색 분류: {rag_data.get('searched_classifications', [])}")

                recommendations = rag_data.get("recommendations", [])
                if recommendations:
                    lines.append(f"  추천 요금제 ({len(recommendations)}건):")
                    for i, rec in enumerate(recommendations[:3]):
                        title = rec.get('title', '제목없음')
                        metadata = rec.get('metadata', {})
                        price = metadata.get('monthly_price', '-')
                        reason = rec.get('recommendation_reason', '')
                        search_text = metadata.get('search_text', '')
                        data_info = voice_info = ""
                        if search_text:
                            for p in search_text.split('|'):
                                p = p.strip()
                                if not data_info and p.startswith("데이터"):
                                    data_info = p
                                elif not voice_info and p.startswith("음성"):
                                    voice_info = p
                        lines.append(f"    [{i+1}] {title} ({price})")
                        if data_info or voice_info:
                            lines.append(f"        {data_info} | {voice_info}" if voice_info else f"        {data_info}")
                        if reason:
                            lines.append(f"        추천: {reason}")
                else:
                    lines.append("  추천 요금제: 없음")

            if rag_data.get("error"):
                lines.append(f"  오류: {rag_data.get('error')}")
            lines.append("")

        lines.append("=" * 80)
        lines.append("테스트 완료")
        lines.append("=" * 80)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"\n결과 저장 완료: {output_path}")

    async def run_interactive(self):
        """대화형 모드: 직접 입력"""
        print_divider()
        print("대화형 모드 시작")
        print("명령어:")
        print("  /고객 <텍스트>  - 고객 발화 추가")
        print("  /상담사 <텍스트> - 상담사 발화 추가")
        print("  /run           - 그래프 실행")
        print("  /history       - 현재 대화 히스토리 보기")
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

                if user_input == "/reset":
                    self.state["conversation_history"] = []
                    self.state["current_summary"] = ""
                    self.state["last_summarized_index"] = 0
                    self.state["summary_result"] = None
                    self.state["intent_result"] = None
                    self.state["sentiment_result"] = None
                    self.state["draft_replies"] = None
                    self.state["risk_result"] = None
                    self.state["rag_policy_result"] = None
                    self.state["last_intent_index"] = 0
                    self.state["last_sentiment_index"] = 0
                    self.state["last_draft_index"] = 0
                    self.state["last_risk_index"] = 0
                    self.state["last_rag_index"] = 0
                    print("대화가 초기화되었습니다.")
                    continue

                if user_input == "/run":
                    if not self.state["conversation_history"]:
                        print("대화 히스토리가 비어있습니다. 먼저 발화를 추가하세요.")
                        continue
                    await self.run_graph()
                    continue

                if user_input.startswith("/고객 "):
                    text = user_input[4:].strip()
                    self.add_utterance("고객", text)
                    print(f"  추가됨: 고객: {text}")
                    # 자동으로 그래프 실행
                    await self.run_graph()
                    continue

                if user_input.startswith("/상담사 "):
                    text = user_input[5:].strip()
                    self.add_utterance("상담사", text)
                    print(f"  추가됨: 상담사: {text}")
                    # 자동으로 그래프 실행
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


def get_default_output_path() -> str:
    """기본 출력 파일 경로 생성 (test/ 디렉토리에 타임스탬프 파일명)"""
    test_dir = Path(__file__).parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return str(test_dir / f"result_{timestamp}.txt")


class DBScenarioTester:
    """DB 저장 기능이 있는 시나리오 테스터 (RoomAgent 사용)"""

    def __init__(
        self,
        agent_code: str = "A001",
        agent_name: str = "김상담",
        customer_name: str = "윤지훈",
        customer_phone: str = "010-2222-3333"
    ):
        self.agent_code = agent_code
        self.agent_name = agent_name
        self.customer_name = customer_name
        self.customer_phone = customer_phone
        self.room_agent: Optional[RoomAgent] = None
        self._db_initialized = False

    async def initialize(self):
        """DB 및 에이전트 초기화"""
        print("=" * 60)
        print("DB 시나리오 테스터 초기화")
        print("=" * 60)

        # DB 초기화
        db = get_db_manager()
        await db.initialize()
        self._db_initialized = True
        print("DB 연결 완료")

        # 상담사 조회
        agent_repo = AgentRepository()
        agent_info = await agent_repo.find_agent(self.agent_code, self.agent_name)
        if not agent_info:
            print(f"상담사를 찾을 수 없습니다: {self.agent_code} / {self.agent_name}")
            return False
        print(f"상담사 확인: {agent_info['agent_name']} ({agent_info['agent_code']})")

        # 고객 조회
        customer_repo = CustomerRepository()
        customer_info = await customer_repo.find_customer(self.customer_name, self.customer_phone)
        if not customer_info:
            print(f"고객을 찾을 수 없습니다: {self.customer_name} / {self.customer_phone}")
            return False
        print(f"고객 확인: {customer_info['customer_name']} ({customer_info['phone_number']})")

        # 룸 생성 (테스트용 임의 룸)
        room_name = f"test_scenario_{datetime.now().strftime('%H%M%S')}"

        # RoomAgent 생성
        self.room_agent = RoomAgent(room_name, save_to_db=True)
        print(f"RoomAgent 생성: {room_name}")

        # 고객 컨텍스트 설정
        consultation_history = await customer_repo.get_consultation_history(customer_info['customer_id'])
        self.room_agent.set_customer_context(customer_info, consultation_history)
        print(f"고객 컨텍스트 설정 완료 (이력 {len(consultation_history)}건)")

        # 세션 시작
        session_id = await self.room_agent.start_session(
            agent_name=self.agent_name,
            customer_id=customer_info['customer_id'],
            agent_id=str(agent_info['agent_id'])
        )
        if session_id:
            print(f"세션 시작: {session_id}")
        else:
            print("세션 시작 실패!")
            return False

        print("=" * 60)
        return True

    async def run_scenario(self, scenario: List[Dict[str, str]], auto_delay: bool = True):
        """시나리오 실행 및 DB 저장"""
        if not self.room_agent:
            print("초기화가 필요합니다. initialize()를 먼저 호출하세요.")
            return

        print(f"\n시나리오 실행 시작 (총 {len(scenario)}개 발화)")
        print("-" * 60)

        for i, utterance in enumerate(scenario):
            speaker = utterance["speaker"]
            text = utterance["text"]

            # 발화자 매핑
            if speaker in ["상담사", "agent"]:
                speaker_type = "agent"
                speaker_name = self.agent_name
                is_customer = False
            else:
                speaker_type = "customer"
                speaker_name = self.customer_name
                is_customer = True

            print(f"\n[{i+1}/{len(scenario)}] {speaker_name}: {text}")

            # 딜레이
            if auto_delay:
                delay = calculate_delay(text)
                print(f"  (대기 {delay}초...)")
                await asyncio.sleep(delay)

            # RoomAgent로 전사 처리 (그래프 실행 + DB 저장)
            await self.room_agent.on_new_transcript(
                speaker_id=f"test_{speaker_type}",
                speaker_name=speaker_name,
                text=text,
                
                is_customer=is_customer
            )

            # 결과 출력
            state = self.room_agent.state
            if state.get("summary_result"):
                sr = state["summary_result"]
                print(f"  [요약] {sr.get('summary', '-')}")
            if state.get("intent_result"):
                ir = state["intent_result"]
                print(f"  [의도] {ir.get('intent_label', '-')} ({ir.get('intent_confidence', 0):.0%})")
            if state.get("sentiment_result"):
                sent = state["sentiment_result"]
                print(f"  [감정] {sent.get('sentiment_label', '-')}")

            print("-" * 60)

        print("\n시나리오 완료!")

        # 세션 종료 및 최종 저장
        print("\n세션 종료 중...")
        success = await self.room_agent.end_session()
        if success:
            print(f"세션 저장 완료! (session_id: {self.room_agent.session_id})")
        else:
            print("세션 저장 실패")

        return success


SCENARIO_MAP = {
    "default": DEFAULT_SCENARIO,
    "billing": DEFAULT_SCENARIO,  # 요금 관련 (기본 시나리오)
    "pass": PASS_SCENARIO,
    "cancel": CANCELLATION_SCENARIO,
    "cancellation": CANCELLATION_SCENARIO,
}


async def main():
    parser = argparse.ArgumentParser(description="LangGraph 텍스트 기반 테스트")
    parser.add_argument("--scenario", action="store_true", help="시나리오 모드 실행")
    parser.add_argument("--scenario-type", "-t", type=str, default="default",
                        choices=list(SCENARIO_MAP.keys()),
                        help="시나리오 타입 (default/billing, pass, cancel/cancellation)")
    parser.add_argument("--file", type=str, help="시나리오 JSON 파일 경로")
    parser.add_argument("--model", type=str, default="gpt-5-mini", help="사용할 LLM 모델")
    parser.add_argument("--no-delay", action="store_true", help="시나리오 모드에서 딜레이 없이 실행")
    parser.add_argument("--output", "-o", type=str, help="결과 저장 파일 경로 (미지정시 test/result_YYYYMMDD_HHMMSS.txt)")
    parser.add_argument("--no-output", action="store_true", help="결과 파일 저장 안함")

    # DB 저장 관련 옵션
    parser.add_argument("--save-db", action="store_true", help="시나리오 결과를 DB에 저장")
    parser.add_argument("--agent-code", type=str, default="A001", help="상담사 코드 (기본: A001)")
    parser.add_argument("--agent-name", type=str, default="김상담", help="상담사 이름 (기본: 김상담)")
    parser.add_argument("--customer-name", type=str, default="윤지훈", help="고객 이름 (기본: 윤지훈)")
    parser.add_argument("--customer-phone", type=str, default="010-2222-3333", help="고객 전화번호 (기본: 010-2222-3333)")

    args = parser.parse_args()

    # 시나리오 로드
    scenario = SCENARIO_MAP.get(args.scenario_type, DEFAULT_SCENARIO)
    if args.file:
        scenario_path = Path(args.file)
        if scenario_path.exists():
            with open(scenario_path, "r", encoding="utf-8") as f:
                scenario = json.load(f)
            print(f"시나리오 파일 로드: {args.file}")
        else:
            print(f"파일을 찾을 수 없습니다: {args.file}")

    # DB 저장 모드
    if args.save_db:
        print("\n*** DB 저장 모드 ***")
        print(f"상담사: {args.agent_name} ({args.agent_code})")
        print(f"고객: {args.customer_name} ({args.customer_phone})\n")

        tester = DBScenarioTester(
            agent_code=args.agent_code,
            agent_name=args.agent_name,
            customer_name=args.customer_name,
            customer_phone=args.customer_phone
        )

        if await tester.initialize():
            await tester.run_scenario(scenario, auto_delay=not args.no_delay)
        else:
            print("초기화 실패. DB와 상담사/고객 정보를 확인하세요.")
        return

    # 기존 모드 (DB 저장 없음)
    output_file = None
    if not args.no_output:
        output_file = args.output if args.output else get_default_output_path()

    tester = GraphTester(model=args.model, output_file=output_file)

    if args.scenario:
        # 시나리오 모드
        print(f"시나리오 타입: {args.scenario_type}")
        await tester.run_scenario(scenario, auto_delay=not args.no_delay)
    else:
        # 대화형 모드
        await tester.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
