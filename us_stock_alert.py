import yfinance as yf
import requests
import os
import json
from datetime import datetime, timedelta

# --- ตั้งค่าตรงนี้ ---
PORTFOLIO = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'AMD', 'GOOGL', 'META'] # แก้เป็นหุ้นที่คุณถือ

# คำสำคัญที่ถือว่ากระทบราคาหุ้นเมกาแรงๆ
HIGH_IMPACT_KEYWORDS = [
    'earnings', 'earnings beat', 'earnings miss', 'guidance', 'raises guidance', 'cuts guidance',
    'upgrade', 'downgrade', 'price target', 'initiated coverage',
    'lawsuit', 'investigation', 'SEC', 'DOJ', 'settlement',
    'merger', 'acquisition', 'buyout', 'spinoff',
    'CEO', 'CFO', 'resigns', 'appointed',
    'FDA approval', 'FDA rejection', 'clinical trial',
    'bankruptcy', 'chapter 11', 'delisting',
    'stock split', 'dividend', 'buyback',
    'contract', 'deal', 'partnership'
]

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
SENT_FILE = 'sent_news.json'

def load_sent_news():
    try:
        with open(SENT_FILE, 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_sent_news(sent_news):
    # เก็บแค่ 200 ลิงก์ล่าสุด กันไฟล์ใหญ่เกิน
    with open(SENT_FILE, 'w') as f:
        json.dump(list(sent_news)[-200:], f)

def send_telegram_alert(ticker, title, link, published_time):
    message = f"🚨 *{ticker} News Alert*\n\n{title}\n\n🕒 {published_time}\n\n🔗 {link}"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        print(f"Sent alert for {ticker}")
    except Exception as e:
        print(f"Failed to send Telegram: {e}")

def check_ticker_news(ticker, sent_news):
    try:
        stock = yf.Ticker(ticker)
        news_list = stock.news
        
        for item in news_list[:7]: # เช็ค 7 ข่าวล่าสุด กันพลาด
            title = item.get('title', '').strip()
            link = item.get('link', '')
            if not title or not link or link in sent_news:
                continue

            # แปลงเวลาข่าวเป็นเวลาอ่านง่าย
            pub_timestamp = item.get('providerPublishTime', 0)
            pub_dt = datetime.fromtimestamp(pub_timestamp)
            # เอาเฉพาะข่าวไม่เกิน 24 ชม กันข่าวเก่าเด้งมา
            if datetime.now() - pub_dt > timedelta(days=1):
                continue
                
            pub_str = pub_dt.strftime('%d %b %Y %H:%M')

            # เช็คว่ามี keyword สำคัญไหม
            if any(keyword.lower() in title.lower() for keyword in HIGH_IMPACT_KEYWORDS):
                send_telegram_alert(ticker, title, link, pub_str)
                sent_news.add(link)
                
    except Exception as e:
        print(f"Error checking {ticker}: {e}")

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_TOKEN or CHAT_ID in environment")
        return
        
    sent_news = load_sent_news()
    print(f"Checking news for {len(PORTFOLIO)} tickers. Already sent: {len(sent_news)} items.")
    
    for ticker in PORTFOLIO:
        check_ticker_news(ticker, sent_news)
        
    save_sent_news(sent_news)
    print("Run complete.")

if __name__ == "__main__":
    main()
