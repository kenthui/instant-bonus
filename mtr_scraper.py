import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
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

def make_link(code):
    return f"https://link.mtrmb.mtr.com.hk/moblink/?promotioncode/?code={code}"

def scrape_codes(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return f"❌ 頁面未找到：{url}"

    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.find("article") or soup.find("div", class_="entry-content") or soup.body
    text = content.get_text(separator="\n", strip=True)

    # 匹配格式：「3月16日 答案X，推廣代碼「XXXXXXX」」
    pattern = re.compile(
        r"(\d+)\s*月\s*(\d+)\s*日.*?推廣代碼[「\s「]*([A-Za-z0-9]+)[」\s」]?",
        re.DOTALL
    )
    matches = pattern.findall(text)

    if not matches:
        return f"⚠️ 暫時未能 parse 到答案，請直接睇：{url}"

    lines = ["🚇 港鐵即時賞本週答案\n"]
    weekdays = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
    for month, day, code in matches:
        try:
            year = datetime.now().year
            date = datetime(year, int(month), int(day))
            wd = weekdays[date.weekday()]
            date_str = f"{month}/{day}（{wd}）"
        except:
            date_str = f"{month}/{day}"
        link = make_link(code)
        lines.append(f"📅 {date_str}\n🔗 {link}\n")

    return "\n".join(lines)

def send_telegram(message):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload)
    print(r.json())

if __name__ == "__main__":
    url = get_week_url()
    print(f"抓取：{url}")
    message = scrape_codes(url)
    print(message)
    send_telegram(message)
