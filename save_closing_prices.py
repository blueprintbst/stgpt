import json
import requests
from token_manager import get_access_token
from config import STOCK_GROUPS, APP_KEY, APP_SECRET

BASE_URL = "https://openapi.koreainvestment.com:9443"
HISTORY_ENDPOINT = "/uapi/overseas-price/v1/quotations/dailyprice"
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

def fetch_closing_price(access_token, ticker):
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
            "GUBN": "0",   # 0: 일자 기준 조회
            "BYMD": "",    # 비워두면 최신 날짜 기준
            "MODP": "0"
        }

        try:
            response = requests.get(BASE_URL + HISTORY_ENDPOINT, headers=headers, params=params)
            response.raise_for_status()
            data = response.json().get("output2", [])
            if data:
                item = data[0]  # 오전 5시 기준 가장 최근 종가
                clos = float(item["clos"])
                rate = float(item["rate"])
                emoji = get_direction_emoji(rate)
                return {"close": clos, "change": rate, "emoji": emoji}
        except Exception as e:
            print(f"❌ {ticker} 종가 조회 실패: {e}")
            continue
    return None

def main():
    print("🚀 정규장 종가 저장 시작")
    access_token = get_access_token()
    result = {}

    for group_name, stocks in STOCK_GROUPS.items():
        for name, ticker in stocks:
            price_info = fetch_closing_price(access_token, ticker)
            if price_info:
                result[ticker] = price_info
                print(f"✅ {ticker} 저장 완료: ${price_info['close']} ({price_info['change']}%)")
            else:
                print(f"❌ {ticker} 저장 실패")

    try:
        with open("closing_prices.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=4, ensure_ascii=False)
        print("💾 closing_prices.json 저장 완료")
    except Exception as e:
        print(f"❌ JSON 저장 실패: {e}")

if __name__ == "__main__":
    main()
