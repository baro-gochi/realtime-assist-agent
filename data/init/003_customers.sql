-- 고객 및 상담 이력 테이블 스키마
-- KT 멤버십 상담 시스템용

-- ============================================
-- 1. 고객 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGSERIAL PRIMARY KEY,
    customer_name VARCHAR(50) NOT NULL,
    phone_number VARCHAR(20),
    age INT,
    gender VARCHAR(10),
    residence VARCHAR(100),

    membership_grade VARCHAR(20),
    current_plan VARCHAR(200),
    monthly_fee INT,
    contract_status VARCHAR(100),
    bundle_info VARCHAR(200),
    data_allowance VARCHAR(50),
    subscription_date DATE,

    consultation_history JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(customer_name);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone_number);
CREATE INDEX IF NOT EXISTS idx_customers_grade ON customers(membership_grade);

-- ============================================
-- 2. 상담 이력 테이블
-- ============================================
CREATE TABLE IF NOT EXISTS consultation_history (
    consultation_id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,

    consultation_date DATE NOT NULL,
    consultation_type VARCHAR(50),

    detail JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_consultation_customer_id ON consultation_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_consultation_date ON consultation_history(consultation_date DESC);
CREATE INDEX IF NOT EXISTS idx_consultation_type ON consultation_history(consultation_type);
CREATE INDEX IF NOT EXISTS idx_consultation_detail ON consultation_history USING gin (detail);

COMMENT ON TABLE customers IS 'KT 고객 정보';
COMMENT ON TABLE consultation_history IS '고객별 상담 이력';

-- ============================================
-- 3. 고객 초기 데이터
-- ============================================
INSERT INTO customers (
    customer_name, phone_number, age, gender, residence,
    membership_grade, current_plan, monthly_fee, contract_status, bundle_info,
    data_allowance, subscription_date
) VALUES
('윤지훈', '010-2222-3333', 29, '남', '서울시 성동구', 'Gold', '인기LTE 데이터ON - 비디오 플러스 69,000원', 69000, '무약정 (24개월 만료)', '없음 (단독 회선)', '11GB + 3GB (소진 시 3Mbps)', '2022-08-15'),
('김동훈', '010-8888-9999', 47, '남', '경기도 용인시 수지구', 'VVIP', '5G 프라임 100,000원', 285000, '인터넷 무약정 / 휴대폰 약정 중', '온가족결합 4회선 (인터넷+TV+휴대폰4)', '무제한', '2019-03-22')
ON CONFLICT DO NOTHING;

-- ============================================
-- 4. 상담 이력 초기 데이터
-- ============================================
-- 윤지훈
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-08-15', '해외로밍',
'{"summary": "일본 출장 5일간 로밍 옵션 문의", "request": "baro 로밍과 현지 유심 비용 비교 요청", "action": "baro 로밍 매니아 5일권 신청 (44,000원), VIP 20% 할인 안내"}'::jsonb
FROM customers WHERE customer_name = '윤지훈';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-01-22', '요금청구문의',
'{"summary": "12월 청구서 콘텐츠 이용료 4,400원 발생 원인 문의", "request": "결제한 기억 없음, 환불 요청", "action": "앱스토어 게임 결제 확인, 환불 불가 안내, 소액결제 차단 설정 완료"}'::jsonb
FROM customers WHERE customer_name = '윤지훈';

-- 김동훈
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2023-11-08', '부가서비스',
'{"summary": "올레TV 스포츠 채널 패키지 추가 문의", "request": "SPOTV 시청 희망, 결합할인 영향 여부 확인", "action": "올레TV 스포츠팩 추가, 결합할인 영향 없음 안내, 첫 달 무료 적용"}'::jsonb
FROM customers WHERE customer_name = '김동훈';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-07-22', '요금제문의',
'{"summary": "둘째 자녀 Y틴 요금제 만료 후 전환 문의", "request": "Y틴 유지 조건, 자동 전환 여부, 결합 영향 확인", "action": "만 19세까지 유지 가능, 자동 전환 없음 안내, 생일 후 재상담 예약"}'::jsonb
FROM customers WHERE customer_name = '김동훈';

-- ============================================
-- 5. 뷰: 고객 상담 요약
-- ============================================
CREATE OR REPLACE VIEW customer_consultation_summary AS
SELECT
    c.customer_id,
    c.customer_name,
    c.phone_number,
    c.membership_grade,
    c.current_plan,
    c.monthly_fee,
    COUNT(ch.consultation_id) AS total_consultations,
    MAX(ch.consultation_date) AS last_consultation_date,
    ARRAY_AGG(DISTINCT ch.consultation_type) FILTER (WHERE ch.consultation_type IS NOT NULL) AS consultation_types
FROM customers c
LEFT JOIN consultation_history ch ON c.customer_id = ch.customer_id
GROUP BY c.customer_id, c.customer_name, c.phone_number, c.membership_grade, c.current_plan, c.monthly_fee;

COMMENT ON VIEW customer_consultation_summary IS '고객별 상담 요약 뷰';
