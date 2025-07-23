import asyncio
import requests
from datetime import datetime, time, timedelta
from token_manager import get_access_token
from config import APP_KEY, APP_SECRET, STOCK_GROUPS, GROUP_ICONS
from telegram_sender import send_telegram_message

BASE_URL = "https://openapi.koreainvestment.com:9443"
ENDPOINT = "/uapi/overseas-price/v1/quotations/price-detail"
TR_ID = "HHDFS76200200"  # 실전용

def get_direction_emoji(percent):
    if percent >= 5:
        return "🔥"
    elif percent >= 0:
        return "📈"
    elif percent > -5:
        return "📉"
    else:
        return "🧳"

def get_market_session_and_exchanges():
    now_kst = datetime.utcnow() + timedelta(hours=9)
    current = now_kst.time()

    if time(9, 0) <= current <= time(16, 59):
        return "주간거래", ["BAQ", "BAY", "BAA"]
    elif time(17, 0) <= current <= time(22, 29):
        return "프리마켓", ["NAS", "NYS", "AMS"]
    elif time(22, 30) <= current or current <= time(4, 59):
        return "정규장", ["NAS", "NYS", "AMS"]

def fetch_price_kis(access_token, ticker, exchanges):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID
    }

    for excd in exchanges:
        params = {
            "AUTH": "P",
            "EXCD": excd,
            "SYMB": ticker
        }

        try:
            response = requests.get(BASE_URL + ENDPOINT, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get("output", {})

            last_raw = data.get("last")
            base_raw = data.get("base")

            if not last_raw or not base_raw:
                continue

            last = float(last_raw)
            base = float(base_raw)

            change_percent = ((last - base) / base) * 100
            emoji = get_direction_emoji(change_percent)

            return f"${last:.2f} ({change_percent:+.2f}%) {emoji}"

        except Exception as e:
            print(f"⚠️ {ticker} @ {excd} 실패: {e}")
            continue

    return "N/A"

def build_message(access_token):
    lines = []
    session, exchanges = get_market_session_and_exchanges()
    lines.append(f"<b>📊 해외주식 시세 ({session} 기준)</b>\n")

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            price_str = fetch_price_kis(access_token, ticker, exchanges)
            lines.append(f"- {name} : {price_str}")
        lines.append("")

    return "\n".join(lines)

async def main():
    print("🚀 시세 조회 시작")
    access_token = get_access_token()
    message = build_message(access_token)
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())
