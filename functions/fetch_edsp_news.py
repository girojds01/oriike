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


def fetch_edsp_news(max_count, execution_timestamp, executable_path):
    """イーデザイン損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.e-design.net/company/news/2024/"
    json_file = f"./data/edsp.json"
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
        print(f"イーデザイン損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_block = soup.find('div', class_='c-newsBlock__content')
    if not news_block:
        print("イーデザイン損害保険株式会社: ニュースブロックが見つかりません。")
        return []

    for li in news_block.find_all('li'):

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.e-design.net" + link
        title = title_tag.get_text(strip=True)
        pub_date_tag = li.find('p', class_='m-date')
        if pub_date_tag:
            pub_date_text = pub_date_tag.get_text(strip=True)
            pub_date = pub_date_text.split(' ')[0]  # 日付部分のみ取得
        else:
            pub_date = ""

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"イーデザイン損害保険株式会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース記事の内容を取得
                # 適切なセレクタを使用して本文を抽出してください
                # 以下は仮のセレクタです。実際のHTML構造に合わせて調整してください。
                content_div = page_soup.find('div', class_='l-inner')
                if content_div:
                    paragraphs = content_div.find_all(['p', 'li'])
                    content = "\n".join([para.get_text(strip=True) for para in paragraphs])
                else:
                    content = page_soup.get_text(strip=True)

            if not content:
                print(f"イーデザイン損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "イーデザイン損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"イーデザイン損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items