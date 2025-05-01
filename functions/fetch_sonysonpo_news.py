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


def fetch_sonysonpo_news(max_count, execution_timestamp, executable_path):
    """ソニー損害保険株式会社（お知らせ）の最新情報を収集・要約します。"""
    url = "https://from.sonysonpo.co.jp/topics/information/N0086000.html"
    json_file = "./data/sonysonpo.json"
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
        print(f"ソニー損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 重要なお知らせセクション
    important_section = soup.find('div', class_='information-list2')
    if important_section:
        for li in important_section.find_all('li', class_='has-category'):
            a_tag = li.find('a', class_='arrow_link')
            if not a_tag:
                continue
            link = a_tag.get('href')
            if link.startswith("/"):
                link = "https://from.sonysonpo.co.jp" + link
            title = a_tag.get_text(strip=True)

            # URLから日付を抽出 (例: /topics/information/19102020_03_287623.html -> 19-10-2020)
            try:
                date_code = link.split('/')[-1].split('_')[0]
                pub_date = datetime.datetime.strptime(date_code, "%d%m%Y").strftime("%Y-%m-%d")
            except Exception:
                pub_date = datetime.datetime.now().strftime("%Y-%m-%d")

            # 重複チェック
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"ソニー損保: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'utf-8'
                    content_soup = BeautifulSoup(response.text, 'html.parser')
                    # ニュース内容を抽出（適宜調整が必要）
                    content = content_soup.get_text(separator="\n", strip=True)

                if not content:
                    print(f"ソニー損保: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "ソニー損害保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"ソニー損保: 要約中にエラー発生 - {e}")

    # その他のセクション（例: 自然災害に備えるなど）
    archive_box = soup.find('div', class_='archiveBox')
    if archive_box:
        # 最新の自社ニュースセクション
        news_section = archive_box.find('h2', class_='heading2-n0086000')
        if news_section:
            for li in news_section.find_next_siblings('ul')[0].find_all('li', class_='has-category'):
                a_tag = li.find('a', class_='arrow_link')
                if not a_tag:
                    continue
                link = a_tag.get('href')
                if link.startswith("/"):
                    link = "https://from.sonysonpo.co.jp" + link
                title = a_tag.get_text(strip=True)

                # URLから日付を抽出
                try:
                    date_code = link.split('/')[-1].split('_')[0]
                    pub_date = datetime.datetime.strptime(date_code, "%d%m%Y").strftime("%Y-%m-%d")
                except Exception:
                    pub_date = datetime.datetime.now().strftime("%Y-%m-%d")

                # 重複チェック
                if any(title == item['title'] for item in existing_data):
                    continue  # 既に存在するニュースはスキップ

                print(f"ソニー損保: 記事取得開始 - {title}")
                try:
                    if is_pdf_link(link):
                        content = extract_text_from_pdf(link)
                    else:
                        response = requests.get(link)
                        response.encoding = 'utf-8'
                        content_soup = BeautifulSoup(response.text, 'html.parser')
                        # ニュース内容を抽出（適宜調整が必要）
                        content = content_soup.get_text(separator="\n", strip=True)

                    if not content:
                        print(f"ソニー損保: コンテンツ取得失敗 - {link}")
                        continue

                    summary = ""
                    if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                        summary = summarize_text(title, content)

                    news_item = {
                        'pubDate': pub_date,
                        'execution_timestamp': execution_timestamp,
                        'organization': "ソニー損害保険株式会社",
                        'title': title,
                        'link': link,
                        'summary': summary
                    }
                    news_items.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1  # カウンターを増加
                except Exception as e:
                    print(f"ソニー損保: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items