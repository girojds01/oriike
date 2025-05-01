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


def fetch_chubb_news(max_count, execution_timestamp, executable_path):
    """Chubb損害保険株式会社のお知らせページから最新情報を収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-info.html"
    json_file = f"./data/chubb_news.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページがロードされるまで待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"Chubb_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースブロックを取得
    news_block = soup.find('ul', class_='news-block')
    if not news_block:
        print("Chubb_news: ニュースブロックが見つかりませんでした。")
        return []

    for li in news_block.find_all('li', class_='news-list news-listing'):

        # 公開日を取得
        news_time_div = li.find('div', class_='news-time')
        if not news_time_div:
            continue
        pub_date = news_time_div.find_all('div')[-1].get_text(strip=True)

        # タイトルとリンクを取得
        news_content_div = li.find('div', class_='news-content')
        if not news_content_div:
            continue

        title_tag = news_content_div.find(['h2', 'div'], class_=['h4-title', 'h4-title bottom'])
        if not title_tag:
            continue
        a_tag = title_tag.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link:
            continue
        if not link.startswith('http'):
            link = "https://www.chubb.com" + link

        # 既存のデータに含まれているか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"Chubb_news: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                page_soup = BeautifulSoup(response.text, 'html.parser')

                # 主要なコンテンツを抽出（具体的なHTML構造に応じて調整が必要）
                # ここでは、記事本文が<div class="article-content">にあると仮定
                content_div = page_soup.find('div', class_='article-content')
                if content_div:
                    paragraphs = content_div.find_all(['p', 'li'])
                    content = "\n".join(p.get_text(strip=True) for p in paragraphs)
                else:
                    # 見つからない場合は簡易的に現在の要約を使用
                    content = news_content_div.find('p')
                    content = content.get_text(strip=True) if content else ""

            if not content:
                print(f"Chubb_news: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "Chubb損害保険株式会社_news",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"Chubb_news: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items