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


def fetch_nihonjishin(max_count, execution_timestamp, executable_path):
    """日本地震再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.nihonjishin.co.jp/news.html"
    json_file = "./data/nihonjishin_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"日本地震再保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # タブごとに処理
    tabs = [
        {'id': 'archive-tab-content-1', 'category': 'お知らせ'},
        {'id': 'archive-tab-content-2', 'category': 'ニュースリリース'}
    ]

    for tab in tabs:
        tab_id = tab['id']
        category = tab['category']
        tab_section = soup.find('div', id=tab_id)
        if not tab_section:
            print(f"{category}: タブセクションが見つかりません。")
            continue

        # 各年のカードを取得
        cards = tab_section.find_all('div', class_='card')
        for card in cards:
            year_id = card.get('id')  # 例: tab01-2024
            year = year_id.split('-')[-1].strip() if '-' in year_id else '不明'

            if year < '2024':
                continue

            card_body = card.find('div', class_='card-body')
            if not card_body:
                print(f"{category} {year}: カードボディが見つかりません。")
                continue

            news_list = card_body.find_all('li')
            for li in news_list:
                date_div = li.find('div', class_='archive-date')
                if not date_div:
                    print(f"{category} {year}: 日付が見つかりません。")
                    continue
                pub_date = date_div.get_text(strip=True)

                # タイトルとリンクを取得
                link_tag = li.find('a')
                if not link_tag:
                    print(f"{category} {year}: タイトルリンクが見つかりません。")
                    continue
                link = link_tag.get('href')
                if link.startswith("/"):
                    link = "https://www.nihonjishin.co.jp" + link
                title = link_tag.get_text(strip=True)

                # カテゴリーを追加
                # チェック: 既に存在するか
                if any(title == item.get('title') for item in existing_data):
                    continue

                print(f"日本地震再保険: 記事取得開始 - {title}")
                try:
                    if is_pdf_link(link):
                        content = extract_text_from_pdf(link)
                    else:
                        response = requests.get(link)
                        response.raise_for_status()
                        response.encoding = 'UTF-8'
                        content_soup = BeautifulSoup(response.text, 'html.parser')
                        # 主要なコンテンツを抽出（仮定）
                        content = content_soup.get_text(separator='\n', strip=True)

                    if not content:
                        print(f"日本地震再保険: コンテンツ取得失敗 - {link}")
                        continue

                    summary = ""
                    if new_count < max_count:
                        summary = summarize_text(title, content)

                    news_item = {
                        'pubDate': pub_date,
                        'execution_timestamp': execution_timestamp,
                        'organization': "日本地震再保険株式会社",
                        'category': category,
                        'title': title,
                        'link': link,
                        'summary': summary
                    }
                    news_items.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1
                except Exception as e:
                    print(f"日本地震再保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items