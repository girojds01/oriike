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


def fetch_capital_sonpo_news(max_count, execution_timestamp, executable_path):
    """キャピタル損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.capital-sonpo.co.jp/"  # 最新情報ページのURLに置き換えてください
    json_file = f"./data/capital_sonpo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページ読み込み待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"キャピタル損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュース項目を含むセクションを特定します。
    # 以下は仮のセレクターです。実際のHTML構造に合わせて調整してください。
    # 例: <div class="news-list"><ul><li>...</li></ul></div>
    news_section = soup.find('div', class_='news-list')  # クラス名は実際のものに置き換えてください
    if not news_section:
        print("ニュースセクションが見つかりませんでした。セレクターを確認してください。")
        return []

    for li in news_section.find_all('li'):

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.capital-sonpo.co.jp" + link  # 相対URLの場合の対応
        title = title_tag.get_text(strip=True)
        pub_date_tag = li.find('span', class_='date')  # 日付を含むタグのクラス名に置き換えてください
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else "不明"

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"キャピタル損害保険株式会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'  # エンコーディングを必要に応じて調整
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # 記事内容を含むセクションを特定します。以下は仮のセレクターです。
                content_section = content_soup.find('div', class_='article-content')  # 実際のクラス名に置き換えてください
                if content_section:
                    content = content_section.get_text(separator="\n", strip=True)
                else:
                    content = response.text  # セクションが見つからない場合は全体を使用

            if not content:
                print(f"キャピタル損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "キャピタル損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"キャピタル損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items