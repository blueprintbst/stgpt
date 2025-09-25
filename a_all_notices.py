# a_all_notices.py
import os
import re
import sys
import json
import atexit
import asyncio
import time
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Tuple

# ---------------------------
# 외부 모듈
# ---------------------------
from z_token_manager import get_access_token
from z_holiday_checker import is_business_day
from z_config import today as config_today
from z_telegram_sender import send_telegram_message

# ---------------------------
# 경로/환경
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent
PY = sys.executable  # 현재 파이썬 인터프리터

# 수집 스크립트 (실행 순서)
GENERATORS = [
    "a_caution_notices.py",
    "a_overheating_notices.py",
    "a_waring_notices.py",
    "a_danger_notices.py",
    "a_suspend_notices.py",
]

# 섹션별 데이터 소스(JSON)과 타이틀
SOURCES: List[Tuple[str, str]] = [
    ("a_caution_notices.json",      "투자주의"),
    ("a_overheating_notices.json",  "단기과열"),
    ("a_waring_notices.json",       "투자경고"),
    ("a_danger_notices.json",       "투자위험"),
    ("a_suspend_notices.json",      "거래정지"),
]

# 섹션별 카테고리 우선순위
SECTION_PRIORITY: Dict[str, List[str]] = {
    "투자주의": ["소수계좌 매수관여","소수계좌 거래집중","단일계좌 거래량 상위"],
    "단기과열": ["지정예고","지정"],
    "투자경고": ["초단기예고","단기예고","단기불건전예고","장기예고","초장기불건전예고","재지정예고","재지정","지정"],
    "투자위험": ["투위예고","투위해제","투위지정"],
    "거래정지": ["정지예고","투경정지","투위최초정지","투위중정지"],
}

# ---------------------------
# 유틸 (날짜)
# ---------------------------
STRICT_CONFIG_DATE = False  # True면 config 날짜를 무조건 사용

def to_yyyymmdd(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        ymd = digits[:8]
        try:
            datetime.strptime(ymd, "%Y%m%d")
            return ymd
        except Exception:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y%m%d")
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""

def kst_today() -> str:
    if ZoneInfo:
        return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
    return datetime.now().strftime("%Y%m%d")

def resolve_base_date(config_today: str) -> str:
    cfg = to_yyyymmdd(config_today)
    now_kst = kst_today()
    if STRICT_CONFIG_DATE:
        if not cfg:
            print("⚠️ z_config.today 파싱 실패 → KST 오늘로 대체:", now_kst)
            return now_kst
        return cfg
    if not cfg:
        print("⚠️ z_config.today 비어있음 → KST 오늘로 대체:", now_kst)
        return now_kst
    try:
        d_cfg = datetime.strptime(cfg, "%Y%m%d")
        d_now = datetime.strptime(now_kst, "%Y%m%d")
        if abs((d_now - d_cfg).days) > 1:
            print(f"⚠️ 설정일자({cfg})가 현재(KST {now_kst})와 차이 큼 → 오늘로 대체")
            return now_kst
    except Exception:
        print("⚠️ z_config.today 검증 실패 → KST 오늘로 대체:", now_kst)
        return now_kst
    return cfg

def cli_override_date() -> str:
    # 사용법: python a_all_notices.py 20250925
    if len(sys.argv) >= 2:
        ymd = to_yyyymmdd(sys.argv[1])
        if ymd:
            print("🔧 CLI 기준일 오버라이드:", ymd)
            return ymd
        else:
            print("⚠️ CLI 날짜 형식 인식 실패, 무시:", sys.argv[1])
    return ""

# ---------------------------
# 유틸 (JSON/정렬/포맷)
# ---------------------------
def load_json(path: Path):
    if (not path.exists()) or path.stat().st_size == 0:
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def normalize_categories(cats: Any) -> List[str]:
    if isinstance(cats, list):
        return [str(c).strip() for c in cats if str(c).strip()]
    if isinstance(cats, str):
        c = cats.strip()
        return [c] if c else []
    return []

def cats_to_text(cats: Any) -> str:
    arr = normalize_categories(cats)
    return ", ".join(arr) if arr else ""

def fmt_item(n: int, name: str, code: str, cats_text: str) -> str:
    name = (name or "").strip() or "이름없음"
    code = (code or "").strip() or "코드없음"
    cats_text = (cats_text or "-").strip()
    return f"{n}. {name}({code}) - {cats_text}"

def dedupe_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        key = (it.get("stock_name",""), it.get("stock_code",""), cats_to_text(it.get("categories","")))
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def best_rank_for_categories(section_title: str, cats: List[str]) -> int:
    order = SECTION_PRIORITY.get(section_title, [])
    if not order or not cats:
        return 10_000
    ranks = []
    for idx, label in enumerate(order):
        for c in cats:
            if label in c:
                ranks.append(idx)
                break
    return min(ranks) if ranks else 10_000

def sort_entries(entries: List[Dict[str, Any]], section_title: str) -> List[Dict[str, Any]]:
    def key_fn(e):
        cats_list = normalize_categories(e.get("categories", []))
        rank = best_rank_for_categories(section_title, cats_list)
        name = (e.get("stock_name") or "")
        return (rank, name)
    return sorted(entries, key=key_fn)

# 날짜 키 후보 + 당일 필터
DATE_KEYS = [
    "base_date","baseDate","date","noticed_at","notice_date","noticeDt",
    "publish_date","reg_date","disclosure_date","disclosureDt",
    "time","timestamp","created_at","yyyymmdd"
]

def is_same_day(item: Dict[str, Any], base_yyyymmdd: str) -> bool:
    for key in DATE_KEYS:
        if key in item:
            ymd = to_yyyymmdd(item.get(key))
            if ymd:
                return ymd == base_yyyymmdd
    # URL/텍스트에서 YYYY-MM-DD 또는 YYYYMMDD를 스캔 (fallback)
    for v in item.values():
        s = str(v)
        m = re.search(r"\b(20\d{2})[-/.](\d{2})[-/.](\d{2})\b", s)
        if m and "".join(m.groups()) == base_yyyymmdd:
            return True
        m = re.search(r"\b(20\d{6})\b", s)
        if m and m.group(1) == base_yyyymmdd:
            return True
    return False

def filter_today(entries: List[Dict[str, Any]], base_yyyymmdd: str) -> List[Dict[str, Any]]:
    return [e for e in entries if is_same_day(e, base_yyyymmdd)]

def build_section_block(title: str, entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return ""
    entries = dedupe_items(entries)
    entries = sort_entries(entries, title)

    lines = [f"<b>▪️[{title}] 관련 공시</b>", ""]
    for idx, e in enumerate(entries, start=1):
        lines.append(fmt_item(
            idx,
            e.get("stock_name",""),
            e.get("stock_code",""),
            cats_to_text(e.get("categories","")),
        ))
    lines.append("")
    return "\n".join(lines)

def build_all_notice_message(base_yyyymmdd: str) -> str:
    parts = [f"<b>📢 공시 목록 (키워드별 정렬) - {base_yyyymmdd}</b>", ""]
    any_block = False
    for filename, section_title in SOURCES:
        data = load_json(BASE_DIR / filename)
        data = filter_today(data, base_yyyymmdd)
        block = build_section_block(section_title, data)
        if block:
            parts.append(block)
            any_block = True
    if not any_block:
        return f"<b>📢 공시 목록 (키워드별 정렬) - {base_yyyymmdd}</b>\n\n(표시할 공시가 없습니다)"
    return "\n".join(parts).rstrip()

# ---------------------------
# 수집기 실행 (이 파일이 오케스트레이터 역할 수행)
# ---------------------------
async def run_generator(script: str, timeout: int = 60) -> int:
    path = BASE_DIR / script
    if not path.exists():
        print(f"⚠️ 경고: 수집기 없음: {script}")
        return 0

    print(f"▶ 실행: {script}")

    # 🔧 여기 추가: 서브프로세스 인코딩 강제 UTF-8
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    p = await asyncio.create_subprocess_exec(
        PY, "-X", "utf8", str(path),                 # ← -X utf8 켬
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env                                      # ← 환경변수 주입
    )
    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        p.kill()
        print(f"⏱️ 타임아웃: {script}")
        return 124

    # (참고) 디코딩은 그대로 둬도 됨. 그래도 안전하게 errors='replace' 써도 OK
    if out: print(out.decode("utf-8", "replace").rstrip())
    if err: print(err.decode("utf-8", "replace").rstrip())

    print(f"✔ 종료코드 {p.returncode}: {script}\n")
    return p.returncode

async def run_generators_sequential() -> None:
    for s in GENERATORS:
        rc = await run_generator(s, timeout=90)
        if rc != 0:
            print(f"⚠️ 경고: {s} 실패(코드 {rc}) — 계속 진행")

# 필요하면 병렬 실행으로 바꿀 수도 있음
# async def run_generators_parallel():
#     tasks = [run_generator(s, timeout=90) for s in GENERATORS]
#     results = await asyncio.gather(*tasks, return_exceptions=True)
#     for s, rc in zip(GENERATORS, results):
#         if isinstance(rc, Exception) or rc != 0:
#             print(f"⚠️ 경고: {s} 실패: {rc}")

# ---------------------------
# 메인
# ---------------------------
async def main():
    # 기준일 계산 (config → 보정 → CLI 오버라이드)
    base_date = resolve_base_date(config_today)
    override = cli_override_date()
    if override:
        base_date = override
    print("🚀 시작 / 기준일:", base_date)

    token = get_access_token()

    # 휴장일/주말 필터
    if not is_business_day(token, base_date):
        print("🛑 오늘은 휴장일입니다. 작업을 종료합니다.")
        return

    start_ts = time.time()

    # 1) 수집기 실행 (순차)
    await run_generators_sequential()

    # 2) 집계/전송
    message = build_all_notice_message(base_date)
    print("📨 텔레그램 전송 미리보기:\n", message)
    await send_telegram_message(message)
    print("✅ 텔레그램 전송 완료")

if __name__ == "__main__":
    asyncio.run(main())