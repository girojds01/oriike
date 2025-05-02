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


def fetch_yamap_sonpo_news(max_count, execution_timestamp, executable_path):
    """ヤマップ損保の最新情報を収集・要約します。"""
    url = "https://yamap-naturance.co.jp/news"
    base_url = "https://yamap-naturance.co.jp"
    json_file = "./data/yamap_sonpo_news.json"

    # 既存データのロード（外部 or グローバルで定義されている想定）
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ヤマップ損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # (1) ニュース全体を囲む <div data-s-5deaa163-... class="sd appear">
    #     を探す。attrs={"data-s-5deaa163-5502-4e12-81e7-c06a1f5591af": True} で検索。
    container_div = soup.find('div', attrs={"data-s-5deaa163-5502-4e12-81e7-c06a1f5591af": True}, class_='sd appear')
    if not container_div:
        print("ヤマップ損保: ニュースのメインコンテナ(div)が見つかりませんでした。")
        return []

    # (2) 各ニュース項目: <a href="/tkBjcRkC/..." class="link sd appear"> ... </a> を全て取得
    news_links = container_div.find_all('a', class_='link sd appear')
    if not news_links:
        print("ヤマップ損保: ニュース項目<a>が見つかりませんでした。")
        return []

    for a_tag in news_links:
        # (2-1) 相対パスを絶対URLに
        relative_link = a_tag.get('href', '').strip()
        if relative_link.startswith('http'):
            full_link = relative_link
        else:
            full_link = base_url + relative_link

        # (2-2) <p class="text sd appear"> を全部取得
        #  3つある想定:
        #   p_list[0] = ラベル (例: お知らせ / 商品・サービス)
        #   p_list[1] = 日付 (例: 2025.3.27)
        #   p_list[2] = ニュースタイトル本文
        p_list = a_tag.find_all('p', class_='text sd appear')
        if len(p_list) < 3:
            # 3つなければ想定外なのでスキップ or 例外処理
            continue

        label = p_list[0].get_text(strip=True)
        pub_date = p_list[1].get_text(strip=True)
        title_text = p_list[2].get_text(strip=True)

        if not title_text:
            continue

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"ヤマップ損保: 記事取得 - 日付: {pub_date}, タイトル: {title_text}")

        try:
            # (3) コンテンツ取得 & 要約
            #     必要に応じて PDF判定などを追加
            resp = requests.get(full_link, verify=False)
            resp.encoding = 'utf-8'
            content = resp.text

            if not content:
                print(f"ヤマップ損保: コンテンツ取得失敗 - {full_link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            # (4) news_itemにまとめる
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル想定
                'organization': "ヤマップ損保",
                'label': label,
                'title': title_text,
                'link': full_link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"ヤマップ損保: 要約中にエラー発生 - {e}")

    # 保存
    save_json(existing_data, json_file)
    return news_items