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


def fetch_daidokasai_news(max_count, execution_timestamp, executable_path):
    """大同火災海上保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.daidokasai.co.jp/news/"
    json_file = "./data/daidokasai_news.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    post_group = soup.find('ul', class_='post-group')
    if not post_group:
        print("ニュースリストが見つかりませんでした。")
        return []

    for li in post_group.find_all('li'):

        a_tag = li.find('a', class_='link')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.daidokasai.co.jp" + link

        title = a_tag.find('span', class_='title').get_text(strip=True)
        pub_date = a_tag.find('span', class_='date').get_text(strip=True)

        if pub_date < "2024-01-01":
            continue

        # カテゴリ取得（存在しない場合は「その他」）
        badge = a_tag.find('span', class_='badge-group').find('span', class_='badge')
        category = badge.get_text(strip=True) if badge else "その他"

        # 既に存在するニュースか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在する場合はスキップ

        print(f"新規記事取得: {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 主要な記事コンテンツを抽出（適宜調整が必要）
                content_div = page_soup.find('div', class_='entry-content')  # クラス名は実際に確認
                if content_div:
                    content = content_div.get_text(separator='\n', strip=True)
                else:
                    content = page_soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"コンテンツが空です: {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "大同火災海上保険株式会社",
                'title': title,
                'link': link,
                'category': category,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"記事処理中にエラーが発生しました: {e}")
            continue

    save_json(existing_data, json_file)
    return news_items