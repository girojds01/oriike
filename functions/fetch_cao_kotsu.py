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


def fetch_cao_kotsu(max_count, execution_timestamp, executable_path):
    """内閣府（交通安全対策）の新着情報を収集・要約します。"""
    url = "https://www8.cao.go.jp/koutu/news.html"
    json_file = "./data/cao_kotsu.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"内閣府_交通安全対策: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを初期化

    # 年度ごとのセクションを取得（最新年度から順に）
    for year_section in soup.find_all('h2'):
        dl = year_section.find_next_sibling('dl', class_='topicsList')
        if not dl:
            continue

        # dtとddのペアを取得
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')

        for dt, dd in zip(dts, dds):

            pub_date = dt.get_text(strip=True)
            link_tag = dd.find('a')
            if not link_tag:
                continue

            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')

            # リンクが相対パスの場合は絶対URLに変換
            if not link.startswith('http'):
                link = "https://www8.cao.go.jp/koutu/" + link.lstrip('/')

            # 既存データに存在するかチェック
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在する場合はスキップ

            print(f"内閣府_交通安全対策: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"内閣府_交通安全対策: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "内閣府(交通安全対策)",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"内閣府_交通安全対策: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items