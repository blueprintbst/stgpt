# a_danger_notices.py
import feedparser
import requests
import re
import json
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

DATA_FILE = "a_danger_notices.json"
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

    # 오늘 기준 10일 전까지만 보관
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
            filtered.append(n)

    # 새 공시 추가
    key_new = (notice["title"], notice["date"])
    if key_new not in seen:
        filtered.append(notice)

    save_notices(filtered)

# ---------------------------
# 본문 + 종목명/코드 추출
# ---------------------------
def extract_text_from_rss(rss_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.Session() as s:
        # 1) 뷰어 페이지
        r = s.get(rss_url, headers=headers, timeout=10)
        r.raise_for_status()

        # 종목명/코드 추출 (뷰어 상단 h1)
        soup0 = BeautifulSoup(r.text, "html.parser")
        h1 = soup0.find("h1", class_="ttl type-99 fleft")
        stock_name, stock_code = "", ""
        if h1:
            m = re.match(r"(.+)\s+\((\d+)\)", h1.get_text(strip=True))
            if m:
                stock_name, stock_code = m.group(1), m.group(2)

        # 2) docNo 추출
        m = re.search(r"value=['\"](\d{14})\|[YN]['\"]", r.text)
        if not m:
            raise ValueError("docNo를 찾지 못했어요.")
        doc_no = m.group(1)

        # 3) 내부 API
        api_url = "https://kind.krx.co.kr/common/disclsviewer.do"
        r2 = s.get(api_url, headers=headers,
                   params={"method": "searchContents", "docNo": doc_no},
                   timeout=10)
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
# 메인 실행
# ---------------------------
if __name__ == "__main__":
    RSS_URL = (
        "http://kind.krx.co.kr:80/disclosure/rsstodaydistribute.do?"
        "method=searchRssTodayDistribute&repIsuSrtCd=&mktTpCd=0&"
        "searchCorpName=&currentPageSize=50"
    )
    feed = feedparser.parse(RSS_URL)

    # 필터 키워드
    keywords = [
        "투자위험종목 지정예고",
        "투자위험종목 지정",
        "투자위험종목 지정해제",
    ]
    filtered = [e for e in feed.entries if any(k in e.title for k in keywords)]

    for e in filtered:
        # 접두사 확인 (없으면 스킵)
        market_class = parse_market_class(e.title)
        if not market_class:
            print(f"⏭️ 접두사 없음(저장 스킵): {e.title}")
            continue

        print(f"\n▶ {e.title} ({market_class})")

        try:
            result = extract_text_from_rss(e.link)
            stock_name = result["stock_name"]
            stock_code = result["stock_code"]
            frame_url = result["frame_url"]

            # 분류
            if "투자위험종목 지정예고" in e.title:
                categories = ["투위예고"]
            elif "투자위험종목 지정해제" in e.title:
                categories = ["투위해제"]
            elif "투자위험종목 지정" in e.title:
                categories = ["투위지정"]
            else:
                categories = []

            print("프레임소스:", frame_url)
            print("분류:", ", ".join(categories) if categories else "분류 없음")

        except Exception as ex:
            print("본문 추출 실패:", ex)
            stock_name, stock_code, frame_url, categories = "", "", "", []

        notice_data = {
            "title": clean_title(e.title),      # 접두사 제거
            "class": market_class,              # 코스피/코스닥
            "stock_name": stock_name,
            "stock_code": stock_code,
            "link": e.link,
            "frame_url": frame_url,
            "categories": categories,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        add_notice(notice_data)
        print("저장 완료 ✅")
