import yfinance as yf

def fetch_pre_or_regular(ticker):
    stock = yf.Ticker(ticker)
    info = stock.info

    pre_price = info.get("preMarketPrice")
    pre_change = info.get("preMarketChangePercent")
    regular_price = info.get("regularMarketPrice")
    regular_change = info.get("regularMarketChangePercent")

    if pre_price:
        print(f"🕓 {ticker} 프리마켓: ${pre_price} ({pre_change:+.2f}%)")
    else:
        print(f"📈 {ticker} 정규장: ${regular_price} ({regular_change:+.2f}%)")

# 테스트
fetch_pre_or_regular("TSLA")
