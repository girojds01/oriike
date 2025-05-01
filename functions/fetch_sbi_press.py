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


def fetch_sbi_press(max_count, execution_timestamp, executable_path):
    """SBI損害保険の最新プレスリリースを収集・要約します。"""
    url = "https://www.sbisonpo.co.jp/company/news/"
    json_file = f"./data/sbi_press.json"
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
        print(f"SBI損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新しいニュースの数

    # ニュースリストを取得
    news_list = soup.find('ul', class_='si-listNews si-mgt50')
    if not news_list:
        print("SBI損保_press: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):
        date_div = li.find('div', class_='si-listNews__date')
        main_div = li.find('div', class_='si-listNews__main')

        if not date_div or not main_div:
            continue  # 必要な情報が欠けている場合はスキップ

        pub_date = date_div.get_text(strip=True)
        title_tag = main_div.find('a')
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = f"https://www.sbisonpo.co.jp{link}"

        # 既存のニュースと重複しているかチェック
        if any(item['title'] == title for item in existing_data):
            continue  # 重複している場合はスキップ

        print(f"SBI損保_press: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'shift_jis'  # ページのエンコーディングに合わせる
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # コンテンツを抽出（適宜変更が必要です）
                content_div = page_soup.find('div', class_='article-content')  # 仮のクラス名
                if content_div:
                    content = content_div.get_text(separator='\n', strip=True)
                else:
                    # コンテンツが見つからない場合は全テキストを取得
                    content = page_soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"SBI損保_press: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "SBI損保_press",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"SBI損保_press: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items