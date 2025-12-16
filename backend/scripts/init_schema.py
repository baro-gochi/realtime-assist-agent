"""데이터베이스 스키마 초기화 스크립트.

PostgreSQL 테이블, 뷰, 함수를 생성합니다.

Usage:
    uv run python scripts/init_schema.py
    uv run python scripts/init_schema.py --drop  # 기존 테이블 삭제 후 재생성
"""

import asyncio
import argparse
import logging
import os
import sys

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://assistant:assistant123@localhost:5432/realtime_assist"
)

# ==============================================================================
# DDL Statements
# ==============================================================================

DROP_STATEMENTS = """
-- Drop views first (depends on tables)
DROP VIEW IF EXISTS consultation_session_summary CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS end_consultation_session CASCADE;

-- Drop tables (reverse order of dependencies)
DROP TABLE IF EXISTS consultation_agent_results CASCADE;
DROP TABLE IF EXISTS consultation_transcripts CASCADE;
DROP TABLE IF EXISTS consultation_sessions CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS agents CASCADE;
"""

CREATE_AGENTS_TABLE = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id SERIAL PRIMARY KEY,
    agent_code VARCHAR(50) NOT NULL UNIQUE,
    agent_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_code ON agents(agent_code);

COMMENT ON TABLE agents IS '상담사 정보 테이블';
COMMENT ON COLUMN agents.agent_id IS '상담사 DB ID (auto-increment)';
COMMENT ON COLUMN agents.agent_code IS '상담사 코드 (사번 등 사용자 입력 ID)';
COMMENT ON COLUMN agents.agent_name IS '상담사 이름';
"""

CREATE_CUSTOMERS_TABLE = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    customer_name VARCHAR(100),
    phone_number VARCHAR(20),
    membership_grade VARCHAR(20) DEFAULT 'NORMAL',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone_number);

COMMENT ON TABLE customers IS '고객 정보 테이블';
COMMENT ON COLUMN customers.membership_grade IS '회원 등급 (NORMAL, SILVER, GOLD, VIP)';
"""

CREATE_CONSULTATION_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS consultation_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID,
    customer_id INTEGER REFERENCES customers(customer_id) ON DELETE SET NULL,
    agent_id VARCHAR(50),
    agent_name VARCHAR(100),
    channel VARCHAR(20) DEFAULT 'call',
    status VARCHAR(20) DEFAULT 'active',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    final_summary TEXT,
    consultation_type VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_room ON consultation_sessions(room_id);
CREATE INDEX IF NOT EXISTS idx_sessions_customer ON consultation_sessions(customer_id);
CREATE INDEX IF NOT EXISTS idx_sessions_agent ON consultation_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON consultation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON consultation_sessions(started_at DESC);

COMMENT ON TABLE consultation_sessions IS '상담 세션 테이블';
COMMENT ON COLUMN consultation_sessions.channel IS '채널 (call, chat)';
COMMENT ON COLUMN consultation_sessions.status IS '상태 (active, ended, abandoned)';
"""

CREATE_CONSULTATION_TRANSCRIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS consultation_transcripts (
    transcript_id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES consultation_sessions(session_id) ON DELETE CASCADE,
    turn_index INTEGER NOT NULL,
    speaker_type VARCHAR(20) NOT NULL,
    speaker_name VARCHAR(100),
    text TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    confidence FLOAT,
    is_final BOOLEAN DEFAULT TRUE,
    source VARCHAR(20) DEFAULT 'google',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_transcripts_session ON consultation_transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_turn ON consultation_transcripts(session_id, turn_index);

COMMENT ON TABLE consultation_transcripts IS '통화 전사 테이블';
COMMENT ON COLUMN consultation_transcripts.speaker_type IS '발화자 타입 (agent, customer)';
COMMENT ON COLUMN consultation_transcripts.source IS 'STT 소스 (google, whisper 등)';
"""

CREATE_CONSULTATION_AGENT_RESULTS_TABLE = """
CREATE TABLE IF NOT EXISTS consultation_agent_results (
    result_id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES consultation_sessions(session_id) ON DELETE CASCADE,
    turn_id VARCHAR(100),
    result_type VARCHAR(30) NOT NULL,
    result_data JSONB NOT NULL,
    processing_time_ms INTEGER,
    model_version VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_results_session ON consultation_agent_results(session_id);
CREATE INDEX IF NOT EXISTS idx_results_type ON consultation_agent_results(session_id, result_type);

COMMENT ON TABLE consultation_agent_results IS '에이전트 분석 결과 테이블';
COMMENT ON COLUMN consultation_agent_results.result_type IS '결과 타입 (intent, sentiment, summary, draft, risk, rag, faq)';
"""

CREATE_SESSION_SUMMARY_VIEW = """
CREATE OR REPLACE VIEW consultation_session_summary AS
SELECT
    cs.session_id,
    cs.room_id,
    cs.customer_id,
    c.customer_name,
    c.phone_number,
    c.membership_grade,
    cs.agent_id,
    cs.agent_name,
    cs.channel,
    cs.status,
    cs.started_at,
    cs.ended_at,
    cs.final_summary,
    cs.consultation_type,
    cs.metadata,
    EXTRACT(EPOCH FROM (COALESCE(cs.ended_at, NOW()) - cs.started_at))::INTEGER as duration_seconds,
    (SELECT COUNT(*) FROM consultation_transcripts ct WHERE ct.session_id = cs.session_id) as transcript_count,
    (SELECT COUNT(*) FROM consultation_agent_results car WHERE car.session_id = cs.session_id) as result_count
FROM consultation_sessions cs
LEFT JOIN customers c ON cs.customer_id = c.customer_id;

COMMENT ON VIEW consultation_session_summary IS '상담 세션 요약 뷰';
"""

CREATE_END_SESSION_FUNCTION = """
CREATE OR REPLACE FUNCTION end_consultation_session(
    p_session_id UUID,
    p_final_summary TEXT DEFAULT NULL,
    p_consultation_type VARCHAR DEFAULT NULL
) RETURNS BOOLEAN AS $$
BEGIN
    UPDATE consultation_sessions
    SET
        status = 'ended',
        ended_at = NOW(),
        final_summary = COALESCE(p_final_summary, final_summary),
        consultation_type = COALESCE(p_consultation_type, consultation_type)
    WHERE session_id = p_session_id
      AND status = 'active';

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION end_consultation_session IS '상담 세션 종료 함수';
"""


async def init_schema(drop_existing: bool = False):
    """데이터베이스 스키마를 초기화합니다.

    Args:
        drop_existing: True이면 기존 테이블을 삭제 후 재생성
    """
    logger.info(f"Connecting to database: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL}")

    try:
        conn = await asyncpg.connect(DATABASE_URL)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

    try:
        if drop_existing:
            logger.warning("Dropping existing tables...")
            await conn.execute(DROP_STATEMENTS)
            logger.info("Existing tables dropped")

        logger.info("Creating agents table...")
        await conn.execute(CREATE_AGENTS_TABLE)

        logger.info("Creating customers table...")
        await conn.execute(CREATE_CUSTOMERS_TABLE)

        logger.info("Creating consultation_sessions table...")
        await conn.execute(CREATE_CONSULTATION_SESSIONS_TABLE)

        logger.info("Creating consultation_transcripts table...")
        await conn.execute(CREATE_CONSULTATION_TRANSCRIPTS_TABLE)

        logger.info("Creating consultation_agent_results table...")
        await conn.execute(CREATE_CONSULTATION_AGENT_RESULTS_TABLE)

        logger.info("Creating consultation_session_summary view...")
        await conn.execute(CREATE_SESSION_SUMMARY_VIEW)

        logger.info("Creating end_consultation_session function...")
        await conn.execute(CREATE_END_SESSION_FUNCTION)

        logger.info("Schema initialization completed successfully!")

        # 테이블 확인
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        logger.info(f"Created tables: {[t['table_name'] for t in tables]}")

    except Exception as e:
        logger.error(f"Failed to initialize schema: {e}")
        raise
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Initialize database schema")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating"
    )
    args = parser.parse_args()

    asyncio.run(init_schema(drop_existing=args.drop))


if __name__ == "__main__":
    main()
