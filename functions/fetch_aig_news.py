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


def fetch_aig_news(max_count, execution_timestamp, executable_path):
    """AIG損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://www.aig.co.jp/sonpo/company/news"
    json_file = "./data/aig_news.json"
    existing_data = load_existing_data(json_file)

    # ディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(json_file), exist_ok=True)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページロードを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"AIG損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新たに取得したニュースのカウンター

    # ニュースリストを取得
    news_list = soup.find('ul', class_='cmp-newslist')
    if not news_list:
        print("AIG損保: ニュースリストが見つかりません。")
        return []

    for li in news_list.find_all('li', class_='cmp-newslist__item'):

        article = li.find('article', class_='cmp-newslist__row')
        if not article:
            continue

        link_tag = article.find('a', class_='cmp-newslist__link')
        if not link_tag:
            continue

        link = link_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.aig.co.jp" + link  # 相対URLの場合はベースURLを追加

        title = article.find('div', class_='cmp-newslist-item__title').get_text(strip=True)
        pub_date = article.find('div', class_='cmp-newslist-item__date').get_text(strip=True)

        # 既存のデータにタイトルが存在する場合はスキップ
        if any(item['title'] == title for item in existing_data):
            continue

        print(f"AIG損保: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 本文の抽出方法はページの構造に依存します。適宜調整してください。
                content_div = page_soup.find('div', class_='cmp-news-content')  # 仮のクラス名
                if content_div:
                    content = content_div.get_text(separator='\n', strip=True)
                else:
                    content = page_soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"AIG損保: コンテンツ取得失敗 - {link}")
                continue

            # 要約の生成
            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            # ニュースアイテムを構築
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "AIG損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"AIG損保: 要約中にエラー発生 - {e}")
            continue

    # JSONファイルに保存
    save_json(existing_data, json_file)
    return news_items