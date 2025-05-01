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


def fetch_nisshinfire_news(max_count, execution_timestamp, executable_path):
    """日新火災海上保険株式会社(お知らせ)の新着情報を収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/info/"
    json_file = f"./data/nisshinfire.json"
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
        print(f"日新火災: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新しい記事の数
    try:
        # 最新のニューステーブルを取得
        table = soup.find('table', class_='newsinfo__idx__table')
        if not table:
            print("日新火災: ニューステーブルが見つかりません。")
            return []

        for tr in table.find_all('tr'):
            th = tr.find('th', class_='newsinfo__idx__table__th')
            td = tr.find('td', class_='newsinfo__idx__table__td')
            if not th or not td:
                continue

            pub_date = th.get_text(strip=True)
            a_tag = td.find('a', class_='_link')
            if not a_tag:
                continue

            link = a_tag.get('href')
            if not link.startswith('http'):
                link = "https://www.nisshinfire.co.jp" + link
            title = a_tag.get_text(strip=True).split('(')[0].strip()

            # 既存データに存在するか確認
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"日新火災: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    soup_detail = BeautifulSoup(response.text, 'html.parser')
                    # 記事の本文を取得（サイト構造に合わせて調整が必要）
                    content = soup_detail.get_text(separator='\n', strip=True)

                if not content:
                    print(f"日新火災: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "日新火災海上保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加


            except Exception as e:
                print(f"日新火災: 要約中にエラー発生 - {e}")

    except Exception as e:
        print(f"日新火災: ニュース解析中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items