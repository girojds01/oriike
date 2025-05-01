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


def fetch_nta_news(max_count, execution_timestamp, executable_path):
    """国税庁の新着情報を収集・要約します。"""
    url = "https://www.nta.go.jp/information/release/index.htm"
    json_file = f"./data/nta.json"
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
        print(f"国税庁: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # 国税庁発表分セクションを探す
    nta_section = soup.find('h2', id='nta')
    if nta_section:
        # 発表分内のすべてのテーブルを取得
        tables = nta_section.find_all_next('table', class_='index_news')
        for table in tables:
            for tr in table.find_all('tr'):
                th = tr.find('th')
                td = tr.find('td')
                if not th or not td:
                    continue

                # 日付とタイトル、リンクを抽出
                date = th.get_text(strip=True)
                a_tag = td.find('a')

                year_month = tr.get('id')[3:8]

                if year_month < '24001':  # 2024年1月以前の記事はスキップ
                    continue

                if not a_tag:
                    continue
                link = a_tag.get('href')
                title = a_tag.get_text(strip=True)

                # 絶対URLに変換
                if link.startswith("/information"):
                    link = "https://www.nta.go.jp" + link
                elif link.startswith("http"):
                    pass
                else:
                    link = "https://www.nta.go.jp/information/release/" + link

                # 既存のデータと照合
                if any(title == item['title'] for item in existing_data):
                    continue  # 既に存在するニュースはスキップ

                print(f"国税庁: 記事取得開始 - {title}")
                try:
                    if is_pdf_link(link):
                        content = extract_text_from_pdf(link)
                    else:
                        response = requests.get(link)
                        response.encoding = 'utf-8'
                        content = response.text

                    if not content:
                        print(f"国税庁: コンテンツ取得失敗 - {link}")
                        continue

                    summary = ""
                    if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                        summary = summarize_text(title, content)

                    news_item = {
                        'pubDate': date,
                        'execution_timestamp': execution_timestamp,
                        'organization': "国税庁",
                        'title': title,
                        'link': link,
                        'summary': summary
                    }
                    new_news.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1  # カウンターを増加
                except Exception as e:
                    print(f"国税庁: 要約中にエラー発生 - {e}")

    else:
        print("国税庁: 指定されたセクションが見つかりません。")

    save_json(existing_data, json_file)
    return new_news