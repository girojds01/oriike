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


def fetch_statistics_bureau_news(max_count, execution_timestamp, executable_path):
    """総務省統計局の新着情報を収集・要約します。"""
    url = "https://www.stat.go.jp/whatsnew/index.html"
    json_file = "./data/statistics_bureau.json"
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
        print(f"統計局: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得したニュースのカウンター
    current_year = datetime.datetime.now().year

    news_div = soup.find('div', id='news')
    if not news_div:
        print("統計局: 新着情報セクションが見つかりませんでした。")
        return []

    # 現在の年月を基準に年を調整（例: 12月以降に1月の日付が出現した場合）
    def get_full_pub_date(month_day_str):
        try:
            month, day = map(int, month_day_str.replace('日', '').split('月'))
            pub_date = datetime.datetime(current_year, month, day)
            # 過去の日付が未来に見える場合、前年とする
            if pub_date > datetime.datetime.now() + datetime.timedelta(days=1):
                pub_date = datetime.datetime(current_year - 1, month, day)
            return pub_date.strftime("%Y年%m月%d日")
        except ValueError:
            return f"{current_year}年{month_day_str}"

    # イテレーション用のリストを作成
    children = list(news_div.children)
    i = 0
    while i < len(children):
        child = children[i]
        if isinstance(child, str):
            stripped = child.strip()
            if stripped.endswith("日"):
                pub_date = get_full_pub_date(stripped)
                # 次の要素が<ul>であることを確認
                if i + 1 < len(children):
                    next_child = children[i + 1]
                    if next_child.name == 'ul':
                        for li in next_child.find_all('li'):

                            a_tag = li.find('a')
                            if not a_tag:
                                continue

                            link = a_tag.get('href')
                            if not link.startswith('http'):
                                link = "https://www.stat.go.jp" + link
                            title = a_tag.get_text(strip=True).replace("NEW", "").strip()

                            # 既存データに存在するか確認
                            if any(item['title'] == title for item in existing_data):
                                continue  # 既に存在するニュースはスキップ

                            print(f"統計局: 記事取得開始 - {title}")
                            try:
                                if is_pdf_link(link):
                                    content = extract_text_from_pdf(link)
                                else:
                                    response = requests.get(link)
                                    response.encoding = response.apparent_encoding
                                    content = response.text

                                if not content:
                                    print(f"統計局: コンテンツ取得失敗 - {link}")
                                    continue

                                summary = ""
                                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                                    summary = summarize_text(title, content)

                                news_item = {
                                    'pubDate': pub_date,
                                    'execution_timestamp': execution_timestamp,
                                    'organization': "総務省統計局",
                                    'title': title,
                                    'link': link,
                                    'summary': summary
                                }
                                news_items.append(news_item)
                                existing_data.append(news_item)
                                new_count += 1
                            except Exception as e:
                                print(f"統計局: 要約中にエラー発生 - {e}")
        i += 1

    save_json(existing_data, json_file)
    return news_items