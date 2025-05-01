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


def fetch_axa_news(max_count, execution_timestamp, executable_path):
    """アクサ損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.axa-direct.co.jp/company/official_info/announce/"
    json_file = "./data/axa_news.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 15)  # 最大15秒間待機

        # 公開されたリリースリストがロードされるのを待つ
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "releaseList-wrapper")))

        # ページのソースを取得
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"AXA: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新のリリースリストを取得
    release_wrapper = soup.find('div', class_='releaseList-wrapper', attrs={'data-info-category': 'announce'})
    if not release_wrapper:
        print("AXA_お知らせ: リリースラップパーが見つかりません")
        return []

    # リリースリスト内の各リリースを処理
    for release in release_wrapper.find_all(['div', 'li'], recursive=False):

        # タイトルとリンクの取得
        title_tag = release.find('a')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if link.startswith('/'):
            link = "https://www.axa-direct.co.jp" + link

        # 公開日の取得（例として 'span' タグを使用）
        pub_date_tag = release.find('span', class_='date')  # 適切なクラス名に変更
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else ''

        # 既存データとの重複チェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"AXA: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"AXA_お知らせ: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "アクサ損害保険株式会社_お知らせ",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"AXA_お知らせ: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items