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


def fetch_kensatsu_news(max_count, execution_timestamp, executable_path):
    """検察庁の最新情報を収集・要約します。"""
    url = "https://www.kensatsu.go.jp/rireki/index.shtml"
    json_file = f"./data/kensatsu.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url) # seleniumアクセス禁止のためかページのhtmlが読み込めない。
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"検察庁: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # 検察庁のページの構造に応じてセレクタを調整してください
    # 例として、ニュースが <ul class="news-list"> 内の <li> にリストされていると仮定
    news_list = soup.find('ul', class_='news-list')
    if not news_list:
        print("検察庁: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        a_tag = li.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.kensatsu.go.jp" + link

        pub_date_text = li.get_text()
        # 日付形式に合わせてパース。例: "2023年10月01日"
        pub_date = pub_date_text.split('）')[-1].strip() if '）' in pub_date_text else pub_date_text

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"検察庁: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"検察庁: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "検察庁",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"検察庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news