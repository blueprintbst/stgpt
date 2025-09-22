#기능 A - 단기과열/투자경고 공시 알림 - 파이썬애니웨어
#-> holiday_checker로 휴장일 체크 후 휴장일이면 실행 X (매년 초 수정해줘야함.)
#-> main.py

##기능 B - 단기과열/투자경고 공시 지정 가격 알림 - 파이썬애니웨어
#-> holiday_checker로 휴장일 체크 후 휴장일이면 실행 X (매년 초 수정해줘야함.)
#-> notice_fetcher.py / config 내 키워드 변수 중 지정예고 공시만 필터링
#-> price_fetcher.py / 필터링 된 공시 가지고 가격 계산 후 메세지 전송##

#기능 C - 거래대금 정규장/애프터마켓 마감 후 알림 - 파이썬애니웨어 (시간차이만 둠)
#-> holiday_checker로 휴장일 체크 후 휴장일이면 실행 X (매년 초 수정해줘야함.)
#-> market_value.py / KRX는 API로 대금 조회 + NXT는 크롤링 대금 조회 (20분 지연) 후 합산 뒤 출력

#기능 D - 나스닥 애프터마켓 마감 후 알림 - 파이썬애니웨어 (우리나라 오전 시간대)
#-> save_closing_prices.py로 정규장 마감 후 시세 조회 뒤 json 파일 생성해서 저장
#-> after_globalstock.py로 json 파일 읽어와 정규장 시세 출력 및 현재가 출력 (애프터마켓)

#기능 E - 나스닥 주간거래 중 알림 - Render (우리나라 낮 시간대)
#-> pre_globalstock.py로 현재가 시세 조회. 시간 조건만 걸어주면 됨.

#기능 F - 나스닥 프리마켓, 정규장 중 알림 - Render (우리나라 오후 시간대)
#-> pre_globalstock.py로 현재가 시세 조회. 시간 조건만 걸어주면 됨.

#기능 G - 선물 시세 조회 - Render
#-> futures.py로 인베스팅닷컴 크롤링. 

#기능 H - 선물 시세 조회 + 코스피200 - Render
#-> futures_kospi200로 휴장일에는 미조회




#<대전제는 나스닥 쪽은 시세조회 시간 조건을 걸어줘야함.>

#매주 월 오전 07시~ 토 오전 09시 사이에만 실행하도록 한다.


#------------------------- module. 세팅 모듈 -------------------------

#token_manager.py -> 토큰매니저 (로그인용)
#telegram_sender.py -> 텔레그램 보내는 기능
#config.py -> 중요정보 및 종목 정보 나열
#holiday_checker.py -> 휴장일 조회

#----------------------- a. 단기과열/투자경고 알림  ----------------- (파이썬애니웨어)

#main.py -> 단기과열, 투자경고 공시 필터
#message_builder.py -> main.py에서 메세지 빌더 양식

#---------------- b. 단기과열/투자경고 공시 지정 가격 알림  ----------------- (파이썬애니웨어 / import : a.holiday_checker, a.config)

#notice_fetcher.py -> config 내 키워드 변수 중 지정예고 공시만 필터링
#stock_name_mapper.py -> mst 파일을 읽고, notice_fetcher에서 종목코드를 받아와서, price_fetcher.py에서 사용하여 종목명으로 변환
#price_fetcher.py -> 필터링 된 공시 가지고 가격 계산 후 메세지 전송

#----------------------- c. 거래대금 정규장/애프터마켓 마감 후 알림  ----------------- (파이썬애니웨어 / 시간차이만 둠. / import : a.holiday_checker)

#market_value.py -> NXT, KRX 거래대금 (KRX는 API로 대금 조회 + NXT는 크롤링 대금 조회 (20분 지연) 후 합산 뒤 출력)

#---------------- d. 나스닥 애프터마켓 마감 후 알림  ----------------- (파이썬애니웨어 / KST0700)

#save_closing_prices.py -> 정규장 종가 저장 후, jason 파일로 저장. 이후 after_globalstock.py에서 출력
#after_globalstock.py -> 애프터마켓 조회 (07시, jason 사용)

#---------------- e. 나스닥 주간거래 / 프리마켓 / 정규장 시세 조회  ----------------- (Render / 시간 조건으로 구분. 파일 내 조건 참고)

#pre_globalstock.py -> (09시~16시 59분 주간거래 / 17시~22시 29분 프리마켓 / 22시 30분~04시 59분 정규장)
"★★ 썸머타임 때 시간변경 필수!!★★"

#---------------- f. 선물 시세 조회  ----------------- (Render / 인베스팅닷컴 크롤링)

#futures.py -> 해외선물 인베스팅닷컴 조회
#futures_kospi200.py -> 코스피 야간선물 조회 (휴장일에는 미조회. 한국투자증권API 사용) / import : a.holiday_checker
"★★ 선물 3,6,9,12월물 변경 수동 ★★"


module_token_manager.py
module_telegram_sender.py
module_config.py
module_holiday_checker.py

- 메인 이름 바꾸는걸로. 
a_main.py
a_message_builder.py

b_notice_fetcher.py
b_stock_name_mapper.py
b_price_fetcher.py

c_market_value.py

d_save_closing_prices.py
d_after_globalstock.py

e_pre_globalstock.py

f_futures.py
f_futures_kospi200.py