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


def fetch_sonpohogo_news(max_count, execution_timestamp, executable_path):
    """損害保険契約者保護機構の最新情報を収集・要約します。"""
    url = "http://www.sonpohogo.or.jp/"  # 最新情報ページのURLを設定
    json_file = "./data/sonpohogo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページの読み込みを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"損保機構: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新規ニュースのカウンターを追加

    # "ºÇ¿·¾ðÊó" セクションを探す（最新情報）
    whatnew_div = soup.find('div', class_='whatnew')
    if not whatnew_div:
        print("損保機構: 'whatnew' セクションが見つかりませんでした。")
        return []

    top_cont_table = whatnew_div.find('table', class_='top_cont')
    if not top_cont_table:
        print("損保機構: 'top_cont' テーブルが見つかりませんでした。")
        return []

    # 各ニュース項目を処理
    for tr in top_cont_table.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) != 2:
            continue  # 予期しない構造の場合はスキップ

        # 日付を取得
        pub_date = tds[0].get_text(strip=True)

        # タイトルとリンクを取得
        news_td = tds[1]
        title_tag = news_td.find('a')
        if title_tag:
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href')
            if not link.startswith('http'):
                link = "http://www.sonpohogo.or.jp" + link  # 相対リンクの場合の対応
        else:
            title = news_td.get_text(strip=True)
            link = ""

        # 既存のデータに存在するかチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"損保機構: 記事取得開始 - {title}")
        try:
            content = ""
            summary = ""
            if link:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'EUC-JP'  # ソースがEUC-JPエンコーディングのため
                    content = response.text

                if not content:
                    print(f"損保機構: コンテンツ取得失敗 - {link}")
                    continue

                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)
                    new_count += 1  # カウンターを増加

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "損害保険契約者保護機構",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)

        except Exception as e:
            print(f"損保機構: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items