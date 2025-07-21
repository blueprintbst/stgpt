import yfinance as yf
from config import STOCK_GROUPS, GROUP_ICONS
import asyncio
from telegram_sender import send_telegram_message  # ✅ 형이 만든 비동기 전송 함수

def build_message():
    lines = []
    used_postmarket = False

    lines.append("")  # placeholder for title

    for group, stocks in STOCK_GROUPS.items():
        if group:
            icon = GROUP_ICONS.get(group, "")
            lines.append(f"<b>[{icon} {group}]</b>")
        for name, ticker in stocks:
            stock = yf.Ticker(ticker)
            info = stock.info

            regular_price = info.get("regularMarketPrice")
            regular_change = info.get("regularMarketChangePercent")
            post_price = info.get("postMarketPrice")
            post_change = info.get("postMarketChangePercent")

            if regular_price is not None and regular_change is not None:
                arrow = "📈" if regular_change >= 0 else "📉"
                price_str = f"${regular_price:.2f} ({regular_change:+.2f}%) {arrow}"
                if post_price is not None and post_change is not None:
                    used_postmarket = True
                    post_arrow = "📈" if post_change >= 0 else "📉"
                    post_str = f"${post_price:.2f} ({post_change:+.2f}%) {post_arrow}"
                    price_str += f" / 애프터 {post_str}"
            else:
                price_str = "N/A"

            lines.append(f"- {name} : {price_str}")
        lines.append("")

    # 헤더 업데이트
    title = "<b>📊 해외주식 시세 (애프터마켓 포함)</b>\n" if used_postmarket else "<b>📊 해외주식 시세 (정규장 기준)</b>\n"
    lines[0] = title

    return "\n".join(lines)

async def main():
    print("🚀 애프터마켓 시세 조회 시작")
    message = build_message()
    print("📨 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())
