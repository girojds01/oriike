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


def fetch_toa_news(max_count, execution_timestamp, executable_path):
    """トーア再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.toare.co.jp/newsrelease"
    json_file = f"./data/toa_news.json"
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
        print(f"トーア再保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('div', class_='news_cont').find('ul')
    if not news_list:
        print("ニュースリリースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue
        # 絶対URLに変換
        if link.startswith("/"):
            link = "https://www.toare.co.jp" + link

        date_tag = a_tag.find('span', class_='date')
        label_tag = a_tag.find('span', class_='label')
        p_tag = a_tag.find('p')

        pub_date = date_tag.get_text(strip=True) if date_tag else ""
        label = label_tag.get_text(strip=True) if label_tag else ""
        title = p_tag.get_text(strip=True) if p_tag else ""

        # チェック用タイトル（重複確認）
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"トーア再保険株式会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link) or '/jp-news/download/' in link:
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"トーア再保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'label': label,
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"トーア再保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items