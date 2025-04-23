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


def fetch_sompo_direct_news(max_count, execution_timestamp, executable_path):
    """SOMPOダイレクト損害保険株式会社のニュースリリースから新着情報を収集・要約します。"""
    url = "https://news-ins-saison.dga.jp/topics/?type=news"
    json_file = f"./data/sompo_direct_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"SOMPO_direct_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='p-link-news')
    if not news_list:
        print("SOMPO_direct_news: ニュースリストの取得に失敗しました。")
        return []

    for li in news_list.find_all('li', class_='p-link-news__item'):

        link_tag = li.find('a', class_='p-link-news__link')
        if not link_tag:
            continue

        href = link_tag.get('href')
        if not href:
            continue

        # フルURLに変換
        if href.startswith('/'):
            link = "https://news-ins-saison.dga.jp" + href
        else:
            link = href

        date_tag = li.find('span', class_='p-link-news__date')
        summary_tag = li.find('span', class_='p-link-news__summary')

        pub_date = date_tag.get_text(strip=True) if date_tag else ""
        summary_text = summary_tag.get_text(strip=True) if summary_tag else ""
        title = summary_text.split(' ', 1)[0]  # タイトルの抽出方法は適宜調整してください

        # 既存のデータと重複チェック
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"SOMPO_direct_news: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding
                content = response.text

                # BeautifulSoupで詳細ページを解析し、記事内容を抽出
                detail_soup = BeautifulSoup(content, 'html.parser')
                # 実際のサイトのHTML構造に合わせて以下を調整してください
                content_div = detail_soup.find('div', class_='l-section__content')
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = summary_text  # 取得できない場合はサマリーを使用

            if not content:
                print(f"SOMPO_direct_news: コンテンツ取得失敗 - {link}")
                continue

            # 要約
            if new_count < max_count:
                summary = summarize_text(title, content)
            else:
                summary = ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "SOMPOダイレクト損害保険株式会社_news",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"SOMPO_direct_news: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items