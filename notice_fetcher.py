import requests
from config import APP_KEY, APP_SECRET, KEYWORDS, EXCLUDE_KEYWORDS, DESIGNATION_KEYWORDS

def get_notices(token, market_code, date_str):
    """키워드 기반 공시 그룹화"""
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/news-title"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01011800",
        "custtype": "P"
    }
    params = {
        "FID_NEWS_OFER_ENTP_CODE": market_code,
        "FID_COND_MRKT_CLS_CODE": "",
        "FID_INPUT_ISCD": "",
        "FID_TITL_CNTT": "",
        "FID_INPUT_DATE_1": date_str,
        "FID_INPUT_HOUR_1": "",
        "FID_RANK_SORT_CLS_CODE": "",
        "FID_INPUT_SRNO": ""
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json().get("output", [])
    except Exception as e:
        print(f"❌ 공시 요청 실패: {e}")
        return {}

    grouped = {kw: [] for kw in KEYWORDS}
    for item in data:
        title = item.get("hts_pbnt_titl_cntt", "")
        if any(ex_kw in title for ex_kw in EXCLUDE_KEYWORDS):
            continue
        for kw in KEYWORDS:
            if kw in title:
                grouped[kw].append(item)
    return grouped


def get_designation_notices(token, market_code: str, date_str: str) -> list[dict]:
    """단기과열·투자경고 지정예고 공시만 필터링"""
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/news-title"
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01011800",
        "custtype": "P"
    }
    params = {
        "FID_NEWS_OFER_ENTP_CODE": market_code,
        "FID_COND_MRKT_CLS_CODE": "",
        "FID_INPUT_ISCD": "",
        "FID_TITL_CNTT": "",
        "FID_INPUT_DATE_1": date_str,
        "FID_INPUT_HOUR_1": "",
        "FID_RANK_SORT_CLS_CODE": "",
        "FID_INPUT_SRNO": ""
    }

    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json().get("output", [])
    except Exception as e:
        return []

    result = []
    for item in data:
        title = item.get("hts_pbnt_titl_cntt", "")
        code = item.get("iscd1", "")
        name = item.get("isu_abbrv", "") or item.get("isu_nm", "")

        if any(ex_kw in title for ex_kw in EXCLUDE_KEYWORDS):
            continue
        if "지정예고" not in title:
            continue
        for kw in DESIGNATION_KEYWORDS:
            if kw in title:
                result.append({
                    "title": title,
                    "stock_code": code,
                    "stock_name": name,
                    "type": kw
                })
                break

    return result