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


def fetch_fdma_news(max_count, execution_timestamp, executable_path):
    """消防庁の最新情報を収集・要約します。"""
    url = "https://www.fdma.go.jp/index.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/fdma.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"消防庁: 記事取得開始 - {entry.title}")
        try:
            # リンクからコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            # 直接HTMLコンテンツを要約する場合
            if not is_pdf_link(entry.link):
                soup = BeautifulSoup(content, 'html.parser')

                # 要約対象のテキストを適切に抽出
                # 具体的なページ構造に応じて調整が必要です
                main_content = soup.find('div', {'class': 'main-content'})  # 例
                if main_content:
                    content_text = main_content.get_text(separator='\n', strip=True)
                else:
                    content_text = content  # フォールバック

            else:
                content_text = content  # PDFテキスト

            if not content_text:
                print(f"消防庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content_text)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "消防庁",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"消防庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news