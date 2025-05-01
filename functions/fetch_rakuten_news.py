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


def fetch_rakuten_news(max_count, execution_timestamp, executable_path):
    """楽天損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.rakuten-sonpo.co.jp/news/tabid/85/Default.aspx"
    json_file = f"./data/rakuten_sonpo.json"
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
        print(f"楽天損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースのリストを取得
    announcements = soup.find_all('div', class_='ViewAnnouncements')  # 変更点
    for announcement in announcements:
        news_list = announcement.find_all('dl')
        for dl in news_list:
            dt = dl.find('dt')
            dd1 = dl.find('dd', class_='dd1')  # カテゴリ等の情報
            dd2 = dl.find('dd', class_='dd2')

            if not (dt and dd2):
                continue

            pub_date = dt.get_text(strip=True)
            link_tag = dd2.find('a')
            if not link_tag:
                continue

            link = link_tag.get('href')
            if not link.startswith("http"):
                link = "https://www.rakuten-sonpo.co.jp" + link

            title = link_tag.get_text(separator=' ', strip=True)
            # 結合されたテキストから概要部分を抽出
            summary_tag = link_tag.find('span')
            summary = summary_tag.get_text(strip=True) if summary_tag else ""

            # 既存のデータに存在するか確認
            if any(item['title'] == title for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"楽天損保: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.raise_for_status()
                    response.encoding = 'UTF-8'
                    page_soup = BeautifulSoup(response.text, 'html.parser')

                    # ニュース記事本文の抽出方法を調整
                    # 以下は一般的な例であり、実際のサイトの構造に応じて調整が必要です
                    content_div = page_soup.find('div', class_='newsDetail')  # 仮のクラス名
                    if content_div:
                        content = content_div.get_text(separator='\n', strip=True)
                    else:
                        # 見つからない場合は全体のテキストを取得
                        content = page_soup.get_text(separator='\n', strip=True)

                if not content:
                    print(f"楽天損保: コンテンツ取得失敗 - {link}")
                    continue

                summary_generated = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary_generated = summarize_text(title, content)
                    new_count += 1  # カウンターを増加

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "楽天損害保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary_generated
                }
                news_items.append(news_item)
                existing_data.append(news_item)
            except Exception as e:
                print(f"楽天損保: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items