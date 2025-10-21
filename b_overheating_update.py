# b_overheating_update.py
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Tuple

import requests

from z_config import today as config_today, APP_KEY, APP_SECRET
from z_token_manager import get_access_token

BASE_DIR = Path(__file__).resolve().parent
IO_JSON = BASE_DIR / "b_overheating_price_cal.json"

KIS_BASE = "https://openapi.koreainvestment.com:9443"
KIS_DAILY_API = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
KIS_TR_ID = "FHKST01010400"  # 일별시세

# ---------- utils ----------
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

def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

# ---------- KIS (dedup + cache) ----------
_price_cache: Dict[str, Tuple[str, int]] = {}  # stock_code -> (date, close)

def kis_get_latest_close(token: str, stock_code: str, lookback_days: int = 60) -> Tuple[str, int]:
    """
    해당 종목의 '가장 최신 일자(rows[0])' 종가를 반환.
    반환: (stck_bsop_date, stck_clpr)
    """
    if stock_code in _price_cache:
        return _price_cache[stock_code]

    d0 = datetime.today()
    start_date = (d0 - timedelta(days=lookback_days * 2)).strftime("%Y%m%d")
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
        if rows:
            dt = str(rows[0].get("stck_bsop_date", ""))
            cl = _to_int(rows[0].get("stck_clpr"))
            _price_cache[stock_code] = (dt, cl)
            return dt, cl
    except Exception as e:
        print(f"⚠️ KIS 일별시세 조회 실패: {stock_code} / {e}")

    _price_cache[stock_code] = ("-", 0)
    return "-", 0

# ---------- main ----------
def main():
    data = load_json(IO_JSON)
    if not data:
        print(f"⚠️ 파일 없음/비어있음: {IO_JSON.name}")
        return

    token = get_access_token()

    # 종목코드 집합 추출 후, 코드 단위로 최신가 미리 조회
    codes = sorted({str(r.get("stock_code", "")).strip() for r in data if str(r.get("stock_code", "")).strip()})
    print(f"🔎 종목 수: {len(codes)} (전 레코드 D-1_price 갱신)")
    code_to_close: Dict[str, int] = {}
    code_to_date: Dict[str, str] = {}

    for i, code in enumerate(codes, 1):
        dt, cl = kis_get_latest_close(token, code, lookback_days=60)
        code_to_date[code] = dt
        code_to_close[code] = cl
        if i % 20 == 0:
            time.sleep(0.2)  # API 완충

    # 전체 레코드에 일괄 반영
    updated = 0
    skipped = 0
    updated_names: List[str] = []

    for rec in data:
        code = str(rec.get("stock_code", "")).strip()
        name = rec.get("stock_name", "")
        if not code:
            skipped += 1
            continue
        cl = int(code_to_close.get(code, 0) or 0)
        if cl > 0:
            rec["D-1_price"] = cl
            updated += 1
            if name:
                updated_names.append(name)
        else:
            skipped += 1

    save_json(IO_JSON, data)
    # 중복 이름 정리
    uniq_names = []
    seen = set()
    for n in updated_names:
        if n not in seen:
            seen.add(n)
            uniq_names.append(n)

    names_str = ", ".join(uniq_names[:20]) + (" ..." if len(uniq_names) > 20 else "")
    print(f"✅ 완료: {IO_JSON.name} | 업데이트 {updated}건, 스킵 {skipped}건 (업데이트: {names_str})")

if __name__ == "__main__":
    main()
