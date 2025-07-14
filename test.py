import cloudscraper
from bs4 import BeautifulSoup

def fetch_bitcoin_price_from_crypto_table():
    url = "https://kr.investing.com/crypto"
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    })

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # 🔍 테이블에서 모든 행을 순회
        rows = soup.find_all("tr")
        for row in rows:
            # 1. 이름 셀에서 '비트코인' 포함 여부 확인
            if "비트코인" in row.text:
                tds = row.find_all("td")
                spans = row.find_all("span")

                # 2. 가격 추출
                price_span = None
                for span in spans:
                    try:
                        text = span.text.strip().replace(",", "").replace(".", "")
                        if text.isdigit():
                            price_span = span
                            break
                    except:
                        continue

                # 3. 등락률 추출
                percent_td = None
                for td in tds:
                    if "%" in td.text and not td.has_attr("data-test"):
                        percent_td = td
                        break

                if price_span and percent_td:
                    price = price_span.text.strip()
                    change = percent_td.text.strip()
                    print(f"💰 비트코인 시세: {price} ({change})")
                    return price, change

        print("⚠️ 비트코인 데이터 요소를 찾지 못했습니다.")
        return "0", "0"

    except Exception as e:
        print(f"❌ 비트코인 시세 요청 실패: {e}")
        return "0", "0"


if __name__ == "__main__":
    print("✅ 비트코인 시세 크롤링 시작")
    fetch_bitcoin_price_from_crypto_table()
