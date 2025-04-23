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


def fetch_zurich_news(max_count, execution_timestamp, executable_path):
    """チューリッヒの最新情報を収集・要約します。"""
    url = "https://www.zurich.co.jp/aboutus/news/"
    json_file = f"./data/zurich_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"チューリッヒ: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='list-date-01')
    if not news_list:
        print("チューリッヒ: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        # 日付とタイプを取得
        spans = li.find_all('span')
        if len(spans) < 2:
            continue  # 必要な情報が不足している場合はスキップ

        pub_date = spans[0].get_text(strip=True)
        news_type = spans[1].get_text(strip=True)

        # タイトルとリンクを取得
        title_tag = li.find('a')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.zurich.co.jp" + link

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"チューリッヒ: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                if response.encoding is None:
                    response.encoding = 'utf-8'  # エンコーディング不明の場合はutf-8をデフォルト
                content = response.text

            if not content:
                print(f"チューリッヒ: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'type': news_type,
                'organization': "チューリッヒ・インシュアランス・カンパニー・リミテッド",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"チューリッヒ: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items