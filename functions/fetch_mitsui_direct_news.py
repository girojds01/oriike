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


def fetch_mitsui_direct_news(max_count, execution_timestamp, executable_path):
    """三井ダイレクト損保の最新情報を収集・要約します。"""
    url = "https://news.mitsui-direct.co.jp/index.html?category=4000"
    json_file = f"./data/mitsui_direct_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページのロードを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"三井ダイレクト損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストのセクションを特定（仮定）
    # 実際のサイトのHTML構造に合わせて変更してください
    # 例えば、ニュースが<div class="news-list">内にある場合
    news_list_section = soup.find('div', class_='news-list')  # クラス名は実際に合わせてください
    if not news_list_section:
        print("ニュースリストのセクションが見つかりませんでした。")
        return []

    for article in news_list_section.find_all('article'):  # タグやクラス名は実際に合わせてください

        title_tag = article.find('h2')  # タイトルのタグを実際に合わせてください
        link_tag = article.find('a', href=True)
        date_tag = article.find('time')  # 日付のタグを実際に合わせてください

        if not title_tag or not link_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = link_tag['href']
        if not link.startswith('http'):
            link = "https://news.mitsui-direct.co.jp" + link
        pub_date = date_tag.get_text(strip=True)

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"三井ダイレクト損保: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"三井ダイレクト損保: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "三井ダイレクト損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"三井ダイレクト損保: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items