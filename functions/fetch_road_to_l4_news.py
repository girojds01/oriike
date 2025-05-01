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


def fetch_road_to_l4_news(max_count, execution_timestamp, executable_path):
    """Road-to-the-L4の新着情報を収集・要約します。"""
    url = "https://www.road-to-the-l4.go.jp/news/"
    json_file = "./data/road_to_l4.json"
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
        print(f"Road-to-the-L4: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='newsList02')
    if not news_list:
        print("Road-to-the-L4: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        # 日付を抽出
        date_p = li.find('p', class_='date01')
        if date_p and date_p.has_attr('datetime'):
            pub_date = date_p['datetime']
            pub_date_text = date_p.get_text(strip=True)
        else:
            pub_date = ""
            pub_date_text = ""

        # カテゴリを抽出
        cat_p = li.find('p', class_='cat01')
        category = cat_p.get_text(strip=True) if cat_p else ""

        # コンテンツを抽出
        text_p = li.find('p', class_='text01')
        if not text_p:
            continue  # テキストがない場合はスキップ

        # タイトルとリンクを抽出
        link_a = text_p.find('a')
        if link_a:
            title = link_a.get_text(strip=True)
            link = link_a.get('href')
            if link.startswith('/'):
                link = "https://www.road-to-the-l4.go.jp" + link
        else:
            # リンクがない場合はテキストの一部をタイトルとして使用
            title = text_p.get_text(strip=True)[:50]  # 最初の50文字をタイトルに
            link = url  # メインニュースページへのリンク

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"Road-to-the-L4: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content_text = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content_text = response.text

            if not content_text:
                print(f"Road-to-the-L4: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content_text)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "RoAD to the L4",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"Road-to-the-L4: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news