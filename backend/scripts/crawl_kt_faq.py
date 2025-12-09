"""KT 멤버십 FAQ 크롤러.

KT 멤버십 FAQ 페이지를 크롤링하여 JSON 파일로 저장합니다.

Usage:
    cd backend
    uv run python scripts/crawl_kt_faq.py
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

FAQ_URL = "https://membership.kt.com/guide/faq/FAQList.do"
OUTPUT_DIR = Path(__file__).parent.parent.parent / "data" / "kt_faq"


async def wait_for_page_load(page: Page, timeout: int = 10000):
    """페이지 로드 대기."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        await asyncio.sleep(2)


async def get_faq_iframe(page: Page) -> Optional[Page]:
    """FAQ 컨텐츠가 있는 iframe을 찾습니다."""
    frames = page.frames
    for frame in frames:
        content = await frame.content()
        if "faq" in content.lower() or "등급" in content:
            return frame
    return page


async def extract_faq_items(page: Page) -> list[dict]:
    """현재 페이지의 FAQ 항목들을 추출합니다."""
    faqs = []

    # FAQ 리스트 아이템 찾기
    items = await page.query_selector_all("li.faq-item, ul.faq-list > li, .accordion-item, [class*='faq'] li")

    if not items:
        # 대안: 모든 li 요소에서 FAQ 패턴 찾기
        items = await page.query_selector_all("li")

    logger.info(f"Found {len(items)} potential FAQ items")

    for idx, item in enumerate(items):
        try:
            # 질문 텍스트 추출
            question_el = await item.query_selector("a, button, .question, [class*='title'], p:nth-child(2)")
            if not question_el:
                continue

            question_text = await question_el.inner_text()
            question_text = question_text.strip()

            if not question_text or len(question_text) < 5:
                continue

            # 카테고리 추출
            category_el = await item.query_selector(".category, .tag, p:first-child, span:first-child")
            category = ""
            if category_el:
                category = await category_el.inner_text()
                category = category.strip()
                # 질문에서 카테고리 제거
                if category and question_text.startswith(category):
                    question_text = question_text[len(category):].strip()

            # 클릭하여 답변 확장
            clickable = await item.query_selector("a, button, [class*='toggle'], [class*='accordion']")
            if clickable:
                try:
                    await clickable.click()
                    await asyncio.sleep(0.5)
                except Exception:
                    pass

            # 답변 텍스트 추출
            answer_el = await item.query_selector(".answer, .content, .panel, [class*='answer'], [class*='content']")
            answer_text = ""
            if answer_el:
                answer_text = await answer_el.inner_text()
                answer_text = answer_text.strip()

            if question_text:
                faq = {
                    "id": f"kt_faq_{idx + 1}",
                    "category": category,
                    "question": question_text,
                    "answer": answer_text,
                }
                faqs.append(faq)
                logger.info(f"Extracted: [{category}] {question_text[:50]}...")

        except Exception as e:
            logger.warning(f"Error extracting FAQ item {idx}: {e}")
            continue

    return faqs


async def extract_faq_from_snapshot(page: Page) -> list[dict]:
    """스냅샷 기반으로 FAQ 추출 (대안 방법)."""
    faqs = []

    # JavaScript로 FAQ 데이터 직접 추출
    try:
        result = await page.evaluate("""
            () => {
                const faqs = [];
                const items = document.querySelectorAll('li');

                items.forEach((item, idx) => {
                    const links = item.querySelectorAll('a');
                    links.forEach(link => {
                        const text = link.innerText.trim();
                        if (text.length > 10) {
                            // 카테고리와 질문 분리
                            const paragraphs = link.querySelectorAll('p');
                            let category = '';
                            let question = text;

                            if (paragraphs.length >= 2) {
                                category = paragraphs[0].innerText.trim();
                                question = paragraphs[1].innerText.trim();
                            }

                            faqs.push({
                                category: category,
                                question: question,
                                answer: ''
                            });
                        }
                    });
                });

                return faqs;
            }
        """)

        for idx, item in enumerate(result):
            item["id"] = f"kt_faq_{idx + 1}"
            faqs.append(item)

    except Exception as e:
        logger.warning(f"JavaScript extraction failed: {e}")

    return faqs


async def get_total_pages(page: Page) -> int:
    """총 페이지 수를 반환합니다."""
    try:
        # 페이지네이션 요소 찾기
        pagination = await page.query_selector_all(".pagination a, .paging a, [class*='page'] a")
        if pagination:
            max_page = 1
            for el in pagination:
                text = await el.inner_text()
                try:
                    page_num = int(text.strip())
                    max_page = max(max_page, page_num)
                except ValueError:
                    continue
            return max_page
    except Exception:
        pass
    return 7  # 기본값 (이전 분석에서 7페이지 확인)


async def go_to_page(page: Page, page_num: int):
    """특정 페이지로 이동합니다."""
    try:
        # 페이지 번호 클릭
        pagination_link = await page.query_selector(f".pagination a:has-text('{page_num}'), .paging a:has-text('{page_num}')")
        if pagination_link:
            await pagination_link.click()
            await wait_for_page_load(page)
            return True

        # JavaScript로 페이지 이동 시도
        await page.evaluate(f"goPage({page_num})")
        await wait_for_page_load(page)
        return True

    except Exception as e:
        logger.warning(f"Failed to navigate to page {page_num}: {e}")
        return False


async def crawl_faq_with_clicks(browser: Browser) -> list[dict]:
    """클릭 기반 FAQ 크롤링."""
    all_faqs = []
    page = await browser.new_page()

    try:
        logger.info(f"Navigating to {FAQ_URL}")
        await page.goto(FAQ_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)  # 페이지 완전 로드 대기

        # iframe 내부 접근
        frame = await get_faq_iframe(page)

        total_pages = await get_total_pages(frame)
        logger.info(f"Total pages: {total_pages}")

        for page_num in range(1, total_pages + 1):
            logger.info(f"Processing page {page_num}/{total_pages}")

            if page_num > 1:
                success = await go_to_page(frame, page_num)
                if not success:
                    logger.warning(f"Skipping page {page_num}")
                    continue

            # 현재 페이지 FAQ 추출
            page_faqs = await extract_faq_items(frame)

            if not page_faqs:
                # 대안 방법 시도
                page_faqs = await extract_faq_from_snapshot(frame)

            # ID 재할당
            start_idx = len(all_faqs)
            for idx, faq in enumerate(page_faqs):
                faq["id"] = f"kt_faq_{start_idx + idx + 1}"
                faq["page"] = page_num

            all_faqs.extend(page_faqs)
            logger.info(f"Page {page_num}: extracted {len(page_faqs)} FAQs")

            await asyncio.sleep(1)  # 요청 간 딜레이

    except Exception as e:
        logger.error(f"Crawling error: {e}")
        raise
    finally:
        await page.close()

    return all_faqs


async def crawl_faq_direct(browser: Browser) -> list[dict]:
    """직접 DOM 파싱으로 FAQ 크롤링."""
    all_faqs = []
    page = await browser.new_page()

    try:
        logger.info(f"Navigating to {FAQ_URL}")
        await page.goto(FAQ_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # 페이지 스냅샷 저장 (디버깅용)
        content = await page.content()
        debug_file = OUTPUT_DIR / "debug_page.html"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        debug_file.write_text(content, encoding="utf-8")
        logger.info(f"Saved debug HTML to {debug_file}")

        # 모든 페이지를 순회하며 FAQ 수집
        for page_num in range(1, 8):  # 7페이지
            logger.info(f"Processing page {page_num}/7")

            # JavaScript로 페이지 이동
            if page_num > 1:
                try:
                    await page.evaluate(f"goPage({page_num})")
                    await asyncio.sleep(2)
                except Exception:
                    # 페이지네이션 링크 클릭 시도
                    try:
                        await page.click(f"text='{page_num}'")
                        await asyncio.sleep(2)
                    except Exception:
                        logger.warning(f"Could not navigate to page {page_num}")
                        continue

            # FAQ 항목 추출
            items = await page.evaluate("""
                () => {
                    const faqs = [];
                    // 여러 선택자 시도
                    const selectors = [
                        'ul li a',
                        '.faq-list li a',
                        '[class*="faq"] li a',
                        'li a'
                    ];

                    for (const selector of selectors) {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            const text = el.innerText.trim();
                            // FAQ 패턴 감지 (질문 형태)
                            if (text.includes('?') || text.includes('나요') || text.includes('까요') ||
                                text.includes('어떻게') || text.includes('무엇') || text.length > 20) {

                                const paragraphs = el.querySelectorAll('p');
                                let category = '';
                                let question = text;

                                if (paragraphs.length >= 2) {
                                    category = paragraphs[0].innerText.trim();
                                    question = paragraphs[1].innerText.trim();
                                }

                                // 중복 체크
                                if (!faqs.some(f => f.question === question)) {
                                    faqs.push({ category, question });
                                }
                            }
                        });

                        if (faqs.length > 0) break;
                    }

                    return faqs;
                }
            """)

            for item in items:
                item["id"] = f"kt_faq_{len(all_faqs) + 1}"
                item["page"] = page_num
                item["answer"] = ""  # 답변은 별도 크롤링 필요
                all_faqs.append(item)

            logger.info(f"Page {page_num}: found {len(items)} items, total: {len(all_faqs)}")

    except Exception as e:
        logger.error(f"Direct crawling error: {e}")
        raise
    finally:
        await page.close()

    return all_faqs


async def fetch_faq_answers(browser: Browser, faqs: list[dict]) -> list[dict]:
    """각 FAQ의 답변을 가져옵니다."""
    page = await browser.new_page()

    try:
        await page.goto(FAQ_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        for faq in faqs:
            if faq.get("answer"):
                continue

            question = faq["question"]
            try:
                # 질문 텍스트로 요소 찾기
                element = await page.query_selector(f"text='{question[:30]}'")
                if element:
                    await element.click()
                    await asyncio.sleep(0.5)

                    # 답변 컨텐츠 찾기
                    answer_el = await page.query_selector(".answer, .content, [class*='answer']")
                    if answer_el:
                        answer = await answer_el.inner_text()
                        faq["answer"] = answer.strip()
                        logger.info(f"Got answer for: {question[:30]}...")

            except Exception as e:
                logger.warning(f"Could not get answer for: {question[:30]}... - {e}")
                continue

    finally:
        await page.close()

    return faqs


async def main():
    """메인 크롤링 함수."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            # FAQ 크롤링
            logger.info("Starting FAQ crawl...")
            faqs = await crawl_faq_direct(browser)

            if not faqs:
                logger.warning("Direct crawl returned no results, trying click-based method...")
                faqs = await crawl_faq_with_clicks(browser)

            if not faqs:
                logger.error("No FAQs found!")
                return

            # 답변 수집 (선택적)
            # faqs = await fetch_faq_answers(browser, faqs)

            # 결과 저장
            output_file = OUTPUT_DIR / "kt_membership_faq.json"

            result = {
                "source": FAQ_URL,
                "crawled_at": datetime.now().isoformat(),
                "total_count": len(faqs),
                "faqs": faqs
            }

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"Saved {len(faqs)} FAQs to {output_file}")

            # 카테고리별 통계
            categories = {}
            for faq in faqs:
                cat = faq.get("category", "미분류")
                categories[cat] = categories.get(cat, 0) + 1

            logger.info("Category distribution:")
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                logger.info(f"  {cat}: {count}")

        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
