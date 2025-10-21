# b_waring_price_cal.py
import json, sys
import requests
from pathlib import Path
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from typing import Any, List, Dict, Tuple

from z_config import today as config_today  # KST 기준이면 더 좋음
from z_token_manager import get_access_token
from z_config import APP_KEY, APP_SECRET
from z_holiday_checker import is_business_day  # ⬅️ 영업일 판별

BASE_DIR = Path(__file__).resolve().parent
INPUT_JSON = BASE_DIR / "a_waring_notices.json"           # 입력 공시
OUTPUT_JSON = BASE_DIR / "b_waring_price_cal.json"        # 출력 결과 (업서트 + 최근 10영업일 보관)

# 날짜 키 후보 (JSON마다 다를 수 있어 넓게 지원)
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

def collect_warning_targets(ymd: str) -> List[Dict[str, Any]]:
    data = load_json(INPUT_JSON)
    today_items = [e for e in data if is_today_item(e, ymd)]
    seen = set()
    out: List[Dict[str, Any]] = []
    for e in today_items:
        code = str(e.get("stock_code") or "").strip()
        if not code or not code.isdigit() or code in seen:
            continue
        seen.add(code)
        out.append({
            "stock_code": code,
            "stock_name": (e.get("stock_name") or "").strip(),
            "categories": e.get("categories", []),
        })
    return out

# ---------------------------
# KIS 일별시세 조회 (최근 N거래일)
# ---------------------------
KIS_BASE = "https://openapi.koreainvestment.com:9443"
KIS_DAILY_API = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"
KIS_TR_ID = "FHKST01010400"  # 일별시세

def kis_get_daily_prices(token: str, stock_code: str, count: int = 20, base_ymd: str | None = None):
    """
    한국투자증권 일별시세 조회 (최신→과거 정렬, 최대 count개 반환)
    - 날짜 구간(FID_INPUT_DATE_1/2) 지정
    - 응답 'output' 리스트 사용
    """
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
        rows.sort(key=lambda x: x["stck_bsop_date"], reverse=True)
        return rows[:count]
    except Exception as e:
        print(f"⚠️ KIS 일별시세 조회 실패: {stock_code} / {e}")
        return []

# ---------------------------
# 투자경고 기준가 계산 (내일 기준 offset 보정)
# ---------------------------
CAT_RULES = {
    "초단기예고":        {"days_ago": 3,   "mult": 2.0},   # 100% 상승
    "단기예고":          {"days_ago": 5,   "mult": 1.6},   # 60% 상승
    "장기예고":          {"days_ago": 15,  "mult": 2.0},   # 100% 상승
    "단기불건전예고":    {"days_ago": 5,   "mult": 1.45},  # 45% 상승
    # "초장기불건전예고": 15일 최고만 사용
}

# 계산에서 제외할 분류(부분 포함 매칭)
# ※ "지정해제 및 재지정 예고"는 스킵 대상 아님 (별도 처리)
SKIP_KEYWORDS = ["재지정", "지정"]  # 형이 원한 그대로 유지

def normalize_categories_value(v) -> List[str]:
    """categories를 키용으로 정규화: 리스트/문자열 모두 리스트[str]로, 공백 제거, 빈 값 제거"""
    if isinstance(v, list):
        arr = [str(x).strip() for x in v if str(x).strip()]
    elif isinstance(v, str):
        arr = [v.strip()] if v.strip() else []
    else:
        arr = []
    return arr

def cats_key(v) -> str:
    """카테고리 키: 중복 제거 + 정렬 + '|' 조인 (순서 차이 무시)"""
    arr = sorted(set(normalize_categories_value(v)))
    return "|".join(arr)

def has_release_category(categories) -> bool:
    """'지정해제 및 재지정 예고' 포함 여부"""
    for c in normalize_categories_value(categories):
        if "지정해제 및 재지정 예고" in c:
            return True
    return False

def is_skip_category(categories) -> bool:
    """스킵 로직: '지정해제 및 재지정 예고'는 예외적으로 스킵하지 않음"""
    if has_release_category(categories):
        return False
    cats = normalize_categories_value(categories)
    for c in cats:
        for w in SKIP_KEYWORDS:
            if w in c:
                return True
    return False

def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", "").strip())
    except Exception:
        return 0

def _fmt_won(x: int) -> str:
    return f"{x:,}원"

def pick_category_label(categories) -> str:
    """categories(list/str)에서 규칙 라벨 반환 (초장기불건전예고 포함)"""
    cats = normalize_categories_value(categories)
    for c in cats:
        if "초장기불건전예고" in c:
            return "초장기불건전예고"
    for key in CAT_RULES.keys():
        for c in cats:
            if key in c:
                return key
    return ""

def _base_close_at_index_for_tomorrow(rows, n_days_ago: int) -> Tuple[str, int]:
    """
    rows: 최신→과거
    '내일 기준 n일 전'은 오늘 rows 인덱스에서 (n-1)칸 뒤.
    예) n=3 → rows[2], n=5 → rows[4], n=15 → rows[14]
    반환: (기준일, 종가)
    """
    idx = max(0, n_days_ago - 1)
    if idx < len(rows):
        d = str(rows[idx].get("stck_bsop_date", "")) or "-"
        return d, _to_int(rows[idx].get("stck_clpr"))
    return "-", 0

def _high_with_date(rows: List[Dict[str, Any]], n: int = 14) -> Tuple[int, str, int]:
    """최근 n영업일 종가 최고와 그 날짜/가격(최신에 가까운 날짜 우선)"""
    best = 0
    best_date = "-"
    for r in rows[:n]:
        cl = _to_int(r.get("stck_clpr"))
        if cl >= best:
            best = cl
            best_date = str(r.get("stck_bsop_date", "-"))
    return best, best_date, best

def _price_at_offset_today(rows: List[Dict[str, Any]], offset: int) -> Tuple[str, int]:
    """
    당일 기준 offset 영업일 전 종가 (rows: 최신→과거)
    offset=0: 당일, 1: 전일, 2: 2영업일 전, ...
    """
    if offset < len(rows):
        d = str(rows[offset].get("stck_bsop_date", "-"))
        return d, _to_int(rows[offset].get("stck_clpr"))
    return "-", 0

def _high15_with_date(rows: List[Dict[str, Any]]) -> Tuple[int, str, int]:
    """최근 15영업일 종가 최고 (기존 계산용: 유지)"""
    return _high_with_date(rows, n=15)

def calc_warning_price(rows: List[Dict[str, Any]], base_ymd: str, category_label: str) -> Tuple[int, str, int]:
    """
    반환: (지정가, 기준일, 기준일 종가)
    - 단기불건전예고: max( (내일 기준 5일 전 종가×1.45), 최근 15영업일 종가 최고 )
    - 초장기불건전예고: 최근 15영업일 종가 최고만 사용
    - 그 외(초단기/단기/장기예고): max(룰가격, 최근 15영업일 종가 최고)
    """
    if not rows:
        return 0, "-", 0

    high15, high_date, high_close = _high15_with_date(rows)

    if category_label == "초장기불건전예고":
        return high15, high_date, high_close

    rule = CAT_RULES.get(category_label)
    if not rule:
        return high15, high_date, high_close

    base_date, base_close = _base_close_at_index_for_tomorrow(rows, rule["days_ago"])
    rule_price = int(base_close * rule["mult"]) if base_close > 0 else 0

    if rule_price >= high15:
        return rule_price, base_date, base_close
    else:
        return high15, high_date, high_close

# ---------------------------
# 카테고리 정렬 우선순위 (작을수록 먼저)
# ---------------------------
CATEGORY_ORDER = [
    "단기예고",
    "장기예고",
    "초단기예고",
    "단기불건전예고",
    "초장기불건전예고",
    "지정",
    "지정해제 및 재지정 예고",
]
_CATEGORY_RANK = {name: i for i, name in enumerate(CATEGORY_ORDER)}
_DEFAULT_RANK = len(CATEGORY_ORDER) + 99

def _category_rank_for_record(rec: Dict[str, Any]) -> int:
    """
    레코드의 categories(list/str)에서 매칭되는 카테고리들 중
    가장 높은 우선순위(=가장 작은 rank)를 반환.
    부분일치의 경우 더 '긴 키워드'를 우선 적용해 '지정'이 '지정해제 및 재지정 예고'를 잡아먹지 않도록 함.
    """
    cats = normalize_categories_value(rec.get("categories"))
    if not cats:
        return _DEFAULT_RANK

    best_rank = _DEFAULT_RANK
    for c in cats:
        # 1) 완전일치 먼저
        if c in _CATEGORY_RANK:
            best_rank = min(best_rank, _CATEGORY_RANK[c])
            continue
        # 2) 부분일치: 가장 긴 키워드 우선
        matches = [(key, rank) for key, rank in _CATEGORY_RANK.items() if key in c]
        if matches:
            # 가장 긴 key 선택 (동일 길이면 낮은 rank)
            matches.sort(key=lambda kr: (len(kr[0]), -kr[1]), reverse=True)
            best_rank = min(best_rank, matches[0][1])
    return best_rank

# ---------------------------
# 영업일 보관 범위 계산
# ---------------------------
def _to_date(ymd: str) -> date:
    return datetime.strptime(ymd, "%Y%m%d").date()

def nearest_business_day_on_or_before(ymd: str) -> str:
    """ymd(YYYYMMDD)와 같거나 그 이전 중 가장 가까운 '영업일'을 반환"""
    d = _to_date(ymd)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")

def business_day_cutoff(base_ymd: str, n_days: int = 10) -> Tuple[str, str]:
    """
    base_ymd 기준으로 최근 n영업일 범위를 계산.
    반환: (cutoff_ymd, anchor_ymd)
      - anchor_ymd: base_ymd와 같거나 그 이전의 가장 가까운 '영업일'
      - cutoff_ymd: anchor에서 (n-1) 영업일 뒤로 간 날짜
    """
    anchor_ymd = nearest_business_day_on_or_before(base_ymd)
    d = _to_date(anchor_ymd)
    kept = 1  # anchor 포함

    while kept < n_days:
        d -= timedelta(days=1)
        if is_business_day(d):
            kept += 1

    cutoff_ymd = d.strftime("%Y%m%d")
    return cutoff_ymd, anchor_ymd

# ---------------------------
# 업서트 키: (date, stock_code, categories)
# ---------------------------
def retain_last_n_days(rows: List[Dict[str, Any]], base_ymd: str, n_days: int = 10) -> List[Dict[str, Any]]:
    """
    base_ymd 기준 '최근 n영업일'만 남김.
    - 상한: anchor(=base_ymd와 같거나 그 이전의 최근 영업일)
    - 하한: cutoff(=anchor에서 (n-1) 영업일 전)
    """
    try:
        cutoff, anchor = business_day_cutoff(base_ymd, n_days=n_days)
    except Exception:
        # 문제 시 달력일수 fallback (기존 동작)
        d0 = datetime.now(ZoneInfo("Asia/Seoul"))
        cutoff = (d0 - timedelta(days=n_days - 1)).strftime("%Y%m%d")
        anchor = base_ymd

    kept = []
    for r in rows:
        y = to_yyyymmdd(r.get("date"))
        if y and cutoff <= y <= anchor:
            kept.append(r)
    return kept

def upsert_results(output_path: Path, base_ymd: str, new_rows: List[Dict[str, Any]], keep_days: int = 10) -> List[Dict[str, Any]]:
    """
    - 기존 파일 읽어서 최근 keep_days(=영업일)만 남김
    - (date, stock_code, categories) 키로 업서트 (동일 키는 새 값으로 덮기)
    - 정렬: 날짜 블록 내 카테고리/종목명/코드 순, 날짜 블록은 내림차순
    """
    existing = load_json(output_path)
    existing = retain_last_n_days(existing, base_ymd, n_days=keep_days)

    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    # 기존 데이터 인덱싱
    for r in existing:
        ymd = to_yyyymmdd(r.get("date"))
        code = str(r.get("stock_code", "")).strip()
        ckey = cats_key(r.get("categories"))
        if ymd and code:
            index[(ymd, code, ckey)] = r

    # 신규 데이터 업서트
    for r in new_rows:
        ymd = to_yyyymmdd(r.get("date"))
        code = str(r.get("stock_code", "")).strip()
        ckey = cats_key(r.get("categories"))
        if ymd and code:
            index[(ymd, code, ckey)] = r  # 동일 키면 덮어쓰기

    merged = list(index.values())

    # 1) 날짜 오름차순 정렬
    merged.sort(key=lambda x: to_yyyymmdd(x.get("date")))

    # 2) 같은 날짜끼리 카테고리/종목명/코드 기준 오름차순 재정렬
    from itertools import groupby
    grouped_blocks = []
    for d, group in groupby(merged, key=lambda x: to_yyyymmdd(x.get("date"))):
        block = list(group)
        block.sort(key=lambda x: (
            _category_rank_for_record(x),               # ✅ 카테고리 순서
            str(x.get("stock_name", "")).strip(),       # 종목명
            str(x.get("stock_code", "")).zfill(6),      # 코드
            cats_key(x.get("categories")),              # 키 안정화
        ))
        grouped_blocks.append((d, block))

    # 3) 날짜 블록 자체는 내림차순으로 뒤집고 펼치기
    grouped_blocks.sort(key=lambda t: t[0], reverse=True)
    merged = [rec for _, block in grouped_blocks for rec in block]

    return merged

# ---------------------------
# 유틸: 특정 날짜 종가 찾기 (없으면 최신 종가)
# ---------------------------
def find_close_for_date(rows: List[Dict[str, Any]], ymd: str) -> Tuple[str, int]:
    """
    rows: 최신→과거
    ymd 날짜의 종가를 우선 반환. 없으면 rows[0] (최신) 사용.
    반환: (적용한 날짜, 종가)
    """
    for r in rows:
        if str(r.get("stck_bsop_date")) == ymd:
            return ymd, _to_int(r.get("stck_clpr"))
    # fallback: 최신일
    if rows:
        d = str(rows[0].get("stck_bsop_date", "-"))
        return d, _to_int(rows[0].get("stck_clpr"))
    return "-", 0

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
    targets = collect_warning_targets(ymd)
    print(f"📌 투자경고 대상 {len(targets)}개")
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
        cats_text = ", ".join(cats) if isinstance(cats, list) else (cats or "")

        # 1) '지정해제 및 재지정 예고' 별도 처리 (release_price 저장)
        if has_release_category(cats):
            rows = kis_get_daily_prices(token, code, count=40, base_ymd=ymd)
            if not rows:
                print(f"  · {name}({code}) — 지정해제/재지정: 시세 데이터 없음")
            else:
                applied_date, rel_close = find_close_for_date(rows, ymd)
                print(f"  · {name}({code}) [지정해제 및 재지정 예고] → release_price {_fmt_won(rel_close)} (적용일 {applied_date})")
                out_rows.append({
                    "stock_name": name,
                    "stock_code": code,
                    "categories": cats,     # 카테고리는 그대로 보존
                    "date": ymd,            # 기준일(공시 기준일)
                    "release_price": rel_close,  # 당일(또는 가장 근접 최신일) 종가
                })
            # 지정해제 공시는 지정가 계산과 무관하므로 여기서 continue
            continue

        # 2) 그 외 스킵 분류는 계산/호출 생략
        if is_skip_category(cats):
            print(f"  · {name}({code}) — 계산 생략 (분류: {cats_text})")
            continue

        # 3) 투자경고 규칙 분류 식별
        cat_label = pick_category_label(cats)
        if not cat_label:
            print(f"  · {name}({code}) — 계산 생략 (해당 규칙 없음 / 분류: {cats_text})")
            continue

        rows = kis_get_daily_prices(token, code, count=40, base_ymd=ymd)
        if not rows:
            print(f"  · {name}({code}) — 시세 데이터 없음")
            continue

        designated, base_date, base_close = calc_warning_price(rows, ymd, cat_label)
        if designated <= 0:
            print(f"  · {name}({code}) — 계산 실패")
            continue

        latest = rows[0]
        latest_d = latest.get("stck_bsop_date")
        latest_cl = _to_int(latest.get("stck_clpr"))

        # ➕ 추가: 보조 필드 계산 (당일 기준)
        extra_fields: Dict[str, Any] = {}
        if cat_label == "초단기예고":
            _, d3p = _price_at_offset_today(rows, 2)   # 당일 기준 2영업일 전
            hi14, _, _ = _high_with_date(rows, n=14)   # 최근 14영업일 신고가
            extra_fields["D-3_price"] = d3p
            extra_fields["high_price"] = hi14
        elif cat_label == "단기예고":
            _, d5p = _price_at_offset_today(rows, 4)   # 당일 기준 4영업일 전
            hi14, _, _ = _high_with_date(rows, n=14)
            extra_fields["D-5_price"] = d5p
            extra_fields["high_price"] = hi14
        elif cat_label == "단기불건전예고":
            _, d5_45p = _price_at_offset_today(rows, 4)  # 당일 기준 4영업일 전 (원가격)
            hi14, _, _ = _high_with_date(rows, n=14)
            extra_fields["D-5_45_price"] = d5_45p
            extra_fields["high_price"] = hi14
        elif cat_label == "장기예고":
            _, d15p = _price_at_offset_today(rows, 14) # 당일 기준 14영업일 전
            hi14, _, _ = _high_with_date(rows, n=14)
            extra_fields["D-15_price"] = d15p
            extra_fields["high_price"] = hi14
        elif cat_label == "초장기불건전예고":
            # ✅ 요청: 초장기불건전예고에도 14영업일 신고가 저장
            hi14, _, _ = _high_with_date(rows, n=14)
            extra_fields["high_price"] = hi14

        extra = " + 소수계좌" if cat_label in ("단기불건전예고", "초장기불건전예고") else ""
        print(f"  · {name}({code}) [{cat_label}] → 지정가 {_fmt_won(designated)}{extra} "
              f"(최근일 {latest_d}, 종가 {_fmt_won(latest_cl)}, 기준일 {base_date}, 종가 {_fmt_won(base_close)})")

        # JSON 저장용 레코드
        record = {
            "stock_name": name,
            "stock_code": code,
            "categories": cats,
            "date": ymd,                    # 기준일(당일 공시 기준일)
            "first_price": designated,      # 계산된 지정가
        }
        record.update(extra_fields)          # ➕ 보조 필드 포함
        out_rows.append(record)

    # 업서트 + 최근 10영업일 유지 + 날짜별 카테고리 정렬
    merged = upsert_results(OUTPUT_JSON, ymd, out_rows, keep_days=10)
    save_json(OUTPUT_JSON, merged)
    print(f"💾 저장: {OUTPUT_JSON} ({len(merged)}건, 오늘 {len(out_rows)}건 업서트)")

if __name__ == "__main__":
    main()
