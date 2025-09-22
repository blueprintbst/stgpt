import asyncio
import json
import os
import requests
from datetime import datetime, time, timedelta  # timedelta는 다른 곳에서 쓸 수도 있으니 유지
from zoneinfo import ZoneInfo  # ✅ 추가: 타임존 안전하게 처리
from z_token_manager import get_access_token
from z_config import APP_KEY, APP_SECRET, STOCK_GROUPS, GROUP_ICONS
from z_telegram_sender import send_telegram_message

BASE_URL = "https://openapi.koreainvestment.com:9443"
DETAIL_ENDPOINT = "/uapi/overseas-price/v1/quotations/price-detail"
TR_ID_DETAIL = "HHDFS76200200"

def get_direction_emoji(percent):
    if percent >= 5:
        return "🔥"
    elif percent >= 0:
        return "📈"
    elif percent > -5:
        return "📉"
    else:
        return "🧊"

def get_price_history_from_file(ticker):
    """📂 저장된 종가 JSON에서 종가 정보 읽기"""
    if not os.path.exists("closing_prices.json"):
        return None

    with open("closing_prices.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get(ticker)

def fetch_current_price(access_token, ticker):
    """🌐 애프터마켓 현재가 조회"""
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID_DETAIL
    }

    for excd in ["NAS", "NYS", "AMS"]:
        params = {
            "AUTH": "P",
            "EXCD": excd,
            "SYMB": ticker
        }

        try:
            response = requests.get(BASE_URL + DETAIL_ENDPOINT, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get("output", {})
            last = data.get("last")
            base = data.get("base")
            if last and base:
                last = float(last)
                base = float(base)
                change = ((last - base) / base) * 100
                emoji = get_direction_emoji(change)
                return last, change, emoji
        except Exception as e:
            print(f"⚠️ {ticker}@{excd} 조회 실패: {e}")
            continue
    return None, None, ""

def build_message(access_token):
    lines = []
    lines.append("<b>📊 해외주식 시세 (정규장 마감 / 애프터마켓)</b>\n")

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            history = get_price_history_from_file(ticker)
            last, after_change, after_emoji = fetch_current_price(access_token, ticker)

            if history and last:
                prev_close = history["close"]
                prev_rate = history["change"]
                prev_emoji = history["emoji"]

                lines.append(f"- {name}")
                lines.append(f"   정규장  : ${prev_close:.2f} ({prev_rate:+.2f}%) {prev_emoji}")
                lines.append(f"   애프터 : ${last:.2f} ({after_change:+.2f}%) {after_emoji}")
            else:
                lines.append(f"- {name} : N/A")
            lines.append("")

    return "\n".join(lines)

# ✅ 한국시간 기준 월 04:00 ~ 토 06:59 체크 함수 (타임존 인지)
def is_kst_trading_window():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    kst_time = now_kst.time()
    kst_weekday = now_kst.weekday()  # 월=0 ... 일=6

    if kst_weekday == 0 and kst_time < time(4, 0):
        return False
    if kst_weekday == 5 and kst_time >= time(7, 0):
        return False
    if kst_weekday == 6:
        return False
    return True

async def main():
    print("🚀 애프터마켓 시세 조회 시작")
    # 디버깅용 현재 KST 시각 출력
    print("🕒 현재 KST:", datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S"))

    # ✅ 한국시간 기준 조건 체크
    if not is_kst_trading_window():
        print("🚫 KST 기준 실행시간이 아님. 종료합니다.")
        return

    token = get_access_token()
    message = build_message(token)
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())
