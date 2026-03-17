import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re
import os

HKT = timezone(timedelta(hours=8))

def get_week_url():
    today = datetime.now(HKT)
    year = today.strftime("%Y")
    month = today.strftime("%m")
    day = today.day
    if day <= 7: week = 1
    elif day <= 14: week = 2
    elif day <= 21: week = 3
    elif day <= 28: week = 4
    else: week = 5
    return f"https://jetsostation.com/mtr-mobile-{year}{month}-{week}/"

def make_link(code):
    return f"https://link.mtrmb.mtr.com.hk/moblink/?promotioncode/?code={code}"

def scrape(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=10)
    if r.status_code != 200:
        return f"❌ 頁面未找到：{url}"

    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.find("div", class_="entry-content")
    text = content.get_text(separator="\n", strip=True)

    pattern = re.compile(r"(\d+)月(\d+)日\s*答案\s*\(([A-E])\)\s*[「「]([A-Za-z0-9]+)[」」]")
    matches = pattern.findall(text)

    if not matches:
        return f"⚠️ 暫時未能 parse 到答案，請直接睇：{url}"

    today = datetime.now(HKT)
    weekdays = {0:"一", 1:"二", 2:"三", 3:"四", 4:"五", 5:"六", 6:"日"}
    is_monday = today.weekday() == 0

    if is_monday:
        lines = ["🚇 港鐵即時賞本週答案\n"]
        for month, day, answer, code in matches:
            try:
                date = datetime(today.year, int(month), int(day), tzinfo=HKT)
                wd = weekdays[date.weekday()]
                date_str = f"{int(month)}/{int(day)}（{wd}）"
            except:
                date_str = f"{month}/{day}"
            lines.append(f"📅 {date_str} 答案：{answer}\n🔗 {make_link(code)}\n")
        return "\n".join(lines)

    else:
        for month, day, answer, code in matches:
            try:
                date = datetime(today.year, int(month), int(day), tzinfo=HKT)
            except:
                continue
            if date.date() == today.date():
                wd = weekdays[date.weekday()]
                return (
                    f"🚇 港鐵即時賞\n"
                    f"📅 {int(month)}/{int(day)}（{wd}） 答案：{answer}\n"
                    f"🔗 {make_link(code)}"
                )
        return f"⚠️ 今日（{today.month}/{today.day}）答案未找到，請直接睇：{url}"

def send_telegram(message):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    url = get_week_url()
    message = scrape(url)
    print(message)
    send_telegram(message)
