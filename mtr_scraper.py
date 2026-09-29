import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

HKT = timezone(timedelta(hours=8))


def get_week_url(reference_date=None):
    today = (reference_date or datetime.now(HKT)).astimezone(HKT)
    week = min((today.day - 1) // 7 + 1, 5)
    return f"https://jetsostation.com/mtr-mobile-{today:%Y%m}-{week}/"


def get_week_urls(reference_date=None):
    return [get_week_url(reference_date)]


def make_link(code):
    return f"https://link.mtrmb.mtr.com.hk/moblink/?promotioncode/?code={code}"


def _candidate_text_blocks(soup):
    for node in soup(["script", "style", "noscript"]):
        node.decompose()

    selectors = (
        "div.inner-post-entry.entry-content",
        "div.entry-content",
        "div.post-content",
        "article",
        "main",
        "div#content",
    )
    blocks = []
    for selector in selectors:
        for node in soup.select(selector):
            text = node.get_text("\n", strip=True)
            if text and text not in blocks:
                blocks.append(text)
    if not blocks:
        text = (soup.body or soup).get_text("\n", strip=True)
        if text:
            blocks.append(text)
    return blocks


def scrape_content(text):
    """Extract entries from lines such as: 9月28日 答案 (B) 「Oct31MP」."""
    soup = BeautifulSoup(text, "html.parser")
    blocks = _candidate_text_blocks(soup)
    if not blocks:
        return []

    # Do not use a generic alphanumeric fallback: it previously captured the
    # answer letter B as the code instead of Oct31MP.
    entry_re = re.compile(
        r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
        r"\s*(?:正確)?答案\s*[：:]?\s*"
        r"[（(]\s*(?P<answer>[A-E])\s*[）)]"
        r"\s*[「『\"'“‘]?\s*(?P<code>[A-Za-z0-9][A-Za-z0-9-]{2,})"
        r"\s*[」』\"'”’]?",
        re.IGNORECASE,
    )
    # Also accept a plain answer/code without brackets, while still requiring
    # the labels so unrelated page text cannot become a coupon code.
    loose_re = re.compile(
        r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日"
        r"\s*(?:正確)?答案\s*[：:]?\s*"
        r"[（(]?\s*(?P<answer>[A-E])\s*[）)]?\s*"
        r"[「『\"'“‘]\s*(?P<code>[A-Za-z0-9][A-Za-z0-9-]{2,})\s*[」』\"'”’]",
        re.IGNORECASE,
    )

    entries = []
    seen = set()
    for block in blocks:
        normalized = re.sub(r"\s+", " ", block)
        matches = list(entry_re.finditer(normalized))
        if not matches:
            matches = list(loose_re.finditer(normalized))
        for match in matches:
            item = (
                match.group("month"),
                match.group("day"),
                match.group("answer").upper(),
                match.group("code").upper(),
            )
            if item not in seen:
                seen.add(item)
                entries.append(item)
    return entries


def build_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-HK,zh-TW;q=0.9,zh;q=0.8,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://jetsostation.com/",
    })
    return session


def scrape_with_retry(url, max_retries=3):
    session = build_session()
    for attempt in range(max_retries):
        print(f"嘗試 {attempt + 1}/{max_retries}")
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            print(f"HTTP {response.status_code} ({response.url})")
            if response.status_code == 200:
                matches = scrape_content(response.text)
                if matches:
                    return matches
                print("頁面存在但未見符合格式的答案內容。")
                preview = re.sub(
                    r"\s+", " ", BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True)
                )[:1200]
                if preview:
                    print(f"HTML 預覽: {preview}")
                break
            if response.status_code in (403, 404, 415):
                print("網站拒絕請求，或者頁面不存在。")
                break
            print(f"非預期 HTTP {response.status_code}。")
        except requests.RequestException as error:
            print(f"Request failed: {error}")
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

    if today.weekday() == 0:
        lines = ["🚇 港鐵即時賞本週答案\n"]
        for month, day, answer, code in matches:
            date = datetime(today.year, int(month), int(day), tzinfo=HKT)
            lines.append(
                f"📅 {int(month)}/{int(day)}（{weekdays[date.weekday()]}）答案：{answer}\n"
                f"🔗 {make_link(code)}\n"
            )
        return "\n".join(lines)

    for month, day, answer, code in matches:
        date = datetime(today.year, int(month), int(day), tzinfo=HKT)
        if date.date() == today.date():
            return (
                f"🚇 港鐵即時賞\n"
                f"📅 {int(month)}/{int(day)}（{weekdays[date.weekday()]}）答案：{answer}\n"
                f"🔗 {make_link(code)}"
            )

    # The supplied 2026-09-29 page contains 9/28 and 9/30, but no 9/29.
    # Show the entries that were actually published instead of reporting a
    # misleading parser failure.
    lines = [f"⚠️ 今日（{today.month}/{today.day}）未有答案；頁面現有答案："]
    for month, day, answer, code in matches:
        lines.append(f"📅 {int(month)}/{int(day)} 答案：{answer}\n🔗 {make_link(code)}")
    return "\n".join(lines) + f"\n\n來源：{url}"


def send_telegram(message):
    response = requests.post(
        f"https://api.telegram.org/bot{os.environ['TELEGRAM_TOKEN']}/sendMessage",
        json={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": message, "disable_web_page_preview": True},
        timeout=20,
    )
    response.raise_for_status()


if __name__ == "__main__":
    url = get_week_url()
    message = scrape(url)
    print(message)
    send_telegram(message)
