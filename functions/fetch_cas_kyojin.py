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


def fetch_cas_kyojin(max_count, execution_timestamp, executable_path):
    """内閣官房(国土強靭化)の新着情報を収集・要約します。"""
    url = "https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/topics.html"
    json_file = f"./data/cas_kyojin.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"内閣官房_国土強靭化: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    topics_div = soup.find('div', class_='topics')
    if not topics_div:
        print("内閣官房_国土強靭化: 'topics' div が見つかりません。")
        return []

    for dl in topics_div.find_all('dl'):

        dt = dl.find('dt').get_text(strip=True)
        dd = dl.find('dd')

        if dt < 'R6.1.1':  # 2024年1月1日以前の記事はスキップ
            continue

        if not dd:
            continue

        a_tag = dd.find('a')
        if not a_tag:
            continue
        link = a_tag.get('href')

        if link.startswith("//www.kantei.go.jp/"):
            link = "https:" + link
        if link.startswith("/jp/"):
            link = "https://www.cas.go.jp" + link
        if not link.startswith("http"):
            link = "https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/" + link

        title = a_tag.get_text(strip=True)

        # 既存データと照合
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"内閣官房_国土強靭化: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"内閣官房_国土強靭化: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': dt,
                'execution_timestamp': execution_timestamp,
                'organization': "内閣官房(国土強靭化)",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"内閣官房_国土強靭化: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news