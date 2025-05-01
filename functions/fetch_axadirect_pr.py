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


def fetch_axadirect_pr(max_count, execution_timestamp, executable_path):
    """アクサダイレクトのプレスリリースを収集・要約します。"""
    url = "https://www.axa-direct.co.jp/company/official_info/pr/"
    json_file = f"./data/axa_direct_pr.json"
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
        print(f"アクサダイレクト_プレスリリース: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新のリリースリストを取得
    release_list = soup.find('div', class_='releaseList-wrapper')
    if not release_list:
        print("アクサダイレクト_プレスリリース: リリースリストが見つかりません。")
        return []

    for li in release_list.find_all('li', class_='releaseList-item'):
        a_tag = li.find('a', class_='releaseList-item-link')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if link.startswith('/'):
            link = "https://www.axa-direct.co.jp" + link
        elif link.startswith('http'):
            pass  # 完全なURL
        else:
            continue  # 不明な形式のリンクはスキップ

        title = a_tag.find('p', class_='releaseList-item-link-title').get_text(strip=True)
        date_tag = a_tag.find('p', class_='releaseList-item-link-date')
        pub_date = date_tag.get_text(strip=True) if date_tag else "不明"

        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"アクサダイレクト_プレスリリース: 記事取得開始 - {title}")
        try:
            # コンテンツの取得
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"アクサダイレクト_プレスリリース: コンテンツ取得失敗 - {link}")
                continue

            # 要約の生成
            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "アクサダイレクト_プレスリリース",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"アクサダイレクト_プレスリリース: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items