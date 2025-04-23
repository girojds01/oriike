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


def fetch_au_news(max_count, execution_timestamp, executable_path):
    """au損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.au-sonpo.co.jp/corporate/news/"
    json_file = f"./data/au_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページが完全にロードされるまで待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"au損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新規ニュースのカウンター

    # ニュースリストのul要素を取得
    news_list_ul = soup.find('ul', class_='js-news-list-render')
    if not news_list_ul:
        print("au損害保険: ニュースリストが見つかりません。")
        return []

    # 各ニュース項目をループ
    for li in news_list_ul.find_all('li'):
        title_tag = li.find('a')
        if not title_tag:
            continue

        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.au-sonpo.co.jp" + link
        title = title_tag.get_text(strip=True)

        # 日付を取得（例としてspanタグ内にあると仮定）
        date_tag = li.find('span', class_='date')  # 実際のクラス名に合わせて変更
        if date_tag:
            pub_date = date_tag.get_text(strip=True)
        else:
            # 日付が見つからない場合は空文字を設定
            pub_date = ""

        # 既存データに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"au損害保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding  # 正しいエンコーディングを自動検出
                content = response.text

            if not content:
                print(f"au損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "au損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"au損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items