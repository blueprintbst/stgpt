import requests
from config import APP_KEY, APP_SECRET

def is_business_day(token, base_date):
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/chk-holiday"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "CTCA0903R",
        "custtype": "P"
    }
    params = {
        "BASS_DT": base_date,
        "CTX_AREA_NK": "",
        "CTX_AREA_FK": ""
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        output = data.get('output', [])

        if not output:
            print("❌ 휴장일/요일 조회 실패: 응답이 비어있음")
            return False

        today_data = next((item for item in output if item.get('bass_dt') == base_date), None)
        if not today_data:
            print("❌ 오늘 날짜 데이터 없음")
            return False

        wday_cd = today_data.get('wday_dvsn_cd', '')
        bzdy_yn = today_data.get('bzdy_yn', '')

        weekday_map = {
            "01": "일요일",
            "02": "월요일",
            "03": "화요일",
            "04": "수요일",
            "05": "목요일",
            "06": "금요일",
            "07": "토요일"
        }
        today_weekday = weekday_map.get(wday_cd, "알 수 없음")
        print(f"📅 오늘은 {today_weekday}입니다.")
        print(f"🏦 휴장일 여부: {'영업일' if bzdy_yn == 'Y' else '휴장일'}")

        return bzdy_yn == 'Y'
    except Exception as e:
        print(f"❌ 휴장일/요일 조회 실패: {e}")
        return False
