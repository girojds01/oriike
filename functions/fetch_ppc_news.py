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


def fetch_ppc_news(max_count, execution_timestamp, executable_path):
    """個人情報保護委員会の最新情報を収集・要約します。"""
    url = "https://www.ppc.go.jp/information/"
    json_file = f"./data/ppc.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"個人情報保護委員会: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 'ul' タグで class が 'news-list' のものをすべて取得
    news_lists = soup.find_all('ul', class_='news-list')
    for news_list in news_lists:
        for li in news_list.find_all('li'):

            # 'time' タグから日付を取得
            time_tag = li.find('time', class_='news-date')
            if not time_tag:
                continue
            pub_date = time_tag['datetime']

            if pub_date < "2024-01-01":  # 2021年1月1日以降の記事のみ取得
                continue

            # 'div.news-text a' タグからタイトルとリンクを取得
            news_text_div = li.find('div', class_='news-text')
            if not news_text_div:
                continue
            link_tag = news_text_div.find('a')
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')
            if link.startswith("/"):
                link = "https://www.ppc.go.jp" + link

            # 既存のデータに存在するかチェック
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"個人情報保護委員会: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"個人情報保護委員会: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "個人情報保護委員会",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"個人情報保護委員会: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items