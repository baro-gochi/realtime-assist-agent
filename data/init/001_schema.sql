-- 실시간 상담 어시스턴트 데이터베이스 스키마
-- PostgreSQL 17 + pgvector

-- 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";  -- pgvector for embeddings

-- ============================================
-- 1. 상담 세션(룸) 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS rooms (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(50) DEFAULT 'active',  -- active, ended
    metadata JSONB DEFAULT '{}'::jsonb,

    CONSTRAINT rooms_room_name_created_unique UNIQUE (room_name, created_at)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_rooms_room_name ON rooms(room_name);
CREATE INDEX IF NOT EXISTS idx_rooms_status ON rooms(status);
CREATE INDEX IF NOT EXISTS idx_rooms_created_at ON rooms(created_at DESC);

-- ============================================
-- 2. 참가자(피어) 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS peers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    peer_id VARCHAR(255) NOT NULL,  -- WebSocket에서 할당된 UUID
    nickname VARCHAR(255) NOT NULL,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    left_at TIMESTAMP WITH TIME ZONE,

    CONSTRAINT peers_room_peer_unique UNIQUE (room_id, peer_id)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_peers_room_id ON peers(room_id);
CREATE INDEX IF NOT EXISTS idx_peers_peer_id ON peers(peer_id);

-- ============================================
-- 3. 대화 내용(Transcript) 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS transcripts (
    id BIGSERIAL PRIMARY KEY,
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    peer_id VARCHAR(255) NOT NULL,
    nickname VARCHAR(255) NOT NULL,
    text TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    source VARCHAR(50) DEFAULT 'google',  -- STT 소스 (google, whisper 등)
    is_final BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_transcripts_room_id ON transcripts(room_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_timestamp ON transcripts(timestamp);
CREATE INDEX IF NOT EXISTS idx_transcripts_room_timestamp ON transcripts(room_id, timestamp);

-- ============================================
-- 4. 에이전트 요약 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS agent_summaries (
    id BIGSERIAL PRIMARY KEY,
    room_id UUID NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    last_summarized_index INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_agent_summaries_room_id ON agent_summaries(room_id);
CREATE INDEX IF NOT EXISTS idx_agent_summaries_created_at ON agent_summaries(created_at DESC);

-- ============================================
-- 5. 시스템 로그 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS system_logs (
    id BIGSERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,  -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    logger_name VARCHAR(255),
    message TEXT NOT NULL,
    module VARCHAR(255),
    func_name VARCHAR(255),
    line_no INTEGER,
    exception TEXT,
    extra JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_system_logs_logger_name ON system_logs(logger_name);

-- 파티셔닝을 위한 인덱스 (대용량 로그 처리시 활용)
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at_level ON system_logs(created_at DESC, level);

-- ============================================
-- 뷰: 룸별 대화 요약
-- ============================================
CREATE OR REPLACE VIEW room_conversation_summary AS
SELECT
    r.id AS room_id,
    r.room_name,
    r.created_at AS room_created,
    r.ended_at AS room_ended,
    r.status,
    COUNT(DISTINCT p.peer_id) AS participant_count,
    COUNT(t.id) AS message_count,
    MIN(t.timestamp) AS first_message_at,
    MAX(t.timestamp) AS last_message_at,
    EXTRACT(EPOCH FROM (COALESCE(r.ended_at, NOW()) - r.created_at)) / 60 AS duration_minutes
FROM rooms r
LEFT JOIN peers p ON r.id = p.room_id
LEFT JOIN transcripts t ON r.id = t.room_id
GROUP BY r.id, r.room_name, r.created_at, r.ended_at, r.status;

-- ============================================
-- 함수: 오래된 로그 정리 (3일 이상)
-- ============================================
CREATE OR REPLACE FUNCTION cleanup_old_logs(days_to_keep INTEGER DEFAULT 3)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM system_logs
    WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 코멘트
COMMENT ON TABLE rooms IS '상담 세션(룸) 정보';
COMMENT ON TABLE peers IS '상담 참가자 정보';
COMMENT ON TABLE transcripts IS 'STT 인식 대화 내용';
COMMENT ON TABLE agent_summaries IS 'LangGraph 에이전트 요약 결과';
COMMENT ON TABLE system_logs IS '시스템 로그 저장';
COMMENT ON VIEW room_conversation_summary IS '룸별 대화 요약 뷰';
COMMENT ON FUNCTION cleanup_old_logs IS '3일 지난 로그 정리 함수';
