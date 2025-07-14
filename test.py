import cloudscraper
from bs4 import BeautifulSoup

def fetch_gold_price():
    url = "https://kr.investing.com/commodities/gold"
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    })

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        price_div = soup.find("div", {"data-test": "instrument-price-last"})
        change_span = soup.find("span", {"data-test": "instrument-price-change-percent"})

        if not price_div or not change_span:
            print("❌ 금 시세 요소 탐색 실패")
            return

        price = price_div.text.strip()
        change = change_span.text.strip()

        print(f"🥇 금 시세: {price} ({change})")

    except Exception as e:
        print(f"❌ 금 시세 요청 실패: {e}")

if __name__ == "__main__":
    print("✅ 금 시세 크롤링 시작")
    fetch_gold_price()
