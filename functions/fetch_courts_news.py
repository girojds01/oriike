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


def fetch_courts_news(max_count, execution_timestamp, executable_path):
    """裁判所の最新情報を収集・要約します。"""
    url = "https://www.courts.go.jp/news/index.html"
    json_file = f"./data/courts_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"裁判所: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_list_div = soup.find('div', class_='module-sub-page-parts-news-parts-1-1')
    if not news_list_div:
        print("裁判所: ニュースリストが見つかりません。")
        return []

    news_items = []
    new_count = 0  # カウンターを追加
    for li in news_list_div.find_all('li'):

        meta_div = li.find('div', class_='module-news-list-meta')
        link_div = li.find('div', class_='module-news-list-link')

        if not meta_div or not link_div:
            continue

        pub_date_span = meta_div.find('span', class_='module-news-pub-time')
        if not pub_date_span:
            continue
        pub_date = pub_date_span.get_text(strip=True)   # 令和6年10月1日の形式

        # '令和6年10月1日' のようなフォーマットを変換
        match = re.match(r'令和(\d+)年(\d+)月(\d+)日', pub_date)
        if not match:
            pub_date = '1000-01-01' # ダミーデータ
        if match:
            # 抽出した年、月、日をゼロ埋め
            year = int(match.group(1)) + 2018
            month = match.group(2).zfill(2)
            day = match.group(3).zfill(2)
            # '2024-10-01' の形式でリストに追加
            pub_date = f'{year}-{month}-{day}'

        if pub_date < '2024-10-01':  # 2024年10月1日以前の記事はスキップ
            continue

        a_tag = link_div.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link:
            continue

        # 相対URLの場合は絶対URLに変換
        if link.startswith('/'):
            link = "https://www.courts.go.jp" + link
        if link.startswith('../'):
            link = "https://www.courts.go.jp" + link[2:]

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"裁判所: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                soup_link = BeautifulSoup(response.text, 'html.parser')
                # ページから本文を抽出するロジックを適宜追加
                content = soup_link.get_text(separator='\n', strip=True)

            if not content:
                print(f"裁判所: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "裁判所",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"裁判所: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items