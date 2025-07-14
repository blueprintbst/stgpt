import requests
import asyncio
from datetime import datetime, timedelta
from token_manager import get_access_token
from config import APP_KEY, APP_SECRET
from telegram_sender import send_telegram_message  # 비동기 함수
from holiday_checker import is_business_day  # ✅ 형이 만든 휴장일 모듈 사용

# 🔸 NXT 거래대금 가져오기
def get_nxt_trading_value():
    url = "https://www.nextrade.co.kr/menu/refreshMarketData.do"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {"scLanguageSe": "kor"}

    response = requests.post(url, headers=headers, data=data)

    if response.status_code == 200:
        json_data = response.json()
        kospi_value = int(json_data['stkVO']['totalAccTrval'])
        kosdaq_value = int(json_data['ksqVO']['totalAccTrval'])
        return kospi_value, kosdaq_value
    else:
        print(f"[NXT] 요청 실패: {response.status_code}")
        return 0, 0

# 🔸 KRX 거래대금 가져오기
def get_krx_trading_value():
    token = get_access_token()
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPUP02100000"
    }

    # 코스피 조회
    params_kospi = {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd": "0001"
    }
    response_kospi = requests.get(url, headers=headers, params=params_kospi)
    if response_kospi.status_code == 200:
        json_kospi = response_kospi.json()
        krx_kospi = int(json_kospi['output']['acml_tr_pbmn']) * 1_000_000
    else:
        print(f"[KRX] 코스피 요청 실패: {response_kospi.status_code}")
        krx_kospi = 0

    # 코스닥 조회
    params_kosdaq = {
        "fid_cond_mrkt_div_code": "U",
        "fid_input_iscd": "1001"
    }
    response_kosdaq = requests.get(url, headers=headers, params=params_kosdaq)
    if response_kosdaq.status_code == 200:
        json_kosdaq = response_kosdaq.json()
        krx_kosdaq = int(json_kosdaq['output']['acml_tr_pbmn']) * 1_000_000
    else:
        print(f"[KRX] 코스닥 요청 실패: {response_kosdaq.status_code}")
        krx_kosdaq = 0

    return krx_kospi, krx_kosdaq

# 🔸 조 단위 변환
def to_trillion(value):
    return round(value / 1_0000_0000_0000, 1)

# 🔸 소수점 0.0 제거
def format_trillion(value):
    trillion = to_trillion(value)
    if trillion.is_integer():
        return str(int(trillion))
    else:
        return str(trillion)

# 🔸 한국 시간 반환
def get_korean_date():
    korean_time = datetime.utcnow() + timedelta(hours=9)
    return korean_time.strftime("%y년 %m월 %d일")

# 🔸 텔레그램 메시지 생성
def build_telegram_message(total_kospi, krx_kospi, nxt_kospi, total_kosdaq, krx_kosdaq, nxt_kosdaq):
    today = get_korean_date()

    message = f"""
<b>[📊 {today} 거래대금 현황]</b>

🔸 코스피 : {format_trillion(total_kospi)}조 (KRX {format_trillion(krx_kospi)}조, NXT {format_trillion(nxt_kospi)}조)
🔹 코스닥 : {format_trillion(total_kosdaq)}조 (KRX {format_trillion(krx_kosdaq)}조, NXT {format_trillion(nxt_kosdaq)}조)
"""
    return message.strip()

# 🔸 비동기 실행
async def main():
    token = get_access_token()
    base_today = (datetime.utcnow() + timedelta(hours=9)).strftime('%Y%m%d')

    if not is_business_day(token, base_today):
        print("🛑 오늘은 휴장일입니다. 작업을 종료합니다.")
        return

    nxt_kospi, nxt_kosdaq = get_nxt_trading_value()
    krx_kospi, krx_kosdaq = get_krx_trading_value()

    total_kospi = nxt_kospi + krx_kospi
    total_kosdaq = nxt_kosdaq + krx_kosdaq

    print(f"[로그] 코스피 거래대금 : {format_trillion(total_kospi)}조 (KRX-{format_trillion(krx_kospi)}조, NXT-{format_trillion(nxt_kospi)}조)")
    print(f"[로그] 코스닥 거래대금 : {format_trillion(total_kosdaq)}조 (KRX-{format_trillion(krx_kosdaq)}조, NXT-{format_trillion(nxt_kosdaq)}조)\n")

    message = build_telegram_message(total_kospi, krx_kospi, nxt_kospi, total_kosdaq, krx_kosdaq, nxt_kosdaq)
    await send_telegram_message(message)

if __name__ == "__main__":
    asyncio.run(main())
