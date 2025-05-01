# 以下の関数は、各官公庁の新着情報を取得するための関数です。
import sys
sys.path.append('C:/Users/giroj/packages')
import requests
from utilities_oriike import client,summarize_text,load_existing_data,save_json,is_pdf_link,extract_text_from_pdf
from bs4 import BeautifulSoup
import re
import feedparser
import datetime
import os
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# Seleniumのオプションを設定
options = Options()
# options.add_argument("--headless")
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--lang=ja")
# options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
options.add_argument("--start-maximized")

options.use_chromium = True


def fetch_kensatsu_news(max_count, execution_timestamp, executable_path):
    """検察庁お知らせ一覧を取得して要約する"""
    base_url = "https://www.kensatsu.go.jp"
    url      = f"{base_url}/oshirase/index.shtml"
    json_file = "./data/kensatsu.json"
    existing_data = load_existing_data(json_file)

    # --- EdgeDriver 初期化 ---
    opts = Options()
    opts.use_chromium = True
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Safari/537.36")
    opts.add_argument(f"--user-agent={ua}")
    driver = webdriver.Edge(service=EdgeService(executable_path=executable_path),
                            options=opts)

    try:
        # --- ページ表示 ---
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.arrowLists"))
        )

        # --- a タグを文字列で吸い出す ---
        tmp = []
        for a in driver.find_elements(By.CSS_SELECTOR, "ul.arrowLists li a"):
            title = a.get_attribute("textContent").strip()
            href  = urljoin(base_url, a.get_attribute("href"))
            tmp.append((title, href))
            print(f"📌 {title} → {href}")

    finally:
        # 文字列を確保してから quit
        try:
            driver.quit()
        except Exception:
            pass

    # --- quit 後は文字列処理なので安全 ---
    news_items, new_cnt = [], 0
    for title, href in tmp:
        if any(title == it["title"] for it in existing_data):
            continue

        try:
            # PDF or HTML 取得
            if is_pdf_link(href):
                content = extract_text_from_pdf(href)
            else:
                r = requests.get(href, headers={"User-Agent": ua}, timeout=10)
                r.encoding = "utf-8"
                content = r.text
            if not content:
                print(f"❌ コンテンツ取得不可: {href}")
                continue

            summary = ""
            if new_cnt < max_count:
                summary = summarize_text(title, content)

            item = {
                "pubDate": "",
                "execution_timestamp": execution_timestamp,
                "organization": "検察庁",
                "title": title,
                "link": href,
                "summary": summary,
            }
            news_items.append(item)
            existing_data.append(item)
            new_cnt += 1

        except Exception as e:
            print(f"⚠️ 要約失敗: {e}")

    save_json(existing_data, json_file)
    return news_items