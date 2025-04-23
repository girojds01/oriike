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


def fetch_env_news(max_count, execution_timestamp, executable_path):
    """環境省の新着情報を収集・要約します。"""
    url = "https://www.env.go.jp/press/index.html"
    json_file = f"./data/env.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"環境省: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0   # カウンターを追加

    # 全ての報道発表ブロックを取得
    for block in soup.find_all('details', class_='p-press-release-list__block'):
        # 各ブロックの発表日を取得
        summary_block = block.find('summary', class_='p-press-release-list__head')
        date_heading = summary_block.find('span', class_='p-press-release-list__heading').get_text(strip=True)
        date_heading = date_heading.replace('発表', '')

        if date_heading < "2024年10月01日":  # 2024年10月1日以前の記事はスキップ
            continue

        # そのブロック内のニュースリストを取得
        news_list = block.find('ul', class_='p-news-link c-news-link')
        if not news_list:
            continue

        for li in news_list.find_all('li', class_='c-news-link__item'):

            title_tag = li.find('a', class_='c-news-link__link')
            if not title_tag:
                continue
            link = title_tag.get('href')
            if link.startswith("/"):
                link = "https://www.env.go.jp" + link
            title = title_tag.get_text(strip=True)

            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"環境省: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"環境省: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': date_heading,
                    'execution_timestamp': execution_timestamp,
                    'organization': "環境省",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"環境省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items