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


def fetch_hs_news(max_count, execution_timestamp, executable_path):
    """エイチ・エス損害保険の最新情報を収集・要約します。"""
    url = "https://www.hs-sonpo.co.jp/news/"
    json_file = "./data/hs.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページがロードされるまで最大10秒待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"HS損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新しいニュースのカウンタ
    base_url = "https://www.hs-sonpo.co.jp"

    # 最新年度の <ul> を取得（例: id="2024"）
    latest_year_ul = soup.find('ul', id=str(datetime.datetime.now().year))
    if not latest_year_ul:
        # もし最新年度が見つからない場合、最も新しい <ul> を取得
        latest_year_ul = soup.find('ul', class_='news--news_list')

    if latest_year_ul:
        for li in latest_year_ul.find_all('li'):

            a_tag = li.find('a')
            if not a_tag:
                continue

            link = a_tag.get('href')
            if not link:
                continue
            if not link.startswith("http"):
                link = base_url + link

            header = a_tag.find('header')
            if not header:
                continue

            time_tag = header.find('time')
            pub_date = time_tag.get_text(strip=True) if time_tag else ""

            span_tag = header.find('span')
            category = span_tag.get_text(strip=True) if span_tag else ""

            p_tag = a_tag.find('p')
            title = p_tag.get_text(strip=True) if p_tag else ""

            # 既存データに存在するか確認
            if any(item['title'] == title for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"HS損保: 記事取得開始 - {title}")

            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.raise_for_status()
                    response.encoding = 'utf-8'
                    detail_soup = BeautifulSoup(response.text, 'html.parser')
                    # 詳細ページから本文を抽出（適宜調整が必要）
                    # ここでは仮に <div class="news-detail"> を本文として抽出
                    content_div = detail_soup.find('div', class_='news-detail')
                    content = content_div.get_text(separator="\n", strip=True) if content_div else p_tag.get_text(strip=True)

                if not content:
                    print(f"HS損保: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "エイチ・エス損害保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1
            except Exception as e:
                print(f"HS損保: 要約中にエラー発生 - {e}")

    else:
        print("HS損保: 最新年度のニュースリストが見つかりませんでした。")

    save_json(existing_data, json_file)
    return news_items