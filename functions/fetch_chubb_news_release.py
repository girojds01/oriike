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


def fetch_chubb_news_release(max_count, execution_timestamp, executable_path):
    """Chubb損害保険株式会社のニュースリリースを収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-release.html"
    json_file = "./data/chubb_news_release.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"Chubb_news_release: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    news_list = soup.find('ul', class_='news-block')
    if not news_list:
        print("Chubb_news_release: ニュースリリースのリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li', class_='news-list'):

        date_span = li.find('span', class_='news-time')
        if not date_span:
            continue
        pub_date = date_span.get_text(strip=True)

        content_div = li.find('div', class_='news-content')
        if not content_div:
            continue
        a_tag = content_div.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.chubb.com" + link

        # 既に存在するニュースはスキップ
        if any(item['title'] == title for item in existing_data):
            continue

        print(f"Chubb_news_release: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'UTF-8'
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュースリリースの本文を抽出（適宜タグを調整）
                article = content_soup.find('div', class_='press-release-content')
                if article:
                    content = article.get_text(separator='\n', strip=True)
                else:
                    # 本文が見つからない場合は全テキストを使用
                    content = content_soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"Chubb_news_release: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "Chubb損害保険株式会社_news_release",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"Chubb_news_release: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items