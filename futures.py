import asyncio
import cloudscraper
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

from token_manager import get_access_token
from telegram_sender import send_telegram_message  # 형이 만든 비동기 전송 함수


### 📦 자산별 시세 크롤링 함수들

def fetch_price_and_change(url):
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
    })

    try:
        response = scraper.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        price_div = soup.find("div", {"data-test": "instrument-price-last"})
        change_span = soup.find("span", {"data-test": "instrument-price-change-percent"})

        if not price_div or not change_span:
            print(f"❌ HTML 요소를 찾지 못함: {url}")
            return "0", "0"

        price = price_div.text.strip()
        change = change_span.text.strip()
        return price, change

    except Exception as e:
        print(f"❌ 예외 발생: {e}")
        return "0", "0"

def get_us100_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/indices/nq-100-futures")

def get_nikkei225_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/indices/japan-225-futures")

def get_bitcoin_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/crypto/bitcoin")

def get_usdkrw_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/currencies/usd-krw")

def get_copper_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/commodities/copper")

def get_gold_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/commodities/gold")

def get_wti_price_and_change():
    return fetch_price_and_change("https://kr.investing.com/commodities/crude-oil")


### 📅 날짜 포맷

def get_korean_date():
    korean_time = datetime.utcnow() + timedelta(hours=9)
    return korean_time.strftime("%y년 %m월 %d일")


### 📩 텔레그램 메시지 생성

def build_market_summary_message():
    us100_price, us100_change = get_us100_price_and_change()
    nikkei225_price, nikkei225_change = get_nikkei225_price_and_change()
    bitcoin_price, bitcoin_change = get_bitcoin_price_and_change()
    usdkrw_price, usdkrw_change = get_usdkrw_price_and_change()
    copper_price, copper_change = get_copper_price_and_change()
    gold_price, gold_change = get_gold_price_and_change()
    wti_price, wti_change = get_wti_price_and_change()

    today = get_korean_date()

    message = f"""

<b>[🌐 {today} 선물 시세]</b>

🇺🇸 <b>나스닥100 :</b> {us100_price} {us100_change}
🇯🇵 <b>닛케이225 :</b> {nikkei225_price} {nikkei225_change}
💰 <b>비트코인 :</b> {bitcoin_price} {bitcoin_change}
💵 <b>환율(USD/KRW) :</b> {usdkrw_price} {usdkrw_change}
🥇 <b>금 :</b> {gold_price} {gold_change}
🥉 <b>구리 :</b> {copper_price} {copper_change}
🛢️ <b>WTI유 :</b> {wti_price} {wti_change}
""".strip()
    return message


### 🚀 비동기 실행

async def main():
    message = build_market_summary_message()
    print("[디버그] 메시지:\n", message)
    await send_telegram_message(message)


if __name__ == "__main__":
    asyncio.run(main())