from datetime import datetime, timedelta
import requests
import asyncio
from z_config import today, APP_KEY, APP_SECRET
from z_token_manager import get_access_token
from b_notice_fetcher import get_designation_notices
from z_telegram_sender import send_telegram_message
from b_stock_name_mapper import get_stock_name
from z_holiday_checker import is_business_day  # ✅ 추가

# 기준일 설정
base_date = today[-8:]

def fetch_recent_prices(token, stock_code, days=20):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-price"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010400",
        "custtype": "P"
    }
    today_date = datetime.today().strftime("%Y%m%d")
    start_date = (datetime.today() - timedelta(days=days * 2)).strftime("%Y%m%d")  # 넉넉하게 조회

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": today_date,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0"
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        output = res.json().get("output", [])
        return output  # 최근 시세 데이터 전체 반환
    except Exception as e:
        print(f"❌ {stock_code} 시세 조회 실패: {e}")
    return []

async def main():
    print("🚀 가격 비교 시작")
    token = get_access_token()

    # ✅ 휴장일/주말 필터링
    if not is_business_day(token, base_date):
        print("🛑 오늘은 휴장일입니다. 작업을 종료합니다.")
        return

    kospi = get_designation_notices(token, "F", base_date)
    kosdaq = get_designation_notices(token, "G", base_date)
    total = kospi + kosdaq

    if not total:
        await send_telegram_message("📊 지정예고 공시 없음")
        return

    processed = set()
    overheating_lines = ["<b>📊 단기과열 공시</b>\n"]
    warning_lines = ["<b>📊 투자경고 공시</b>\n"]

    for item in total:
        code = item["stock_code"]
        notice_type = item["type"]
        unique_key = f"{code}_{notice_type}"

        if unique_key in processed:
            continue
        processed.add(unique_key)

        raw_name = item.get("stock_name", "")
        name = raw_name if raw_name else get_stock_name(code)
        name = name.split(' ST')[0].strip()

        print(f"\n📌 {name} ({code}) | {notice_type}")

        recent_prices = fetch_recent_prices(token, code)

        if notice_type == "단기과열":
            if recent_prices:
                close = int(recent_prices[0]['stck_clpr'])
                result = f"▸ 단기과열 기준가격: {close:,}원\n"
            else:
                result = "▶ ❌ 가격 없음"
            print(result)
            overheating_lines.append(f"📌 <b>{name}</b> ({code}) | {notice_type}")
            overheating_lines.append(result)

        elif notice_type == "투자경고":
            if len(recent_prices) >= 15:
                close_d4 = int(recent_prices[4]['stck_clpr'])
                close_d14 = int(recent_prices[14]['stck_clpr'])
                high_15 = max(int(day['stck_clpr']) for day in recent_prices[:15])

                p1 = int(close_d4 * 1.6)
                p2 = int(close_d14 * 2)
                step1 = min(p1, p2)
                기준가 = max(step1, high_15)

                result = (
                    f"▸ 투자경고 기준가격: {기준가:,}원 "
                    f"(D-5*1.6={p1:,}, D-15*2={p2:,}, 15일 최고가={high_15:,})\n"
                )
            else:
                result = "⚠️ 가격 데이터 부족"
            print(result)
            warning_lines.append(f"📌 <b>{name}</b> ({code}) | {notice_type}")
            warning_lines.append(result)

    final_message = "\n".join(overheating_lines) + "\n\n" + "\n".join(warning_lines)
    await send_telegram_message(final_message)

if __name__ == "__main__":
    asyncio.run(main())
