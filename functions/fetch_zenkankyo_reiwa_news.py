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


def fetch_zenkankyo_reiwa_news(max_count, execution_timestamp, executable_path):
    """全管協れいわ損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.zkreiwa-sonpo.co.jp/"
    json_file = f"./data/zkreiwa_news.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページの読み込みを待つ
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"全管協れいわ損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 「お知らせ一覧」セクションを探す
    post_list_container = soup.find('div', class_='postList postList_miniThumb')
    if not post_list_container:
        print("お知らせ一覧のセクションが見つかりませんでした。")
        return []

    for post_item in post_list_container.find_all('div', class_='postList_item'):
        title_tag = post_item.find('div', class_='postList_title').find('a')
        date_tag = post_item.find('div', class_='postList_date')

        if not title_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        pub_date = date_tag.get_text(strip=True)

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"全管協れいわ損害保険株式会社: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # 記事本文を抽出（実際のサイト構造に合わせて調整が必要）
                content_div = content_soup.find('div', class_='entry-body')  # クラス名は仮
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = content_soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"全管協れいわ損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "全管協れいわ損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"全管協れいわ損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items