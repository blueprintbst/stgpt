import asyncio
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time
from z_token_manager import get_access_token  # (현재 코드에선 미사용이지만 형 코드 유지)
from z_telegram_sender import send_telegram_message
import json
import websockets

UPBIT_WS = "wss://api.upbit.com/websocket/v1"


# ----------------------------
# ✅ Investing 크롤링: Firefox 프로필 + 스크래퍼 재사용
# ----------------------------
def make_investing_scraper():
    s = cloudscraper.create_scraper(
        browser={"browser": "firefox", "platform": "windows", "desktop": True}
    )
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://kr.investing.com/",
        "Connection": "keep-alive",
    })
    return s

INVESTING_SCRAPER = make_investing_scraper()


def get_direction_emoji(change_str):
    try:
        clean = change_str.strip().replace("(", "").replace(")", "").replace("%", "").replace(",", "")
        percent = float(clean.replace("+", "").replace("-", ""))

        if "-" in change_str and ("+" not in change_str):
            percent *= -1
    except:
        return ""

    if percent >= 2.0:
        return "🔥"
    elif percent >= 1.5:
        return "📈"
    elif percent <= -2.0:
        return "🧊"
    elif percent <= -1.5:
        return "📉"
    else:
        return ""


# ✅ Investing 개별 페이지(나스닥/닛케이/금/구리/WTI 등)
def fetch_price_and_change(url):
    scraper = INVESTING_SCRAPER

    def _try_once():
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        price_div = soup.find("div", {"data-test": "instrument-price-last"})
        change_span = soup.find("span", {"data-test": "instrument-price-change-percent"})
        if not price_div or not change_span:
            return None

        price = price_div.get_text(strip=True)
        change = change_span.get_text(strip=True)
        emoji = get_direction_emoji(change)
        return price, change, emoji

    try:
        out = _try_once()
        if out:
            return out

        # ✅ 1회 리트라이 (첫 요청만 막히는 케이스 방지)
        out = _try_once()
        if out:
            return out

        return "0", "0", ""
    except Exception as e:
        print(f"❌ Investing 크롤링 실패: {url} -> {e}")
        return "0", "0", ""


# ✅ Investing 환율 리스트 테이블(USD/KRW)
def get_usdkrw_price_and_change():
    url = "https://kr.investing.com/currencies/"
    scraper = INVESTING_SCRAPER

    def _try_once():
        r = scraper.get(url, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        price_td = soup.find("td", class_="pid-650-last")
        change_td = soup.find("td", class_="pid-650-pcp")
        if not price_td or not change_td:
            return None

        price = price_td.get_text(strip=True)
        change = change_td.get_text(strip=True)
        emoji = get_direction_emoji(change)
        return price, change, emoji

    try:
        out = _try_once()
        if out:
            return out

        out = _try_once()
        if out:
            return out

        return "0", "0", ""
    except Exception as e:
        print(f"❌ USD/KRW 크롤링 실패: {e}")
        return "0", "0", ""


# ✅ 업비트 WS 공통 함수
async def get_upbit_ticker_snapshot(market_code: str):
    """
    market_code: KRW-BTC, KRW-USDT 등
    반환: (price_str, change_str, emoji)
    """
    req = [
        {"ticket": f"{market_code}_snapshot"},
        {"type": "ticker", "codes": [market_code], "is_only_snapshot": True},
        {"format": "DEFAULT"},
    ]

    try:
        async with websockets.connect(UPBIT_WS, ping_interval=30, ping_timeout=10) as ws:
            await ws.send(json.dumps(req))
            raw = await ws.recv()
            data = json.loads(raw)

            if isinstance(data, dict) and "error" in data:
                name = data["error"].get("name")
                msg = data["error"].get("message")
                raise RuntimeError(f"[Upbit WS Error] {name}: {msg}")

            trade_price = data.get("trade_price", 0.0)
            scr = data.get("signed_change_rate", 0.0)
            change_str = f"{scr:+.2%}"
            price_str = f"{int(round(trade_price)):,}"
            emoji = get_direction_emoji(change_str)
            return price_str, change_str, emoji

    except Exception as e:
        print(f"❌ 업비트 WS {market_code} 조회 실패: {e}")
        return "0", "0", ""


# ✅ 각각의 자산 조회 함수
async def get_bitcoin_price_and_change_upbit():
    return await get_upbit_ticker_snapshot("KRW-BTC")


async def get_tether_price_and_change_upbit():
    return await get_upbit_ticker_snapshot("KRW-USDT")


def get_korean_date():
    korean_time = datetime.utcnow() + timedelta(hours=9)
    return korean_time.strftime("%y년 %m월 %d일")


# ✅ 메인 메시지 구성
async def build_market_summary_message():
    us100_price, us100_change, us100_emoji = fetch_price_and_change(
        "https://kr.investing.com/indices/nq-100-futures"
    )
    nikkei225_price, nikkei225_change, nikkei_emoji = fetch_price_and_change(
        "https://kr.investing.com/indices/japan-225-futures"
    )

    # 🔄 비트코인 & 테더: 업비트 WS로 동시 조회 (기존 코드 흐름 유지)
    bitcoin_price, bitcoin_change, bitcoin_emoji = await get_bitcoin_price_and_change_upbit()
    tether_price, tether_change, tether_emoji = await get_tether_price_and_change_upbit()

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
🌱 <b>테더(USDT) :</b> {tether_price}원 ({tether_change}) {tether_emoji}
💵 <b>환율(USD/KRW) :</b> {usdkrw_price}원 ({usdkrw_change}) {usdkrw_emoji}
🥇 <b>금 :</b> ${gold_price} {gold_change} {gold_emoji}
🥉 <b>구리 :</b> ${copper_price} {copper_change} {copper_emoji}
🛢️ <b>WTI유 :</b> ${wti_price} {wti_change} {wti_emoji}
""".strip()

    return message


# ✅ KST 기준 실행 조건
def is_kst_trading_window():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    kst_time = now_kst.time()
    kst_weekday = now_kst.weekday()

    if kst_weekday == 0 and kst_time < time(4, 0):
        return False
    if kst_weekday == 5 and kst_time >= time(7, 0):
        return False
    if kst_weekday == 6:
        return False
    return True


async def main():
    if not is_kst_trading_window():
        print("🚫 KST 기준 실행 시간 아님. 종료합니다.")
        return

    message = await build_market_summary_message()
    print("[디버그] 메시지:\n", message)
    await send_telegram_message(message)


if __name__ == "__main__":
    asyncio.run(main())
