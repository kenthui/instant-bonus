import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os

def get_week_url():
    today = datetime.now()
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.day
    if day <= 7:
        week = 1
    elif day <= 14:
        week = 2
    elif day <= 21:
        week = 3
    elif day <= 28:
        week = 4
    else:
        week = 5
    return f"https://jetsostation.com/mtr-mobile-{year}{month}-{week}/"

def scrape_page(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return f"❌ 頁面未找到：{url}"
    soup = BeautifulSoup(r.text, "html.parser")
    # 抓主要內容區
    content = soup.find("article") or soup.find("div", class_="entry-content") or soup.body
    text = content.get_text(separator="\n", strip=True) if content else "無法解析頁面"
    # 只保留有答案/代碼相關行
    lines = [l for l in text.splitlines() if l.strip()]
    # 篩出關鍵行（答案、推廣代碼、日期）
    keywords = ["答案", "代碼", "推廣", "3月", "/3", "MTR", "Code", "code"]
    filtered = [l for l in lines if any(k in l for k in keywords)]
    result = "\n".join(filtered[:30]) if filtered else "\n".join(lines[:30])
    return f"📌 港鐵即時賞本週答案\n🔗 {url}\n\n{result}"

def send_telegram(message):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    r = requests.post(url, json=payload)
    print(r.json())

if __name__ == "__main__":
    url = get_week_url()
    print(f"抓取：{url}")
    message = scrape_page(url)
    print(message)
    send_telegram(message)
