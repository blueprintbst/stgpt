# b_all_cal.py
import json
import sys
import subprocess
import inspect
import asyncio
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List

from z_config import today as config_today
from z_telegram_sender import send_telegram_message  # 동기/비동기 모두 대응

# ✅ 영업일(=토/일/공휴일 모두 포함) 필터용
from z_token_manager import get_access_token
from z_holiday_checker import is_business_day

BASE_DIR = Path(__file__).resolve().parent

# 투자경고 파이프라인
PRICE_CAL_PY    = BASE_DIR / "b_waring_price_cal.py"
PRICE_JSON      = BASE_DIR / "b_waring_price_cal.json"
UPDATE_EXTRAS   = BASE_DIR / "b_waring_upadte.py"   # 파일명 유지

# 단기과열 파이프라인
OH_CAL_PY       = BASE_DIR / "b_overheating_price_cal.py"
OH_JSON         = BASE_DIR / "b_overheating_price_cal.json"
OH_UPDATE_PY    = BASE_DIR / "b_overheating_update.py"

# ---------------- utils ----------------
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
        return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%Y%m%d")
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

def _fmt_won(x: int) -> str:
    try:
        return f"{int(x):,}원"
    except Exception:
        return f"{x}원"

def _mul_round(val: Any, mult: float) -> int:
    try:
        return int(float(val) * mult)
    except Exception:
        return 0

def run_script(pyfile: Path, *args: str) -> None:
    """지정 파이썬 스크립트를 현재 파이썬으로 실행"""
    cmd = [sys.executable, str(pyfile)]
    cmd.extend(args)
    subprocess.run(cmd, check=False)

def send_to_telegram(msg: str) -> None:
    """z_telegram_sender.send_telegram_message 동기/비동기 모두 지원"""
    try:
        if inspect.iscoroutinefunction(send_telegram_message):
            asyncio.run(send_telegram_message(msg))
        else:
            send_telegram_message(msg)
        print("✈️ 텔레그램 전송 완료")
    except Exception as e:
        print(f"⚠️ 텔레그램 전송 실패: {e}")

# ---------------- 투자경고 블록 ----------------
def compute_warning_block(rec: Dict[str, Any]) -> str | None:
    """
    레코드 한 건에서 '모든 해당 카테고리' 결과를
    한 블록(헤더 1줄 + 가격 라인 여러 줄)로 생성.
    헤더엔 첫 번째 카테고리만 노출.
    """
    name = rec.get("stock_name", "")
    code = rec.get("stock_code", "")
    cats = normalize_categories_value(rec.get("categories", []))
    if not name or not code or not cats:
        return None

    # 값들
    d3  = rec.get("D-3_price")
    d5  = rec.get("D-5_price")
    d5b = rec.get("D-5_45_price")
    d15 = rec.get("D-15_price")
    hi  = rec.get("high_price")
    hi_val = int(hi or 0)

    # 출력 순서 (블록 내 라인 순서)
    order = ["초단기예고", "단기예고", "단기불건전예고", "장기예고", "초장기불건전예고"]
    matched = [label for label in order if any(label in c for c in cats)]
    if not matched:
        return None

    # 헤더엔 첫 번째 카테고리만 노출
    header_label = matched[0]
    lines = [f"📌 <b>{name}</b> ({code}) | {header_label}"]

    # 각 카테고리 가격 라인(카테고리명 미표기)
    for label in matched:
        price = None
        tail = ""
        if label == "초단기예고":
            price = max(_mul_round(d3, 2.0), hi_val)
        elif label == "단기예고":
            price = max(_mul_round(d5, 1.6), hi_val)
        elif label == "단기불건전예고":
            price = max(_mul_round(d5b, 1.45), hi_val)
            tail = " + 소수계좌"
        elif label == "장기예고":
            price = max(_mul_round(d15, 2.0), hi_val)
        elif label == "초장기불건전예고":
            price = hi_val
            tail = " + 소수계좌"

        if price and price > 0:
            lines.append(f"▸ 투자경고 기준가격: {_fmt_won(price)}{tail}")

    return "\n".join(lines) if len(lines) > 1 else None

# ---------------- 단기과열 블록 ----------------
def compute_overheating_block(rec: Dict[str, Any]) -> str | None:
    """
    오늘자 단기과열 공시: first_price가 있는 항목만 출력
    """
    name = rec.get("stock_name", "")
    code = rec.get("stock_code", "")
    price = rec.get("first_price")
    if not name or not code or not price:
        return None
    return f"📌 <b>{name}</b> ({code}) | 단기과열\n▸ 단기과열 기준가격: {_fmt_won(int(price))}"

# ---------------- main ----------------
def main():
    ymd = today_yyyymmdd()

    # ✅ 토/일/공휴일 모두 동일하게 휴장일 처리 → 작업/전송 전부 생략
    token = get_access_token()
    if not is_business_day(token, ymd):
        print(f"🛑 휴장일({ymd}) — 작업 및 전송 생략")
        return

    # 0) (선택) a_waring_notices.json / a_overheating_notices.json 은 사전 갱신되어 있다고 가정

    # 1) 투자경고: 오늘자 업서트 + 과거 보조필드 갱신
    run_script(PRICE_CAL_PY, ymd)
    if UPDATE_EXTRAS.exists():
        run_script(UPDATE_EXTRAS)
    else:
        print(f"ℹ️ {UPDATE_EXTRAS.name} 파일이 없어 투자경고 업데이트 단계는 건너뜀.")

    # 2) 단기과열: 오늘자 업서트 + 전 레코드 D-1_price 갱신
    if OH_CAL_PY.exists():
        run_script(OH_CAL_PY, ymd)
    else:
        print(f"ℹ️ {OH_CAL_PY.name} 파일이 없어 단기과열 가격계산 단계는 건너뜀.")
    if OH_UPDATE_PY.exists():
        run_script(OH_UPDATE_PY)
    else:
        print(f"ℹ️ {OH_UPDATE_PY.name} 파일이 없어 단기과열 업데이트 단계는 건너뜀.")

    # 3) 결과 JSON 로드
    warn_data = load_json(PRICE_JSON)
    oh_data   = load_json(OH_JSON)

    # 4) 오늘자 필터
    todays_warn = [
        r for r in warn_data
        if to_yyyymmdd(r.get("date")) == ymd
        and not has_release_category(r.get("categories"))
    ]
    todays_oh = [
        r for r in oh_data
        if to_yyyymmdd(r.get("date")) == ymd
    ]

    # 5) 섹션 구성
    sections: List[str] = []

    # 단기과열 섹션
    oh_blocks = []
    for rec in todays_oh:
        block = compute_overheating_block(rec)
        if block:
            oh_blocks.append(block)
    if oh_blocks:
        sections.append("<b>📊 단기과열 공시</b>\n\n" + "\n\n".join(oh_blocks))

    # 투자경고 섹션
    warn_blocks = []
    for rec in todays_warn:
        block = compute_warning_block(rec)
        if block:
            warn_blocks.append(block)
    if warn_blocks:
        sections.append("<b>📊 투자경고 기준가격 (당일 공시)</b>\n\n" + "\n\n".join(warn_blocks))

    # ✅ 전송할 게 없으면 조용히 종료 (주말/휴장일은 이미 걸러짐, 평일에도 스팸 방지)
    if not sections:
        print(f"ℹ️ {ymd} — 전송 대상 없음 (전송 생략)")
        return

    # 6) 메시지 전송
    msg = "\n\n".join(sections)
    print(msg)
    send_to_telegram(msg)

if __name__ == "__main__":
    main()
