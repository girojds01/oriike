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


def fetch_americanhome_news(max_count, execution_timestamp, executable_path):
    """アメリカンホーム医療・損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www2.americanhome.co.jp/v2/news/"
    json_file = f"./data/americanhome_news.json"
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
        print(f"アメリカンホーム: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを含む要素を特定
    articles_list = soup.find('div', class_='articleslist')
    if not articles_list:
        print("アメリカンホーム: ニュースリストが見つかりません。")
        return []

    for dl in articles_list.find_all('dl'):
        dt = dl.find('dt')
        dd = dl.find('dd')
        if not dt or not dd:
            continue

        pub_date = dt.get_text(strip=True)
        link_tag = dd.find('a')
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        link = link_tag.get('href')
        if not link.startswith('http'):
            link = "https://www2.americanhome.co.jp" + link

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"アメリカンホーム: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"アメリカンホーム: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                # BeautifulSoupで本文を抽出（HTMLの場合）
                page_soup = BeautifulSoup(content, 'html.parser')
                # 本文のクラスやタグは実際のページに合わせて調整してください
                article_body = page_soup.find('div', class_='article-body')
                if article_body:
                    text_content = article_body.get_text(separator="\n", strip=True)
                else:
                    text_content = content  # 必要に応じて他の方法でテキストを抽出

                summary = summarize_text(title, text_content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "アメリカンホーム医療・損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"アメリカンホーム: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items