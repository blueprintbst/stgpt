import re
import os

# 현재 파일 기준 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_stock_names(file_name):
    stock_dict = {}
    file_path = os.path.join(BASE_DIR, file_name)

    try:
        with open(file_path, 'r', encoding='euc-kr', errors='ignore') as f:
            lines = f.readlines()

        for line in lines:
            stock_code = line[0:6].strip()
            stock_name = line[18:58].strip()

            # 종목명 정제
            clean_name = re.sub(r'^\d+', '', stock_name).strip()
            clean_name = re.sub(r'\s+[A-Z]{1,}$', '', clean_name).strip()

            stock_dict[stock_code] = clean_name

        print(f"✅ {file_name} 종목 {len(stock_dict)}개 로딩 완료")
        return stock_dict

    except Exception as e:
        print(f"❌ {file_name} 파일 로드 실패: {e}")
        return {}

# 코스피 + 코스닥 로딩
stock_name_dict = {}
stock_name_dict.update(load_stock_names('kospi_code.mst'))
stock_name_dict.update(load_stock_names('kosdaq_code.mst'))

# 종목명 조회 함수
def get_stock_name(stock_code):
    return stock_name_dict.get(stock_code, "이름없음")
