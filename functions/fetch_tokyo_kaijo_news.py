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


def fetch_tokyo_kaijo_news(max_count, execution_timestamp, executable_path):
    """東京海上日動火災保険株式会社のお知らせを収集・要約します。"""
    url = "https://www.tokiomarine-nichido.co.jp/company/news/"
    json_file = f"./data/tokyo_kaijo_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"東京海上日動_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('dl', class_='listNewsBa')
    if not news_list:
        print("東京海上日動_news: ニュースリストが見つかりませんでした。")
        return []

    for item in news_list.find_all('div', class_='list-detail-07__list'):
        dt = item.find('dt', class_='list-detail-07__term')
        dd = item.find('dd', class_='list-detail-07__desc')

        if not dt or not dd:
            continue

        # 日付の抽出
        date_span = dt.find('span', class_='list-detail-07__date')
        pub_date = date_span.get_text(strip=True) if date_span else ""

        # タイトルとリンクの抽出
        a_tag = dd.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith('http'):
            link = f"https://www.tokiomarine-nichido.co.jp{link}"

        # 既存データのチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"東京海上日動_news: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"東京海上日動_news: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "東京海上日動火災保険_news",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"東京海上日動_news: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items