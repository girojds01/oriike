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


def fetch_hdmf_news(max_count, execution_timestamp, executable_path):
    """現代海上火災保険株式会社の最新情報を収集・要約します。"""
    url = "http://www.hdinsurance.co.jp/"
    json_file = f"./data/hdmf.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"現代海上火災保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # '最新情報'セクションを特定（例としてPDFリンクを探す）
    # 実際のHTML構造に基づいて適宜調整してください
    # ここでは osirase*.pdf のリンクを収集
    osirase_links = soup.find_all('a', href=lambda href: href and href.startswith('./osirase') and href.endswith('.pdf'))

    for link_tag in osirase_links:
        relative_link = link_tag.get('href')
        link = requests.compat.urljoin(url, relative_link)
        title = link_tag.get_text(strip=True) or link.split('/')[-1]

        # 公開日の推定（PDF名から取得。例: osirase40.pdf → 40回目のお知らせ）
        # 必要に応じて日付の解析を追加
        pub_date = "不明"

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"現代海上火災保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'shift_jis'
                content = response.text

            if not content:
                print(f"現代海上火災保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "現代海上火災保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"現代海上火災保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items