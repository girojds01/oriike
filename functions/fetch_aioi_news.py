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


def fetch_aioi_news(max_count, execution_timestamp, executable_path):
    """あいおいニッセイ同和損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://www.aioinissaydowa.co.jp/corporate/about/news/"
    json_file = f"./data/aioi_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"あいおいニッセイ同和損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新年のセクションを取得（例: 2024年）
    latest_year_tab = soup.find('div', class_='m-tab-contents is-active')
    if not latest_year_tab:
        print("最新年のニュースセクションが見つかりませんでした。")
        return []

    # ニュースリストを取得
    news_list = latest_year_tab.find('ul')
    if not news_list:
        print("ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li', class_='m-news'):

        title_tag = li.find('a', class_='iconPdf01')
        if not title_tag:
            continue
        link = title_tag.get('href')
        title = title_tag.get_text(strip=True)
        time_tag = li.find('time', class_='m-news__date')
        pub_date = time_tag.get_text(strip=True) if time_tag else "不明"

        # フルURLを生成
        if link.startswith("/"):
            link = "https://www.aioinissaydowa.co.jp" + link
        if link.startswith("pdf/"):
            link = url + link

        # 既存のデータに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"あいおいニッセイ同和損害保険: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"あいおいニッセイ同和損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "あいおいニッセイ同和損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"あいおいニッセイ同和損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items