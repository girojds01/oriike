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


def fetch_rescue_news(max_count, execution_timestamp, executable_path):
    """レスキュー損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.rescue-sonpo.jp/news.php"
    json_file = f"./data/rescue.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"レスキュー損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='news-list newsListArea nobordertop')
    if not news_list:
        print("レスキュー損害保険: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li', class_='news-list__item newsListLi'):
        title_tag = li.find('p', class_='article__hdg')
        date_tag = li.find('p', class_='date').find('time')

        if not title_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        pub_date = date_tag.get_text(strip=True)
        link_tag = li.find('a', class_='newsListLiLink')
        link = link_tag.get('href') if link_tag else ''

        if pub_date < '2024-01-01':
            continue

        # 相対リンクを絶対URLに変換
        if link.startswith('./'):
            link = "https://www.rescue-sonpo.jp" + link[1:]
        elif link.startswith('/'):
            link = "https://www.rescue-sonpo.jp" + link
        elif not link.startswith('http'):
            link = "https://www.rescue-sonpo.jp/" + link

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"レスキュー損害保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"レスキュー損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                # コンテンツがHTMLの場合、必要なテキスト部分を抽出する処理を追加することを推奨
                # 例: BeautifulSoupを使用して特定のタグからテキストを抽出
                if not is_pdf_link(link):
                    content_soup = BeautifulSoup(content, 'html.parser')
                    # ニュース詳細ページの構造に応じて適切なタグを選択
                    # ここでは本文が<div class="article-content">内にあると仮定
                    article_content = content_soup.find('div', class_='article-content')
                    content_text = article_content.get_text(separator='\n', strip=True) if article_content else content
                else:
                    content_text = content

                summary = summarize_text(title, content_text)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "レスキュー損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"レスキュー損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items