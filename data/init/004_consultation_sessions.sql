-- 상담 세션 및 에이전트 결과 테이블 스키마
-- 상담 이력, 통화 전사, 에이전트 분석 결과를 분리 저장

-- ============================================
-- 1. 상담 세션 테이블 (메인)
-- ============================================
CREATE TABLE IF NOT EXISTS consultation_sessions (
    session_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- WebRTC 룸 연결 (nullable - 룸 없이 생성 가능)
    room_id UUID REFERENCES rooms(id) ON DELETE SET NULL,

    -- 고객 정보 (nullable - 미확인 고객 가능)
    customer_id BIGINT REFERENCES customers(customer_id) ON DELETE SET NULL,

    -- 상담사 정보
    agent_id VARCHAR(100),
    agent_name VARCHAR(100) NOT NULL,

    -- 시간 정보
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    duration_seconds INTEGER,

    -- 상담 상태
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, transferred, abandoned
    channel VARCHAR(20) DEFAULT 'call',   -- call, chat

    -- 요약 및 메타데이터
    final_summary TEXT,
    consultation_type VARCHAR(50),  -- 요금문의, 해지문의, 기술장애 등
    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_cs_room_id ON consultation_sessions(room_id);
CREATE INDEX IF NOT EXISTS idx_cs_customer_id ON consultation_sessions(customer_id);
CREATE INDEX IF NOT EXISTS idx_cs_agent_id ON consultation_sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_cs_status ON consultation_sessions(status);
CREATE INDEX IF NOT EXISTS idx_cs_started_at ON consultation_sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_cs_consultation_type ON consultation_sessions(consultation_type);

-- ============================================
-- 2. 통화 전사 테이블 (STT 결과)
-- ============================================
CREATE TABLE IF NOT EXISTS consultation_transcripts (
    transcript_id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES consultation_sessions(session_id) ON DELETE CASCADE,

    -- 발화 순서
    turn_index INTEGER NOT NULL,

    -- 발화자 정보
    speaker_type VARCHAR(20) NOT NULL,  -- agent, customer
    speaker_name VARCHAR(100),

    -- 발화 내용
    text TEXT NOT NULL,

    -- 시간 정보
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,

    -- STT 메타데이터
    confidence FLOAT,  -- STT 신뢰도 (0.0 ~ 1.0)
    is_final BOOLEAN DEFAULT TRUE,
    source VARCHAR(50) DEFAULT 'google',  -- google, whisper 등

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT ct_session_turn_unique UNIQUE (session_id, turn_index)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_ct_session_id ON consultation_transcripts(session_id);
CREATE INDEX IF NOT EXISTS idx_ct_timestamp ON consultation_transcripts(timestamp);
CREATE INDEX IF NOT EXISTS idx_ct_speaker_type ON consultation_transcripts(speaker_type);

-- ============================================
-- 3. 에이전트 분석 결과 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS consultation_agent_results (
    result_id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES consultation_sessions(session_id) ON DELETE CASCADE,

    -- 연관된 turn (nullable - 전체 세션 결과일 수 있음)
    turn_id VARCHAR(50),  -- "turn_1", "turn_5" 등

    -- 결과 타입
    result_type VARCHAR(30) NOT NULL,  -- intent, sentiment, summary, draft, risk, rag, faq

    -- 결과 데이터 (JSONB)
    result_data JSONB NOT NULL,

    -- 메타데이터
    processing_time_ms INTEGER,  -- 처리 시간
    model_version VARCHAR(50),   -- 사용된 모델 버전

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_car_session_id ON consultation_agent_results(session_id);
CREATE INDEX IF NOT EXISTS idx_car_result_type ON consultation_agent_results(result_type);
CREATE INDEX IF NOT EXISTS idx_car_turn_id ON consultation_agent_results(turn_id);
CREATE INDEX IF NOT EXISTS idx_car_created_at ON consultation_agent_results(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_car_result_data ON consultation_agent_results USING gin (result_data);

-- ============================================
-- 뷰: 상담 세션 요약
-- ============================================
CREATE OR REPLACE VIEW consultation_session_summary AS
SELECT
    cs.session_id,
    cs.started_at,
    cs.ended_at,
    cs.duration_seconds,
    cs.status,
    cs.channel,
    cs.consultation_type,
    cs.agent_name,
    c.customer_name,
    c.phone_number,
    c.membership_grade,
    COUNT(DISTINCT ct.transcript_id) AS transcript_count,
    COUNT(DISTINCT car.result_id) AS agent_result_count,
    cs.final_summary
FROM consultation_sessions cs
LEFT JOIN customers c ON cs.customer_id = c.customer_id
LEFT JOIN consultation_transcripts ct ON cs.session_id = ct.session_id
LEFT JOIN consultation_agent_results car ON cs.session_id = car.session_id
GROUP BY
    cs.session_id, cs.started_at, cs.ended_at, cs.duration_seconds,
    cs.status, cs.channel, cs.consultation_type, cs.agent_name,
    c.customer_name, c.phone_number, c.membership_grade, cs.final_summary;

-- ============================================
-- 뷰: 세션별 에이전트 결과 요약
-- ============================================
CREATE OR REPLACE VIEW session_agent_results_summary AS
SELECT
    cs.session_id,
    cs.agent_name,
    cs.started_at,
    -- Intent 결과
    (SELECT result_data->>'intent'
     FROM consultation_agent_results
     WHERE session_id = cs.session_id AND result_type = 'intent'
     ORDER BY created_at DESC LIMIT 1) AS latest_intent,
    -- Sentiment 결과
    (SELECT result_data->>'sentiment'
     FROM consultation_agent_results
     WHERE session_id = cs.session_id AND result_type = 'sentiment'
     ORDER BY created_at DESC LIMIT 1) AS latest_sentiment,
    -- Summary 결과
    (SELECT result_data->>'summary'
     FROM consultation_agent_results
     WHERE session_id = cs.session_id AND result_type = 'summary'
     ORDER BY created_at DESC LIMIT 1) AS latest_summary,
    -- RAG 검색 횟수
    (SELECT COUNT(*)
     FROM consultation_agent_results
     WHERE session_id = cs.session_id AND result_type = 'rag') AS rag_search_count,
    -- FAQ 검색 횟수
    (SELECT COUNT(*)
     FROM consultation_agent_results
     WHERE session_id = cs.session_id AND result_type = 'faq') AS faq_search_count
FROM consultation_sessions cs;

-- ============================================
-- 함수: 상담 세션 종료 처리
-- ============================================
CREATE OR REPLACE FUNCTION end_consultation_session(
    p_session_id UUID,
    p_final_summary TEXT DEFAULT NULL,
    p_consultation_type VARCHAR(50) DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_started_at TIMESTAMP WITH TIME ZONE;
BEGIN
    -- 시작 시간 조회
    SELECT started_at INTO v_started_at
    FROM consultation_sessions
    WHERE session_id = p_session_id;

    IF v_started_at IS NULL THEN
        RETURN FALSE;
    END IF;

    -- 세션 종료 업데이트
    UPDATE consultation_sessions
    SET
        ended_at = NOW(),
        duration_seconds = EXTRACT(EPOCH FROM (NOW() - v_started_at))::INTEGER,
        status = 'completed',
        final_summary = COALESCE(p_final_summary, final_summary),
        consultation_type = COALESCE(p_consultation_type, consultation_type)
    WHERE session_id = p_session_id;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- 함수: 세션의 전체 대화 내용 조회
-- ============================================
CREATE OR REPLACE FUNCTION get_session_conversation(p_session_id UUID)
RETURNS TABLE (
    turn_index INTEGER,
    speaker_type VARCHAR(20),
    speaker_name VARCHAR(100),
    text TEXT,
    timestamp TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ct.turn_index,
        ct.speaker_type,
        ct.speaker_name,
        ct.text,
        ct.timestamp
    FROM consultation_transcripts ct
    WHERE ct.session_id = p_session_id
    ORDER BY ct.turn_index ASC;
END;
$$ LANGUAGE plpgsql;

-- 코멘트
COMMENT ON TABLE consultation_sessions IS '상담 세션 메인 테이블 - 상담 기본 정보';
COMMENT ON TABLE consultation_transcripts IS '통화 전사 테이블 - STT 결과 저장';
COMMENT ON TABLE consultation_agent_results IS '에이전트 분석 결과 - intent, sentiment, summary, rag, faq 등';
COMMENT ON VIEW consultation_session_summary IS '상담 세션 요약 뷰';
COMMENT ON VIEW session_agent_results_summary IS '세션별 에이전트 결과 요약 뷰';
COMMENT ON FUNCTION end_consultation_session IS '상담 세션 종료 처리 함수';
COMMENT ON FUNCTION get_session_conversation IS '세션의 전체 대화 내용 조회 함수';
