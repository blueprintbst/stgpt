# b_overheating_price_cal.py
import json
import sys
import requests
from pathlib import Path
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Any, List, Dict, Tuple

from z_config import today as config_today  # KST 권장
from z_token_manager import get_access_token
from z_config import APP_KEY, APP_SECRET
from z_holiday_checker import is_business_day  # 영업일 판별

BASE_DIR = Path(__file__).resolve().parent
INPUT_JSON  = BASE_DIR / "a_overheating_notices.json"       # 입력 공시
OUTPUT_JSON = BASE_DIR / "b_overheating_price_cal.json"     # 출력 결과 (업서트 + 최근 10영업일 보관)

# 날짜 키 후보
DATE_KEYS = [
    "base_date","baseDate","date","noticed_at","notice_date","noticeDt",
    "publish_date","reg_date","disclosure_date","disclosureDt",
    "time","timestamp","created_at","yyyymmdd"
]

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

def base_yyyymmdd() -> str:
    ymd = to_yyyymmdd(config_today)
    if ymd:
        return ymd
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

def load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def save_json(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

def is_today_item(item: Dict[str, Any], ymd: str) -> bool:
    for k in DATE_KEYS:
        if k in item:
            v = to_yyyymmdd(item.get(k))
            if v and v == ymd:
                return True
    return False

def normalize_categories_value(v) -> List[str]:
    if isinstance(v, list):
        arr = [str(x).strip() for x in v if str(x).strip()]
    elif isinstance(v, str):
        arr = [v.strip()] if v.strip() else []
    else:
        arr = []
    return arr

def cats_key(v) -> str:
    arr = sorted(set(normalize_categories_value(v)))
    return "|".join(arr)

def collect_targets(ymd: str) -> List[Dict[str, Any]]:
    """당일 공시만 모아 중복 종목은 제거(같은 종목이 여러 건 있으면 모두 처리하되, 업서트 키는 categories까지 포함)"""
    data = load_json(INPUT_JSON)
    today_items = [e for e in data if is_today_item(e, ymd)]
    out: List[Dict[str, Any]] = []
    for e in today_items:
        code = str(e.get("stock_code") or "").strip()
        if not code or not code.isdigit():
            continue
        out.append({
            "stock_code": code,
            "stock_name": (e.get("stock_name") or "").strip(),
            "categories": e.get("categories", []),
        })
    return out

# ---------------------------
# KIS 일별시세 조회
# ---------------------------
KIS_BASE = "https://openapi.koreainvestment.com:9443"
KIS_DAILY_API = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
KIS_TR_ID = "FHKST01010400"

def kis_get_daily_prices(token: str, stock_code: str, count: int = 40, base_ymd: str | None = None) -> List[Dict[str, Any]]:
    if base_ymd:
        try:
            d0 = datetime.strptime(base_ymd, "%Y%m%d")
        except Exception:
            d0 = datetime.today()
    else:
        d0 = datetime.today()
    start_date = (d0 - timedelta(days=count * 2)).strftime("%Y%m%d")
    end_date   = datetime.today().strftime("%Y%m%d")

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
        data = r.json()
        rows = data.get("output", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            rows = []
        rows = [x for x in rows if x.get("stck_bsop_date")]
        rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)  # 최신→과거
        return rows[:count]
    except Exception as e:
        print(f"⚠️ KIS 일별시세 조회 실패: {stock_code} / {e}")
        return []

def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

def find_close_for_date(rows: List[Dict[str, Any]], ymd: str) -> Tuple[str, int]:
    """해당 ymd의 종가가 있으면 사용, 없으면 최신일 종가 사용"""
    for r in rows:
        if str(r.get("stck_bsop_date")) == ymd:
            return ymd, _to_int(r.get("stck_clpr"))
    if rows:
        d = str(rows[0].get("stck_bsop_date", "-"))
        return d, _to_int(rows[0].get("stck_clpr"))
    return "-", 0

# ---------------------------
# 영업일 보관 범위 계산
# ---------------------------
def _to_date(ymd: str) -> date:
    return datetime.strptime(ymd, "%Y%m%d").date()

def nearest_business_day_on_or_before(ymd: str) -> str:
    d = _to_date(ymd)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def business_day_cutoff(base_ymd: str, n_days: int = 10) -> Tuple[str, str]:
    anchor_ymd = nearest_business_day_on_or_before(base_ymd)
    d = _to_date(anchor_ymd)
    kept = 1
    while kept < n_days:
        d -= timedelta(days=1)
        if is_business_day(d):
            kept += 1
    cutoff_ymd = d.strftime("%Y%m%d")
    return cutoff_ymd, anchor_ymd

def retain_last_n_days(rows: List[Dict[str, Any]], base_ymd: str, n_days: int = 10) -> List[Dict[str, Any]]:
    try:
        cutoff, anchor = business_day_cutoff(base_ymd, n_days=n_days)
    except Exception:
        d0 = datetime.now(ZoneInfo("Asia/Seoul"))
        cutoff = (d0 - timedelta(days=n_days - 1)).strftime("%Y%m%d")
        anchor = base_ymd

    kept = []
    for r in rows:
        y = to_yyyymmdd(r.get("date"))
        if y and cutoff <= y <= anchor:
            kept.append(r)
    return kept

# ---------------------------
# 업서트
# ---------------------------
def upsert_results(output_path: Path, base_ymd: str, new_rows: List[Dict[str, Any]], keep_days: int = 10) -> List[Dict[str, Any]]:
    """
    키: (date, stock_code, categories) 로 업서트
    정렬: 날짜 내림차순, 종목명/코드 오름차순
    """
    existing = load_json(output_path)
    existing = retain_last_n_days(existing, base_ymd, n_days=keep_days)

    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    # 기존
    for r in existing:
        ymd = to_yyyymmdd(r.get("date"))
        code = str(r.get("stock_code", "")).strip()
        ckey = cats_key(r.get("categories"))
        if ymd and code:
            index[(ymd, code, ckey)] = r

    # 신규 덮어쓰기
    for r in new_rows:
        ymd = to_yyyymmdd(r.get("date"))
        code = str(r.get("stock_code", "")).strip()
        ckey = cats_key(r.get("categories"))
        if ymd and code:
            index[(ymd, code, ckey)] = r

    merged = list(index.values())
    merged.sort(
        key=lambda x: (
            to_yyyymmdd(x.get("date")),
            str(x.get("stock_name", "")).strip(),
            str(x.get("stock_code", "")).zfill(6),
            cats_key(x.get("categories")),
        ),
        reverse=True,  # 날짜 최신 우선
    )
    return merged

# ---------------------------
# 메인
# ---------------------------
def main():
    ymd = base_yyyymmdd()
    if len(sys.argv) >= 2:
        arg = to_yyyymmdd(sys.argv[1])
        if arg:
            ymd = arg

    print(f"🗓 기준일: {ymd}")
    targets = collect_targets(ymd)
    print(f"📌 단기과열 대상 {len(targets)}개")
    for t in targets:
        cats = t.get("categories")
        cats_text = ", ".join(cats) if isinstance(cats, list) else (cats or "")
        print(f"- {t['stock_name']}({t['stock_code']}) - {cats_text}")

    token = get_access_token()
    print("🔑 토큰 OK, KIS 일별시세 확인/계산 시작")

    out_rows: List[Dict[str, Any]] = []

    for t in targets:
        code = t["stock_code"]
        name = t["stock_name"]
        cats = t.get("categories", [])

        rows = kis_get_daily_prices(token, code, count=40, base_ymd=ymd)
        if not rows:
            print(f"  · {name}({code}) — 시세 데이터 없음")
            continue

        applied_date, close_price = find_close_for_date(rows, ymd)
        record: Dict[str, Any] = {
            "stock_name": name,
            "stock_code": code,
            "categories": cats,
            "date": ymd,
        }

        # 규칙:
        # - "단기과열 지정예고" 포함 → first_price 저장
        # - "단기과열 지정" 포함 → designated_price 저장
        cats_norm = normalize_categories_value(cats)
        has_notice = any("단기과열 지정예고" in c for c in cats_norm)
        has_design = any("단기과열 지정" in c and "지정예고" not in c for c in cats_norm)

        if has_notice:
            record["first_price"] = close_price
            print(f"  · {name}({code}) [단기과열 지정예고] → first_price {close_price:,}원 (적용일 {applied_date})")

        if has_design:
            record["designated_price"] = close_price
            print(f"  · {name}({code}) [단기과열 지정] → designated_price {close_price:,}원 (적용일 {applied_date})")

        # 아무 플래그도 없으면 패스(혹은 저장만 원하면 아래 줄만 남겨도 됨)
        if not (has_notice or has_design):
            print(f"  · {name}({code}) — 인식 가능한 단기과열 분류 없음")
            continue

        out_rows.append(record)

    merged = upsert_results(OUTPUT_JSON, ymd, out_rows, keep_days=10)
    save_json(OUTPUT_JSON, merged)
    print(f"💾 저장: {OUTPUT_JSON} ({len(merged)}건, 오늘 {len(out_rows)}건 업서트)")

if __name__ == "__main__":
    main()
