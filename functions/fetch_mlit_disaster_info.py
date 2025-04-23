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


def fetch_mlit_disaster_info(max_count, execution_timestamp, executable_path):
    """国土交通省の災害・防災情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/saigai/index.html"
    json_file = f"./data/mlit_disaster.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.encoding = 'UTF-8'
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"国土交通省: ページ取得中にエラー発生 {e}")
        return []

    news_items = []
    new_count = 0  # カウンターを追加

    # 災害情報のリストを取得
    disaster_section = soup.find('div', class_='SaigaiPressRelease01')
    if not disaster_section:
        print("災害情報のセクションが見つかりません。")
        return []

    for dd in disaster_section.find_all('dd'):
        text_p = dd.find('p', class_='text')
        if not text_p:
            continue
        a_tag = text_p.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.mlit.go.jp" + link

        # 日付の抽出
        # 例: "令和6年9月20日からの大雨による被害状況等について（第11報　2024年9月26日 08時00分現在）"
        try:
            pub_date_str = title.split('（')[1].split('報')[1].split('）')[0].strip()
            pub_date = datetime.datetime.strptime(pub_date_str, '%Y年%m月%d日 %H時%M分現在').strftime('%Y-%m-%d %H:%M:%S')
        except:
            pub_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 既存のニュースに含まれているか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国土交通省: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"国土交通省: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "国土交通省",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国土交通省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items