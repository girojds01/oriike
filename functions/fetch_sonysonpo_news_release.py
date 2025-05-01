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


def fetch_sonysonpo_news_release(max_count, execution_timestamp, executable_path):
    """ソニー損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://from.sonysonpo.co.jp/topics/news/2024/"
    json_file = f"./data/sonysonpo_news_release.json"
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
        print(f"ソニー損保_news_release: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースが掲載されているテーブルを特定
    news_table = soup.find('table', class_='contentTbox font-l fullWidthSp')
    if not news_table:
        print("ソニー損保_news_release: ニューステーブルが見つかりませんでした。")
        return []

    for tr in news_table.find_all('tr'):
        th = tr.find('th')
        td = tr.find('td')

        if not th or not td:
            continue  # thまたはtdがない行はスキップ

        pub_date = th.get_text(strip=True)
        a_tag = td.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://from.sonysonpo.co.jp" + link

        # 既存のデータに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"ソニー損保_news_release: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース内容がどのタグにあるかに応じて適宜変更してください
                # ここでは例として<div class="news-content">を想定
                content_div = page_soup.find('div', class_='news-content')
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = page_soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"ソニー損保_news_release: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ソニー損害保険_news_release",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"ソニー損保_news_release: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items