import requests
import json
import os
from datetime import datetime, timedelta
from config import APP_KEY, APP_SECRET

TOKEN_FILE = "token.json"

def is_token_valid(token):
    """토큰이 실제 API에 사용할 수 있는지 확인"""
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/news-title"
    headers = {
        "Authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01011800",
        "custtype": "P"
    }
    try:
        res = requests.get(url, headers=headers, params={"FID_INPUT_DATE_1": "0020250101"})
        print(f"🧪 유효성 테스트 응답 코드: {res.status_code}")
        if res.status_code == 200:
            return True
    except Exception as e:
        print("❌ 유효성 검사 중 예외 발생:", e)
    return False

def load_token_from_file():
    if not os.path.exists(TOKEN_FILE):
        print("📂 token.json 없음")
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            expire_time = datetime.fromisoformat(data["expires_at"])
            print("📂 token.json 로딩 성공")

            if expire_time > datetime.now():
                print("⏱ 유효기간 체크 통과")
                token = data["access_token"]

                if is_token_valid(token):
                    remaining = expire_time - datetime.now()
                    hours, remainder = divmod(remaining.seconds, 3600)
                    minutes = remainder // 60
                    print(f"✅ 기존 토큰 재사용 (만료까지 {remaining.days * 24 + hours}시간 {minutes}분 남음)")
                    return token
                else:
                    print("❌ 서버가 토큰을 거부함 (is_token_valid 실패)")
            else:
                print("⏱ 토큰 만료됨")
    except Exception as e:
        print("❌ token.json 로딩 중 오류:", e)
    return None

def save_token_to_file(token):
    expires_at = datetime.now() + timedelta(hours=23, minutes=59)
    data = {
        "access_token": token,
        "expires_at": expires_at.isoformat()
    }
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        print("💾 새 토큰 저장 완료")
    except Exception as e:
        print("❌ 토큰 저장 실패:", e)

def get_access_token(force_refresh=False):
    if not force_refresh:
        token = load_token_from_file()
        if token:
            return token

    print("🔐 새 토큰 발급 요청 중...")
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"Content-Type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }

    try:
        res = requests.post(url, headers=headers, json=body)
        print(f"📡 발급 응답 코드: {res.status_code}")
        res.raise_for_status()
        token = res.json().get("access_token")
        save_token_to_file(token)
        print("✅ 새 토큰 발급 완료 및 저장됨")
        return token
    except requests.RequestException as e:
        print("❌ 토큰 발급 실패:", e)
        raise
