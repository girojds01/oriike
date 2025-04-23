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
# Seleniumのオプションを設定
options = Options()
options.add_argument("--headless")
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--no-sandbox")
options.add_argument("--lang=ja")
# options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
options.add_argument("--start-maximized")
options.use_chromium = True


def fetch_moj_news(max_count, execution_timestamp, executable_path):
    """法務省の新着情報を収集・要約します。"""
    url = "https://www.moj.go.jp/news.xml"
    feed = feedparser.parse(url)
    json_file = "./data/moj-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # 新しい記事のカウンター

    for entry in feed.entries:
        # 既に存在するニュースはスキップ
        if any(entry.title == item['title'] for item in existing_data):
            continue

        print(f"法務省: 記事取得開始 - {entry.title}")
        try:
            # リンクがPDFの場合はテキストを抽出、そうでなければHTMLコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"法務省: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            # 最大取得数に達していない場合に要約を実行
            if new_count < max_count:
                summary = summarize_text(entry.title, content)

            # 公開日を取得（存在しない場合は空文字を設定）
            pubDate = entry.get('updated', entry.get('published', ''))

            news_item = {
                'pubDate': pubDate,
                'execution_timestamp': execution_timestamp,
                'organization': "法務省",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"法務省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news