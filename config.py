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