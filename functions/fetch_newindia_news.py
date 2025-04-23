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


def fetch_newindia_news(max_count, execution_timestamp, executable_path):
    """ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッドの最新情報を収集・要約します。"""
    url = "https://www.newindia.co.jp/topics/"  # 最新情報ページのURLを指定
    json_file = f"./data/newindia.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ニューインディア: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 'div'にid='nProgram'を探し、その中の'dt'と'dd'を取得
    nprogram_div = soup.find('div', id='nProgram')
    if not nprogram_div:
        print("ニューインディア: 最新情報セクションが見つかりませんでした。")
        return []

    dl = nprogram_div.find('dl')
    if not dl:
        print("ニューインディア: 定義リスト（dl）が見つかりませんでした。")
        return []

    dts = dl.find_all('dt')
    dds = dl.find_all('dd')

    if len(dts) != len(dds):
        print("ニューインディア: dtとddの数が一致しません。")
        return []

    for dt, dd in zip(dts, dds):
        pub_date = dt.get_text(strip=True)
        a_tag = dd.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        # 絶対URLに変換
        if link.startswith('/'):
            link = "https://www.newindia.co.jp" + link
        elif not link.startswith('http'):
            link = "https://www.newindia.co.jp/" + link

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"ニューインディア: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"ニューインディア: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                soup_content = BeautifulSoup(content, 'html.parser')
                # ニュース記事の本文を抽出（具体的なHTML構造に応じて調整が必要）
                # ここでは仮に<div class="article-content">を使用
                article_div = soup_content.find('div', class_='article-content')
                if article_div:
                    text_content = article_div.get_text(separator='\n', strip=True)
                else:
                    # 見つからない場合は全文を使用
                    text_content = soup_content.get_text(separator='\n', strip=True)

                summary = summarize_text(title, text_content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッド",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"ニューインディア: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items