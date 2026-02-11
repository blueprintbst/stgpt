import asyncio
import requests
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, time
from zoneinfo import ZoneInfo

from z_config import APP_KEY, APP_SECRET
from z_token_manager import get_access_token
from z_holiday_checker import is_business_day
from z_telegram_sender import send_telegram_message

# ✅ 추가: 업비트 WS 사용
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://kr.investing.com/",
        "Connection": "keep-alive",
    })
    return s

INVESTING_SCRAPER = make_investing_scraper()

# 한국 시간 필터 (월 04:00 ~ 토 06:59 -> 형 코드 기준: 토 08:00)
def is_kst_trading_window():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    kst_time = now_kst.time()
    kst_weekday = now_kst.weekday()  # 월=0 ... 일=6

    if kst_weekday == 0 and kst_time < time(4, 0):
        return False
    if kst_weekday == 5 and kst_time >= time(8, 0):
        return False
    if kst_weekday == 6:
        return False
    return True

# 📦 방향 이모지 판별
def get_direction_emoji(change_str):
    try:
        clean = (
            change_str.strip()
            .replace("(", "")
            .replace(")", "")
            .replace("%", "")
            .replace(",", "")
        )
        percent = float(clean.replace("+", "").replace("-", ""))
        if "-" in change_str and "+" not in change_str:
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

# 📡 웹 크롤링 기반 시세 수집 함수들 (✅ 여기만 교체)
def fetch_price_and_change(url):
    scraper = INVESTING_SCRAPER

    def _try_once():
        response = scraper.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        price_div = soup.find("div", {"data-test": "instrument-price-last"})
        change_span = soup.find("span", {"data-test": "instrument-price-change-percent"})
        if not price_div or not change_span:
            return None
        price = price_div.text.strip()
        change = change_span.text.strip()
        return price, change, get_direction_emoji(change)

    try:
        out = _try_once()
        if out:
            return out

        # ✅ 셀렉터 못 잡히면 1회 리트라이(가끔 첫 요청만 삑나는 케이스 방지)
        out = _try_once()
        if out:
            return out

        return "0", "0", ""
    except Exception as e:
        print(f"❌ Investing fetch fail: {url} -> {e}")
        return "0", "0", ""

def get_usdkrw_price_and_change():
    url = "https://kr.investing.com/currencies/"
    scraper = INVESTING_SCRAPER

    def _try_once():
        res = scraper.get(url, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        price_td = soup.find("td", class_="pid-650-last")
        change_td = soup.find("td", class_="pid-650-pcp")
        if price_td and change_td:
            price = price_td.text.strip()
            change = change_td.text.strip()
            return price, change, get_direction_emoji(change)
        return None

    try:
        out = _try_once()
        if out:
            return out

        out = _try_once()
        if out:
            return out

        return "0", "0", ""
    except Exception as e:
        print(f"❌ USDKRW fetch fail -> {e}")
        return "0", "0", ""

# 🇰🇷 KOSPI200 야간선물 조회 함수 (평일만 작동)
def get_kospi200_futures():
    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    if not is_business_day(get_access_token(), today):
        return None  # 휴장일이면 리턴

    token = get_access_token()
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-futureoption/v1/quotations/inquire-daily-fuopchartprice"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKIF03020100",
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "CM",
        "FID_INPUT_ISCD": "A01603",  # 분기마다 업데이트 필요
        "FID_INPUT_DATE_1": today,
        "FID_INPUT_DATE_2": today,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        info = data.get("output1")

        if isinstance(info, dict):
            price = info.get("futs_prpr", "N/A")
            change_raw = info.get("futs_prdy_ctrt", "0")

            try:
                change_val = float(change_raw)
                change_str = f"+{change_val:.2f}" if change_val >= 0 else f"{change_val:.2f}"
            except:
                change_str = change_raw

            emoji = get_direction_emoji(change_str)
            return f"코스피200 야간 : {price}pt ({change_str}%) {emoji}"
    except Exception as e:
        print(f"❌ KOSPI200 futures fail -> {e}")

    return None

# ✅ 업비트 WS 공통: 특정 마켓 스냅샷 1회 조회 (KRW-BTC, KRW-USDT 등)
async def get_upbit_ticker_snapshot(market_code: str):
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
        print(f"❌ 업비트 WS {market_code} 스냅샷 실패: {e}")
        return "0", "0", ""

async def get_bitcoin_price_and_change_upbit():
    return await get_upbit_ticker_snapshot("KRW-BTC")

async def get_tether_price_and_change_upbit():
    return await get_upbit_ticker_snapshot("KRW-USDT")

# 📩 메시지 구성
async def main():
    if not is_kst_trading_window():
        print("🚫 KST 기준 실행 시간 아님. 종료합니다.")
        return

    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%y년 %m월 %d일")

    us100_price, us100_change, us100_emoji = fetch_price_and_change("https://kr.investing.com/indices/nq-100-futures")
    nikkei_price, nikkei_change, nikkei_emoji = fetch_price_and_change("https://kr.investing.com/indices/japan-225-futures")

    (bitcoin_price, bitcoin_change, btc_emoji), (tether_price, tether_change, tether_emoji) = await asyncio.gather(
        get_bitcoin_price_and_change_upbit(),
        get_tether_price_and_change_upbit()
    )

    usdkrw_price, usdkrw_change, usdkrw_emoji = get_usdkrw_price_and_change()
    copper_price, copper_change, copper_emoji = fetch_price_and_change("https://kr.investing.com/commodities/copper")
    gold_price, gold_change, gold_emoji = fetch_price_and_change("https://kr.investing.com/commodities/gold")
    wti_price, wti_change, wti_emoji = fetch_price_and_change("https://kr.investing.com/commodities/crude-oil")
    kospi200_msg = get_kospi200_futures()

    message = f"""
<b>[🌐 {today} 선물 시세]</b>

🇺🇸 <b>나스닥100 :</b> ${us100_price} {us100_change} {us100_emoji}
🇯🇵 <b>닛케이225 :</b> ¥{nikkei_price} {nikkei_change} {nikkei_emoji}
💰 <b>비트코인 :</b> {bitcoin_price}원 ({bitcoin_change}) {btc_emoji}
🌱 <b>테더(USDT) :</b> {tether_price}원 ({tether_change}) {tether_emoji}
💵 <b>환율(USD/KRW) :</b> {usdkrw_price}원 ({usdkrw_change}) {usdkrw_emoji}
🥇 <b>금 :</b> ${gold_price} {gold_change} {gold_emoji}
🥉 <b>구리 :</b> ${copper_price} {copper_change} {copper_emoji}
🛢️ <b>WTI유 :</b> ${wti_price} {wti_change} {wti_emoji}
""".strip()

    if kospi200_msg:
        label, rest = kospi200_msg.split(":", 1)
        message += f"\n🇰🇷 <b>{label}:</b>{rest}"

    print("[디버그] 메시지 출력:\n", message)
    await send_telegram_message(message)

if __name__ == "__main__":
    asyncio.run(main())
