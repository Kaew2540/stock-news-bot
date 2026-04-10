import yfinance as yf
import requests
import os
import json
from datetime import datetime, timedelta, timezone
import pytz

# ==================== ตั้งค่าทั้งหมดตรงนี้ ====================
PORTFOLIO = ['NVDA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NFLX', 'MA', 'MELI', 'RKLB', 'RBRK', 'ASML', 'LLY', 'UNH', 'PLTR', 'CRWD', 'AVGO', 'DUOL']

# Keywords แบ่งระดับความแรง 3 Tier
TIER_1_KEYWORDS = ['bankruptcy', 'chapter 11', 'delisting', 'SEC investigation', 'DOJ', 'fraud', 'halt']
TIER_2_KEYWORDS = ['earnings', 'guidance', 'raises guidance', 'cuts guidance', 'upgrade', 'downgrade',
                   'price target', 'lawsuit', 'merger', 'acquisition', 'buyout', 'CEO resigns']
TIER_3_KEYWORDS = ['dividend', 'stock split', 'buyback', 'contract', 'partnership', 'FDA approval', 'clinical trial']

# คะแนน Sentiment ขั้นต่ำที่จะส่ง Finnhub: 0.35 = บวก/ลบชัดเจนมาก, 0.15 = มีทิศทาง
MIN_SENTIMENT_SCORE = 0.15

# ข่าวเก่าเกินกี่ชั่วโมงไม่เอา
NEWS_MAX_AGE_HOURS = 24

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
FINNHUB_KEY = os.environ.get('FINNHUB_KEY') # แก้แล้ว: ดึงจาก Secrets ชื่อ FINNHUB_KEY
SENT_FILE = 'sent_news.json'
DAILY_SUMMARY_FILE = 'daily_summary.json'

# ============================================================

def now_th():
    return datetime.now(pytz.timezone('Asia/Bangkok'))

def log(msg):
    print(f"[{now_th().strftime('%H:%M:%S')}] {msg}")

def load_json_file(filename, default):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json_file(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

def get_tier_emoji(title):
    title_lower = title.lower()
    if any(kw.lower() in title_lower for kw in TIER_1_KEYWORDS):
        return '🚨🚨', 'CRITICAL'
    if any(kw.lower() in title_lower for kw in TIER_2_KEYWORDS):
        return '🚨', 'HIGH'
    if any(kw.lower() in title_lower for kw in TIER_3_KEYWORDS):
        return '⚠️', 'MEDIUM'
    return None, None

def get_sentiment_emoji(score):
    if score > 0.35: return '🟢🟢'
    if score > 0.15: return '🟢'
    if score < -0.35: return '🔴🔴'
    if score < -0.15: return '🔴'
    return '⚪️'

def get_stock_price_info(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        prev_close = info.get('previousClose', 0)
        if price and prev_close:
            change_pct = ((price - prev_close) / prev_close) * 100
            return f"${price:.2f} ({change_pct:+.2f}%)"
        return f"${price:.2f}" if price else "N/A"
    except Exception as e:
        log(f"Price fetch error {ticker}: {e}")
        return "N/A"

def fetch_yahoo_news(ticker):
    news_items = []
    try:
        for item in yf.Ticker(ticker).news:
            news_items.append({
                'title': item.get('title', ''),
                'url': item.get('link', ''),
                'time': item.get('providerPublishTime', 0),
                'source': item.get('publisher', 'Yahoo')
            })
    except Exception as e:
        log(f"Yahoo error {ticker}: {e}")
    return news_items

def fetch_finnhub_news(ticker):
    if not FINNHUB_KEY:
        return []
    news_items = []
    try:
        to_date = datetime.now().strftime('%Y-%m-%d')
        from_date = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        url = f"https://finnhub.io/api/v1/company-news"
        params = {'symbol': ticker, 'from': from_date, 'to': to_date, 'token': FINNHUB_KEY}
        r = requests.get(url, params=params, timeout=10)
        for item in r.json():
            news_items.append({
                'title': item.get('headline', ''),
                'url': item.get('url', ''),
                'time': item.get('datetime', 0),
                'source': item.get('source', 'Finnhub'),
                'sentiment': item.get('sentiment', 0)
            })
    except Exception as e:
        log(f"Finnhub error {ticker}: {e}")
    return news_items

def send_telegram(message, disable_preview=False):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': disable_preview
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        log(f"Telegram send failed: {e}")
        return False

def process_ticker(ticker, sent_urls, daily_log):
    log(f"Checking {ticker}")
    all_news = fetch_yahoo_news(ticker) + fetch_finnhub_news(ticker)
    unique_news = {item['url']: item for item in all_news if item.get('url')}.values()

    for item in unique_news:
        url = item['url']
        title = item['title'].strip()
        if not title or url in sent_urls:
            continue

        pub_dt = datetime.fromtimestamp(item['time'])
        if datetime.now() - pub_dt > timedelta(hours=NEWS_MAX_AGE_HOURS):
            continue

        tier_emoji, tier_name = get_tier_emoji(title)
        if not tier_emoji:
            continue

        sentiment_score = item.get('sentiment', 0)
        if abs(sentiment_score) < MIN_SENTIMENT_SCORE and tier_name == 'MEDIUM':
            continue

        sent_emoji = get_sentiment_emoji(sentiment_score)
        price_info = get_stock_price_info(ticker)
        time_str = pub_dt.strftime('%d %b %H:%M')

        msg = f"{tier_emoji} *{ticker}* {sent_emoji}\n"
        msg += f"💵 {price_info}\n\n"
        msg += f"*{title}*\n\n"
        msg += f"📰 {item['source']} | 🕒 {time_str}\n"
        msg += f"🔗 {url}"

        if send_telegram(msg):
            sent_urls.add(url)
            if ticker not in daily_log:
                daily_log[ticker] = []
            daily_log[ticker].append({'title': title, 'tier': tier_name, 'sentiment': sentiment_score})
            log(f"Sent: {ticker} - {title[:50]}...")

def send_daily_summary(daily_log):
    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.now(ny_tz)

    if ny_time.hour == 16 and ny_time.minute < 15:
        if not daily_log:
            send_telegram("📊 *Daily Summary*\n\nวันนี้ไม่มีข่าวสำคัญในพอร์ตของคุณ")
        else:
            msg = "📊 *Daily Summary - Market Close*\n\n"
            for ticker, news_list in daily_log.items():
                msg += f"*{ticker}* - {len(news_list)} ข่าว\n"
                for news in news_list[:3]:
                    sent_emoji = get_sentiment_emoji(news['sentiment'])
                    msg += f" {sent_emoji} {news['title'][:60]}...\n"
                msg += "\n"
            send_telegram(msg, disable_preview=True)
        return True
    return False

def main():
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("FATAL: Missing TELEGRAM_TOKEN or CHAT_ID")
        return

    # บรรทัดเทส ย่อหน้า 4 space ตรงกับบรรทัดอื่น
    send_telegram("✅ *บอทออนไลน์แล้ว* ระบบ Pro ทำงานปกติ รอตรวจข่าวทุก 10 นาที")

    # ย่อหน้า 4 space เท่ากันทุกบรรทัดใน main()
    sent_urls = set(load_json_file(SENT_FILE, []))
    daily_log = load_json_file(DAILY_SUMMARY_FILE, {})
    log(f"Start run. Portfolio: {len(PORTFOLIO)} tickers. Sent history: {len(sent_urls)} urls.")

    for ticker in PORTFOLIO:
        process_ticker(ticker, sent_urls, daily_log)

    if send_daily_summary(daily_log):
        daily_log = {}
        log("Daily summary sent. Log cleared.")

    save_json_file(SENT_FILE, list(sent_urls)[-500:])
    save_json_file(DAILY_SUMMARY_FILE, daily_log)
    log("Run complete.")

if __name__ == "__main__":
    main()
