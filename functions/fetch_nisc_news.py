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


def fetch_nisc_news(max_count, execution_timestamp, executable_path):
    """NISCの新着情報を収集・要約します。"""
    url = "https://www.nisc.go.jp/news/list/index.html"
    json_file = "./data/nisc.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)     # 新着情報のページのhtmlが1部しか読み込めない。
        # ページ全体が読み込まれるまで待機
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"NISC: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # #newsList 内のニュース項目を取得
    news_list_div = soup.find('div', id='newsList')
    if not news_list_div:
        print("NISC: ニュースリストが見つかりませんでした。")
        return []

    # ニュース項目の仮想的な構造に基づいて解析
    # 例えば、各ニュースが <div class="news-item"> のような構造であると仮定
    # 実際の構造に合わせて調整してください
    for news_item_div in news_list_div.find_all('div', class_='flex gap-2 w-full py-1 md:flex-col border-b border-dotted border-nisc-gray'):

        title_tag = news_item_div.find('a')
        if not title_tag:
            continue  # タイトルリンクが見つからない場合はスキップ

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.nisc.go.jp" + link  # 相対パスの場合はベースURLを追加

        # 公開日を取得（仮定）
        pub_date_tag = news_item_div.find('span', class_='pub-date')  # 実際のクラス名に合わせて調整
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else "不明"

        # 既存のデータに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"NISC: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"NISC: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "NISC",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"NISC: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items