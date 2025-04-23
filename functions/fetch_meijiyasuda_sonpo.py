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


def fetch_meijiyasuda_sonpo(max_count, execution_timestamp, executable_path):
    """明治安田損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.meijiyasuda-sonpo.co.jp/newsrelease/"
    json_file = "./data/meijiyasuda_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"明治安田損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストのセクションを特定（例として <ul> 内の <li> を想定）
    news_list = soup.find('div', id='mainContents').find_all('li')
    for li in news_list:

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.meijiyasuda-sonpo.co.jp" + link
        title = title_tag.get_text(strip=True)

        # 公開日の取得（例として <span> タグ内にあると仮定）
        pub_date_tag = li.find('span', class_='date')
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else ""

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"明治安田損害保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"明治安田損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "明治安田損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"明治安田損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items