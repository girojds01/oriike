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


def fetch_jai_news(max_count, execution_timestamp, executable_path):
    """ジェイアイ傷害火災保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.jihoken.co.jp/whats/wh_index.html"
    json_file = "./data/jai_insurance.json"
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
        print(f"JAI傷害火災保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新情報のコンテナを特定
    whats_box = soup.find('div', id='whatsBox2')
    if not whats_box:
        print("JAI傷害火災保険: 最新情報コンテナが見つかりませんでした。")
        return []

    # ニュース記事を抽出（仮定: 各ニュースは<li>タグ内にある）
    for li in whats_box.find_all('li'):
        if new_count >= max_count:
            break

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        # 絶対URLに変換
        if not link.startswith('http'):
            link = "https://www.jihoken.co.jp" + link
        title = title_tag.get_text(strip=True)
        pub_date = li.get_text().split('　')[0].strip()  # 仮に日付がタイトルの前にある場合

        # 既存データに存在するかチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"JAI傷害火災保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"JAI傷害火災保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ジェイアイ傷害火災保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"JAI傷害火災保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items