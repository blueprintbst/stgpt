import cloudscraper
from bs4 import BeautifulSoup

def fetch_usdkrw_from_pid650():
    url = "https://kr.investing.com/currencies/"
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    })

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 🎯 USD/KRW 시세 요소 찾기
        price_td = soup.find("td", class_="pid-650-last")
        change_td = soup.find("td", class_="pid-650-pcp")

        if price_td and change_td:
            price = price_td.text.strip()
            change = change_td.text.strip()
            print(f"💵 USD/KRW 환율: {price} ({change})")
            return price, change
        else:
            print("⚠️ 환율 데이터 요소를 찾지 못했습니다.")
            return "0", "0"

    except Exception as e:
        print(f"❌ 환율 시세 요청 실패: {e}")
        return "0", "0"


if __name__ == "__main__":
    print("✅ USD/KRW 환율 시세 크롤링 시작")
    fetch_usdkrw_from_pid650()
