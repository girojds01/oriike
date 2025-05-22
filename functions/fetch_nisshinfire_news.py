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
    """日新火災のニュースリリースを収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/news_release/"
    json_file = "./data/nisshinfire_news.json"

    # 既存データのロード
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
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # ニュース一覧が掲載されているテーブルを取得
    table = soup.find('table', class_='newsinfo__idx__table')
    if not table:
        print("日新火災: ニュースリリースのテーブルが見つかりませんでした。")
        return []

    # テーブル内の行(<tr>)を順次処理
    for tr in table.find_all('tr'):
        # 日付セル
        date_th = tr.find('th', class_='newsinfo__idx__table__th')
        if not date_th:
            # 日付セルがない行はスキップ
            continue
        pub_date = date_th.get_text(strip=True)

        # ジャンルセル
        label_th = tr.find('th', class_='newsinfo__idx__table__genre')
        label = ""
        if label_th:
            span_genre = label_th.find('span', class_='newsinfo__idx__genre')
            if span_genre:
                label = span_genre.get_text(strip=True)

        # タイトルとリンク（<td class="newsinfo__idx__table__td">配下の<a>）
        td = tr.find('td', class_='newsinfo__idx__table__td')
        if not td:
            continue

        a_tag = td.find('a')
        if not a_tag:
            continue

        relative_link = a_tag.get('href', '').strip()

        # ------------------------------------------
        # urljoinを使わず、自前でパターン判定してリンク補完
        # ------------------------------------------
        if relative_link.startswith('http'):
            # すでに絶対URL（httpまたはhttps）
            link = relative_link
        elif relative_link.startswith('/'):
            # サイトルートからのパス（例: /pdf/...）
            link = "https://www.nisshinfire.co.jp" + relative_link
        else:
            # news_release/以下からの相対パス（例: pdf/news250324.pdf）
            # 必要に応じて "./pdf/...","pdf/..." などをまとめて扱う
            if relative_link.startswith('./'):
                relative_link = relative_link[2:]
            link = "https://www.nisshinfire.co.jp/news_release/" + relative_link

        title_text = a_tag.get_text(strip=True)

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"日新火災: 記事取得開始 - {title_text}")

        # コンテンツ・要約取得
        try:
            if is_pdf_link(link):  
                # PDFファイルの場合のテキスト抽出
                content = extract_text_from_pdf(link)
            else:
                # 通常Webページの場合
                response = requests.get(link, verify=False)  # 必要なら証明書をチェック
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"日新火災: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            # max_count を超えない範囲でのみ要約を実行（例: 3件まで要約など）
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル or 外部で定義
                'organization': "日新火災",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"日新火災: 要約中にエラー発生 - {e}")

    # 保存
    save_json(existing_data, json_file)
    return news_items