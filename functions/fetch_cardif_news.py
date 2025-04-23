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


def fetch_cardif_news(max_count, execution_timestamp, executable_path):
    """カーディフ損害保険の最新情報を収集・要約します。"""
    url = "https://nonlife.cardif.co.jp/company/news/release"
    json_file = "./data/cardif_news.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        return []

    news_items = []
    new_count = 0  # 取得した新しいニュースのカウント

    # ニュース項目を取得
    for a_tag in soup.find_all('a', class_='news-item'):

        title_tag = a_tag.find('h3')
        date_tag = a_tag.find('span', class_='date')
        p_tag = a_tag.find('p')

        if not title_tag or not date_tag or not p_tag:
            continue  # 必要な情報が不足している場合はスキップ

        title = title_tag.get_text(strip=True)
        pub_date = date_tag.get_text(strip=True)
        link = a_tag.get('href')

        # 既存のデータと重複していないか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"新しいニュースを検出: {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"カーディフ: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "カーディフ損害保険",
                'title': title,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"ニュース処理中にエラーが発生しました: {e}")

    save_json(existing_data, json_file)
    return news_items