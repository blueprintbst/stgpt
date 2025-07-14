import cloudscraper
from bs4 import BeautifulSoup

def test_url(url):
    print(f"\n🔍 URL 테스트: {url}")

    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        print(f"✅ 요청 성공 (status {response.status_code})")

        soup = BeautifulSoup(response.text, "html.parser")

        # 1. data-test selector (PC 웹 버전)
        price = soup.find("div", {"data-test": "instrument-price-last"})
        change = soup.find("span", {"data-test": "instrument-price-change-percent"})

        # 2. 모바일 버전 selector (클래스 기반 예시)
        if not price:
            price = soup.find("div", class_="price")
        if not change:
            change = soup.find("div", class_="change")

        if price and change:
            print(f"💰 시세: {price.text.strip()} ({change.text.strip()})")
        else:
            print("⚠️ 시세 관련 요소를 찾지 못했습니다.")

    except Exception as e:
        print(f"❌ 요청 실패: {e}")


if __name__ == "__main__":
    urls = [
        "https://m.kr.investing.com/crypto/bitcoin",
        "https://m.investing.com/crypto/bitcoin",
        "https://kr.investing.com/crypto",
        "https://kr.investing.com/crypto/bitcoin/usd",
        "https://kr.investing.com/crypto/currencies"
    ]

    for url in urls:
        test_url(url)
