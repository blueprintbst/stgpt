import requests
from z_token_manager import get_access_token
from z_config import APP_KEY, APP_SECRET

BASE_URL = "https://openapi.koreainvestment.com:9443"
INDEX_URL = "/uapi/domestic-stock/v1/quotations/inquire-index-price"
TR_ID = "FHPUP02100000"

INDEX_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
    "KOSPI200": "2001",
}

def get_index_price(access_token, index_name, index_code):
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": TR_ID,
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "U",
        "FID_INPUT_ISCD": index_code,
    }

    resp = requests.get(BASE_URL + INDEX_URL, headers=headers, params=params, timeout=5)
    resp.raise_for_status()
    data = resp.json()

    if data.get("rt_cd") != "0":
        print(f"[{index_name}] 조회 실패:", data.get("msg_cd"), data.get("msg1"))
        return None

    output = data["output"]

    # 현재 지수
    current = float(output["bstp_nmix_prpr"])

    # 업종 지수 전용 등락률 (%)
    rate = float(output.get("bstp_nmix_prdy_ctrt", 0.0))

    return current, rate


def main():
    access_token = get_access_token()  # 🔥 1회만 실행

    results = []
    for name, code in INDEX_CODES.items():
        current, rate = get_index_price(access_token, name, code)
        results.append((name, current, rate))

    print("📈 국내 지수")
    for name, price, rate in results:
        arrow = "📈" if rate >= 0 else "📉"
        print(f"{name}: {price:.2f} ({arrow} {rate:.2f}%)")


if __name__ == "__main__":
    main()
