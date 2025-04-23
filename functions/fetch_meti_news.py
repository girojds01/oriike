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


def fetch_meti_news(max_count, execution_timestamp, executable_path):
    """経済産業省の新着情報を収集・要約します。"""
    url = "https://www.meti.go.jp/ml_index_release_atom.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/meti.json"
    existing_data = load_existing_data(json_file)

    new_news = []

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"経済産業省: 記事取得開始 - {entry.title}")

        # リンク先のhtmlがrequests, seleniumともに取得不可。RSSにsummaryがあるのでそちらを利用

        news_item = {
            'pubDate': entry.updated,
            'execution_timestamp': execution_timestamp,
            'organization': "経済産業省",
            'title': entry.title,
            'link': entry.link,
            'summary': entry.summary
        }
        new_news.append(news_item)
        existing_data.append(news_item)

    save_json(existing_data, json_file)
    return new_news