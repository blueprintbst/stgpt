import asyncio
import requests
from datetime import datetime
from token_manager import get_access_token
from config import APP_KEY, APP_SECRET, STOCK_GROUPS, GROUP_ICONS
from telegram_sender import send_telegram_message

BASE_URL = "https://openapi.koreainvestment.com:9443"
DETAIL_ENDPOINT = "/uapi/overseas-price/v1/quotations/price-detail"
HISTORY_ENDPOINT = "/uapi/overseas-price/v1/quotations/dailyprice"
TR_ID_DETAIL = "HHDFS76200200"
TR_ID_HISTORY = "HHDFS76240000"

def get_direction_emoji(percent):
    if percent >= 5:
        return "🔥"
    elif percent >= 0:
        return "📈"
    elif percent > -5:
        return "📉"
    else:
        return "🧊"

def get_price_history(access_token, ticker):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID_HISTORY,
    }

    for excd in ["NAS", "NYS", "AMS"]:
        params = {
            "AUTH": "P",
            "EXCD": excd,
            "SYMB": ticker,
            "GUBN": "0",
            "BYMD": "",
            "MODP": "0"
        }

        try:
            response = requests.get(BASE_URL + HISTORY_ENDPOINT, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get("output2", [])
            if len(data) >= 2:
                return data[1]  # 가장 최근(전일) 종가 기준
        except:
            continue
    return None

def fetch_current_price(access_token, ticker):
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
        except:
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
            history = get_price_history(access_token, ticker)
            last, after_change, after_emoji = fetch_current_price(access_token, ticker)

            if history and last:
                prev_close = float(history.get("clos", 0))
                prev_rate = float(history.get("rate", 0))
                prev_emoji = get_direction_emoji(prev_rate)

                lines.append(f"- {name}")
                lines.append(f"   정규장  : ${prev_close:.2f} ({prev_rate:+.2f}%) {prev_emoji}")
                lines.append(f"   애프터 : ${last:.2f} ({after_change:+.2f}%) {after_emoji}")
            else:
                lines.append(f"- {name} : N/A")
            lines.append("")

    return "\n".join(lines)

async def main():
    print("🚀 애프터마켓 시세 조회 시작")
    token = get_access_token()
    message = build_message(token)
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())