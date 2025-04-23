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


def fetch_jishinhonbu(max_count, execution_timestamp, executable_path):
    """地震本部の新着情報を収集・要約します。"""
    url = "https://www.jishin.go.jp/update/2024/"
    json_file = f"./data/jishinhonbu.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.encoding = 'UTF-8'
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"地震本部: ページ取得中にエラー発生 {e}")
        return []

    news_items = []
    new_count = 0

    # 更新履歴のリストを取得
    updates = soup.find('dl', class_='updates')
    if not updates:
        print("更新履歴のセクションが見つかりません。")
        return []

    for dt, dd in zip(updates.find_all('dt'), updates.find_all('dd')):

        pub_date = dt.get_text(strip=True)

        title_tag = dd.find('a')
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.jishin.go.jp" + link

        # 既存のニュースに含まれているか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"地震本部: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"地震本部: コンテンツ取得失敗 - {link}")
                continue


            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "地震本部",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"地震本部: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items