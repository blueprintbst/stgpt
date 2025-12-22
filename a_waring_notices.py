import feedparser
import requests
import re
import json
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

DATA_FILE = "a_waring_notices.json"
MAX_DAYS = 10

# ---------------------------
# JSON 저장/불러오기
# ---------------------------
def load_notices():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_notices(all_data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

def add_notice(notice):
    all_data = load_notices()

    cutoff_date = datetime.now() - timedelta(days=MAX_DAYS)

    filtered = []
    seen = set()  # (title, date) 중복 체크
    for n in all_data:
        try:
            n_date = datetime.strptime(n["date"], "%Y-%m-%d")
            if n_date >= cutoff_date:
                key = (n["title"], n["date"])
                if key not in seen:
                    filtered.append(n)
                    seen.add(key)
        except Exception:
            # date 파싱 실패 데이터는 그냥 보관
            filtered.append(n)

    key_new = (notice["title"], notice["date"])
    if key_new not in seen:
        filtered.append(notice)

    save_notices(filtered)

# ---------------------------
# 시장 구분 + 접두사 제거
# ---------------------------
_market_pat = re.compile(r"^\s*\[(유|코)\]")

def parse_market_class(title: str):
    m = _market_pat.match(title)
    if not m:
        return None
    return "코스피" if m.group(1) == "유" else "코스닥"

def clean_title(title: str) -> str:
    return re.sub(r"^\s*\[(유|코)\]\s*", "", title).strip()

# ---------------------------
# 폴백 유틸
# ---------------------------
def guess_name_from_title(title: str) -> str:
    """
    제목에서 '회사명 ...' 형태로 첫 토큰을 종목명으로 추정
    """
    t = clean_title(title)
    if not t:
        return ""
    # 보통 회사명이 맨 앞
    return t.split()[0].strip()

def extract_code_from_viewer_html(html: str) -> str:
    """
    KIND 뷰어 페이지 소스에서 종목코드 후보를 추출.
    (repIsuSrtCd / isuSrtCd / isuCd 등)
    """
    patterns = [
        r'(repIsuSrtCd|isuSrtCd|isuCd)\s*=\s*[\'"]([0-9A-Za-z]+)[\'"]',
        r'name=["\'](repIsuSrtCd|isuSrtCd|isuCd)["\']\s+value=["\']([0-9A-Za-z]+)["\']',
        r'id=["\'](repIsuSrtCd|isuSrtCd|isuCd)["\']\s+value=["\']([0-9A-Za-z]+)["\']',
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return (m.group(2) or "").strip()
    return ""

def extract_name_code_from_h1(soup: BeautifulSoup) -> tuple[str, str]:
    """
    뷰어 상단 h1에서 '종목명 (코드)' 형태 파싱.
    class 매칭은 select_one로 (순서/추가클래스 변화에 강함)
    """
    h1 = soup.select_one("h1.ttl.type-99.fleft")
    if not h1:
        # 혹시 클래스가 살짝 다르면, ttl만이라도 시도
        h1 = soup.select_one("h1.ttl")
    if not h1:
        return "", ""

    text = h1.get_text(strip=True)
    m = re.match(r"(.+?)\s+\(([0-9A-Za-z]+)\)", text)
    if not m:
        return "", ""
    return (m.group(1) or "").strip(), (m.group(2) or "").strip()

# ---------------------------
# 본문 + 종목명/코드 추출
# ---------------------------
def extract_text_from_rss(rss_url: str, fallback_title: str = "") -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}

    with requests.Session() as s:
        # 1) 뷰어 페이지
        r = s.get(rss_url, headers=headers, timeout=10)
        r.raise_for_status()

        soup0 = BeautifulSoup(r.text, "html.parser")

        # (A) 1차: h1에서 종목명/코드
        stock_name, stock_code = extract_name_code_from_h1(soup0)

        # (B) 2차: 뷰어 HTML 소스에서 코드 폴백
        if not stock_code:
            stock_code = extract_code_from_viewer_html(r.text)

        # (C) 3차: RSS 제목에서 종목명 폴백
        if not stock_name and fallback_title:
            stock_name = guess_name_from_title(fallback_title)

        # (D) 4차: 제목에 '회사명 (CODE)'가 박혀있다면 거기서도 폴백(영숫자)
        if fallback_title and (not stock_name or not stock_code):
            t = clean_title(fallback_title)
            m = re.match(r"(.+?)\s+\(([0-9A-Za-z]+)\)", t)
            if m:
                if not stock_name:
                    stock_name = (m.group(1) or "").strip()
                if not stock_code:
                    stock_code = (m.group(2) or "").strip()

        # 2) docNo 추출
        m = re.search(r"value=['\"](\d{14})\|[YN]['\"]", r.text)
        if not m:
            raise ValueError("docNo를 찾지 못했어요.")
        doc_no = m.group(1)

        # 3) 내부 API
        api_url = "https://kind.krx.co.kr/common/disclsviewer.do"
        r2 = s.get(
            api_url,
            headers=headers,
            params={"method": "searchContents", "docNo": doc_no},
            timeout=10,
        )
        r2.raise_for_status()

        # 4) 프레임소스 경로
        m2 = re.search(r'(/external/[^"\']+\.htm)', r2.text)
        if not m2:
            raise ValueError("docLocPath를 찾지 못했어요.")
        frame_url = urljoin(api_url, m2.group(1))

        # 5) 프레임소스 HTML
        r3 = s.get(frame_url, headers=headers, timeout=10)
        r3.raise_for_status()

        if not r3.encoding or r3.encoding.lower() in ("iso-8859-1", "us-ascii"):
            r3.encoding = r3.apparent_encoding or "utf-8"

        soup = BeautifulSoup(r3.text, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return {
            "frame_url": frame_url,
            "text": text,
            "stock_name": stock_name,
            "stock_code": stock_code,
        }

# ---------------------------
# 투자경고예고분류 규칙
# ---------------------------
RULES = {
    "초단기예고": ["종가가 3일 전일의 종가보다 100% 이상 상승"],
    "단기예고": ["종가가 5일 전일의 종가보다 60% 이상 상승"],
    "단기불건전예고": ["종가가 5일 전일의 종가보다 45% 이상 상승", "__INVEST_FLAG__"],
    "장기예고": ["종가가 15일 전일의 종가보다 100% 이상 상승"],
    "초장기불건전예고": ["종가가 1년 전의 종가보다 200% 이상 상승", "__INVEST_FLAG__"],
}

def has_invest_flag(text: str) -> bool:
    return bool(re.search(r"투자경고종목\s*지정여부.*\[\d\]\s*중\s*③", text))

def classify_notice(text: str):
    matched = []
    for rule_name, keywords in RULES.items():
        ok = True
        for kw in keywords:
            if kw == "__INVEST_FLAG__":
                if not has_invest_flag(text):
                    ok = False
                    break
            else:
                if kw not in text:
                    ok = False
                    break
        if ok:
            matched.append(rule_name)
    return matched

# ---------------------------
# 메인 실행
# ---------------------------
if __name__ == "__main__":
    RSS_URL = (
        "http://kind.krx.co.kr:80/disclosure/rsstodaydistribute.do?"
        "method=searchRssTodayDistribute&repIsuSrtCd=&mktTpCd=0&"
        "searchCorpName=&currentPageSize=50"
    )
    feed = feedparser.parse(RSS_URL)

    keywords = [
        "투자경고종목 지정예고",
        "투자경고종목 지정해제 및 재지정 예고",
        "투자경고종목지정(재지정)",
        "투자경고종목지정",
    ]
    filtered = [e for e in feed.entries if any(k in e.title for k in keywords)]

    for e in filtered:
        market_class = parse_market_class(e.title)
        if not market_class:
            print(f"⏭️ 접두사 없음(저장 스킵): {e.title}")
            continue

        print(f"\n▶ {e.title} ({market_class})")

        try:
            # ⭐ fallback_title로 RSS 제목을 넘겨서 종목명/코드 폴백 가능하게 함
            result = extract_text_from_rss(e.link, fallback_title=e.title)

            stock_name = result["stock_name"]
            stock_code = result["stock_code"]
            frame_url = result["frame_url"]

            if "투자경고종목 지정해제 및 재지정 예고" in e.title:
                categories = ["지정해제 및 재지정 예고"]
            elif "투자경고종목 지정예고" in e.title:
                categories = classify_notice(result["text"])
            elif "투자경고종목지정(재지정)" in e.title:
                categories = ["재지정"]
            elif "투자경고종목지정" in e.title:
                categories = ["지정"]
            else:
                categories = []

            print("프레임소스:", frame_url)
            print("종목:", stock_name or "(없음)", stock_code or "(없음)")
            print("분류:", ", ".join(categories) if categories else "분류 없음")

        except Exception as ex:
            print("본문 추출 실패:", ex)
            stock_name, stock_code, frame_url, categories = "", "", "", []

        notice_data = {
            "title": clean_title(e.title),
            "class": market_class,
            "stock_name": stock_name,
            "stock_code": stock_code,
            "link": e.link,
            "frame_url": frame_url,
            "categories": categories,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        add_notice(notice_data)
        print("저장 완료 ✅")
