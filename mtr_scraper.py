import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import re
import os
import time

HKT = timezone(timedelta(hours=8))


def get_week_url(reference_date=None):
    today = (reference_date or datetime.now(HKT)).astimezone(HKT)

    # The site groups pages by the week number in the month. Using the actual
    # calendar date is more reliable than deriving from the Monday/Sunday cross-
    # month boundary, which can drift to the previous week when the page is not
    # updated yet.
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

    year = today.strftime("%Y")
    month = today.strftime("%m")
    return f"https://jetsostation.com/mtr-mobile-{year}{month}-{week}/"


def get_week_urls(reference_date=None):
    today = (reference_date or datetime.now(HKT)).astimezone(HKT)
    urls = [get_week_url(today)]

    # Some days can still show the previous week's page before the new week page
    # is available. Check the last week only as a fallback.
    previous_week = today - timedelta(days=7)
    previous_url = get_week_url(previous_week)
    if previous_url not in urls:
        urls.append(previous_url)
    return urls


def make_link(code):
    return f"https://link.mtrmb.mtr.com.hk/moblink/?promotioncode/?code={code}"


def scrape_content(text):
    soup = BeautifulSoup(text, "html.parser")
    content = soup.find("div", class_="entry-content")
    if not content:
        return []

    text_content = content.get_text(separator="\n", strip=True)
    pattern = re.compile(
        r"(\d+)月(\d+)日\s*答案[：:]?\s*[\(（]?([A-E])[\)）]?\s*[,，]?\s*(?:推廣代碼[：:]?\s*)?[「『\"]?([A-Za-z0-9]+)[」』\"]?",
        re.UNICODE
    )
    return pattern.findall(text_content)


def build_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Accept-Language": "zh-HK,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://jetsostation.com/",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def scrape_with_retry(url, max_retries=3):
    session = build_session()

    for attempt in range(max_retries):
        print(f"嘗試 {attempt + 1}/{max_retries}")

        try:
            r = session.get(url, timeout=20, allow_redirects=True)
            status = r.status_code
            print(f"HTTP {status}")

            if status == 200:
                matches = scrape_content(r.text)
                if matches:
                    return matches
                print("頁面存在但未見答案內容。")

            elif status in (403, 415):
                print("網站阻擋咗呢個 request，唔係等15分鐘就會好。")
                break

            elif status == 404:
                print("頁面未發布或網址唔存在。")
                break

            else:
                print(f"非預期 HTTP {status}。")

        except requests.RequestException as e:
            print(f"Request failed: {e}")

        if attempt < max_retries - 1:
            print("5分鐘後重試...")
            time.sleep(300)

    return []


def scrape(url):
    matches = scrape_with_retry(url)
    if not matches:
        return f"❌ 未找到答案：{url}"

    today = datetime.now(HKT)
    weekdays = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}
    is_monday = today.weekday() == 0

    if is_monday:
        lines = ["🚇 港鐵即時賞本週答案\n"]
        for month, day, answer, code in matches:
            try:
                date = datetime(today.year, int(month), int(day), tzinfo=HKT)
                wd = weekdays[date.weekday()]
                date_str = f"{int(month)}/{int(day)}（{wd}）"
            except Exception:
                date_str = f"{month}/{day}"

            lines.append(f"📅 {date_str} 答案：{answer}\n🔗 {make_link(code)}\n")
        return "\n".join(lines)

    for month, day, answer, code in matches:
        try:
            date = datetime(today.year, int(month), int(day), tzinfo=HKT)
        except Exception:
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
    requests.post(url, json=payload, timeout=20)


if __name__ == "__main__":
    for url in get_week_urls():
        message = scrape(url)

        # Prefer current week; if the current page is not updated yet, fall back
        # to the previous week's page instead of sending stale content.
        if "❌ 未找到答案" not in message and "⚠️ 今日" not in message:
            print(message)
            send_telegram(message)
            break
    else:
        url = get_week_url()
        message = scrape(url)
        print(message)
        send_telegram(message)
