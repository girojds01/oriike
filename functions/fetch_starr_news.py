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


def fetch_starr_news(max_count, execution_timestamp, executable_path):
    """スター・インデムニティ・アンド・ライアビリティ・カンパニーの最新情報を収集・要約します。"""
    url = "https://www.starrcompanies.jp/News"
    json_file = "./data/starr_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"スター保険会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 「大切なお知らせ」セクションを特定
    header = soup.find('h1', text="大切なお知らせ")
    if not header:
        print("スター保険会社: 「大切なお知らせ」セクションが見つかりませんでした。")
        return []

    # ヘッダーの次の兄弟要素として<p>タグを取得
    for p in header.find_next_siblings('p'):
        a_tag = p.find('a')
        if not a_tag:
            continue
        link = a_tag.get('href')
        if not link:
            continue
        # 絶対URLに変換
        if not link.startswith("http"):
            link = "https://www.starrcompanies.jp" + link
        title = a_tag.get_text(strip=True)
        pub_date = datetime.datetime.now().strftime("%Y-%m-%d")  # 公開日が明示されていないため、現在の日付を使用

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"スター保険会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 主要なコンテンツを抽出（例として本文を選択）
                # 適宜、正しいセレクタに調整してください
                content_div = page_soup.find('div', class_='text-content__content')
                content = content_div.get_text(separator='\n', strip=True) if content_div else response.text

            if not content:
                print(f"スター保険会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "スター・インデムニティ・アンド・ライアビリティ・カンパニー",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"スター保険会社: 要約中にエラー発生 - {e}")

        if new_count >= max_count:
            break  # max_countに達したらループを終了

    save_json(existing_data, json_file)
    return news_items