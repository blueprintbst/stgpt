import feedparser
import requests
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# 본문 추출 함수
def extract_text_from_rss(rss_url: str) -> dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.Session() as s:
        r = s.get(rss_url, headers=headers, timeout=10)
        r.raise_for_status()

        m = re.search(r"value=['\"](\d{14})\|[YN]['\"]", r.text)
        if not m:
            raise ValueError("docNo를 찾지 못했어요.")
        doc_no = m.group(1)

        api_url = "https://kind.krx.co.kr/common/disclsviewer.do"
        r2 = s.get(api_url, headers=headers, params={"method":"searchContents","docNo":doc_no}, timeout=10)
        r2.raise_for_status()

        m2 = re.search(r'(/external/[^"\']+\.htm)', r2.text)
        if not m2:
            raise ValueError("docLocPath를 찾지 못했어요.")
        frame_url = urljoin(api_url, m2.group(1))

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

# 분류 규칙
RULES = {
    "초단기": ["종가가 3일 전일의 종가보다 100% 이상 상승"],
    "단기": ["종가가 5일 전일의 종가보다 60% 이상 상승"],
    "단기불건전": ["종가가 5일 전일의 종가보다 45% 이상 상승", "4. 투자경고종목 지정여부의 [1]중 ③"],
    "장기": ["종가가 15일 전일의 종가보다 100% 이상 상승"],
    "초장기불건전": ["종가가 1년 전의 종가보다 200% 이상 상승", "4. 투자경고종목 지정여부의 [1]중 ③"],
}

def classify_notice(text: str):
    matched = []
    for rule_name, keywords in RULES.items():
        if all(k in text for k in keywords):
            matched.append(rule_name)
    return matched

# 실행
if __name__ == "__main__":
    RSS_URL = "http://kind.krx.co.kr:80/disclosure/rsstodaydistribute.do?method=searchRssTodayDistribute&repIsuSrtCd=&mktTpCd=0&searchCorpName=&currentPageSize=30"
    feed = feedparser.parse(RSS_URL)

    keywords = ["투자경고종목 지정예고", "투자경고종목 지정해제 및 재지정 예고"]
    filtered = [e for e in feed.entries if any(k in e.title for k in keywords)]

    for e in filtered:
        print(f"\n▶ {e.title}")
        if "투자경고종목 지정해제 및 재지정 예고" in e.title:
            print("분류: 재지정")
        else:
            try:
                result = extract_text_from_rss(e.link)
                categories = classify_notice(result["text"])
                print("프레임소스:", result["frame_url"])
                print("분류:", ", ".join(categories) if categories else "분류 없음")
            except Exception as ex:
                print("본문 추출 실패:", ex)
