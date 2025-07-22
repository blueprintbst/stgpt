import yfinance as yf
from config import STOCK_GROUPS, GROUP_ICONS
import asyncio
from telegram_sender import send_telegram_message  # ✅ 형이 만든 비동기 전송 함수

def build_message():
    lines = ["<b>🌙 해외주식 시세 (오버나이트 기준)</b>\n"]

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            stock = yf.Ticker(ticker)
            info = stock.info

            overnight_price = info.get("postMarketPrice")
            overnight_change = info.get("postMarketChangePercent")

            if overnight_price is not None and overnight_change is not None:
                arrow = "📈" if overnight_change >= 0 else "📉"
                price_str = f"${overnight_price:.2f} ({overnight_change:+.2f}%) {arrow}"
            else:
                price_str = "N/A"

            lines.append(f"- {name} : {price_str}")
        lines.append("")

    return "\n".join(lines)

async def main():
    print("🌙 오버나이트 시세 조회 시작")
    message = build_message()
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())
