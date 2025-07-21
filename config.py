import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # .env 파일 불러오기

today = "0020250624"  # datetime.today().strftime("%Y%m%d")

APP_KEY = os.getenv("APP_KEY")
APP_SECRET = os.getenv("APP_SECRET")
TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

KEYWORDS = ["소수계좌", "단기과열", "투자경고", "거래정지", "투자위험"]
EXCLUDE_KEYWORDS = ["가격괴리율", "ELW", "ETF"]
DESIGNATION_KEYWORDS = ["단기과열", "투자경고"]

STOCK_GROUPS = {
    "": [
        ("엔비디아", "NVDA"),
        ("테슬라", "TSLA"),
        ("써클", "CRCL")
    ],
    "반도체": [
        ("TSMC", "TSM"), ("인텔", "INTC"), ("마이크론", "MU"), ("AMD", "AMD"),
        ("브로드컴", "AVGO"), ("ARM", "ARM")
    ],
    "원전": [
        ("뉴스케일", "SMR"), ("오클로", "OKLO")
    ],
    "빅테크": [
        ("아마존", "AMZN"), ("마이크로소프트", "MSFT"), ("메타", "META"), ("애플", "AAPL"),
        ("알파벳", "GOOGL"), ("팔란티어", "PLTR"), ("코인베이스", "COIN")
    ],
    "양자컴퓨터": [
        ("아이온큐", "IONQ"), ("리게티", "RGTI"), ("디 웨이브", "QBTS"), ("퀀텀컴퓨팅", "QUBT")
    ],
    "비만치료제": [
        ("노보노디스크", "NVO"), ("일라이릴리", "LLY"), ("맷세라", "MTSR"), ("바이킹", "VKTX")
    ],
    "신재생에너지": [
        ("퍼스트솔라", "FSLR"), ("썬런", "RUN"), ("솔라엣지", "SEDG"), ("솔라뱅크", "SLBK")
    ],
    "AI": [
        ("C3", "AI"), ("사운드하운드", "SOUN"), ("빅베어AI", "BBAI"), ("가드포스AI", "GFAI"), ("템퍼스AI", "TEM")
    ],
    "ETC": [
        ("퀀텀스케이프", "QS"), ("머크", "MRK"), ("버티브홀딩스", "VRT")
    ]
}

GROUP_ICONS = {
    "반도체": "💾",
    "원전": "☢️",
    "빅테크": "💻",
    "양자컴퓨터": "🧠",
    "비만치료제": "💊",
    "신재생에너지": "🔋",
    "AI": "🤖",
    "ETC": "📦",
}