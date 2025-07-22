import asyncio
import requests
from token_manager import get_access_token
from config import APP_KEY, APP_SECRET, STOCK_GROUPS, GROUP_ICONS
from telegram_sender import send_telegram_message  # ✅ 형이 만든 비동기 전송 함수

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
        return "🧊"

def fetch_price_kis(access_token, ticker):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID
    }

    # 거래소 우선순위
    exchanges = ["NAS", "NYS", "AMS"]

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
                continue  # 다음 거래소 시도

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
    lines.append("<b>📊 해외주식 시세 (현재시간 기준)</b>\n")

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            price_str = fetch_price_kis(access_token, ticker)
            lines.append(f"- {name} : {price_str}")
        lines.append("")

    return "\n".join(lines)

async def main():
    print("🚀 한국투자증권 기반 시세 조회 시작")
    access_token = get_access_token()
    message = build_message(access_token)
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())