import asyncio
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from token_manager import get_access_token
from telegram_sender import send_telegram_message  # ✅ 형이 만든 비동기 전송 함수


def get_direction_emoji(change_str):
    try:
        percent = float(change_str.strip().replace("(", "").replace(")", "").replace("%", "").replace("+", "").replace(",", ""))
        if change_str.startswith("-"):
            percent *= -1
    except:
        return ""

    if percent >= 2.0:
        return "🔥"
    elif percent >= 1.5:
        return "📈"
    elif percent <= -2.0:
        return "🗳️"
    elif percent <= -1.5:
        return "📉"
    else:
        return ""


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
            return "0", "0", ""

        price = price_div.text.strip()
        change = change_span.text.strip()
        emoji = get_direction_emoji(change)
        return price, change, emoji

    except Exception as e:
        print(f"❌ 예외 발생: {e}")
        return "0", "0", ""


def get_bitcoin_price_and_change():
    url = "https://kr.investing.com/crypto"
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"})

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        rows = soup.find_all("tr")
        for row in rows:
            if "비트코인" in row.text:
                tds = row.find_all("td")
                spans = row.find_all("span")

                price = next((s.text.strip() for s in spans if s.text.strip().replace(",", "").replace(".", "").isdigit()), None)
                change = next((td.text.strip() for td in tds if "%" in td.text and not td.has_attr("data-test")), None)

                emoji = get_direction_emoji(change)
                if price and change:
                    return price, change, emoji

        return "0", "0", ""

    except Exception as e:
        print(f"❌ 비트코인 시세 요청 실패: {e}")
        return "0", "0", ""


def get_usdkrw_price_and_change():
    url = "https://kr.investing.com/currencies/"
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"})

    try:
        response = scraper.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        price_td = soup.find("td", class_="pid-650-last")
        change_td = soup.find("td", class_="pid-650-pcp")

        if price_td and change_td:
            price = price_td.text.strip()
            change = change_td.text.strip()
            emoji = get_direction_emoji(change)
            return price, change, emoji

        return "0", "0", ""

    except Exception as e:
        print(f"❌ USD/KRW 시세 요청 실패: {e}")
        return "0", "0", ""


def get_korean_date():
    korean_time = datetime.utcnow() + timedelta(hours=9)
    return korean_time.strftime("%y년 %m월 %d일")


def build_market_summary_message():
    us100_price, us100_change, us100_emoji = fetch_price_and_change("https://kr.investing.com/indices/nq-100-futures")
    nikkei225_price, nikkei225_change, nikkei_emoji = fetch_price_and_change("https://kr.investing.com/indices/japan-225-futures")
    bitcoin_price, bitcoin_change, bitcoin_emoji = get_bitcoin_price_and_change()
    usdkrw_price, usdkrw_change, usdkrw_emoji = get_usdkrw_price_and_change()
    copper_price, copper_change, copper_emoji = fetch_price_and_change("https://kr.investing.com/commodities/copper")
    gold_price, gold_change, gold_emoji = fetch_price_and_change("https://kr.investing.com/commodities/gold")
    wti_price, wti_change, wti_emoji = fetch_price_and_change("https://kr.investing.com/commodities/crude-oil")

    today = get_korean_date()

    message = f"""

<b>[🌐 {today} 선물 시세]</b>

🇺🇸 <b>나스닥100 :</b> ${us100_price} {us100_change} {us100_emoji}
🇯🇵 <b>닛케이225 :</b> ¥{nikkei225_price} {nikkei225_change} {nikkei_emoji}
💰 <b>비트코인 :</b> {bitcoin_price}원 ({bitcoin_change}) {bitcoin_emoji}
💵 <b>환율(USD/KRW) :</b> {usdkrw_price}원 ({usdkrw_change}) {usdkrw_emoji}
🥇 <b>금 :</b> ${gold_price} {gold_change} {gold_emoji}
🥉 <b>구리 :</b> ${copper_price} {copper_change} {copper_emoji}
🛢️ <b>WTI유 :</b> ${wti_price} {wti_change} {wti_emoji}
""".strip()
    return message


async def main():
    message = build_market_summary_message()
    print("[디버그] 메시지:\n", message)
    await send_telegram_message(message)


if __name__ == "__main__":
    asyncio.run(main())