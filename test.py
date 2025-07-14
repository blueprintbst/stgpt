import cloudscraper
from bs4 import BeautifulSoup

def test_url(url):
    print(f"\n🔍 URL 테스트: {url}")

    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    })

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        print(f"✅ 요청 성공 (status {response.status_code})")

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. 고정된 selector 먼저 시도 (단일 페이지인 경우)
        price = soup.find("div", {"data-test": "instrument-price-last"})
        change = soup.find("span", {"data-test": "instrument-price-change-percent"})

        if price and change:
            print(f"💵 환율 시세: {price.text.strip()} ({change.text.strip()})")
            return

        # 2. 테이블 기반 탐색 (테이블 전체 순회)
        rows = soup.find_all("tr")
        for row in rows:
            if "USD/KRW" in row.text or "달러/원" in row.text or "미국 달러" in row.text:
                tds = row.find_all("td")
                spans = row.find_all("span")

                price = next((s.text.strip() for s in spans if s.text.strip().replace(",", "").replace(".", "").isdigit()), None)
                change = next((td.text.strip() for td in tds if "%" in td.text and not td.has_attr("data-test")), None)

                if price and change:
                    print(f"💵 테이블 시세: {price} ({change})")
                    return

        print("⚠️ 환율 데이터 요소를 찾지 못했습니다.")

    except Exception as e:
        print(f"❌ 요청 실패: {e}")


if __name__ == "__main__":
    urls = [
        "https://kr.investing.com/currencies/usd-krw",
        "https://kr.investing.com/currencies/",
        "https://kr.investing.com/currencies/single-currency-crosses",
        "https://www.investing.com/currencies/usd-krw",
        "https://www.investing.com/currencies/",
        "https://kr.investing.com/currencies/streaming-forex-rates-majors",
        "https://kr.investing.com/currencies/live-currency-cross-rates",
    ]

    for url in urls:
        test_url(url)
