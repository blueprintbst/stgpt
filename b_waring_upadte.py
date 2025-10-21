# b_waring_update.py
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

import requests

from z_config import today as config_today, APP_KEY, APP_SECRET
from z_token_manager import get_access_token

BASE_DIR = Path(__file__).resolve().parent
INPUT_OUTPUT_JSON = BASE_DIR / "b_waring_price_cal.json"

KIS_BASE = "https://openapi.koreainvestment.com:9443"
KIS_DAILY_API = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
KIS_TR_ID = "FHKST01010400"  # 일별시세

# -------- util --------
def to_yyyymmdd(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        ymd = digits[:8]
        try:
            datetime.strptime(ymd, "%Y%m%d")
            return ymd
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).strftime("%Y%m%d")
    except Exception:
        return ""

def today_yyyymmdd() -> str:
    ymd = to_yyyymmdd(config_today)
    if ymd:
        return ymd
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

def load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
        return data if isinstance(data, list) else []

def save_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

def normalize_categories_value(v) -> List[str]:
    if isinstance(v, list):
        arr = [str(x).strip() for x in v if str(x).strip()]
    elif isinstance(v, str):
        arr = [v.strip()] if v.strip() else []
    else:
        arr = []
    return arr

def has_release_category(categories) -> bool:
    for c in normalize_categories_value(categories):
        if "지정해제 및 재지정 예고" in c:
            return True
    return False

def need_keys_for_categories(categories) -> List[str]:
    """카테고리 전체 합집합으로 필요한 보조필드 계산"""
    cats = normalize_categories_value(categories)
    needs = set()
    if any("초단기예고" in c for c in cats):
        needs |= {"D-3_price", "high_price"}
    if any("단기예고" in c for c in cats):
        needs |= {"D-5_price", "high_price"}
    if any("단기불건전예고" in c for c in cats):
        needs |= {"D-5_45_price"}
    if any("장기예고" in c for c in cats):
        needs |= {"D-15_price", "high_price"}
    return list(sorted(needs))

def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

# -------- KIS prices (cached) --------
_price_cache: Dict[str, List[Dict[str, Any]]] = {}

def kis_get_daily_prices(token: str, stock_code: str, count: int = 60) -> List[Dict[str, Any]]:
    if stock_code in _price_cache:
        return _price_cache[stock_code]

    d0 = datetime.today()
    start_date = (d0 - timedelta(days=count * 2)).strftime("%Y%m%d")
    end_date = d0.strftime("%Y%m%d")

    url = KIS_BASE + KIS_DAILY_API
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": KIS_TR_ID,
        "custtype": "P",
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0",
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        rows = r.json().get("output", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            rows = []
        rows = [x for x in rows if x.get("stck_bsop_date")]
        rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)  # 최신→과거
    except Exception as e:
        print(f"⚠️ KIS 일별시세 조회 실패: {stock_code} / {e}")
        rows = []

    _price_cache[stock_code] = rows
    return rows

def price_at_offset_today(rows: List[Dict[str, Any]], offset: int) -> int:
    if 0 <= offset < len(rows):
        return _to_int(rows[offset].get("stck_clpr"))
    return 0

def high_n_today(rows: List[Dict[str, Any]], n: int = 14) -> int:
    hi = 0
    for r in rows[:n]:
        cl = _to_int(r.get("stck_clpr"))
        if cl >= hi:
            hi = cl
    return hi

# -------- main --------
def main():
    tdy = today_yyyymmdd()
    token = get_access_token()

    data = load_json(INPUT_OUTPUT_JSON)
    if not data:
        print(f"⚠️ 파일 없음 혹은 비어있음: {INPUT_OUTPUT_JSON.name}")
        return

    targets = []
    for i, rec in enumerate(data):
        rec_date = to_yyyymmdd(rec.get("date"))
        if not rec_date or rec_date == tdy:
            continue
        targets.append((i, rec))

    if not targets:
        print(f"ℹ️ 오늘({tdy}) 제외한 업데이트 대상 없음.")
        return

    print(f"🛠 업데이트 대상: {len(targets)}건 (date != {tdy})")

    updated_names = []
    updated = 0
    skipped = 0

    for i, rec in targets:
        code = str(rec.get("stock_code", "")).strip()
        name = rec.get("stock_name", "")
        cats = rec.get("categories", [])
        if not code:
            skipped += 1
            continue

        rows = kis_get_daily_prices(token, code, count=60)
        if not rows:
            skipped += 1
            continue

        # -----------------------------
        # ① 지정해제 및 재지정 예고
        # -----------------------------
        if has_release_category(cats):
            d2_price = price_at_offset_today(rows, 1)  # 하루 전 종가
            if d2_price > 0:
                rec["D-2_price"] = d2_price
                updated_names.append(name)
                updated += 1
            else:
                skipped += 1
            data[i] = rec
            time.sleep(0.12)
            continue

        # -----------------------------
        # ② 그 외 (투자경고 관련)
        # -----------------------------
        need_keys = need_keys_for_categories(cats)
        if not need_keys:
            skipped += 1
            continue

        patch: Dict[str, int] = {}
        if "D-3_price" in need_keys:
            patch["D-3_price"] = price_at_offset_today(rows, 2)
        if "D-5_price" in need_keys:
            patch["D-5_price"] = price_at_offset_today(rows, 4)
        if "D-5_45_price" in need_keys:
            patch["D-5_45_price"] = price_at_offset_today(rows, 4)
        if "D-15_price" in need_keys:
            patch["D-15_price"] = price_at_offset_today(rows, 14)
        if "high_price" in need_keys:
            patch["high_price"] = high_n_today(rows, 14)

        any_updated = False
        for k, v in patch.items():
            if v not in (None, "", 0):
                rec[k] = v
                any_updated = True

        if any_updated:
            updated += 1
            updated_names.append(name)
        else:
            skipped += 1

        data[i] = rec
        time.sleep(0.12)

    save_json(INPUT_OUTPUT_JSON, data)
    names_str = ", ".join(updated_names) if updated_names else "-"
    print(f"✅ 완료: {INPUT_OUTPUT_JSON.name} | 업데이트 {updated}건, 스킵 {skipped}건 (업데이트: {names_str})")

if __name__ == "__main__":
    main()
