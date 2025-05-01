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


def fetch_tokiomarine_news(max_count, execution_timestamp, executable_path):
    """東京海上日動火災保険のニュースリリースを収集・要約します。"""
    url = "https://www.tokiomarine-nichido.co.jp/company/release/"
    json_file = "./data/tokiomarine_news_release.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページが完全に読み込まれるまで待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"東京海上日動_news_release: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # ニュースリリースリストを取得
    news_list = soup.find('dl', class_='list-detail-07')
    if not news_list:
        print("東京海上日動_news_release: ニュースリリースリストが見つかりません。")
        return []

    for news_div in news_list.find_all('div', class_='list-detail-07__list'):
        # 日付とカテゴリを取得
        dt_term = news_div.find('dt', class_='list-detail-07__term')
        if not dt_term:
            continue
        pub_date_tag = dt_term.find('span', class_='list-detail-07__date')
        category_tag = dt_term.find('span', class_='icon-txt')
        if not pub_date_tag or not category_tag:
            continue
        pub_date = pub_date_tag.get_text(strip=True)
        category = category_tag.get_text(strip=True)

        # タイトルとリンクを取得
        dd_desc = news_div.find('dd', class_='list-detail-07__desc')
        if not dd_desc:
            continue
        a_tag = dd_desc.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link:
            continue
        # 相対URLを絶対URLに変換
        if link.startswith("/"):
            link = "https://www.tokiomarine-nichido.co.jp" + link

        # 既存データに同じタイトルが存在する場合はスキップ
        if any(item['title'] == title for item in existing_data):
            continue

        print(f"東京海上日動_news_release: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding
                content = response.text

            if not content:
                print(f"東京海上日動_news_release: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "東京海上日動火災保険株式会社_news_release",
                'category': category,
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"東京海上日動_news_release: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items