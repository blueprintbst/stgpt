import feedparser
import requests
import re
import json
import os
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

DATA_FILE = "b_notices.json"
MAX_DAYS = 10

# ---------------------------
# JSON 저장/불러오기
# ---------------------------
def load_notices():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_notices(all_data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

def add_notice(notice):
    all_data = load_notices()

    # 오늘 기준 10일 전
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
# 본문 추출
# ---------------------------
def extract_text_from_rss(rss_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.Session() as s:
        # 1) 뷰어 페이지
        r = s.get(rss_url, headers=headers, timeout=10)
        r.raise_for_status()

        # 2) docNo 추출
        m = re.search(r"value=['\"](\d{14})\|[YN]['\"]", r.text)
        if not m:
            raise ValueError("docNo를 찾지 못했어요.")
        doc_no = m.group(1)

        # 3) 내부 API
        api_url = "https://kind.krx.co.kr/common/disclsviewer.do"
        r2 = s.get(api_url, headers=headers, params={"method":"searchContents","docNo":doc_no}, timeout=10)
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

        return {"frame_url": frame_url, "text": text}

# ---------------------------
# 분류 규칙
# ---------------------------
import re

RULES = {
    "초단기": ["종가가 3일 전일의 종가보다 100% 이상 상승"],
    "단기": ["종가가 5일 전일의 종가보다 60% 이상 상승"],
    "단기불건전": ["종가가 5일 전일의 종가보다 45% 이상 상승", "__INVEST_FLAG__"],
    "장기": ["종가가 15일 전일의 종가보다 100% 이상 상승"],
    "초장기불건전": ["종가가 1년 전의 종가보다 200% 이상 상승", "__INVEST_FLAG__"],
}

def has_invest_flag(text: str) -> bool:
    # [1] ~ [9] 한 자리 숫자 허용
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
# 시장 구분 파서 (NEW)
# ---------------------------
_market_pat = re.compile(r"^\s*\[(유|코)\]")

def parse_market_class(title: str):
    """
    제목 맨 앞의 [유]/[코]로 시장을 식별.
    [유] -> 코스피, [코] -> 코스닥
    접두사가 없으면 None 반환(= 저장 스킵).
    """
    m = _market_pat.match(title)
    if not m:
        return None  # 접두사 없음 -> 저장 안 함
    return "코스피" if m.group(1) == "유" else "코스닥"

# ---------------------------
# 메인 실행
# ---------------------------
if __name__ == "__main__":
    RSS_URL = "http://kind.krx.co.kr:80/disclosure/rsstodaydistribute.do?method=searchRssTodayDistribute&repIsuSrtCd=&mktTpCd=0&searchCorpName=&currentPageSize=50"
    feed = feedparser.parse(RSS_URL)

    keywords = ["투자경고종목 지정예고", "투자경고종목 지정해제 및 재지정 예고"]
    filtered = [e for e in feed.entries if any(k in e.title for k in keywords)]

    for e in filtered:
        # ➜ 시장 구분 확인 (없으면 스킵)
        market_class = parse_market_class(e.title)
        if not market_class:
            print(f"⏭️  접두사 없음(저장 스킵): {e.title}")
            continue

        notice_data = {
            "title": e.title,                      # 접두사 포함 원제목 유지
            "class": market_class,                #코스피/코스닥
            "link": e.link,
            "frame_url": "",
            "categories": [],
            "date": datetime.now().strftime("%Y-%m-%d"),
        }

        print(f"\n▶ {e.title} ({market_class})")

        if "투자경고종목 지정해제 및 재지정 예고" in e.title:
            print("분류: 재지정예고")
            notice_data["categories"] = ["재지정예고"]
        else:
            try:
                result = extract_text_from_rss(e.link)
                categories = classify_notice(result["text"])
                print("프레임소스:", result["frame_url"])
                print("분류:", ", ".join(categories) if categories else "분류 없음")

                notice_data["frame_url"] = result["frame_url"]
                notice_data["categories"] = categories if categories else []
            except Exception as ex:
                print("본문 추출 실패:", ex)

        # JSON에 저장
        add_notice(notice_data)
        print("저장 완료 ✅")
