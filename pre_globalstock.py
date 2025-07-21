import yfinance as yf
from config import STOCK_GROUPS
from config import GROUP_ICONS
from datetime import datetime, timezone, timedelta
import asyncio
from telegram_sender import send_telegram_message  # ✅ 형이 만든 비동기 전송 함수

def fetch_price(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    pre_price = info.get("preMarketPrice")
    pre_change = info.get("preMarketChangePercent")
    regular_price = info.get("regularMarketPrice")
    regular_change = info.get("regularMarketChangePercent")

    if pre_price:
        return f"${pre_price} ({pre_change:+.2f}%)"
    elif regular_price:
        return f"${regular_price} ({regular_change:+.2f}%)"
    else:
        return None

def build_message():
    lines = []
    used_premarket = False

    lines.append("")  # placeholder for title

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            stock = yf.Ticker(ticker)
            info = stock.info

            pre_price = info.get("preMarketPrice")
            pre_change = info.get("preMarketChangePercent")
            regular_price = info.get("regularMarketPrice")
            regular_change = info.get("regularMarketChangePercent")

            if pre_price is not None and pre_change is not None:
                used_premarket = True
                arrow = "📈" if pre_change >= 0 else "📉"
                price_str = f"${pre_price} ({pre_change:+.2f}%) {arrow}"
            elif regular_price is not None and regular_change is not None:
                arrow = "📈" if regular_change >= 0 else "📉"
                price_str = f"${regular_price} ({regular_change:+.2f}%) {arrow}"
            else:
                price_str = "N/A"
            lines.append(f"- {name} : {price_str}")
        lines.append("")

    # 헤더 업데이트
    lines[0] = "<b>📊 해외주식 시세 (프리마켓 기준)</b>\n" if used_premarket else "<b>📊 해외주식 시세 (정규장 기준)</b>\n"

    return "\n".join(lines)


async def main():
    print("🚀 프리마켓 시세 조회 시작")
    message = build_message()
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())