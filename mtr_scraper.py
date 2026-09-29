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
    # Do not fall back to the previous week's URL — only check the current week.
    today = (reference_date or datetime.now(HKT)).astimezone(HKT)
    return [get_week_url(today)]


def make_link(code):
    return f"https://link.mtrmb.mtr.com.hk/moblink/?promotioncode/?code={code}"


def _candidate_text_blocks(soup):
    selectors = [
        "div.entry-content",
        "div.post-content",
        "div.content",
        "article",
        "main",
        "div#content",
    ]

    blocks = []
    for selector in selectors:
        for node in soup.select(selector):
            text = node.get_text("\n", strip=True)
            if text:
                blocks.append(text)

    if not blocks:
        body = soup.body or soup
        text = body.get_text("\n", strip=True)
        if text:
            blocks.append(text)

    return blocks


def extract_codes_from_links(soup):
    """從頁面中所有 <a href=...> 嘗試抽取 query param 裡面嘅 code（後備用）。"""
    codes = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # 常見參數形式 code=..., promotioncode=...
        m = re.search(r"(?:code|promotioncode)=([A-Za-z0-9\-]+)", href, re.IGNORECASE)
        if m:
            codes.append((m.group(1).upper(), a.get_text(" ", strip=True), a))
    return codes


def scrape_content(text):
    soup = BeautifulSoup(text, "html.parser")
    blocks = _candidate_text_blocks(soup)
    if not blocks:
        return []

    entries = []
    seen = set()

    # 日期 / 答案 / code patterns（更寬鬆）
    date_regex = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
    answer_patterns = [
        re.compile(r"答案[：:]?\s*[（(]?\s*([A-E])\s*[）)]?", re.IGNORECASE),
        re.compile(r"正確答案[：:]?\s*([A-E])", re.IGNORECASE),
        re.compile(r"答案是\s*([A-E])", re.IGNORECASE),
        re.compile(r"([A-E])\s*(?:[,，\)\。]|$)", re.IGNORECASE),
    ]
    code_patterns = [
        re.compile(r"(?:推廣代碼|優惠代碼|代碼|優惠券代碼)[：:]\s*[「『\"]?([A-Za-z0-9\-]{3,})[」』\"]?", re.IGNORECASE),
        re.compile(r"([A-Za-z0-9\-]{3,})"),
    ]

    # 1) 先在已存在嘅文字區塊內搜尋（原有邏輯 + 放寬）
    for block in blocks:
        normalized = re.sub(r"\s+", " ", block)
        for m in date_regex.finditer(normalized):
            date_start = m.end()
            segment = normalized[date_start:date_start + 350]

            # 找答案
            answer = None
            for p in answer_patterns:
                am = p.search(segment)
                if am:
                    answer = am.group(1).upper()
                    break
            if not answer:
                continue

            # 找 code
            code = None
            for cp in code_patterns:
                cm = cp.search(segment)
                if cm:
                    code = cm.group(1).upper()
                    break
            if not code:
                continue

            item = (m.group(1), m.group(2), answer, code)
            if item not in seen:
                seen.add(item)
                entries.append(item)

    # 2) 如果第一步無結果，試下喺 HTML 節點層次（更貼近原始標籤）搵
    if not entries:
        for text_node in soup.find_all(string=date_regex):
            m = date_regex.search(str(text_node))
            if not m:
                continue
            # 往上兩級嘗試取得更大上下文
            parent = text_node.parent
            context_nodes = [parent]
            if parent is not None and parent.parent is not None:
                context_nodes.append(parent.parent)
            for node in context_nodes:
                context = " ".join(node.stripped_strings)
                context = re.sub(r"\s+", " ", context)
                seg = context
                # 答案
                answer = None
                for p in answer_patterns:
                    am = p.search(seg)
                    if am:
                        answer = am.group(1).upper()
                        break
                if not answer:
                    continue
                # code
                code = None
                for cp in code_patterns:
                    cm = cp.search(seg)
                    if cm:
                        code = cm.group(1).upper()
                        break
                if not code:
                    # 嘗試同一 parent 下的連結（例如按鈕或 href）
                    for a in node.find_all("a", href=True):
                        href = a["href"]
                        cm = re.search(r"(?:code|promotioncode)=([A-Za-z0-9\-]+)", href, re.IGNORECASE)
                        if cm:
                            code = cm.group(1).upper()
                            break
                if code:
                    item = (m.group(1), m.group(2), answer, code)
                    if item not in seen:
                        seen.add(item)
                        entries.append(item)

    # 3) 再唔到，嘗試從所有連結抽 code 作為最後後備，並試配頁內任一日期或今日
    if not entries:
        link_codes = extract_codes_from_links(soup)
        if link_codes:
            # 嘗試搵最接近嘅日期（整個頁面掃一次）
            full_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            m = date_regex.search(full_text)
            # 如果搵到日期，用第一個日期配所有連結；若無，嘗試用今日日子作 fallback
            if m:
                month, day = m.group(1), m.group(2)
            else:
                # 用今天（本月/本日）作為 fallback
                now = datetime.now(HKT)
                month, day = str(now.month), str(now.day)

            for code, link_text, a in link_codes:
                # 嘗試喺連結附近找答案字母
                parent_text = " ".join(a.parent.stripped_strings) if a.parent else link_text
                ans = None
                for p in answer_patterns:
                    am = p.search(parent_text)
                    if am:
                        ans = am.group(1).upper()
                        break
                # 如果冇答案，就用 '?' 佔位（後續可以用 HTML 預覽比人手配對）
                ans = ans or "?"
                item = (month, day, ans, code)
                if item not in seen:
                    seen.add(item)
                    entries.append(item)

    return entries


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
                try:
                    text = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
                    snippet = re.sub(r"\s+", " ", text)[:1200]
                    if snippet:
                        print(f"HTML 預覽: {snippet}")
                except Exception:
                    pass

            elif status in (403, 415):
                print("網站阻擋咗呢個 request，唔係等15分鐘就會好。")
                break

            elif status == 404:
                print("頁面未發布或網址唔不存在。")
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
    # Only check the current week's page; do not fall back to the previous week.
    url = get_week_url()
    message = scrape(url)
    print(message)
    send_telegram(message)
