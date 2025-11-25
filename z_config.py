import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # .env 파일 불러오기

today = "0020250925"  # datetime.today().strftime("%Y%m%d")

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
        ("알파벳", "GOOGL"),
        ("테슬라", "TSLA")
    ],
    "반도체": [
        ("브로드컴", "AVGO"), ("마이크론", "MU"), ("샌디스크", "SNDK"), ("TSMC", "TSM"), ("인텔", "INTC"), ("AMD", "AMD"),
        ("ARM", "ARM")
    ],
    "원전": [
        ("뉴스케일", "SMR"), ("오클로", "OKLO")
    ],
    "빅테크": [
        ("마이크로소프트", "MSFT"), ("메타", "META"), ("오라클", "ORCL"), ("아마존", "AMZN"), ("애플", "AAPL"),
        ("팔란티어", "PLTR")
    ],
    "양자컴퓨터": [
        ("아이온큐", "IONQ"), ("리게티", "RGTI"), ("디 웨이브", "QBTS"), ("퀀텀컴퓨팅", "QUBT")
    ],
    "비만치료제": [
        ("노보노디스크", "NVO"), ("일라이릴리", "LLY"), ("화이자", "PFE"), ("바이킹", "VKTX")
    ],
    "ETC": [
        ("코인베이스", "COIN"), ("써클", "CRCL"), ("머크", "MRK"), ("버티브홀딩스", "VRT"), ("블룸에너지", "BE"), ("플러그파워", "PLUG")
    ]
}

GROUP_ICONS = {
    "반도체": "💾",
    "원전": "☢️",
    "빅테크": "💻",
    "양자컴퓨터": "🧠",
    "비만치료제": "💊",
    "ETC": "📦",
}

US_HOLIDAYS = [
    "2025-09-01",
    "2025-12-25",
]