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


def fetch_nisshin_news(max_count, execution_timestamp, executable_path):
    """日新火災海上保険株式会社のニュースリリースから最新情報を収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/news_release/"  # ニュースリリースページのURL
    json_file = f"./data/nisshin_fire_news_release.json"  # 保存するJSONファイルのパス
    existing_data = load_existing_data(json_file)  # 既存のデータをロード

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"日新火災海上保険_news_release: ページ取得中にエラー発生 - {e}")
        return []

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # ニュースはテーブル内の<tr>要素に格納されていると仮定
    table = soup.find('table', class_='newsinfo__idx__table')  # クラス名は実際のHTMLに合わせて調整
    if not table:
        print("日新火災海上保険_news_release: ニューステーブルが見つかりませんでした。")
        return []

    for tr in table.find_all('tr'):
        try:
            ths = tr.find_all('th')
            tds = tr.find_all('td')
            if len(ths) < 2 or len(tds) < 1:
                continue  # 必要なデータが揃っていない場合はスキップ

            pub_date = ths[0].get_text(strip=True)  # 例: '2024年10月8日'
            genre = ths[1].get_text(strip=True)     # 例: 'その他'

            a_tag = tds[0].find('a')
            if not a_tag:
                continue  # リンクが存在しない場合はスキップ

            link = a_tag.get('href')
            if not link.startswith('http'):
                link = "https://www.nisshinfire.co.jp" + link  # 相対URLの場合はベースURLを追加

            title = a_tag.get_text(strip=True)
            size_text = tds[0].get_text(strip=True).split('(')[-1].rstrip(')') if '(' in tds[0].get_text() else ""

            # 既に存在するニュースか確認
            if any(title == item['title'] for item in existing_data):
                continue  # 既存のニュースはスキップ

            print(f"日新火災海上保険_news_release: 記事取得開始 - {title}")

            # コンテンツの取得
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                try:
                    page_response = requests.get(link)
                    page_response.raise_for_status()
                    page_soup = BeautifulSoup(page_response.content, 'html.parser')
                    # ニュース内容の抽出方法は実際のページ構造に合わせて調整
                    # ここでは仮に<p>タグのテキストを結合しています
                    paragraphs = page_soup.find_all('p')
                    content = '\n'.join(p.get_text() for p in paragraphs)
                except Exception as e:
                    print(f"日新火災海上保険_news_release: コンテンツ取得中にエラー発生 - {e}")
                    continue

            if not content:
                print(f"日新火災海上保険_news_release: コンテンツが空です - {link}")
                continue

            # ニュースの要約
            if new_count < max_count:
                summary = summarize_text(title, content)
            else:
                summary = ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'genre': genre,
                'organization': "日新火災海上保険株式会社_news_release",
                'title': title,
                'link': link,
                'size': size_text,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"日新火災海上保険_news_release: ニュース処理中にエラー発生 - {e}")
            continue

    save_json(existing_data, json_file)
    return news_items