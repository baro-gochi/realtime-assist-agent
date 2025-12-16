# 로그 관리 개선 가이드

> 작성일: 2024-12-16
> 참고문서: "엔터프라이즈 로그 관리 마스터 가이드: 개발/운영 환경 전략, 생명주기 및 컴플라이언스 아키텍처"

---

## 1. 개요

### 1.1 목적

본 문서는 현재 프로젝트의 로그 관리 현황을 분석하고, 엔터프라이즈 로그 관리 모범 사례에 기반한 개선 방안을 제시합니다.

---

## 1.5 구현 완료 사항 (2024-12-16)

### Backend 개선

| 항목 | 구현 내용 | 파일 |
|------|----------|------|
| 환경별 로그 레벨 | `LOG_LEVEL` 환경변수 지원 (기본: INFO) | `app.py:110-123` |
| 환경 구분 | `ENV` 환경변수 (development/staging/production) | `app.py:112` |
| 로그 보관정책 | `LOG_RETENTION_DAYS=60` (2개월 후 자동 삭제) | `app.py:115, 118-153` |
| 서버 시작 시 정리 | `cleanup_old_logs()` lifespan에서 자동 실행 | `app.py:199-202` |
| DEBUG 로그 분리 | `[DEBUG]` 레이블 로그를 `logger.debug()`로 변경 | `app.py`, `consultation_repository.py`, `manager.py` |
| ICE candidate 로그 | 상세 디버깅 로그를 DEBUG 레벨로 변경 | `app.py:1111-1120` |
| join_room 로그 | 수신 데이터 로그를 DEBUG 레벨로 변경 | `app.py:1301-1302` |

### Frontend 개선

| 항목 | 구현 내용 | 파일 |
|------|----------|------|
| 로거 유틸리티 | 환경 기반 로그 레벨 제어 (`logger.js`) | `frontend/src/logger.js` |
| console.log 교체 | 98개 console.log → logger.debug/info/warn/error | `frontend/src/webrtc.js` |
| 환경별 기본값 | development=DEBUG, production=WARN | `frontend/src/logger.js:20-27` |
| 환경변수 지원 | `VITE_LOG_LEVEL` 오버라이드 가능 | `frontend/.env.example` |
| 백엔드 로그 전송 | `VITE_LOG_TO_BACKEND=true` 설정 시 파일 저장 | `frontend/src/logger.js:29-32, 47-70` |
| 로그 배치 전송 | 10개 또는 5초마다 일괄 전송 | `frontend/src/logger.js:31-32` |
| 페이지 언로드 처리 | `sendBeacon` API로 남은 로그 전송 | `frontend/src/logger.js:155-163` |

### Backend 프론트엔드 로그 수신 (개발용)

| 항목 | 구현 내용 | 파일 |
|------|----------|------|
| API 엔드포인트 | `POST /api/logs/frontend` | `app.py:1068-1109` |
| 저장 위치 | `logs/frontend/frontend_YYYYMMDD.log` | `app.py:1065` |
| 보안 제한 | production 환경에서는 403 반환 | `app.py:1078-1080` |
| 자동 정리 | `cleanup_old_logs()`에서 프론트엔드 로그도 정리 | `app.py:137-141` |

### 환경변수 설정

**Backend (`backend/config/.env.example`)**
```bash
ENV=development
LOG_LEVEL=INFO
LOG_RETENTION_DAYS=60
```

**Frontend (`frontend/.env.example`)**
```bash
# VITE_LOG_LEVEL=DEBUG       # 명시적 설정 시 기본값 오버라이드
# VITE_LOG_TO_BACKEND=true   # 백엔드로 로그 전송 (개발용)
```

### 환경별 로그 레벨 권장 설정

| 환경 | Backend LOG_LEVEL | Frontend VITE_LOG_LEVEL |
|------|-------------------|-------------------------|
| Development | DEBUG | (자동) DEBUG |
| Staging | INFO | INFO |
| Production | WARNING | (자동) WARN |

### 사용 예시

```bash
# Backend - 디버그 모드 실행
LOG_LEVEL=DEBUG uv run python app.py

# Backend - 운영 모드 (경고만)
LOG_LEVEL=WARNING ENV=production uv run python app.py

# Frontend - 빌드 시 자동으로 production=WARN 적용
npm run build

# Frontend - 백엔드 로그 전송 활성화 (개발용)
# frontend/.env 파일에 추가:
VITE_LOG_TO_BACKEND=true
VITE_API_URL=http://localhost:8000

# 로그 파일 확인
cat backend/logs/frontend/frontend_20241216.log
```

### 미구현 항목 (향후 과제)

| 항목 | 우선순위 | 비고 |
|------|----------|------|
| 구조화된 로깅 (JSON) | 중 | `python-json-logger` 도입 필요 |
| PII 마스킹 | 높음 | 전화번호, 이메일 마스킹 함수 필요 |
| trace_id 분산 추적 | 낮음 | OpenTelemetry 연동 |
| 로그 로테이션 압축 | 중 | `TimedRotatingFileHandler` + gzip |
| print() 문 제거 | 낮음 | `log_handler.py:151` |

---

### 1.2 현재 로그 아키텍처

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Application   │────▶│  Python logging  │────▶│  Console/File   │
│   (app.py)      │     │   (basicConfig)  │     │  logs/*.log     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │ DatabaseLogHandler│
                        │   (Async Queue)  │
                        └──────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │   PostgreSQL     │
                        │  (system_logs)   │
                        └──────────────────┘
```

### 1.3 현재 구현된 항목

| 항목 | 구현 상태 | 위치 |
|------|-----------|------|
| 비동기 로깅 | O | `modules/database/log_handler.py` |
| 날짜별 파일 분리 | O | `logs/server_YYYYMMDD.log` |
| DB 로그 저장 | O | `DatabaseLogHandler` (배치 처리) |
| 표준 프레임워크 | O | Python logging 모듈 |

---

## 2. 개선 필요 사항

### 2.1 환경별 로그 레벨 분리 미구현

**심각도: 높음**

#### 현재 문제

```python
# backend/app.py:110-117
logging.basicConfig(
    level=logging.INFO,  # 하드코딩
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding="utf-8"),
    ]
)
```

- 개발/스테이징/운영 환경에서 동일한 `INFO` 레벨 사용
- 런타임 로그 레벨 변경 불가

#### 권장 사항

| 환경 | 권장 레벨 | 목적 |
|------|-----------|------|
| Development | DEBUG | 상세한 디버깅 정보 |
| Staging | DEBUG/INFO | 통합 테스트 검증 |
| Production | INFO/WARN | 성능 최적화, 핵심 이벤트만 |

#### 개선 코드

```python
import os
import logging

# 환경 변수에서 로그 레벨 동적 로드
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENV = os.getenv("ENV", "development")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_filename, encoding="utf-8"),
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"Logging initialized: level={LOG_LEVEL}, env={ENV}")
```

```bash
# .env 파일
LOG_LEVEL=DEBUG  # 개발 환경
# LOG_LEVEL=INFO  # 운영 환경
```

---

### 2.2 구조화된 로깅(Structured Logging) 미적용

**심각도: 높음**

#### 현재 문제

```
# 현재 로그 형식 (비구조화)
2024-12-16 10:00:00 [INFO] __main__: Peer abc-123 connected
2024-12-16 10:00:01 [INFO] __main__: [join_room] 수신 데이터: room=room1...
```

- JSON 형식 미지원으로 로그 분석 도구 연동 어려움
- 메타데이터 태그 부재 (env, service, trace_id 등)
- 분산 시스템 추적 불가

#### 권장 메타데이터 태그

| 카테고리 | 필드 | 설명 |
|----------|------|------|
| 환경 정보 | `env` | dev, staging, prod |
| 서비스 정보 | `service_name`, `version` | webrtc-signaling, v1.0.0 |
| 추적 정보 | `trace_id`, `span_id` | 분산 요청 추적 |
| 사용자 정보 | `user_id`, `peer_id` | 특정 사용자 문제 필터링 |
| 위치 정보 | `room_name`, `host` | 컨텍스트 파악 |

#### 개선 코드

```python
# requirements.txt에 추가
# python-json-logger>=2.0.0

import logging
from pythonjsonlogger import jsonlogger

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record['timestamp'] = record.created
        log_record['level'] = record.levelname
        log_record['service'] = 'webrtc-signaling'
        log_record['env'] = os.getenv('ENV', 'development')

# JSON 포맷터 적용
handler = logging.StreamHandler()
handler.setFormatter(CustomJsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s'
))
```

```json
// 개선 후 로그 형식
{
    "timestamp": 1702700400.123,
    "level": "INFO",
    "service": "webrtc-signaling",
    "env": "production",
    "peer_id": "abc-123",
    "room_name": "room1",
    "message": "Peer connected"
}
```

---

### 2.3 성공 로그 과다 (Success Spam)

**심각도: 높음**

#### 현재 문제

`app.py`에서 `logger.info()` 호출이 80회 이상 발생하며, 상당수가 디버깅용 로그임에도 INFO 레벨로 기록됨.

**DEBUG여야 할 로그 예시:**

| 위치 | 현재 코드 | 문제점 |
|------|-----------|--------|
| app.py:1310 | `logger.info(f"[DEBUG] phone_number...")` | 명시적 DEBUG 표시 |
| app.py:1297 | `logger.info(f"[join_room] 수신 데이터...")` | 개발용 상세 로그 |
| app.py:1107 | `logger.info(f"Raw candidate from aiortc...")` | 내부 디버깅 정보 |
| app.py:1115 | `logger.info(f"Converted candidate_dict...")` | 데이터 변환 확인 |

#### 로그 레벨 분류 기준

| 레벨 | 정의 | 예시 | 운영 환경 |
|------|------|------|-----------|
| **TRACE** | 코드 실행 경로 추적 | 루프 내 변수값 | 비활성화 |
| **DEBUG** | 문제 진단용 정보 | SQL 쿼리, API 요청/응답 | 비활성화 (기본) |
| **INFO** | 주요 마일스톤 | 서버 시작, 세션 생성/종료 | 활성화 |
| **WARN** | 잠재적 문제 | Deprecated API, 느린 응답 | 활성화 |
| **ERROR** | 기능 실패 | 트랜잭션 롤백, 타임아웃 | 활성화 + 알림 |
| **FATAL** | 시스템 마비 | DB 연결 불가, OOM | 활성화 + 긴급 호출 |

#### 개선 방안

```python
# 변경 전
logger.info(f"[DEBUG] phone_number 체크: '{phone_number}'")
logger.info(f"[join_room] 수신 데이터: room={room_name}...")
logger.info(f"Raw candidate from aiortc: {candidate}")

# 변경 후
logger.debug(f"phone_number 체크: '{mask_phone(phone_number)}'")
logger.debug(f"join_room 수신: room={room_name}, peer={peer_id[:8]}")
logger.debug(f"aiortc candidate: sdpMid={candidate.sdpMid}")
```

#### 성공 로그 → 메트릭 전환

```python
# 변경 전: 텍스트 로그 (스토리지 낭비)
logger.info(f"Peer {peer_id} connected")  # 연결마다 50바이트

# 변경 후: 메트릭 카운터 (효율적)
from prometheus_client import Counter
peer_connections = Counter('peer_connections_total', 'Total peer connections')
peer_connections.inc()  # 숫자만 증가
```

---

### 2.4 print() 문 잔존

**심각도: 중간**

#### 현재 문제

| 파일 | 라인 | 코드 |
|------|------|------|
| log_handler.py | 151 | `print(f"DatabaseLogHandler worker error: {e}")` |
| test_graph_interactive.py | 다수 | 테스트 출력용 print() |

#### 문제점

- 로그 레벨 제어 불가
- 구조화된 로깅 불가
- 운영 환경 로그 포맷 파괴

#### 개선 코드

```python
# 변경 전
print(f"DatabaseLogHandler worker error: {e}")

# 변경 후
# 별도 fallback 로거 사용 (DB 저장 제외)
fallback_logger = logging.getLogger("fallback")
fallback_logger.error(f"DatabaseLogHandler worker error: {e}")
```

---

### 2.5 로그 로테이션/보관 정책 미구현

**심각도: 높음**

#### 현재 문제

- 로그 파일 자동 삭제/압축 없음
- 디스크 용량 고갈 위험
- 컴플라이언스 보관 기간 미준수

#### 권장 스토리지 계층화 전략

| 계층 | 저장소 | 보관 기간 | 용도 | 비용 |
|------|--------|-----------|------|------|
| **Hot** | 로컬 SSD / ES | 7-14일 | 실시간 검색, 대시보드 | 높음 |
| **Warm** | HDD / ES | 15-90일 | 주간/월간 리포트 | 중간 |
| **Cold** | S3 Standard-IA | 90일-1년 | 컴플라이언스, 비정기 감사 | 낮음 |
| **Frozen** | S3 Glacier | 1-5년+ | 법적 분쟁 대비 | 매우 낮음 |

#### 한국 컴플라이언스 보관 기간

| 법령 | 대상 | 보관 기간 |
|------|------|-----------|
| 전자금융거래법 | 금융 거래 로그 | **5년** |
| 개인정보보호법 (ISMS-P) | 접속 기록 | **1년** (5만명 이상: 2년) |
| 통신비밀보호법 | 로그인 기록 | **3개월** |

#### 개선 코드

```python
from logging.handlers import TimedRotatingFileHandler
import gzip
import os

def namer(name):
    return name + ".gz"

def rotator(source, dest):
    with open(source, 'rb') as f_in:
        with gzip.open(dest, 'wb') as f_out:
            f_out.writelines(f_in)
    os.remove(source)

# 시간 기반 로테이션 핸들러
handler = TimedRotatingFileHandler(
    filename="logs/server.log",
    when="midnight",      # 매일 자정에 로테이션
    interval=1,
    backupCount=30,       # 30일 보관 후 자동 삭제
    encoding="utf-8"
)
handler.rotator = rotator
handler.namer = namer

logging.getLogger().addHandler(handler)
```

---

### 2.6 실패 로그 컨텍스트 부족

**심각도: 중간**

#### 현재 문제

```python
# app.py:1523 - 컨텍스트 부족
logger.error(f"Error handling offer from {peer_id}: {e}")
```

- Stack trace 누락
- trace_id, room_name 등 컨텍스트 부재
- 디버깅 시간 증가

#### 실패 로그 필수 요소 (5W)

| 요소 | 설명 | 예시 |
|------|------|------|
| **What** | 어떤 에러? | Exception Class, Message |
| **Where** | 어디서? | Stack Trace, File, Line |
| **Why** | 왜? | 입력값, 변수 상태, 외부 응답 |
| **Who** | 누가? | User ID, Peer ID, IP |
| **Context** | 어떤 트랜잭션? | Trace ID, Room Name |

#### 개선 코드

```python
# 변경 전
logger.error(f"Error handling offer from {peer_id}: {e}")

# 변경 후
logger.error(
    "Error handling offer",
    extra={
        "peer_id": peer_id,
        "room_name": current_room,
        "offer_type": offer.get("type"),
        "error_type": type(e).__name__,
    },
    exc_info=True  # Stack trace 포함
)
```

---

### 2.7 민감 정보 마스킹 미구현

**심각도: 높음 (보안)**

#### 현재 문제

```python
# app.py:1314 - 전화번호 평문 노출
logger.info(f"[고객조회] 시작 - name='{nickname}', phone='{phone_number}'")
```

- 개인정보(PII) 평문 로깅
- 개인정보보호법 위반 가능성
- 로그 유출 시 2차 피해

#### 마스킹 대상 필드

| 필드 | 마스킹 전 | 마스킹 후 |
|------|-----------|-----------|
| 전화번호 | 010-1234-5678 | 010-****-5678 |
| 이메일 | user@example.com | us**@example.com |
| 주민번호 | 900101-1234567 | 900101-******* |
| 카드번호 | 1234-5678-9012-3456 | 1234-****-****-3456 |

#### 개선 코드

```python
# utils/masking.py
import re

def mask_phone(phone: str) -> str:
    """전화번호 마스킹 (중간 4자리)"""
    if not phone:
        return "****"
    # 하이픈 제거 후 처리
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 7:
        return "****"
    return digits[:3] + "****" + digits[-4:]

def mask_email(email: str) -> str:
    """이메일 마스킹 (@ 앞 부분)"""
    if not email or '@' not in email:
        return "****"
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[:2]}**@{domain}"

# 사용 예시
logger.info(f"고객조회: name='{nickname}', phone='{mask_phone(phone_number)}'")
```

---

## 3. 개선 우선순위

### 3.1 Phase 1: 즉시 개선 (1주 이내)

| 항목 | 작업 내용 | 담당 파일 |
|------|-----------|-----------|
| 민감정보 마스킹 | `mask_phone()`, `mask_email()` 유틸 추가 | 전역 |
| 환경별 로그 레벨 | `LOG_LEVEL` 환경변수 적용 | `app.py` |
| print() 제거 | 로거로 교체 | `log_handler.py` |

### 3.2 Phase 2: 단기 개선 (2주 이내)

| 항목 | 작업 내용 | 예상 작업량 |
|------|-----------|-------------|
| DEBUG/INFO 분류 | 80+ 로그 검토 및 레벨 조정 | 중 |
| 로그 로테이션 | `TimedRotatingFileHandler` 적용 | 소 |
| 실패 로그 강화 | `exc_info=True`, 컨텍스트 추가 | 중 |

### 3.3 Phase 3: 중기 개선 (1개월 이내)

| 항목 | 작업 내용 | 예상 작업량 |
|------|-----------|-------------|
| 구조화된 로깅 | JSON 포맷 + 메타데이터 태그 | 대 |
| trace_id 도입 | 분산 추적 시스템 연동 | 대 |
| 메트릭 전환 | 성공 카운터 → Prometheus | 중 |

---

## 4. 개선 후 예상 효과

| 지표 | 현재 | 개선 후 |
|------|------|---------|
| 로그 용량/일 | 무제한 증가 | 30일 자동 삭제 |
| 디버깅 시간 | 수십 분 | 수 분 (trace_id 검색) |
| 보안 위험 | 높음 (PII 노출) | 낮음 (마스킹 적용) |
| 운영 로그 노이즈 | 높음 (DEBUG 혼재) | 낮음 (레벨 분리) |
| 분석 도구 연동 | 불가 | 가능 (JSON 포맷) |

---

## 5. 참고 자료

- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html)
- [Structured Logging Best Practices](https://www.structlog.org/en/stable/)
- [ISMS-P 인증기준 2.9.4 로그 및 접속기록 관리](https://isms.kisa.or.kr/)
- [전자금융거래법 시행령](https://www.law.go.kr/)
