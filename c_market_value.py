import requests
import asyncio
from datetime import datetime, timedelta
from z_token_manager import get_access_token
from z_config import APP_KEY, APP_SECRET
from z_telegram_sender import send_telegram_message  # 비동기 함수
from z_holiday_checker import is_business_day  # 휴장일 확인용


BASE_URL = "https://openapi.koreainvestment.com:9443"
INDEX_URL = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
TR_ID = "FHPUP02100000"

INDEX_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
    "KOSPI200": "2001",
}

# --------------------------------------------------------
# 🔸 국내 지수 조회 함수 (KOSPI/KOSDAQ/KOSPI200)
# --------------------------------------------------------
def get_index_price(access_token, name, code):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID,
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": code,
    }

    resp = requests.get(BASE_URL + INDEX_URL, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    if data.get("rt_cd") != "0":
        print(f"[{name}] 조회 실패:", data.get("msg_cd"), data.get("msg1"))
        return None

    output = data["output"]

    current = float(output["bstp_nmix_prpr"])                 # 현재 지수
    change_rate = float(output["bstp_nmix_prdy_ctrt"])        # 등락률 %

    return current, change_rate


# --------------------------------------------------------
# 🔸 NXT 거래대금
# --------------------------------------------------------
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


# --------------------------------------------------------
# 🔸 KRX 거래대금
# --------------------------------------------------------
def get_krx_trading_value(token):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-index-price"

    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHPUP02100000"
    }

    # 코스피
    params_kospi = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": "0001"}
    response_kospi = requests.get(url, headers=headers, params=params_kospi)
    if response_kospi.status_code == 200:
        json_kospi = response_kospi.json()
        krx_kospi = int(json_kospi['output']['acml_tr_pbmn']) * 1_000_000
    else:
        print("[KRX] 코스피 조회 실패")
        krx_kospi = 0

    # 코스닥
    params_kosdaq = {"fid_cond_mrkt_div_code": "U", "fid_input_iscd": "1001"}
    response_kosdaq = requests.get(url, headers=headers, params=params_kosdaq)
    if response_kosdaq.status_code == 200:
        json_kosdaq = response_kosdaq.json()
        krx_kosdaq = int(json_kosdaq['output']['acml_tr_pbmn']) * 1_000_000
    else:
        print("[KRX] 코스닥 조회 실패")
        krx_kosdaq = 0

    return krx_kospi, krx_kosdaq


# --------------------------------------------------------
# 🔸 조 변환
# --------------------------------------------------------
def to_trillion(value):
    return round(value / 1_0000_0000_0000, 1)

def format_trillion(value):
    trillion = to_trillion(value)
    if trillion.is_integer():
        return str(int(trillion))
    return str(trillion)


# --------------------------------------------------------
# 🔸 KST 날짜
# --------------------------------------------------------
def get_korean_date():
    korean_time = datetime.utcnow() + timedelta(hours=9)
    return korean_time.strftime("%y년 %m월 %d일")


# --------------------------------------------------------
# 🔸 텔레그램 메시지 조립 (지수 + 거래대금)
# --------------------------------------------------------
def build_message(index_data, total_kospi, krx_kospi, nxt_kospi,
                  total_kosdaq, krx_kosdaq, nxt_kosdaq):

    today = get_korean_date()

    lines = [f"<b>[📊 {today} 시장 현황]</b>\n"]

    # 지수 3개
    # 🗠 <b>국내 지수</b>
    lines.append("🗠 <b>국내 지수</b>")
    for name, (current, rate) in index_data.items():
        arrow = "📈" if rate >= 0 else "📉"
        rate_str = f"+{rate:.2f}%" if rate >= 0 else f"{rate:.2f}%"
        lines.append(f"• {name} : {current:.2f} ({arrow} {rate_str})")

    # 거래대금
    lines.append("\n💰 <b>거래대금</b>")
    lines.append(f"🔸 코스피 : {format_trillion(total_kospi)}조 (KRX {format_trillion(krx_kospi)}조, NXT {format_trillion(nxt_kospi)}조)")
    lines.append(f"🔹 코스닥 : {format_trillion(total_kosdaq)}조 (KRX {format_trillion(krx_kosdaq)}조, NXT {format_trillion(nxt_kosdaq)}조)")

    return "\n".join(lines)


# --------------------------------------------------------
# 🔸 메인 비동기 실행
# --------------------------------------------------------
async def main():
    token = get_access_token()

    base_today = (datetime.utcnow() + timedelta(hours=9)).strftime('%Y%m%d')
    if not is_business_day(token, base_today):
        print("🛑 오늘은 휴장일입니다. 종료.")
        return

    # 📌 지수 3개 한 번에 조회
    index_data = {}
    for name, code in INDEX_CODES.items():
        index_data[name] = get_index_price(token, name, code)

    # 📌 거래대금
    nxt_kospi, nxt_kosdaq = get_nxt_trading_value()
    krx_kospi, krx_kosdaq = get_krx_trading_value(token)

    total_kospi = nxt_kospi + krx_kospi
    total_kosdaq = nxt_kosdaq + krx_kosdaq

    # 📌 메시지 구성
    message = build_message(
        index_data,
        total_kospi, krx_kospi, nxt_kospi,
        total_kosdaq, krx_kosdaq, nxt_kosdaq
    )

    await send_telegram_message(message)


if __name__ == "__main__":
    asyncio.run(main())
