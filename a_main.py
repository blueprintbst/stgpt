import asyncio
from datetime import datetime
from z_token_manager import get_access_token
from b_notice_fetcher import get_notices, get_designation_notices
from a_message_builder import build_message_section
from z_telegram_sender import send_telegram_message
from z_config import today
from z_holiday_checker import is_business_day  # ✅ 휴장일 필터링 함수 추가

base_date = today[-8:]

async def main():
    print("🚀 시작")
    token = get_access_token()

    # ✅ 휴장일/주말 필터링
    if not is_business_day(token, base_date):
        print("🛑 오늘은 휴장일입니다. 작업을 종료합니다.")
        return

    kospi_grouped = get_notices(token, "F", today)
    kosdaq_grouped = get_notices(token, "G", today)

    # 단기과열/투자경고 지정예고 공시만 필터링
    kospi_notices = get_designation_notices(token, "F", today)
    kosdaq_notices = get_designation_notices(token, "G", today)

    # 로그 출력
    print(f"\n🔍 [KOSPI] 단기과열·투자경고 '지정예고' 공시 수: {len(kospi_notices)}건")
    for item in kospi_notices:
        print(f"📄 {item['stock_name']} | {item['type']} | {item['title']}")

    print(f"\n🔍 [KOSDAQ] 단기과열·투자경고 '지정예고' 공시 수: {len(kosdaq_notices)}건")
    for item in kosdaq_notices:
        print(f"📄 {item['stock_name']} | {item['type']} | {item['title']}")

    message = "<b>📢 공시 목록 (키워드별 정렬)</b>\n\n"
    message += build_message_section("🔸 코스피 공시 🔸", kospi_grouped)
    message += "<b>──────────</b>\n\n"
    message += build_message_section("🔹 코스닥 공시 🔹", kosdaq_grouped)

    print("📨 텔레그램 전송 메시지:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())