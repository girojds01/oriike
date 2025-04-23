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


def fetch_yamap_news(max_count, execution_timestamp, executable_path):
    """株式会社ヤマップネイチャランス損害保険の最新情報を収集・要約します。"""
    url = "https://yamap-naturance.co.jp/news"
    json_file = "./data/yamap_naturance_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"YAMAP NATURANCE: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新しいニュースのカウンター

    # ニュース一覧のHTML構造に基づいて調整してください。
    # 一般的に、ニュースは <div class="news-item"> のようなクラスで囲まれていることが多いです。
    # 以下は仮の例です。実際のHTML構造に合わせてセレクタを変更してください。
    for news_div in soup.find_all('div', class_='news-item'):

        title_tag = news_div.find('a')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://yamap-naturance.co.jp" + link

        # 公開日があれば取得（例: <span class="date">2023-10-01</span>）
        date_tag = news_div.find('span', class_='date')
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # 既存データに存在するか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"YAMAP NATURANCE: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース本文のHTML構造に基づいて調整してください。
                # 例えば、<div class="news-content">内に本文がある場合：
                content_div = page_soup.find('div', class_='news-content')
                content = content_div.get_text(separator='\n', strip=True) if content_div else ""

            if not content:
                print(f"YAMAP NATURANCE: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "株式会社ヤマップネイチャランス損害保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"YAMAP NATURANCE: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items