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


def fetch_mlit_jinji(max_count, execution_timestamp, executable_path):
    """国土交通省（人事異動）の最新情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/about/R6jinji.html"  # 最新年度のURL
    json_file = f"./data/mlit_jinji.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"国土交通省: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 解析対象のセクションを特定
    contents_div = soup.find('div', id='contents')
    if not contents_div:
        print("国土交通省: 'contents' div が見つかりませんでした。")
        return []

    # 人事異動セクション内のリンクを取得
    for section in contents_div.find_all('div', class_='section'):
        # タイトル "人事異動　令和6年度" を探す
        title = section.find('h2', class_='title')
        if title and "人事異動" in title.get_text():
            # このセクション内のすべてのaタグを取得
            links = section.find_all('a', href=True)
            for link_tag in links:

                href = link_tag['href'].strip()
                if not href:
                    continue

                # 完全なURLを構築
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"https://www.mlit.go.jp{href}"  # 相対パスの場合

                # タイトルはリンクのテキスト
                entry_title = link_tag.get_text(strip=True)

                # 発行日を解析（リンクテキストから抽出）
                # 例: "令和６年１０月　１日付　（国土交通省第５０号）"
                pub_date_text = entry_title.split('付')[0].strip() + '付'

                if any(entry_title == item['title'] for item in existing_data):
                    continue  # 既に存在するニュースはスキップ

                print(f"国土交通省: 記事取得開始 - {entry_title}")

                try:
                    if is_pdf_link(full_url):
                        content = extract_text_from_pdf(full_url)
                    else:
                        response = requests.get(full_url)
                        response.encoding = 'UTF-8'
                        content = response.text

                    if not content:
                        print(f"国土交通省: コンテンツ取得失敗 - {full_url}")
                        continue

                    summary = ""
                    if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                        summary = summarize_text(entry_title, content)

                    news_item = {
                        'pubDate': pub_date_text,
                        'execution_timestamp': execution_timestamp,
                        'organization': "国土交通省",
                        'title': entry_title,
                        'link': full_url,
                        'summary': summary
                    }
                    news_items.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1  # カウンターを増加
                except Exception as e:
                    print(f"国土交通省: 要約中にエラー発生 - {e}")

            break  # 対象セクションを見つけたらループを終了

    save_json(existing_data, json_file)
    return news_items