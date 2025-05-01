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


def fetch_jftc_news(max_count, execution_timestamp, executable_path):
    """公正取引委員会の最新情報を収集・要約します。"""
    url = "https://www.jftc.go.jp/index.html"
    json_file = f"./data/jftc.json"
    existing_data = load_existing_data(json_file)

    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")
    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)
    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページの読み込みを待つ
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"公正取引委員会: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースセクションを特定
    news_wrap = soup.find('div', class_='newsWrap')
    if not news_wrap:
        print("公正取引委員会: ニュースセクションが見つかりませんでした。")
        return []

    tab_box = news_wrap.find('div', class_='tab_box')
    if not tab_box:
        print("公正取引委員会: タブボックスが見つかりませんでした。")
        return []

    panel_area = tab_box.find('div', class_='panel_area')
    if not panel_area:
        print("公正取引委員会: パネルエリアが見つかりませんでした。")
        return []

    # 注目情報タブを選択
    active_tab = panel_area.find('div', class_='tab_panel active')
    if not active_tab:
        print("公正取引委員会: アクティブなタブパネルが見つかりませんでした。")
        return []

    info_list = active_tab.find('ul', class_='infoList')
    if not info_list:
        print("公正取引委員会: 情報リストが見つかりませんでした。")
        return []

    for li in info_list.find_all('li'):

        # 各ニュースアイテムの情報を抽出
        date_div = li.find('div', class_='b01')
        link_div = li.find('div', class_='b02')
        if not date_div or not link_div:
            continue  # 必要な情報が欠けている場合はスキップ

        # 日付の抽出
        pub_date = date_div.contents[1][2:13] # 2023年10月01日の形式

        if pub_date < '2024年10月01日':  # 2024年10月1日以前の記事はスキップ
            continue

        # カテゴリの抽出
        category_span = date_div.find('span', class_=lambda x: x and 'cate' in x)
        category = category_span.get_text(strip=True) if category_span else ""

        # プレスタイプの抽出
        press_span = date_div.find('span', class_='press')
        press_type = press_span.get_text(strip=True) if press_span else ""

        # タイトルとリンクの抽出
        a_tag = link_div.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if link.startswith("/"):
            link = "https://www.jftc.go.jp" + link

        # 既存データと照合して新規か確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"公正取引委員会: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # requestsでは記事が取得できないため、Seleniumを使用
                # ただし options.set_capability を加えると安定性UP
                options.set_capability("browserName", "MicrosoftEdge")
                # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
                service = EdgeService(executable_path=executable_path)
                # ドライバ起動
                driver = webdriver.Edge(service=service, options=options)

                try:
                    driver.get(link)
                    driver.implicitly_wait(10)  # ページの読み込みを待つ
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                except Exception as e:
                    print(f"公正取引委員会: ページ取得中にエラー発生 -{link}, {e}")
                    driver.quit()
                    return []
                driver.quit()

                content = soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"公正取引委員会: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "公正取引委員会",
                'title': title,
                'link': link,
                'summary': summary,
                'category': category,
                'press_type': press_type
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"公正取引委員会: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items