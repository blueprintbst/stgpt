import asyncio
import requests
import cloudscraper
from bs4 import BeautifulSoup
from datetime import datetime, time
from zoneinfo import ZoneInfo

from config import APP_KEY, APP_SECRET
from token_manager import get_access_token
from holiday_checker import is_business_day
from telegram_sender import send_telegram_message

# 한국 시간 필터 (월 04:00 ~ 토 06:59)
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

# 📡 웹 크롤링 기반 시세 수집 함수들
def fetch_price_and_change(url):
    scraper = cloudscraper.create_scraper()
    scraper.headers.update({"User-Agent": "Mozilla/5.0"})
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
        return price, change, get_direction_emoji(change)
    except:
        return "0", "0", ""

def get_bitcoin_price_and_change():
    url = "https://kr.investing.com/crypto"
    try:
        scraper = cloudscraper.create_scraper()
        scraper.headers.update({"User-Agent": "Mozilla/5.0"})
        res = scraper.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        rows = soup.find_all("tr")
        for row in rows:
            if "비트코인" in row.text:
                tds = row.find_all("td")
                spans = row.find_all("span")
                price = next(
                    (s.text.strip() for s in spans if s.text.strip().replace(",", "").replace(".", "").isdigit()),
                    None,
                )
                change = next(
                    (td.text.strip() for td in tds if "%" in td.text and not td.has_attr("data-test")),
                    None,
                )
                return price or "0", change or "0", get_direction_emoji(change or "")
        return "0", "0", ""
    except:
        return "0", "0", ""

def get_usdkrw_price_and_change():
    url = "https://kr.investing.com/currencies/"
    try:
        scraper = cloudscraper.create_scraper()
        scraper.headers.update({"User-Agent": "Mozilla/5.0"})
        res = scraper.get(url)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        price_td = soup.find("td", class_="pid-650-last")
        change_td = soup.find("td", class_="pid-650-pcp")
        if price_td and change_td:
            return price_td.text.strip(), change_td.text.strip(), get_direction_emoji(change_td.text)
        return "0", "0", ""
    except:
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
        "FID_INPUT_ISCD": "101W09",
        "FID_INPUT_DATE_1": today,
        "FID_INPUT_DATE_2": today,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        info = data.get("output1")
        if isinstance(info, dict):
            price = info.get("futs_prpr", "N/A")
            change = info.get("futs_prdy_ctrt", "0")
            emoji = get_direction_emoji(change)
            return f"코스피200 야간 : {price}pt ({change}%) {emoji}"
    except:
        pass
    return None

# 📩 메시지 구성
async def main():
    # ✅ 실행 조건 체크 (KST)
    if not is_kst_trading_window():
        print("🚫 KST 기준 실행 시간 아님. 종료합니다.")
        return

    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%y년 %m월 %d일")

    us100_price, us100_change, us100_emoji = fetch_price_and_change("https://kr.investing.com/indices/nq-100-futures")
    nikkei_price, nikkei_change, nikkei_emoji = fetch_price_and_change("https://kr.investing.com/indices/japan-225-futures")
    bitcoin_price, bitcoin_change, btc_emoji = get_bitcoin_price_and_change()
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