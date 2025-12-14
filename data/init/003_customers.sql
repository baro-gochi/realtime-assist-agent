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
    membership_grade, current_plan, monthly_fee, contract_status, bundle_info
) VALUES
('윤지현', '010-2222-3333', 29, '여', '서울시 성동구', 'VIP', '5G 슈퍼플랜 스페셜 89,000원', 89000, '무약정 (24개월 만료)', '없음 (단독 회선)'),
('김동훈', '010-8888-9999', 47, '남', '경기도 용인시 수지구', 'VVIP', '5G 프라임 100,000원', 285000, '인터넷 무약정 / 휴대폰 약정 중', '온가족결합 4회선 (인터넷+TV+휴대폰4)'),
('김순자', '010-3456-7890', 68, '여', '서울시 강서구', 'GENERAL', '인터넷 500M + 올레TV 베이직', 48000, '3년 약정 중 (2026-05 만료)', '인터넷+TV 결합'),
('이준혁', '010-1234-5678', 35, '남', '서울시 강남구', 'VIP', '5G 슈퍼플랜 베이직 95,000원', 95000, '약정 4개월 남음', '없음 (단독 회선)'),
('박미영', '010-5555-6666', 45, '여', '경기도 성남시 분당구', 'VIP', 'LTE 스탠다드 55,000원', 187000, '약정 중', '온가족결합 3회선 (인터넷+TV+휴대폰3)'),
('정태호', '010-9876-5432', 52, '남', '서울시 마포구', 'VIP', '기가 인터넷 1G + 업무용 휴대폰', 88000, '3년 약정 중', '인터넷 단독'),
('최서연', '010-1111-2222', 24, '여', '서울시 관악구', 'GENERAL', '5G 언리미티드 79,000원', 79000, '12개월 약정 중', '없음 (단독 회선)'),
('한승우', '010-7777-9999', 40, '남', '경기도 안양시', 'VVIP', '기업용 5G 프라임 (10회선)', 1250000, '2년 약정 중', '기업결합 (인터넷 전용선 + 법인폰 10회선)'),
('오민지', '010-3333-4444', 31, '여', '인천시 연수구', 'GENERAL', 'LTE 스탬다드 55,000원', 143000, '약정 만료 (무약정)', '인터넷+TV+휴대폰2 결합'),
('강현수', '010-6666-7777', 38, '남', '서울시 송파구', 'VIP', '5G 스탠다드 75,000원', 75000, '무약정', '없음 (단독 회선)')
ON CONFLICT DO NOTHING;

-- ============================================
-- 4. 상담 이력 초기 데이터
-- ============================================
-- 윤지현
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-08-15', '해외로밍',
'{"summary": "일본 출장 5일간 로밍 옵션 문의", "request": "baro 로밍과 현지 유심 비용 비교 요청", "action": "baro 로밍 매니아 5일권 신청 (44,000원), VIP 20% 할인 안내"}'::jsonb
FROM customers WHERE customer_name = '윤지현';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-01-22', '요금청구문의',
'{"summary": "12월 청구서 콘텐츠 이용료 4,400원 발생 원인 문의", "request": "결제한 기억 없음, 환불 요청", "action": "앱스토어 게임 결제 확인, 환불 불가 안내, 소액결제 차단 설정 완료"}'::jsonb
FROM customers WHERE customer_name = '윤지현';

-- 김동훈
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2023-11-08', '부가서비스',
'{"summary": "올레TV 스포츠 채널 패키지 추가 문의", "request": "SPOTV 시청 희망, 결합할인 영향 여부 확인", "action": "올레TV 스포츠팩 추가, 결합할인 영향 없음 안내, 첫 달 무료 적용"}'::jsonb
FROM customers WHERE customer_name = '김동훈';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-07-22', '요금제문의',
'{"summary": "둘째 자녀 Y틴 요금제 만료 후 전환 문의", "request": "Y틴 유지 조건, 자동 전환 여부, 결합 영향 확인", "action": "만 19세까지 유지 가능, 자동 전환 없음 안내, 생일 후 재상담 예약"}'::jsonb
FROM customers WHERE customer_name = '김동훈';

-- 김순자
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-05-10', '기술장애',
'{"summary": "TV 화면 신호없음 표시", "request": "TV 고장 여부 확인 요청", "action": "셋톱박스 전원 재부팅 단계별 안내, 고객이 직접 조치하여 정상화"}'::jsonb
FROM customers WHERE customer_name = '김순자';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-12-03', '요금청구문의',
'{"summary": "청구서 금액이 평소보다 높음", "request": "왜 비용이 올랐는지 설명 요청", "action": "TV 스포츠팩 무료 기간 종료로 11,000원 추가됨 안내, 해지 원할 시 재연락 안내"}'::jsonb
FROM customers WHERE customer_name = '김순자';

-- 이준혁
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-09-20', '요금제변경',
'{"summary": "데이터 사용량 대비 요금제가 비싸서 변경 문의", "request": "더 저렴한 요금제로 변경 요청, 위약금 확인", "action": "약정 잔여 4개월, 위약금 45,000원 안내, 만료 후 변경 권유, 알림 예약 설정"}'::jsonb
FROM customers WHERE customer_name = '이준혁';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-02-11', '멤버십문의',
'{"summary": "멤버십 포인트 사용처 문의", "request": "포인트 보유량, 사용 가능처 문의", "action": "12,500P 보유 안내, 영화관/카페/편의점 사용 가능, 앱 다운로드 링크 문자 발송"}'::jsonb
FROM customers WHERE customer_name = '이준혁';

-- 박미영
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-06-15', '요금청구문의',
'{"summary": "이번 달 요금이 4만원 더 나옴", "request": "청구 내역 상세 확인 요청", "action": "자녀 회선 데이터 추가결제 22,000원 + 결합 이탈로 할인율 감소, 데이터 차단 설정 완료"}'::jsonb
FROM customers WHERE customer_name = '박미영';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-03-08', '결합변경',
'{"summary": "시어머니 회선 타사 이동 후 결합할인 변동 문의", "request": "결합 재설계 시 더 유리한 구조 여부 확인", "action": "인터넷 1G 업그레이드 시 프리미엄 결합 적용으로 절감 가능 안내, 비교표 문자 발송"}'::jsonb
FROM customers WHERE customer_name = '박미영';

-- 정태호
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-08-22', '기술장애',
'{"summary": "인터넷 속도 느림", "request": "기사 방문 요청", "action": "원격 진단 후 공유기 문제 확인, 익일 기사 방문 예약, 공유기 무상 교체 완료"}'::jsonb
FROM customers WHERE customer_name = '정태호';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-03-12', '기술장애',
'{"summary": "점심시간 인터넷 장애로 카드결제 불가", "request": "즉시 복구 요청 및 보상 요구", "action": "지역 네트워크 장애 확인, 복구 예상시간 안내, 임시결제 앱 안내, 보상 절차 안내, 3일 요금 감면 처리"}'::jsonb
FROM customers WHERE customer_name = '정태호';

-- 최서연
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-01-05', '요금제문의',
'{"summary": "현재 요금제와 타사 요금제 비교 문의", "request": "KT vs SKT vs LGU+ 동일 가격대 비교 요청", "action": "KT 요금제 장점 설명, 타사 비교는 직접 확인 권유, 요금제 상세 링크 발송"}'::jsonb
FROM customers WHERE customer_name = '최서연';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-04-18', '프로모션문의',
'{"summary": "eSIM 전환 프로모션 여부 문의", "request": "듀얼심 사용 위해 eSIM 전환 희망", "action": "eSIM 전환 무료, 온라인 신청 가능 안내, 신청 링크/가이드 문자 발송"}'::jsonb
FROM customers WHERE customer_name = '최서연';

-- 한승우
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-11-20', '결합변경',
'{"summary": "신규 입사자 3명 법인폰 추가 문의", "request": "추가 회선 견적 및 결합 영향 확인", "action": "3회선 추가 시 결합할인율 15%->20% 상향 안내, 견적서 이메일 발송, 담당 매니저 배정"}'::jsonb
FROM customers WHERE customer_name = '한승우';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-02-28', '요금청구문의',
'{"summary": "2월 법인 청구서 세금계산서 재발행 요청", "request": "사업자번호 변경 반영 요청", "action": "기존 세금계산서 취소 후 새 번호로 재발행 완료, 이메일 발송"}'::jsonb
FROM customers WHERE customer_name = '한승우';

-- 오민지
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-10-05', '결합문의',
'{"summary": "결혼으로 배우자 회선 결합 문의", "request": "남편 번호이동 + 결합 시 혜택 확인 요청", "action": "번호이동 시 결합할인 + 프로모션(3개월 50% 할인) 안내, 예상 금액 시뮬레이션 제공"}'::jsonb
FROM customers WHERE customer_name = '오민지';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-04-02', '프로모션문의',
'{"summary": "신혼부부 대상 프로모션 있는지 문의", "request": "결혼 증빙 시 추가 혜택 여부 문의", "action": "현재 신혼 특별 프로모션 없음 안내, 결합회선 추가 시 할인율 상향 대체 제안"}'::jsonb
FROM customers WHERE customer_name = '오민지';

-- 강현수
INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2024-12-10', '해지문의',
'{"summary": "타사 프로모션이 더 좋아 해지 고려", "request": "KT 매칭 혜택 있는지 확인", "action": "이탈방어 프로모션 적용(6개월 월 15,000원 할인), VIP 유지 혜택 강조, 해지 보류"}'::jsonb
FROM customers WHERE customer_name = '강현수';

INSERT INTO consultation_history (customer_id, consultation_date, consultation_type, detail)
SELECT customer_id, '2025-03-25', '요금제문의',
'{"summary": "할인 기간 종료 후 요금 원복 불만", "request": "할인 연장 또는 추가 혜택 요청", "action": "추가 할인 불가 안내, 요금제 다운그레이드(5G 슬림 61,000원) 제안"}'::jsonb
FROM customers WHERE customer_name = '강현수';

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
