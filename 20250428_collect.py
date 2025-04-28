import datetime
import json
import feedparser
import os
import csv
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from openai import AzureOpenAI
from pypdf import PdfReader
from io import BytesIO
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import certifi
from requests.exceptions import SSLError
from urllib.parse import urljoin

max_count = 0   # 取得するニュースの最大数

# 実行日時を取得
execution_timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H;%M;%S')

# Seleniumのオプションを設定
options = Options()
options.add_argument("--headless")
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--no-sandbox")
options.add_argument("--lang=ja")


# Azure OpenAIクライアントの初期化
client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version="2023-03-15-preview",
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

def summarize_text(title, content):
    """OpenAI APIを使用してテキストを要約します。"""
    print(f"要約中: {title}")
    messages = [
        {
            "role": "system",
            "content": f"あなたはプロの新聞記者です。『{title}』に関する次の記事を120文字程度の日本語で要約してください。内容が保険に関連する場合は、保険種類を明確にしてください。要約結果は記事の件名と同じではなく、件名を補完する内容としてください。背景となっている課題や、期待される効果を記載してください。文体は、だ・である調にしてください。",
        },
        {
            "role": "user",
            "content": content,
        },
    ]

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            messages=messages,
            temperature=0.3,
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"要約中にエラーが発生しました: {e}")
        return ""

def load_existing_data(file_path):
    """既存のJSONデータをロードします。"""
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_json(data, file_path):
    """データをJSONファイルに保存します。"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def is_pdf_link(url):
    """リンクがPDFファイルかどうかを判定します。"""
    return url.lower().endswith('.pdf')

def extract_text_from_pdf(url):
    """PDFリンクからテキストを抽出します。"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        pdf_file = BytesIO(response.content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDFからのテキスト抽出中にエラーが発生しました: {e}")
        return ""

def remove_news_with_exception_keyword(news):
    csv_file_path = './data/keyword/exception_keyword.csv'
    
    # 例外キーワードを組織毎にまとめる
    exception_dict = {}
    with open(csv_file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            org = row['organization']
            keyword = row['exception_keyword']
            if org not in exception_dict:
                exception_dict[org] = []
            exception_dict[org].append(keyword)
    
    # allキーがある場合はグローバル例外リストとして取得
    global_exceptions = exception_dict.get('all', [])
    
    # 新しいリストを作成し、該当しないアイテムを追加する
    filtered_news = []
    for item in news:
        org = item.get('organization', '')
        title = item.get('title', '')

        # グローバル例外または組織固有の例外キーワードと一致するかを確認
        remove_item = any(keyword in title for keyword in global_exceptions)
        if not remove_item and org in exception_dict:
            remove_item = any(keyword in title for keyword in exception_dict[org])

        if remove_item:
            print(f"例外キーワードに一致するニュースを削除します: {org}, {title}")
        else:
            filtered_news.append(item)
    
    return filtered_news

# ▼ 保険会社------------------------------------------------
def fetch_aig_news():
    """AIG損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://www.aig.co.jp/sonpo/company/news"
    json_file = "./data/aig_news.json"
    existing_data = load_existing_data(json_file)
    
    # ディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(json_file), exist_ok=True)
    
    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページロードを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"AIG損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()
    
    news_items = []
    new_count = 0  # 新たに取得したニュースのカウンター

    # ニュースリストを取得
    news_list = soup.find('ul', class_='cmp-newslist')
    if not news_list:
        print("AIG損保: ニュースリストが見つかりません。")
        return []
    
    for li in news_list.find_all('li', class_='cmp-newslist__item'):

        article = li.find('article', class_='cmp-newslist__row')
        if not article:
            continue

        link_tag = article.find('a', class_='cmp-newslist__link')
        if not link_tag:
            continue

        link = link_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.aig.co.jp" + link  # 相対URLの場合はベースURLを追加

        title = article.find('div', class_='cmp-newslist-item__title').get_text(strip=True)
        pub_date = article.find('div', class_='cmp-newslist-item__date').get_text(strip=True)

        # 既存のデータにタイトルが存在する場合はスキップ
        if any(item['title'] == title for item in existing_data):
            continue

        print(f"AIG損保: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 本文の抽出方法はページの構造に依存します。適宜調整してください。
                content_div = page_soup.find('div', class_='cmp-news-content')  # 仮のクラス名
                if content_div:
                    content = content_div.get_text(separator='\n', strip=True)
                else:
                    content = page_soup.get_text(separator='\n', strip=True)
            
            if not content:
                print(f"AIG損保: コンテンツ取得失敗 - {link}")
                continue

            # 要約の生成
            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            # ニュースアイテムを構築
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "AIG損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"AIG損保: 要約中にエラー発生 - {e}")
            continue

    # JSONファイルに保存
    save_json(existing_data, json_file)
    return news_items


def fetch_aioi_news():
    """あいおいニッセイ同和損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://www.aioinissaydowa.co.jp/corporate/about/news/"
    json_file = f"./data/aioi_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"あいおいニッセイ同和損害保険_ニュース: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新年のセクションを取得（例: 2024年）
    latest_year_tab = soup.find('div', class_='m-tab-contents is-active')
    if not latest_year_tab:
        print("最新年のニュースセクションが見つかりませんでした。")
        return []

    # ニュースリストを取得
    news_list = latest_year_tab.find('ul')
    if not news_list:
        print("ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li', class_='m-news'):

        title_tag = li.find('a', class_='iconPdf01')
        if not title_tag:
            continue
        link = title_tag.get('href')
        title = title_tag.get_text(strip=True)
        time_tag = li.find('time', class_='m-news__date')
        pub_date = time_tag.get_text(strip=True) if time_tag else "不明"

        # フルURLを生成
        if link.startswith("/"):
            link = "https://www.aioinissaydowa.co.jp" + link
        if link.startswith("pdf/"):
            link = url + link

        # 既存のデータに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"あいおい社_ニュース: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"あいおい_ニュース: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "あいおいニッセイ同和損保（ニュース）",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"あいおい社_ニュース: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_aioi_notice():
    """あいおいニッセイ同和損保のおしらせを収集・要約します。"""
    url = "https://aioinissaydowa.co.jp/corporate/about/notice/"
    json_file = "./data/aioi_notice.json"

    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"あいおい社お知らせ: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    news_list = soup.find('div', class_='m-news-list')
    if not news_list:
        print("あいおい社お知らせ: ニュースリスト(m-news-list)が見つかりませんでした。")
        return []

    # 各ニュース (li.m-news) を順に処理
    for li in news_list.find_all('li', class_='m-news'):
        # 日付は <time class="m-news__date"> か <time class="m-news_date"> か要確認
        time_tag = li.find('time', class_='m-news__date')
        pub_date = time_tag.get_text(strip=True) if time_tag else ""

        category_tag = li.find('span', class_='m-news_category')
        label = category_tag.get_text(strip=True) if category_tag else ""

        # ニュースのリンクとタイトルは <div class="m-news__body"> 内の <a> から
        a_parent = li.find('div', class_='m-news__body')
        if a_parent:
            a_tag = a_parent.find('a')
        else:
            a_tag = None

        if not a_tag:
            continue

        raw_href = a_tag.get('href', '')

        # JavaScript を使って PDF を呼び出す形式の場合、実際の URL を抽出
        match_pdf = re.search(r"Jump_File\('(.*?)'\)", raw_href)
        if match_pdf:
            link = match_pdf.group(1)
        else:
            link = raw_href

        # タイトルを取得
        title_text = a_tag.get_text(strip=True)

        # 既存データとタイトルで重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"あいおい社お知らせ: 記事取得開始 - {title_text}")

        # コンテンツ取得と要約
        content = None
        try:
            if is_pdf_link(link):
                # PDFの場合
                content = extract_text_from_pdf(link)
            else:
                # HTMLページの場合
                response = requests.get(link, verify=certifi.where())
                response.encoding = 'utf-8'
                content = response.text
        except SSLError as ssl_err:
            print(f"あいおい社お知らせ: セキュリティエラー(SSL証明書エラー) - {link} / {ssl_err}")
            content = None
        except Exception as e:
            print(f"あいおい社お知らせ: コンテンツ取得中にエラー発生 - {e}")
            content = None

        # 要約（最大件数制限などは任意で）
        if not content:
            print("要約文は空のままにします。")
            summary = ""
        else:
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

        # データ作成
        news_item = {
            'pubDate': pub_date,
            'execution_timestamp': execution_timestamp,
            'organization': "あいおいニッセイ同和損保（お知らせ）",
            'title': title_text,
            'link': link,
            'summary': summary
        }
        news_items.append(news_item)
        existing_data.append(news_item)
        new_count += 1

    # JSONに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_americanhome_news():
    """
    アメリカンホーム保険のニュースを収集・要約する
    """
    base_url = "https://www.americanhome.co.jp"
    url      = f"{base_url}/home/news"
    json_file = "./data/americanhome_news.json"

    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"[AmericanHome_news] ページ取得エラー: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items, new_count = [], 0
    date_pat = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")

    # サイトの実カードは div.cmp-teaser で構成されている
    for card in soup.select("div.cmp-teaser"):
        # ① 日付
        date_div = card.select_one("div.cmp-teaser__pretitle")
        pub_date = date_div.get_text(strip=True) if date_div else ""
        if not date_pat.fullmatch(pub_date):
            continue          # トップページ / お知らせ などメニューを除外

        # ② タイトル & リンク
        a_tag = card.select_one("div.cmp-teaser__description a[href]")
        if not a_tag:
            continue
        title_text = a_tag.get_text(strip=True)
        link       = urljoin(base_url, a_tag["href"].strip())  # 相対→絶対

        # ③ 重複チェック
        if any(d["title"] == title_text and d["link"] == link for d in existing_data):
            continue

        print(f"[AmericanHome_news] 取得 - {pub_date}: {title_text}")

        # ④ 本文取得 & 要約
        try:
            resp = requests.get(link, timeout=10, verify=certifi.where())
            resp.encoding = "utf-8"
            content  = resp.text

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                "pubDate": pub_date,
                "execution_timestamp": execution_timestamp,
                "organization": "アメリカンホーム保険（ニュース）",
                "title": title_text,
                "link":  link,
                "summary": summary,
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"[AmericanHome_news] 要約中にエラー: {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_americanhome_info():
    """
    アメリカンホーム保険のお知らせを収集・要約する
    """
    base_url  = "https://www.americanhome.co.jp"
    url       = f"{base_url}/home/information"
    json_file = "./data/americanhome_info.json"

    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"[AmericanHome_info] ページ取得エラー: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items, new_cnt = [], 0
    date_pat = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")

    # 実カードは div.cmp-teaser
    cards = soup.select("div.cmp-teaser")
    if not cards:
        print("[AmericanHome_info] お知らせ項目が見つかりませんでした。")
        return []

    for card in cards:
        # ① 日付
        date_div = card.select_one("div.cmp-teaser__pretitle")
        pub_date = date_div.get_text(strip=True) if date_div else ""
        if not date_pat.fullmatch(pub_date):      # メニュー項目などを除外
            continue

        # ② タイトル & リンク
        a = card.select_one("div.cmp-teaser__description a[href]")
        if not a:
            continue
        title = a.get_text(strip=True)
        link  = urljoin(base_url, a["href"].strip())   # 相対→絶対 URL

        # ③ 重複チェック
        if any(d["title"] == title and d["link"] == link for d in existing_data):
            continue

        print(f"[AmericanHome_info] 取得 - {pub_date}: {title}")

        # ④ 本文取得 & 要約
        try:
            resp = requests.get(link, timeout=10, verify=certifi.where())
            resp.encoding = "utf-8"
            content = resp.text

            summary = ""
            if new_cnt < max_count:
                summary = summarize_text(title, content)

            news_item = {
                "pubDate": pub_date,
                "execution_timestamp": execution_timestamp,
                "organization": "アメリカンホーム保険（お知らせ）",
                "title": title,
                "link":  link,
                "summary": summary,
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_cnt += 1

        except Exception as e:
            print(f"[AmericanHome_info] 要約中にエラー: {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_au_news():
    """au損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.au-sonpo.co.jp/corporate/news/"
    json_file = f"./data/au_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページが完全にロードされるまで待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"au損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新規ニュースのカウンター

    # ニュースリストのul要素を取得
    news_list_ul = soup.find('ul', class_='js-news-list-render')
    if not news_list_ul:
        print("au損害保険: ニュースリストが見つかりません。")
        return []

    # 各ニュース項目をループ
    for li in news_list_ul.find_all('li'):
        title_tag = li.find('a')
        if not title_tag:
            continue

        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.au-sonpo.co.jp" + link
        title = title_tag.get_text(strip=True)

        # 日付を取得（例としてspanタグ内にあると仮定）
        date_tag = li.find('span', class_='date')  # 実際のクラス名に合わせて変更
        if date_tag:
            pub_date = date_tag.get_text(strip=True)
        else:
            # 日付が見つからない場合は空文字を設定
            pub_date = ""

        # 既存データに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"au損害保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding  # 正しいエンコーディングを自動検出
                content = response.text

            if not content:
                print(f"au損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "au損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"au損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_axa_news():
    """
    アクサ損害保険株式会社「お知らせ」
    """
    base_url  = "https://www.axa-direct.co.jp"
    url       = f"{base_url}/company/official_info/announce/"
    json_file = "./data/axa_news.json"

    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "div.releaseList-wrapper[data-info-category='announce'] ul.releaseList"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"[AXA_news] ページ取得エラー: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items, new_cnt = [], 0

    # ───────── li を一括取得（年ごとに複数 UL がある） ─────────
    li_tags = soup.select(
        "div.releaseList-wrapper[data-info-category='announce'] "
        "ul.releaseList li.releaseList-item"
    )
    if not li_tags:
        print("[AXA_news] お知らせ項目が見つかりませんでした。")
        return []

    for li in li_tags:
        a = li.select_one("a.releaseList-item-link[href]")
        if not a:
            continue

        link  = urljoin(base_url, a["href"].strip())
        date  = (a.select_one("p.releaseList-item-link-date")
                 .get_text(strip=True))
        title = (a.select_one("p.releaseList-item-link-title")
                 .get_text(strip=True))

        if any(d["title"] == title and d["link"] == link for d in existing_data):
            continue

        print(f"[AXA_news] 取得 - {date}: {title}")

        try:
            r = requests.get(link, timeout=15, verify=certifi.where())
            r.encoding = "utf-8"
            content = r.text

            summary = ""
            if new_cnt < max_count:
                summary = summarize_text(title, content)

            item = {
                "pubDate": date,
                "execution_timestamp": execution_timestamp,
                "organization": "アクサ損害保険株式会社（お知らせ）",
                "title": title,
                "link":  link,
                "summary": summary,
            }
            news_items.append(item)
            existing_data.append(item)
            new_cnt += 1

        except Exception as e:
            print(f"[AXA_news] 要約中にエラー: {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_axa_pr():
    """アクサ損害保険 プレスリリースを収集・要約する"""
    base_url  = "https://www.axa-direct.co.jp"
    url       = f"{base_url}/company/official_info/pr/"
    json_file = "./data/axa_pr.json"

    existing = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        # <ul class="releaseList"> が出てくるまで待機
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "div.releaseList-wrapper[data-info-category='pr'] ul.releaseList"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"[AXA_pr] ページ取得エラー: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items, new_cnt = [], 0

    # ───────── li を直接取得（年ごとに複数 UL があるため） ─────────
    li_tags = soup.select(
        "div.releaseList-wrapper[data-info-category='pr'] "
        "ul.releaseList li.releaseList-item"
    )
    if not li_tags:
        print("[AXA_pr] プレスリリース項目が見つかりませんでした。")
        return []

    for li in li_tags:
        a = li.select_one("a.releaseList-item-link[href]")
        if not a:
            continue

        link  = urljoin(base_url, a["href"].strip())
        date  = (a.select_one("p.releaseList-item-link-date")
                 .get_text(strip=True))
        title = (a.select_one("p.releaseList-item-link-title")
                 .get_text(strip=True))

        # 重複チェック
        if any(d["title"] == title and d["link"] == link for d in existing):
            continue

        print(f"[AXA_pr] 取得 - {date}: {title}")

        # 本文取得＆要約
        try:
            r = requests.get(link, timeout=15, verify=certifi.where())
            r.encoding = "utf-8"
            content = r.text

            summary = ""
            if new_cnt < max_count:
                summary = summarize_text(title, content)

            item = {
                "pubDate": date,
                "execution_timestamp": execution_timestamp,
                "organization": "アクサ損害保険株式会社（プレスリリース）",
                "title": title,
                "link":  link,
                "summary": summary,
            }
            news_items.append(item)
            existing.append(item)
            new_cnt += 1

        except Exception as e:
            print(f"[AXA_pr] 要約中にエラー: {e}")

    save_json(existing, json_file)
    return news_items

def fetch_axa_sufferers():
    """
    アクサ損害保険株式会社「被害に関するお知らせ」を収集・要約する
    """
    base_url  = "https://www.axa-direct.co.jp"
    url       = f"{base_url}/company/official_info/sufferers/"
    json_file = "./data/axa_sufferers.json"

    existing = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR,
                 "div.releaseList-wrapper[data-info-category='sufferers'] ul.releaseList"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"[AXA_sufferers] ページ取得エラー: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items, new_cnt = [], 0

    # ───────── お知らせ li を一括取得 ─────────
    li_tags = soup.select(
        "div.releaseList-wrapper[data-info-category='sufferers'] "
        "ul.releaseList li.releaseList-item"
    )
    if not li_tags:
        print("[AXA_sufferers] 被害に関するお知らせが見つかりません。")
        return []

    for li in li_tags:
        a = li.select_one("a.releaseList-item-link[href]")
        if not a:
            continue

        link  = urljoin(base_url, a["href"].strip())
        date  = (a.select_one("p.releaseList-item-link-date")
                 .get_text(strip=True))
        title = (a.select_one("p.releaseList-item-link-title")
                 .get_text(strip=True))

        # 重複チェック
        if any(d["title"] == title and d["link"] == link for d in existing):
            continue

        print(f"[AXA_sufferers] 取得 - {date}: {title}")

        try:
            r = requests.get(link, timeout=10, verify=certifi.where())
            r.encoding = "utf-8"
            content = r.text

            summary = ""
            if new_cnt < max_count:
                summary = summarize_text(title, content)

            item = {
                "pubDate": date,
                "execution_timestamp": execution_timestamp,
                "organization": "アクサ損害保険株式会社（被害のお知らせ）",
                "title": title,
                "link":  link,
                "summary": summary,
            }
            news_items.append(item)
            existing.append(item)
            new_cnt += 1

        except Exception as e:
            print(f"[AXA_sufferers] 要約中にエラー: {e}")

    save_json(existing, json_file)
    return news_items

def fetch_capital_sonpo_news():
    """キャピタル損保の最新情報を収集・要約します。"""
    url = "https://www.capital-sonpo.co.jp/index.html"
    base_url = "https://www.capital-sonpo.co.jp"
    json_file = "./data/capital_sonpo_news.json"

    # 既存データをロード（外部やグローバルで定義されている想定）
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"キャピタル損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # <dl class="DateListStyle2">を見つける
    dl_tag = soup.find('dl', class_='DateListStyle2')
    if not dl_tag:
        print("キャピタル損保: DateListStyle2 が見つかりません。")
        return []

    # <dt> は日付、直後の <dd> にリンクリストがある想定
    dt_list = dl_tag.find_all('dt')
    dd_list = dl_tag.find_all('dd')

    # zipでペアを作って繰り返し
    for dt_tag, dd_tag in zip(dt_list, dd_list):
        pub_date = dt_tag.get_text(strip=True)  # 例: "2025.02"

        # <dd> の中に <ul class="LinkListStyle1"> があり、その中に <li> → <a> が並んでいる想定
        ul_tag = dd_tag.find('ul', class_='LinkListStyle1')
        if not ul_tag:
            # リンクがない場合もあるかもしれないのでスキップ
            continue

        # <li> → <a> をすべて取得
        li_tags = ul_tag.find_all('li')
        for li_tag in li_tags:
            a_tag = li_tag.find('a')
            if not a_tag:
                continue

            relative_link = a_tag.get('href', '').strip()
            if relative_link.startswith('/'):
                link = base_url + relative_link
            else:
                # "houjing/jirei_4.html" のような相対パス
                link = base_url + '/' + relative_link

            # タイトル本文は<a>内のテキスト
            title_text = a_tag.get_text(strip=True)
            # 既存データと重複チェック
            if any(item['title'] == title_text for item in existing_data):
                continue

            print(f"キャピタル損保: 記事取得 - {pub_date}: {title_text}")

            # コンテンツ取得（PDF判定などはお好みで）
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    resp = requests.get(link, verify=False)  # 必要に応じて証明書チェック
                    resp.encoding = 'utf-8'
                    content = resp.text

                if not content:
                    print(f"キャピタル損保: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 外部またはグローバルに定義されている想定
                    summary = summarize_text(title_text, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,  # 外部またはグローバル定義
                    'organization': "キャピタル損保",
                    'title': title_text,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1

            except Exception as e:
                print(f"キャピタル損保: 要約中にエラー - {e}")

    # JSONファイルなどに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_cardif_info():
    """カーディフ損害保険の最新情報を収集・要約します。"""
    url = "https://nonlife.cardif.co.jp/company/news/information/"
    json_file = "./data/cardif_info.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        return []

    news_items = []
    new_count = 0  # 取得した新しいニュースのカウント

    # ニュース項目を取得
    for a_tag in soup.find_all('a', class_='news-item'):

        title_tag = a_tag.find('h3')
        date_tag = a_tag.find('span', class_='date')
        p_tag = a_tag.find('p')

        if not title_tag or not date_tag or not p_tag:
            continue  # 必要な情報が不足している場合はスキップ

        title = title_tag.get_text(strip=True)
        pub_date = date_tag.get_text(strip=True)
        link = a_tag.get('href')

        # 既存のデータと重複していないか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"新しいニュースを検出: {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"カーディフ: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)
            
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "カーディフ損害保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"ニュース処理中にエラーが発生しました: {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_cardif_news():
    """カーディフ損害保険の最新情報を収集・要約します。"""
    url = "https://nonlife.cardif.co.jp/company/news/release"
    json_file = "./data/cardif_news.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        return []

    news_items = []
    new_count = 0  # 取得した新しいニュースのカウント

    # ニュース項目を取得
    for a_tag in soup.find_all('a', class_='news-item'):

        title_tag = a_tag.find('h3')
        date_tag = a_tag.find('span', class_='date')
        p_tag = a_tag.find('p')

        if not title_tag or not date_tag or not p_tag:
            continue  # 必要な情報が不足している場合はスキップ

        title = title_tag.get_text(strip=True)
        pub_date = date_tag.get_text(strip=True)
        link = a_tag.get('href')

        # 既存のデータと重複していないか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"新しいニュースを検出: {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"カーディフ: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)
            
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "カーディフ損害保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"ニュース処理中にエラーが発生しました: {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_chubb_info():
    """Chubb損害保険株式会社のお知らせページから最新情報を収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-info.html"
    json_file = f"./data/chubb_info.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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

def fetch_chubb_news():
    """Chubb損害保険株式会社のニュースリリースを収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-release.html"
    json_file = "./data/chubb_news.json"
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

def fetch_daidokasai_news():
    """大同火災海上保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.daidokasai.co.jp/news/"
    json_file = "./data/daidokasai_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ページ取得中にエラーが発生しました: {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    post_group = soup.find('ul', class_='post-group')
    if not post_group:
        print("ニュースリストが見つかりませんでした。")
        return []

    for li in post_group.find_all('li'):

        a_tag = li.find('a', class_='link')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.daidokasai.co.jp" + link

        title = a_tag.find('span', class_='title').get_text(strip=True)
        pub_date = a_tag.find('span', class_='date').get_text(strip=True)

        if pub_date < "2024-01-01":
            continue

        # カテゴリ取得（存在しない場合は「その他」）
        badge = a_tag.find('span', class_='badge-group').find('span', class_='badge')
        category = badge.get_text(strip=True) if badge else "その他"

        # 既に存在するニュースか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在する場合はスキップ

        print(f"新規記事取得: {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 主要な記事コンテンツを抽出（適宜調整が必要）
                content_div = page_soup.find('div', class_='entry-content')  # クラス名は実際に確認
                if content_div:
                    content = content_div.get_text(separator='\n', strip=True)
                else:
                    content = page_soup.get_text(separator='\n', strip=True)
            
            if not content:
                print(f"コンテンツが空です: {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "大同火災海上保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"記事処理中にエラーが発生しました: {e}")
            continue

    save_json(existing_data, json_file)
    return news_items

def fetch_edesign_info():
    """イーデザイン損保の最新情報を収集・要約します。"""
    url = "https://www.e-design.net/company/information/2025/"
    base_url = "https://www.e-design.net"
    json_file = "./data/edesign_info.json"

    # 既存データのロード（外部/グローバルで定義されている想定）
    existing_data = load_existing_data(json_file)
    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"イーデザイン損保: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # 1) ニュースブロック <div class="c-newsBlock__content"> を探す
    news_block = soup.find('div', class_='c-newsBlock__content')
    if not news_block:
        print("イーデザイン損保: c-newsBlock__content が見つかりませんでした。")
        return []

    # 2) その中の <ul> → <li> 全てを取得
    ul_tag = news_block.find('ul')
    if not ul_tag:
        print("イーデザイン損保: <ul> が見つかりませんでした。")
        return []

    li_tags = ul_tag.find_all('li')
    if not li_tags:
        print("イーデザイン損保: ニュース項目(li)が見つかりませんでした。")
        return []

    # 3) liごとに処理
    for li in li_tags:
        # タイトルとリンク: <a href="/company/information/2025/****.html">…</a>
        a_tag = li.find('a')
        if not a_tag:
            continue

        relative_link = a_tag.get('href', '').strip()
        # 相対パスを絶対パスへ
        if relative_link.startswith('http'):
            full_link = relative_link
        else:
            # 例: "/company/information/2025/2025_04_01_03.html"
            full_link = base_url + relative_link

        title_text = a_tag.get_text(strip=True)
        if not title_text:
            continue

        # 日付: <p class="m-date">2025年4月1日</p> など
        date_p = li.find('p', class_='m-date')
        pub_date = date_p.get_text(strip=True) if date_p else ""

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"イーデザイン損保: 取得 - {pub_date}: {title_text}")

        # コンテンツ取得 & 要約（必要に応じてPDF判定etc.）
        try:
            resp = requests.get(full_link, verify=False)
            resp.encoding = 'utf-8'
            content = resp.text

            if not content:
                print(f"イーデザイン損保: コンテンツ取得失敗 - {full_link}")
                continue

            summary = ""
            if new_count < max_count:  # 外部/グローバルで定義想定
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル/外部定義
                'organization': "イーデザイン損保",
                'title': title_text,
                'link': full_link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"イーデザイン損保: 要約中にエラー - {e}")

    # 最後に保存
    save_json(existing_data, json_file)
    return news_items

def fetch_edesign_news():
    """イーデザイン損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.e-design.net/company/news/2025/"
    json_file = f"./data/edesign_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"イーデザイン損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_block = soup.find('div', class_='c-newsBlock__content')
    if not news_block:
        print("イーデザイン損害保険株式会社: ニュースブロックが見つかりません。")
        return []

    for li in news_block.find_all('li'):

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.e-design.net" + link
        title = title_tag.get_text(strip=True)
        pub_date_tag = li.find('p', class_='m-date')
        if pub_date_tag:
            pub_date_text = pub_date_tag.get_text(strip=True)
            pub_date = pub_date_text.split(' ')[0]  # 日付部分のみ取得
        else:
            pub_date = ""

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"イーデザイン損害保険株式会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding
                page_soup = BeautifulSoup(response.text, 'html.parser')
                content_div = page_soup.find('div', class_='l-inner')
                if content_div:
                    paragraphs = content_div.find_all(['p', 'li'])
                    content = "\n".join([para.get_text(strip=True) for para in paragraphs])
                else:
                    content = page_soup.get_text(strip=True)

            if not content:
                print(f"イーデザイン損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "イーデザイン損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"イーデザイン損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_hs_news():
    """エイチ・エス損害保険の最新情報を収集・要約します。"""
    url = "https://www.hs-sonpo.co.jp/news/"
    json_file = "./data/hs.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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

def fetch_sbi_press():
    """SBI損害保険の最新プレスリリースを収集・要約します。"""
    url = "https://www.sbisonpo.co.jp/company/news/"
    json_file = f"./data/sbi_press.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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

def fetch_sbi_news():
    """SBI損害保険株式会社のお知らせを収集・要約します。"""
    url = "https://www.sbisonpo.co.jp/company/information/"
    json_file = "./data/sbi_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"SBI損保_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='si-listNews')
    if not news_list:
        print("SBI損保_news: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):
        date_div = li.find('div', class_='si-listNews__date')
        main_div = li.find('div', class_='si-listNews__main')
        if not date_div or not main_div:
            continue

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

        print(f"SBI損保_news: 記事取得開始 - {title}")

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
                print(f"SBI損保_news: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "SBI損保",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"SBI損保_news: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_newindia_news():
    """
    ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッド
    """
    base_url  = "https://www.newindia.co.jp/topics/"
    json_file = "./data/newindia.json"

    existing  = load_existing_data(json_file)
    news      = []
    new_cnt   = 0

    try:
        r = requests.get(base_url, timeout=15)
        r.encoding = r.apparent_encoding
    except Exception as e:
        print(f"ニューインディア: ページ取得エラー – {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    for anchor in soup.select("a[name]"):
        box = anchor.find_next("div", class_="news_box")
        if not box:
            continue

        # 日付・タイトル抽出
        dt_tag = box.select_one(".title dt")
        dd_tag = box.select_one(".title dd")
        if not (dt_tag and dd_tag):
            continue

        raw_date = dt_tag.get_text(strip=True)          # 例) 2025.03.27
        pub_date = raw_date.replace(".", "-")           # 2025-03-27 形式に

        # dd 内に <a> があれば優先（PDF 直リンクなど）
        a_tag  = dd_tag.find("a")
        if a_tag and a_tag.get("href"):
            link  = urljoin(base_url, a_tag["href"])
            title = a_tag.get_text(strip=True) or dd_tag.get_text(strip=True)
        else:
            link  = f"{base_url}#{anchor['name']}"
            title = dd_tag.get_text(strip=True)

        # 既知タイトルはスキップ
        if any(title == item["title"] for item in existing):
            continue

        print(f"ニューインディア: 取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # topics ページ内の本文を直接抜く
                text_div = box.find_next_sibling("div", class_="text")
                if text_div:
                    content = text_div.get_text(separator="\n", strip=True)
                else:  # 念のためリンク先を GET
                    r2 = requests.get(link, timeout=10)
                    r2.encoding = r2.apparent_encoding
                    content = BeautifulSoup(r2.text, "html.parser")\
                                .get_text(separator="\n", strip=True)
            if not content:
                print(f"ニューインディア: コンテンツ取得失敗 - {link}")
                continue
        except Exception as e:
            print(f"ニューインディア: コンテンツ取得中にエラー – {e}")
            continue

        # 要約（max_count == 0 なら常にスキップ）
        summary = ""
        if new_cnt < max_count:
            summary = summarize_text(title, content)

        item = {
            "execution_timestamp": execution_timestamp,
            "pubDate"           : pub_date,
            "organization"      : "ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッド",
            "title"             : title,
            "link"              : link,
            "summary"           : summary,
        }
        news.append(item)
        existing.append(item)
        new_cnt += 1

    save_json(existing, json_file)
    return news

def fetch_starr_news():
    """
    スター・カンパニーズ・ジャパン
    """
    base_url  = "https://www.starrcompanies.jp/News"
    site_root = "https://www.starrcompanies.jp"
    json_file = "./data/starr.json"

    existing   = load_existing_data(json_file)
    news_items = []
    new_cnt    = 0

    try:
        res = requests.get(base_url, timeout=15)
        res.raise_for_status()
        res.encoding = res.apparent_encoding
    except Exception as e:
        print(f"Starr: ページ取得失敗 – {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")

    for art in soup.select("div.news-article"):
        # ------- タイトル ------------------------------------------------ #
        head = art.select_one(".news-article__content-headline")
        if not head:
            continue
        title = head.get_text(strip=True).strip("「」｢｣\"'”")

        # ------- 日付 ---------------------------------------------------- #
        pub_date = ""
        date_div = art.select_one(".news-article__content-date")
        if date_div:
            dtext = re.sub(r"\s+", " ", date_div.get_text(strip=True))
            # 数字をすべて抽出
            nums = list(map(int, re.findall(r"\d{1,4}", dtext)))
            # 「YYYY MM DD」型 もしくは 「DD MM YYYY」型 の2パターンを想定
            if len(nums) >= 3:
                if nums[0] >= 1900:           # YYYY から始まる
                    y, m, d = nums[0], nums[1], nums[2]
                else:                          # DD MM YYYY
                    d, m, y = nums[0], nums[1], nums[-1]
                # ざっくり妥当性チェック
                if 1 <= m <= 12 and 1 <= d <= 31:
                    pub_date = f"{y:04d}-{m:02d}-{d:02d}"

        # ------- 本文／PDF へのリンク ------------------------------------- #
        link_tag = (
            art.select_one("a.news-article__button-link")
            or art.select_one("a.news-article__image-link")
            or art.find("a", href=True)
        )
        if not link_tag:
            continue
        link = urljoin(site_root, link_tag["href"])

        # ------- 既に取得済みのタイトルはスキップ ------------------------ #
        if any(title == item["title"] for item in existing):
            continue

        print(f"[INFO] Starr: 取得開始 - {title}")

        # ---------------------------------------------------------------- #
        # 3. 本文取得（PDF or HTML）
        # ---------------------------------------------------------------- #
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                r2 = requests.get(link, timeout=10)
                r2.raise_for_status()
                r2.encoding = r2.apparent_encoding
                soup2 = BeautifulSoup(r2.text, "html.parser")
                main = soup2.find("article") or soup2.find("main") or soup2
                content = main.get_text(separator="\n", strip=True)
        except Exception as e:
            print(f"[WARN] Starr: 本文取得失敗 – {e}")
            continue
        if not content:
            print(f"[WARN] Starr: 空コンテンツ – {link}")
            continue

        summary = ""
        if new_cnt < max_count:
            summary = summarize_text(title, content)

        item = {
            "execution_timestamp": execution_timestamp,
            "pubDate"           : pub_date,
            "organization"      : "スター・カンパニーズ・ジャパン",
            "title"             : title,
            "link"              : link,
            "summary"           : summary,
        }
        news_items.append(item)
        existing.append(item)
        new_cnt += 1

    save_json(existing, json_file)
    return news_items

def fetch_secom_news():
    """セコム損害保険株式会社のお知らせから最新情報を収集・要約します。"""
    url = "https://www.secom-sonpo.co.jp/infolist/"
    json_file = "./data/secom.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"セコム: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    for inner_div in soup.find_all('div', class_='inner mt20'):
        year_tag = inner_div.find('p', class_='bold')
        if not year_tag:
            continue
        year = year_tag.get_text(strip=True)

        for dl in inner_div.find_all('dl', class_='news'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if not dt or not dd:
                continue

            pub_date = dt.get_text(strip=True)
            a_tag = dd.find('a')
            if not a_tag:
                continue

            title = a_tag.get_text(strip=True)
            link = a_tag.get('href')
            if not link.startswith("http"):
                link = "https://www.secom-sonpo.co.jp" + link

            # 既に存在するニュースはスキップ
            if any(title == item['title'] for item in existing_data):
                continue

            print(f"セコム: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    page_soup = BeautifulSoup(response.text, 'html.parser')
                    # コンテンツの抽出方法は実際のページ構造に基づいて調整してください
                    content_div = page_soup.find('div', class_='content')  # 例
                    if content_div:
                        content = content_div.get_text(separator='\n', strip=True)
                    else:
                        content = page_soup.get_text(separator='\n', strip=True)

                if not content:
                    print(f"セコム: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': f"{pub_date}",
                    'execution_timestamp': execution_timestamp,
                    'organization': "セコム損害保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"セコム: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items

def fetch_secom_product_news():
    """セコム損害保険の最新情報を収集・要約します。"""
    url = "https://www.secom-sonpo.co.jp/service-infolist/"
    json_file = f"./data/secom_product_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"セコム損害保険_product_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 各年ごとのセクションを取得
    year_sections = soup.find_all('div', class_='inner mt20')
    for year_section in year_sections:
        year_title = year_section.find('p', class_='bold')
        if not year_title:
            continue
        year = year_title.get_text(strip=True)

        # 各ニュース項目を取得
        for dl in year_section.find_all('dl', class_='news'):
            dt = dl.find('dt')
            dd = dl.find('dd')
            if not dt or not dd:
                continue

            pub_date = dt.get_text(strip=True)
            a_tag = dd.find('a')
            if not a_tag:
                continue

            link = a_tag.get('href')
            if not link.startswith("http"):
                link = "https://www.secom-sonpo.co.jp" + link
            title = a_tag.get_text(strip=True)

            # 既に存在するニュースはスキップ
            if any(title == item['title'] for item in existing_data):
                continue

            print(f"セコム損害保険_product_news: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'utf-8'
                    content_soup = BeautifulSoup(response.text, 'html.parser')
                    # 必要なコンテンツを抽出（例として本文を全て取得）
                    content = content_soup.get_text(separator="\n", strip=True)

                if not content:
                    print(f"セコム損害保険_product_news: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "セコム損害保険株式会社_product_news",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加


            except Exception as e:
                print(f"セコム損害保険_product_news: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items

def fetch_zenkankyo_reiwa_news():
    """全管協れいわ損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.zkreiwa-sonpo.co.jp/"
    json_file = f"./data/zkreiwa_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページの読み込みを待つ
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"全管協れいわ損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 「お知らせ一覧」セクションを探す
    post_list_container = soup.find('div', class_='postList postList_miniThumb')
    if not post_list_container:
        print("お知らせ一覧のセクションが見つかりませんでした。")
        return []

    for post_item in post_list_container.find_all('div', class_='postList_item'):
        title_tag = post_item.find('div', class_='postList_title').find('a')
        date_tag = post_item.find('div', class_='postList_date')

        if not title_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        pub_date = date_tag.get_text(strip=True)

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"全管協れいわ損害保険株式会社: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # 記事本文を抽出（実際のサイト構造に合わせて調整が必要）
                content_div = content_soup.find('div', class_='entry-body')  # クラス名は仮
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = content_soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"全管協れいわ損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "全管協れいわ損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"全管協れいわ損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_sonysonpo_news():
    """ソニー損害保険株式会社（お知らせ）の最新情報を収集・要約します。"""
    url = "https://from.sonysonpo.co.jp/topics/information/N0086000.html"
    json_file = "./data/sonysonpo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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


def fetch_sonysonpo_news_release():
    """ソニー損害保険株式会社の最新ニュースを収集・要約します。"""
    url = "https://from.sonysonpo.co.jp/topics/news/2025/"
    json_file = f"./data/sonysonpo_news_release.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ソニー損保_news_release: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースが掲載されているテーブルを特定
    news_table = soup.find('table', class_='contentTbox font-l fullWidthSp')
    if not news_table:
        print("ソニー損保_news_release: ニューステーブルが見つかりませんでした。")
        return []

    for tr in news_table.find_all('tr'):
        th = tr.find('th')
        td = tr.find('td')

        if not th or not td:
            continue  # thまたはtdがない行はスキップ

        pub_date = th.get_text(strip=True)
        a_tag = td.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://from.sonysonpo.co.jp" + link

        # 既存のデータに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"ソニー損保_news_release: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース内容がどのタグにあるかに応じて適宜変更してください
                # ここでは例として<div class="news-content">を想定
                content_div = page_soup.find('div', class_='news-content')
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    content = page_soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"ソニー損保_news_release: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ソニー損害保険_news_release",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"ソニー損保_news_release: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_sonpohogo_news():
    """
    https://www.sonpohogo.or.jp/news/ にある
    <div class="nav-news-area"> 内の <li> を取得して要約を付ける。
    """
    list_url  = "https://www.sonpohogo.or.jp/news/"
    site_root = "https://www.sonpohogo.or.jp/"
    json_file = "./data/sonpohogo_news.json"
    os.makedirs(os.path.dirname(json_file), exist_ok=True)

    existing_data        = load_existing_data(json_file)
    processed_titles     = {d["title"] for d in existing_data}
    new_items, new_count = [], 0

    # ─ 一覧ページを取得 ──────────────────────────────────────────────
    try:
        html = requests.get(list_url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        print(f"損保機構: 一覧ページ取得エラー - {e}")
        return []

    # ─ ニュース行を走査 ─────────────────────────────────────────────
    for li in soup.select("div.nav-news-area ol li"):
        # 日付
        time_tag = li.find("time")
        pub_date = time_tag.get_text(strip=True) if time_tag else ""

        # タイトル & リンク
        a_tag = li.select_one("p.title > a")
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        if title in processed_titles:        # 既読スキップ
            continue

        href      = a_tag.get("href", "")
        link      = urljoin(site_root, href.lstrip("/"))   # 相対→絶対
        print(f"損保機構: 取得 - {title}")

        # ─ 本文取得 ──────────────────────────────────────────────
        try:
            content = (
                extract_text_from_pdf(link)
                if is_pdf_link(link)
                else requests.get(link, timeout=10).text
            )
        except Exception as e:
            print(f"損保機構: コンテンツ取得失敗 - {e}")
            continue

        # ─ 要約（global max_count 件まで）──────────────────────────
        summary = ""
        if new_count < max_count:
            try:
                summary = summarize_text(title, content)
            except Exception as e:
                print(f"損保機構: 要約失敗 - {e}")

        # ─ アイテム保存 ───────────────────────────────────────────
        item = {
            "pubDate"            : pub_date,
            "execution_timestamp": execution_timestamp,
            "organization"       : "損害保険契約者保護機構",
            "label"              : "お知らせ",
            "title"              : title,
            "link"               : link,
            "summary"            : summary,
        }

        new_items.append(item)
        existing_data.append(item)
        processed_titles.add(title)
        new_count += 1

    save_json(existing_data, json_file)
    return new_items

def fetch_sompo_news():
    """損害保険ジャパン株式会社の最新情報を収集・要約します。"""
    url = "https://www.sompo-japan.co.jp/rss/news/"
    feed = feedparser.parse(url)
    json_file = f"./data/sompo-japan-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # 新しいニュースのカウンター

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"損害保険ジャパン: 記事取得開始 - {entry.title}")
        try:
            link = entry.link.replace('?la=ja-JP', '')  # URLのクエリパラメータを削除

            if is_pdf_link(link): # URLのクエリパラメータを削除
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース内容を抽出（適宜調整が必要）
                content = content_soup.get_text(separator="\n", strip=True)


            if not content.strip():
                print(f"損害保険ジャパン: コンテンツ取得失敗または空 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "損害保険ジャパン株式会社",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"損害保険ジャパン: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_sompo_direct_news():
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

def fetch_sompo_direct_important_news():
    """SOMPOダイレクトの大切なお知らせを収集・要約します。"""
    url = "https://news-ins-saison.dga.jp/topics/?type=important"
    json_file = f"./data/sompo_direct_important_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"SOMPOダイレクト_important_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='p-link-news')
    if not news_list:
        print("SOMPO_direct_important_news: ニュースリストの取得に失敗しました。")
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

        print(f"SOMPO_direct_important_news: 記事取得開始 - {title}")

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
                print(f"SOMPO_direct_important_news: コンテンツ取得失敗 - {link}")
                continue

            # 要約
            if new_count < max_count:
                summary = summarize_text(title, content)
            else:
                summary = ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "SOMPOダイレクト損害保険株式会社_important_news",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"SOMPO_direct_important_news: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items

def fetch_zurich_news():
    """チューリッヒの最新情報を収集・要約します。"""
    url = "https://www.zurich.co.jp/aboutus/news/"
    json_file = f"./data/zurich_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"チューリッヒ: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='list-date-01')
    if not news_list:
        print("チューリッヒ: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        # 日付とタイプを取得
        spans = li.find_all('span')
        if len(spans) < 2:
            continue  # 必要な情報が不足している場合はスキップ

        pub_date = spans[0].get_text(strip=True)
        news_type = spans[1].get_text(strip=True)

        # タイトルとリンクを取得
        title_tag = li.find('a')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.zurich.co.jp" + link

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"チューリッヒ: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                if response.encoding is None:
                    response.encoding = 'utf-8'  # エンコーディング不明の場合はutf-8をデフォルト
                content = response.text

            if not content:
                print(f"チューリッヒ: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'type': news_type,
                'organization': "チューリッヒ・インシュアランス・カンパニー・リミテッド",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"チューリッヒ: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_tokiomarine_news():
    """東京海上日動火災保険株式会社のお知らせを収集・要約します。"""
    url = "https://www.tokiomarine-nichido.co.jp/company/news/"
    json_file = f"./data/tokiomarine_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"東京海上日動_news: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('dl', class_='listNewsBa')
    if not news_list:
        print("東京海上日動_news: ニュースリストが見つかりませんでした。")
        return []

    for item in news_list.find_all('div', class_='list-detail-07__list'):
        dt = item.find('dt', class_='list-detail-07__term')
        dd = item.find('dd', class_='list-detail-07__desc')
        
        if not dt or not dd:
            continue

        # 日付の抽出
        date_span = dt.find('span', class_='list-detail-07__date')
        pub_date = date_span.get_text(strip=True) if date_span else ""

        # タイトルとリンクの抽出
        a_tag = dd.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith('http'):
            link = f"https://www.tokiomarine-nichido.co.jp{link}"

        # 既存データのチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"東京海上日動_news: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"東京海上日動_news: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "東京海上日動火災保険_news",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"東京海上日動_news: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_tokiomarine_release():
    """
    東京海上日動ニュースリリースを取得する。
    """
    BASE_URL  = "https://www.tokiomarine-nichido.co.jp"
    INDEX_URL = f"{BASE_URL}/company/release/"
    JSON_FILE = "./data/tokiomarine_release.json"

    existing = load_existing_data(JSON_FILE)

    # ------------- ページ取得 -------------
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(INDEX_URL)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"TOKIO MARINE: ページ取得失敗 - {e}")
        driver.quit()
        return []
    driver.quit()

    collected, hit = [], 0
    limit = max_count if max_count > 0 else float("inf")

    for blk in soup.select("div.list-detail-07__list"):
        try:
            date_txt = blk.select_one("span.list-detail-07__date").get_text(strip=True)
            a_tag    = blk.select_one("dd a")
            title    = a_tag.get_text(strip=True)
            href     = a_tag["href"]
            link     = href if href.startswith("http") else BASE_URL + href

            # 重複チェック
            if any(d["title"] == title for d in existing):
                continue

            # -------- 本文取得 --------
            content = ""
            if is_pdf_link(link):
                try:
                    content = extract_text_from_pdf(link) or ""
                except Exception as e:
                    print(f"TOKIO MARINE: PDF抽出失敗 - {e}")
                    content = ""
            else:
                try:
                    r = requests.get(link, timeout=15)
                    r.encoding = r.apparent_encoding
                    content = BeautifulSoup(r.text, "html.parser").get_text("\n", strip=True)
                except Exception as e:
                    print(f"TOKIO MARINE: HTML取得失敗 - {e}")
                    content = ""

            # -------- 要約（本文があれば）--------
            summary = ""
            if content and hit < limit:
                summary = summarize_text(title, content)

            item = {
                "pubDate": date_txt,
                "execution_timestamp": execution_timestamp,
                "organization": "東京海上日動火災保険株式会社",
                "title": title,
                "link": link,
                "summary": summary,
            }
            collected.append(item)
            existing.append(item)
            hit += 1
            if hit >= limit:
                break

        except Exception as e:
            print(f"TOKIO MARINE: 解析エラー - {e}")
            continue

    # ------------- JSON 保存 -------------
    os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
    save_json(existing, JSON_FILE)
    return collected

def fetch_toa_news():
    """トーア再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.toare.co.jp/newsrelease"
    json_file = "./data/toa_news.json"
    
    # 既存データのロード（定義済みのヘルパー関数）
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定（例: ヘッドレスモード）
    options = Options()
    options.add_argument("--headless")

    # Chromeドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        # ページソースを取得してパース
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"トーア再保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    # ドライバーを閉じる
    driver.quit()

    news_items = []
    new_count = 0  # 新しく取得した記事数カウンター

    # ニュースリストの親要素を探す
    news_cont = soup.find('div', class_='news_cont')
    if not news_cont:
        print("ニュースリリースのコンテナが見つかりませんでした。")
        return []

    news_list = news_cont.find('ul')
    if not news_list:
        print("ニュースリリースリストが見つかりませんでした。")
        return []

    # リスト内の li タグを順次解析
    for li in news_list.find_all('li'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue
        
        # 相対パスの場合は絶対URLに変換
        if link.startswith("/"):
            link = "https://www.toare.co.jp" + link

        # 日付・ラベル・本文（タイトル）を抽出
        date_tag = a_tag.find('span', class_='date')
        label_tag = a_tag.find('span', class_='label')
        p_tag = a_tag.find('p')

        pub_date = date_tag.get_text(strip=True) if date_tag else ""
        label = label_tag.get_text(strip=True) if label_tag else ""

        # "NEW!" などの不要文字が含まれる場合は除去
        title_text = p_tag.get_text(strip=True) if p_tag else ""
        # NEW! の文字列を削除し、改めてstrip
        title_text = title_text.replace("NEW!", "").strip()

        # 既存データとタイトルで重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"トーア再保険株式会社: 記事取得開始 - {title_text}")

        # PDFかダウンロードリンクの場合はテキスト抽出、それ以外は通常リクエスト
        try:
            if is_pdf_link(link) or '/jp-news/download/' in link:
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"トーア再保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            # 取得した本文をサマライズ（上限数に達していなければ）
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "トーア再保険株式会社",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }

            # 新しいニュースをリストに追加
            news_items.append(news_item)
            # 既存データにも追記して重複を防ぐ
            existing_data.append(news_item)
            # 新しい記事をカウント
            new_count += 1

        except Exception as e:
            print(f"トーア再保険株式会社: 要約中にエラー発生 - {e}")

    # 最終的なデータをJSONに保存（定義済みのヘルパー関数）
    save_json(existing_data, json_file)

    return news_items

def fetch_nihonjishin():
    """日本地震再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.nihonjishin.co.jp/news.html"
    json_file = "./data/nihonjishin_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"日本地震再保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # タブごとに処理
    tabs = [
        {'id': 'archive-tab-content-1', 'category': 'お知らせ'},
        {'id': 'archive-tab-content-2', 'category': 'ニュースリリース'}
    ]

    for tab in tabs:
        tab_id = tab['id']
        category = tab['category']
        tab_section = soup.find('div', id=tab_id)
        if not tab_section:
            print(f"{category}: タブセクションが見つかりません。")
            continue

        # 各年のカードを取得
        cards = tab_section.find_all('div', class_='card')
        for card in cards:
            year_id = card.get('id')  # 例: tab01-2024
            year = year_id.split('-')[-1].strip() if '-' in year_id else '不明'

            if year < '2024':
                continue

            card_body = card.find('div', class_='card-body')
            if not card_body:
                print(f"{category} {year}: カードボディが見つかりません。")
                continue

            news_list = card_body.find_all('li')
            for li in news_list:
                date_div = li.find('div', class_='archive-date')
                if not date_div:
                    print(f"{category} {year}: 日付が見つかりません。")
                    continue
                pub_date = date_div.get_text(strip=True)

                # タイトルとリンクを取得
                link_tag = li.find('a')
                if not link_tag:
                    print(f"{category} {year}: タイトルリンクが見つかりません。")
                    continue
                link = link_tag.get('href')
                if link.startswith("/"):
                    link = "https://www.nihonjishin.co.jp" + link
                title = link_tag.get_text(strip=True)

                # カテゴリーを追加
                # チェック: 既に存在するか
                if any(title == item.get('title') for item in existing_data):
                    continue

                print(f"日本地震再保険: 記事取得開始 - {title}")
                try:
                    if is_pdf_link(link):
                        content = extract_text_from_pdf(link)
                    else:
                        response = requests.get(link)
                        response.raise_for_status()
                        response.encoding = 'UTF-8'
                        content_soup = BeautifulSoup(response.text, 'html.parser')
                        # 主要なコンテンツを抽出（仮定）
                        content = content_soup.get_text(separator='\n', strip=True)

                    if not content:
                        print(f"日本地震再保険: コンテンツ取得失敗 - {link}")
                        continue

                    summary = ""
                    if new_count < max_count:
                        summary = summarize_text(title, content)

                    news_item = {
                        'pubDate': pub_date,
                        'execution_timestamp': execution_timestamp,
                        'organization': "日本地震再保険株式会社",
                        'category': category,
                        'title': title,
                        'link': link,
                        'summary': summary
                    }
                    news_items.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1
                except Exception as e:
                    print(f"日本地震再保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items




def fetch_ms_ins_news():
    """三井住友海上火災保険の最新情報を収集・要約します。"""
    url = "https://www.ms-ins.com/rss/news.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/msins-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"三井住友海上火災保険: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # ページのテキストを抽出
                content = soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"三井住友海上火災保険: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            pub_date = entry.updated if 'updated' in entry else entry.published if 'published' in entry else ''

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "三井住友海上火災保険株式会社",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"三井住友海上火災保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_rakuten_news():
    """楽天損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.rakuten-sonpo.co.jp/news/tabid/85/Default.aspx"
    json_file = f"./data/rakuten_sonpo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"楽天損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースのリストを取得
    announcements = soup.find_all('div', class_='ViewAnnouncements')  # 変更点
    for announcement in announcements:
        news_list = announcement.find_all('dl')
        for dl in news_list:
            dt = dl.find('dt')
            dd1 = dl.find('dd', class_='dd1')  # カテゴリ等の情報
            dd2 = dl.find('dd', class_='dd2')

            if not (dt and dd2):
                continue

            pub_date = dt.get_text(strip=True)
            link_tag = dd2.find('a')
            if not link_tag:
                continue

            link = link_tag.get('href')
            if not link.startswith("http"):
                link = "https://www.rakuten-sonpo.co.jp" + link

            title = link_tag.get_text(separator=' ', strip=True)
            # 結合されたテキストから概要部分を抽出
            summary_tag = link_tag.find('span')
            summary = summary_tag.get_text(strip=True) if summary_tag else ""

            # 既存のデータに存在するか確認
            if any(item['title'] == title for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"楽天損保: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.raise_for_status()
                    response.encoding = 'UTF-8'
                    page_soup = BeautifulSoup(response.text, 'html.parser')

                    # ニュース記事本文の抽出方法を調整
                    # 以下は一般的な例であり、実際のサイトの構造に応じて調整が必要です
                    content_div = page_soup.find('div', class_='newsDetail')  # 仮のクラス名
                    if content_div:
                        content = content_div.get_text(separator='\n', strip=True)
                    else:
                        # 見つからない場合は全体のテキストを取得
                        content = page_soup.get_text(separator='\n', strip=True)

                if not content:
                    print(f"楽天損保: コンテンツ取得失敗 - {link}")
                    continue

                summary_generated = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary_generated = summarize_text(title, content)
                    new_count += 1  # カウンターを増加

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "楽天損害保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary_generated
                }
                news_items.append(news_item)
                existing_data.append(news_item)
            except Exception as e:
                print(f"楽天損保: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_rescue_news():
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


def fetch_msadhd_news():
    """MS&ADホールディングスの新着情報を収集・要約します。"""
    url = "https://www.ms-ad-hd.com/contentFeeds/content/superMulti/ja/news/news_topics"
    feed = feedparser.parse(url)
    json_file = f"./data/msad-holdings-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"MS&ADホールディングスの新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"MS&ADホールディングスの新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "MS&ADホールディングスの新着情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"MS&ADホールディングスの新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_msadhd_ir_news():
    """MS&ADホールディングス(IR）新着情報を収集・要約します。"""
    url = "https://www.ms-ad-hd.com/contentFeeds/content/superMulti/ja/news/irnews"
    feed = feedparser.parse(url)
    json_file = f"./data/msad-holdings-ir-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"MS&ADホールディングス(IR）の新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"MS&ADホールディングス(IR）の新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "MS&ADホールディングス(IR）の新着情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"MS&ADホールディングス(IR）の新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_tokiomarine_hd_news():
    """東京海上ホールディングス新着情報を収集・要約します。"""
    url = "https://www.tokiomarinehd.com/feed/news.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/tokiomarine_hd_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"東京海上ホールディングスの新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"東京海上ホールディングスの新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "東京海上ホールディングスの新着情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"東京海上ホールディングスの新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_sompo_hd_news():
    """SOMPOホールディングス新着情報を収集・要約します。"""
    url = "https://www.sompo-hd.com/news/topics/?rss=1"
    feed = feedparser.parse(url)
    json_file = f"./data/sompo_hd_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"SOMPOホールディングスの新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"SOMPOホールディングスの新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "SOMPOホールディングスの新着情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"SOMPOホールディングスの新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_sompo_hd_update_news():
    """SOMPOホールディングス更新情報を収集・要約します。"""
    url = "https://www.sompo-hd.com/news/update/?rss=1"
    feed = feedparser.parse(url)
    json_file = f"./data/sompo_hd_update_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"SOMPOホールディングスの更新情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"SOMPOホールディングスの更新情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "SOMPOホールディングスの更新情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"SOMPOホールディングスの更新情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_zenrosai_news():
    """国民共済COOP（全労済）の新着情報を収集・要約します。"""
    url = "https://www.zenrosai.coop/rss/head.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/zenrosai_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国民共済COOP（全労済）の新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"国民共済COOP（全労済）の新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "国民共済COOP（全労済）",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国民共済COOP（全労済）の新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_zenrosai_tokyo_news():
    """国民共済COOP（全労済）東京支部の新着情報を収集・要約します。"""
    url = "https://www.zenrosai.coop/rss/tokyo.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/zenrosai_tokyo_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国民共済COOP（全労済）東京支部の新着情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"国民共済COOP（全労済）東京支部の新着情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "国民共済COOP（全労済）東京支部",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国民共済COOP（全労済）東京支部の新着情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_bousai_naikaku_news():
    """防災情報（内閣府）の新着ニュースを収集・要約します。"""
    url = "https://www.bousai.go.jp/news.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/bousai_naikaku_news.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"防災情報（内閣府）: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"防災情報（内閣府）: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "防災情報（内閣府）",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"防災情報（内閣府）: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
  
def fetch_toa_news():
    """トーア再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.toare.co.jp/newsrelease"
    json_file = "./data/toa_news.json"
    
    # 既存データのロード
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定
    options = Options()

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"トーア再保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    news_cont = soup.find('div', class_='news_cont')
    if not news_cont:
        print("トーア再保険株式会社: ニュースリリースのコンテナが見つかりませんでした。")
        return []

    news_list = news_cont.find('ul')
    if not news_list:
        print("トーア再保険株式会社: ニュースリリースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue
        
        if link.startswith("/"):
            link = "https://www.toare.co.jp" + link

        date_tag = a_tag.find('span', class_='date')
        label_tag = a_tag.find('span', class_='label')
        p_tag = a_tag.find('p')

        pub_date = date_tag.get_text(strip=True) if date_tag else ""
        label = label_tag.get_text(strip=True) if label_tag else ""
        title_text = p_tag.get_text(strip=True) if p_tag else ""
        title_text = title_text.replace("NEW!", "").strip()

        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"トーア再保険株式会社: 記事取得開始 - {title_text}")
        try:
            # ▼ verify=False でSSL検証回避（暫定措置）
            if is_pdf_link(link) or '/jp-news/download/' in link:
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"トーア再保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル
                'organization': "トーア再保険株式会社",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"トーア再保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_kyoeikasai_news():
    """共栄火災の最新情報を収集・要約します。"""
    url = "https://www.kyoeikasai.co.jp/info/"
    json_file = "./data/kyoeikasai.json"

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"共栄火災: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    news_cont = soup.find('div', class_='box-news')
    if not news_cont:
        print("共栄火災: ニュースコンテナ(box-news)が見つかりませんでした。")
        return []

    news_list = news_cont.find('ul', class_='news-list')
    if not news_list:
        print("共栄火災: ニュースリスト(news-list)が見つかりませんでした。")
        return []

    for li in news_list.find_all('li', class_='news-list-item'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue
        
        if link.startswith("/"):
            link = "https://www.kyoeikasai.co.jp" + link

        # 日付とカテゴリ
        date_container = a_tag.find('span', class_='news-date')
        pub_date = ""
        label = ""
        if date_container:
            inner_spans = date_container.find_all('span', recursive=False)
            if len(inner_spans) > 0:
                pub_date = inner_spans[0].get_text(strip=True)
            if len(inner_spans) > 1:
                label = inner_spans[1].get_text(strip=True)

        # タイトル
        title_container = a_tag.find('span', class_='news-title')
        title_text = title_container.get_text(strip=True) if title_container else ""

        # 既存データチェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"共栄火災: 記事取得開始 - {title_text}")

        # -------------------------
        # コンテンツ取得と要約
        # -------------------------
        content = None
        try:
            if is_pdf_link(link):
                # PDFの場合
                content = extract_text_from_pdf(link)  # ここも内部で verify=certifi.where() 等している想定
            else:
                # HTMLページの場合
                response = requests.get(link, verify=certifi.where())
                response.encoding = 'utf-8'
                content = response.text
        except SSLError as ssl_err:
            # ここでSSLエラーを捕まえて警告表示 → contentはNoneのまま
            print(f"共栄火災: セキュリティエラー(SSL証明書エラー)でコンテンツ取得失敗 - {link} / {ssl_err}")
            content = None
        except Exception as e:
            # その他の例外も同様にコンテンツは取得失敗
            print(f"共栄火災: コンテンツ取得中にエラー発生 - {e}")
            content = None

        # -------------------------
        # セキュリティエラー or 何らかの理由で content がない場合でも
        # ニュース項目は登録し、要約文は空にする
        # -------------------------
        if not content:
            # content取得が失敗した場合
            print(f"共栄火災: コンテンツを読み込めなかったため、要約は空のままにします。")
            summary = ""
        else:
            # 通常どおりサマライズ
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

        # -------------------------
        # ニュース項目を作成・保存
        # -------------------------
        news_item = {
            'pubDate': pub_date,
            'execution_timestamp': execution_timestamp,
            'organization': "共栄火災",
            'label': label,
            'title': title_text,
            'link': link,
            'summary': summary
        }
        news_items.append(news_item)
        existing_data.append(news_item)
        new_count += 1

    save_json(existing_data, json_file)
    return news_items

def fetch_kyoeikasai_news_release():
    """共栄火災のニュースリリースを収集・要約します。"""
    url = "https://www.kyoeikasai.co.jp/about/news/"
    json_file = "./data/kyoei_news_release.json"

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"共栄火災ニュースリリース: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # メインコンテナ
    news_list = soup.find('ul', class_='news-list')
    if not news_list:
        print("共栄火災ニュースリリース: ニュースリスト(news-list)が見つかりませんでした。")
        return []

    # ニュース一覧を順に解析
    for li in news_list.find_all('li', class_='news-list-item'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue

        if link.startswith("/"):
            link = "https://www.kyoeikasai.co.jp" + link

        # 日付が直接入っている想定
        date_container = a_tag.find('span', class_='news-date')
        pub_date = date_container.get_text(strip=True) if date_container else ""

        # カテゴリ（ラベル）は無いようなので空のまま
        label = ""

        # タイトル
        title_container = a_tag.find('span', class_='news-title')
        title_text = title_container.get_text(strip=True) if title_container else ""

        # 既存データとタイトルで重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"共栄火災ニュースリリース: 記事取得開始 - {title_text}")

        # コンテンツ取得と要約
        content = None
        try:
            if is_pdf_link(link):
                # PDFの場合
                content = extract_text_from_pdf(link)
            else:
                # HTMLページの場合
                response = requests.get(link, verify=certifi.where())
                response.encoding = 'utf-8'
                content = response.text
        except SSLError as ssl_err:
            print(f"共栄火災ニュースリリース: セキュリティエラー(SSL証明書エラー)でコンテンツ取得失敗 - {link} / {ssl_err}")
            content = None
        except Exception as e:
            print(f"共栄火災ニュースリリース: コンテンツ取得中にエラー発生 - {e}")
            content = None

        # コンテンツを取得できない場合は要約を空に
        if not content:
            print("要約文は空のままにします。")
            summary = ""
        else:
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

        # ニュース項目を作成
        news_item = {
            'pubDate': pub_date,
            'execution_timestamp': execution_timestamp,
            'organization': "共栄火災",
            'label': label,
            'title': title_text,
            'link': link,
            'summary': summary
        }

        news_items.append(news_item)
        existing_data.append(news_item)
        new_count += 1

    # 取得したデータをJSONに保存
    save_json(existing_data, json_file)
    return news_items


def fetch_ms_news():
    """三井住友海上のニュースを収集・要約します。"""
    url = "https://www.ms-ins.com/information/2024/"
    json_file = "./data/msins_news.json"

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"三井住友海上ニュース: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # 変更ポイント：クラス名を _link_release-01 に
    news_list = soup.find('ul', class_='_link_release-01')
    if not news_list:
        print("三井住友海上ニュース: ニュースリスト(_link_release-01)が見つかりませんでした。")
        return []

    # li 要素ごとに解析
    for li in news_list.find_all('li'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue

        # 相対パスの場合、フルURLに補完
        if link.startswith("/"):
            link = "https://www.ms-ins.com" + link

        # 日付を取得（<span class="date">）
        date_container = li.find('span', class_='date')
        pub_date = date_container.get_text(strip=True) if date_container else ""

        # カテゴリ（<span class="ctg-inner …>）
        category_container = li.find('span', class_='ctg-inner')
        label = category_container.get_text(strip=True) if category_container else ""

        # タイトル（<b>内。ただし疑似要素なら空かもしれない）
        b_tag = a_tag.find('b')
        if b_tag:
            title_text = b_tag.get_text(strip=True)
        else:
            # bタグが取れない・またはCSS疑似要素しかない場合は a_tag のテキストから日付などを除去するなど工夫
            title_text = a_tag.get_text(strip=True)
            # もし date や category の文字が混じってしまう場合は正規表現などで除去

        # 既存データとタイトルで重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"三井住友海上ニュース: 記事取得開始 - {title_text}")

        # コンテンツ取得と要約
        content = None
        try:
            if is_pdf_link(link):
                # PDFの場合
                content = extract_text_from_pdf(link)
            else:
                # HTMLページの場合
                response = requests.get(link, verify=certifi.where())
                response.encoding = 'utf-8'
                content = response.text
        except SSLError as ssl_err:
            print(f"三井住友海上ニュース: セキュリティエラー(SSL証明書エラー) - {link} / {ssl_err}")
            content = None
        except Exception as e:
            print(f"三井住友海上ニュース: コンテンツ取得中にエラー発生 - {e}")
            content = None

        # コンテンツを取得できない場合は要約を空に
        if not content:
            print("要約文は空のままにします。")
            summary = ""
        else:
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

        news_item = {
            'pubDate': pub_date,
            'execution_timestamp': execution_timestamp,
            'organization': "三井住友海上",
            'label': label,
            'title': title_text,
            'link': link,
            'summary': summary
        }

        news_items.append(news_item)
        existing_data.append(news_item)
        new_count += 1

    # JSONに保存
    save_json(existing_data, json_file)
    return news_items


def fetch_sompo_announce():
    """損保ジャパンのお知らせを収集します。"""
    url = "https://www.sompo-japan.co.jp/announce/2025/"
    json_file = "./data/sompo_announce.json"
    
    # 既存データのロード（前提：外部で定義済み）
    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"損保ジャパン（お知らせ）: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    # <ul class="arrowlistG"> 要素を取得
    news_list = soup.find('ul', class_='arrowlistG')
    if not news_list:
        print("損保ジャパン（お知らせ）: ニュースリストが見つかりませんでした。")
        return []

    # <li> 単位でニュースを取得
    for li in news_list.find_all('li'):
        # タイトルとリンクは <a> 要素から取得
        a_tag = li.find('a')
        if not a_tag:
            continue

        title_text = a_tag.get_text(strip=True)
        link = a_tag.get('href', '').strip()
        # 相対パスであればフルパスに補完
        if link.startswith('/'):
            link = "https://www.sompo-japan.co.jp" + link

        # 既存データとの重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"損保ジャパン: 記事取得 - {title_text}")

        # ニュース項目として保存
        # 日付は空欄、ラベルは "arrowlistG"
        news_item = {
            'pubDate': "",
            'execution_timestamp': execution_timestamp,  # グローバル/外部で定義されている想定
            'organization': "損保ジャパン（お知らせ）",
            'label': "",
            'title': title_text,
            'link': link,
            'summary': ""  # 詳細要約が必要なら、別途コンテンツ取得・解析を行う
        }

        news_items.append(news_item)
        existing_data.append(news_item)

    # 取得データを JSON などで保存（外部で定義済み）
    save_json(existing_data, json_file)

    return news_items

def fetch_sompo_service_news():
    url = "https://www.sompo-japan.co.jp/servicenews/"
    json_file = "./data/sompo_service_news.json"

    existing_data = load_existing_data(json_file)  # 定義済み想定

    driver = webdriver.Chrome(options=driver_options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"取得中にエラー発生: {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []

    # ページ内の h2.title1A をすべて取得
    h2_list = soup.find_all('h2', class_='title1A')
    for h2_tag in h2_list:
        section_title = h2_tag.get_text(strip=True)

        # h2タグの「次に続く兄弟要素」である ul.arrowlistG を探す
        # find_next_sibling は、「同じ親をもつ次のタグ」を一つ返す
        next_ul = h2_tag.find_next_sibling('ul', class_='arrowlistG')
        if not next_ul:
            # h2とulの間に何か別の要素(divなど)が挟まっている場合は
            # whileループで繰り返し探す方法を使うか、別の構造把握が必要
            continue

        # 次の <ul class="arrowlistG"> の中の<li>を処理
        for li in next_ul.find_all('li'):
            a_tag = li.find('a')
            if not a_tag:
                continue

            link = a_tag.get('href', '').strip()
            if link.startswith('/'):
                link = "https://www.sompo-japan.co.jp" + link

            title_text = a_tag.get_text(strip=True)
            if not title_text:
                continue

            # 重複チェック
            if any(item['title'] == title_text for item in existing_data):
                continue

            print(f"[{section_title}] {title_text}")

            news_item = {
                'pubDate': "",
                'execution_timestamp': execution_timestamp,  # 定義済み想定
                'organization': "損保ジャパン",
                'section': section_title,
                'title': title_text,
                'link': link,
                'summary': ""
            }
            news_items.append(news_item)
            existing_data.append(news_item)

    # JSONなどに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_nisshinfire_news():
    """日新火災のニュースリリースを収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/news_release/"
    json_file = "./data/nisshinfire_news.json"

    # 既存データのロード
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"日新火災: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # ニュース一覧が掲載されているテーブルを取得
    table = soup.find('table', class_='newsinfo__idx__table')
    if not table:
        print("日新火災: ニュースリリースのテーブルが見つかりませんでした。")
        return []

    # テーブル内の行(<tr>)を順次処理
    for tr in table.find_all('tr'):
        # 日付セル
        date_th = tr.find('th', class_='newsinfo__idx__table__th')
        if not date_th:
            # 日付セルがない行はスキップ
            continue
        pub_date = date_th.get_text(strip=True)

        # ジャンルセル
        label_th = tr.find('th', class_='newsinfo__idx__table__genre')
        label = ""
        if label_th:
            span_genre = label_th.find('span', class_='newsinfo__idx__genre')
            if span_genre:
                label = span_genre.get_text(strip=True)

        # タイトルとリンク（<td class="newsinfo__idx__table__td">配下の<a>）
        td = tr.find('td', class_='newsinfo__idx__table__td')
        if not td:
            continue

        a_tag = td.find('a')
        if not a_tag:
            continue

        relative_link = a_tag.get('href', '').strip()

        # ------------------------------------------
        # urljoinを使わず、自前でパターン判定してリンク補完
        # ------------------------------------------
        if relative_link.startswith('http'):
            # すでに絶対URL（httpまたはhttps）
            link = relative_link
        elif relative_link.startswith('/'):
            # サイトルートからのパス（例: /pdf/...）
            link = "https://www.nisshinfire.co.jp" + relative_link
        else:
            # news_release/以下からの相対パス（例: pdf/news250324.pdf）
            # 必要に応じて "./pdf/...","pdf/..." などをまとめて扱う
            if relative_link.startswith('./'):
                relative_link = relative_link[2:]
            link = "https://www.nisshinfire.co.jp/news_release/" + relative_link

        title_text = a_tag.get_text(strip=True)

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"日新火災: 記事取得開始 - {title_text}")

        # コンテンツ・要約取得
        try:
            if is_pdf_link(link):  
                # PDFファイルの場合のテキスト抽出
                content = extract_text_from_pdf(link)
            else:
                # 通常Webページの場合
                response = requests.get(link, verify=False)  # 必要なら証明書をチェック
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"日新火災: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            # max_count を超えない範囲でのみ要約を実行（例: 3件まで要約など）
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル or 外部で定義
                'organization': "日新火災",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"日新火災: 要約中にエラー発生 - {e}")

    # 保存
    save_json(existing_data, json_file)
    return news_items

def fetch_nisshinfire_info():
    """日新火災の「お知らせ」を収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/info/"
    json_file = "./data/nisshinfire_info.json"

    # 既存データのロード（外部で定義されている想定）
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"日新火災（お知らせ）: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # ページ内のテーブル要素を取得
    # （実際のHTML構造に合わせてクラス名を修正してください）
    table = soup.find('table', class_='newsinfo__idx__table')
    if not table:
        print("日新火災（お知らせ）: テーブル(newsinfo__idx__table)が見つかりませんでした。")
        return []

    # テーブル内の行(<tr>)を繰り返し処理
    for tr in table.find_all('tr'):
        # 日付セル
        date_th = tr.find('th', class_='newsinfo__idx__table__th')
        if not date_th:
            # 日付セルがない行はスキップ
            continue
        pub_date = date_th.get_text(strip=True)

        # ジャンルセル
        label_th = tr.find('th', class_='newsinfo__idx__table__genre')
        label = ""
        if label_th:
            span_genre = label_th.find('span', class_='newsinfo__idx__genre')
            if span_genre:
                label = span_genre.get_text(strip=True)

        # タイトルとリンク
        td = tr.find('td', class_='newsinfo__idx__table__td')
        if not td:
            continue
        a_tag = td.find('a')
        if not a_tag:
            continue

        relative_link = a_tag.get('href', '').strip()
        # 相対パスなら補完する (urljoinを使わず自前で処理)
        if relative_link.startswith('http'):
            link = relative_link
        elif relative_link.startswith('/'):
            link = "https://www.nisshinfire.co.jp" + relative_link
        else:
            # 例: "pdf/...","./pdf/..." などの場合
            if relative_link.startswith('./'):
                relative_link = relative_link[2:]
            link = "https://www.nisshinfire.co.jp/info/" + relative_link

        title_text = a_tag.get_text(strip=True)

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"日新火災（お知らせ）: 記事取得開始 - {title_text}")

        # コンテンツおよび要約取得
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"日新火災（お知らせ）: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            # max_count を超えない範囲で要約を行う（外部で max_count 定義）
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバルまたは外部で定義
                'organization': "日新火災",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"日新火災（お知らせ）: 要約中にエラー発生 - {e}")

    # 取得データをJSONファイルなどに保存（外部で定義済み想定）
    save_json(existing_data, json_file)

    return news_items

def fetch_rakuten_sonpo_IRnews():
    """楽天損保のIRニュースリリースを収集・要約します。"""
    url = "https://www.rakuten-sonpo.co.jp/news/tabid/84/Default.aspx"
    json_file = "./data/rakuten_sonpo_irnews.json"

    # 既存データのロード（外部で定義されている想定）
    existing_data = load_existing_data(json_file)

    # Selenium のオプション設定
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"楽天損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # ニュース一覧が含まれるコンテナ <div class="noticeArea alllist"> を取得
    notice_area = soup.find('div', class_='noticeArea allList')
    if not notice_area:
        print("楽天損保: ニュースリストのコンテナが見つかりませんでした。")
        return []

    # <dl> 単位で繰り返し処理
    for dl in notice_area.find_all('dl'):
        # 日付: <dt>2025.03.24</dt>
        dt_tag = dl.find('dt')
        if not dt_tag:
            continue
        pub_date = dt_tag.get_text(strip=True)  # 例: "2025.03.24"

        # タイトル・リンク: <dd class="dd2 last"> <a href="...">ニュースタイトル</a>
        dd_tag = dl.find('dd', class_=['dd2', 'last'])
        if not dd_tag:
            continue

        a_tag = dd_tag.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href', '').strip()
        title_text = a_tag.get_text(strip=True)
        if not title_text:
            continue

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"楽天損保: 記事取得開始 - {title_text}")

        # コンテンツおよび要約取得
        try:
            # PDFリンクかどうか判定
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # HTMLページのテキスト取得
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"楽天損保: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            # new_count が max_count を超えない範囲で要約実行 (外部で max_count 定義想定)
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # 外部またはグローバルで定義
                'organization': "楽天損保",
                'label': "",   # 特にジャンルが見当たらないため空文字列
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"楽天損保: 要約中にエラー発生 - {e}")

    # JSONファイルなどに保存
    save_json(existing_data, json_file)

    return news_items

def fetch_jihoken_info():
    """ジェイアイ損保のお知らせを収集・要約します。"""
    url = "https://www.jihoken.co.jp/info/"
    json_file = "./data/jihoken_info.json"

    # 既存データのロード（外部またはグローバルで定義されている想定）
    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ジェイアイ損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # ① <ul class="news_posts"> を取得
    news_list = soup.find('ul', class_='news_posts')
    if not news_list:
        print("ジェイアイ損保: ニュースリスト(news_posts)が見つかりません。")
        return []

    # ② <li> を全て取得 (class="grid" の指定があれば使う)
    #    例: for li in news_list.find_all('li', class_='grid'):
    #    ただし class="grid" じゃない li もあるなら 'li' だけでOK
    for li in news_list.find_all('li'):
        # 日付: <div class="dt"><span>2025.03.28</span></div>
        dt_div = li.find('div', class_='dt')
        if not dt_div:
            continue
        date_span = dt_div.find('span')
        pub_date = date_span.get_text(strip=True) if date_span else ""

        # ジャンル: <div class="cat"><span>お知らせ</span></div>
        cat_div = li.find('div', class_='cat')
        label = ""
        if cat_div:
            cat_span = cat_div.find('span')
            label = cat_span.get_text(strip=True) if cat_span else ""

        # タイトル・リンク: <div class="title"><span><a href="...">…</a></span></div>
        title_div = li.find('div', class_='title')
        if not title_div:
            continue

        # aタグを探す
        a_tag = title_div.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href', '').strip()
        title_text = a_tag.get_text(strip=True)
        if not title_text:
            continue

        # 既存データと重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"ジェイアイ損保: 記事取得開始 - {title_text}")

        # ③ コンテンツ取得 & 要約
        try:
            if is_pdf_link(link):
                # PDFの場合
                content = extract_text_from_pdf(link)
            else:
                # HTML取得
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"ジェイアイ損保: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            # max_count 未満なら要約を実行（外部/グローバルで定義）
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            # ニュース項目作成
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル/外部定義
                'organization': "ジェイアイ損保",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"ジェイアイ損保: 要約中にエラー発生 - {e}")

    # ④ 保存
    save_json(existing_data, json_file)

    return news_items

def fetch_meijiyasuda_sonpo_news():
    url = "https://www.meijiyasuda-sonpo.co.jp/newsrelease/"
    base_url = "https://www.meijiyasuda-sonpo.co.jp/newsrelease/"
    json_file = "./data/meijiyasuda_sonpo_news.json"

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"明治安田損保: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    news_divs = soup.find_all('div', id=lambda x: x and x.startswith('news'))
    if not news_divs:
        print("明治安田損保: news系のdivが見つかりません。")
        return []

    for div_block in news_divs:
        # たとえば <h2>2024年度</h2> など
        h2_tag = div_block.find('h2')
        section_label = h2_tag.get_text(strip=True) if h2_tag else ""

        news_contents = div_block.find_all('div', class_='newsContent')
        for content_block in news_contents:
            day_div = content_block.find('div', class_='n_day')
            pub_date = day_div.get_text(strip=True) if day_div else ""

            n_text = content_block.find('div', class_='n_text')
            if not n_text:
                continue

            a_tag = n_text.find('a')
            if not a_tag:
                continue

            link = a_tag.get('href', '').strip()
            # 相対パス補完
            if link.startswith('http'):
                full_link = link
            elif link.startswith('./'):
                full_link = base_url + link[2:]
            else:
                full_link = base_url + link

            title_text = a_tag.get_text(strip=True)
            if not title_text:
                continue

            if any(item['title'] == title_text for item in existing_data):
                continue

            print(f"明治安田損保: 取得 - {pub_date}: {title_text}")

            # ▼ ここで要約を試し、ダメなら空文字
            summary = ""
            try:
                # PDFかどうか判定
                if is_pdf_link(full_link):
                    # PDF取得にUser-Agent, Refererを付与（403対策）
                    headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/112.0.0.0 Safari/537.36"
                        ),
                        "Referer": "https://www.meijiyasuda-sonpo.co.jp/newsrelease/"
                    }
                    pdf_resp = requests.get(full_link, headers=headers, verify=False)
                    if pdf_resp.status_code == 200:
                        content = extract_text_from_pdf(pdf_resp.content)
                    else:
                        print(f"明治安田損保: PDF取得失敗 ({pdf_resp.status_code}) - {full_link}")
                        content = ""
                else:
                    # HTMLの場合
                    resp = requests.get(full_link, verify=False)
                    resp.encoding = 'utf-8'
                    if resp.status_code == 200:
                        content = resp.text
                    else:
                        print(f"明治安田損保: リンク取得失敗 ({resp.status_code}) - {full_link}")
                        content = ""

                if content:
                    # 要約の試行
                    if new_count < max_count:  # 外部 / グローバル定義
                        summary = summarize_text(title_text, content)
                else:
                    print("明治安田損保: コンテンツが無いため要約を諦めます")

            except Exception as e:
                # PDF読み込み失敗 or 要約中エラーなど
                print(f"明治安田損保: 要約エラー - {e}")
                summary = ""  # 要約はあきらめて空欄

            # ▼ 要約できなかった場合、summaryは空文字のまま
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  
                'organization': "明治安田損保",
                'label': section_label,
                'title': title_text,
                'link': full_link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

    save_json(existing_data, json_file)
    return news_items

def fetch_meijiyasuda_sonpo_osirase():
    url = "https://www.meijiyasuda-sonpo.co.jp/news/"
    base_url = "https://www.meijiyasuda-sonpo.co.jp/news/"
    json_file = "./data/meijiyasuda_sonpo_osirase.json"

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"明治安田損保: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    news_divs = soup.find_all('div', id=lambda x: x and x.startswith('news'))
    if not news_divs:
        print("明治安田損保: news系のdivが見つかりません。")
        return []

    for div_block in news_divs:
        # たとえば <h2>2024年度</h2> など
        h2_tag = div_block.find('h2')
        section_label = h2_tag.get_text(strip=True) if h2_tag else ""

        news_contents = div_block.find_all('div', class_='newsContent')
        for content_block in news_contents:
            day_div = content_block.find('div', class_='n_day')
            pub_date = day_div.get_text(strip=True) if day_div else ""

            n_text = content_block.find('div', class_='n_text')
            if not n_text:
                continue

            a_tag = n_text.find('a')
            if not a_tag:
                continue

            link = a_tag.get('href', '').strip()
            # 相対パス補完
            if link.startswith('http'):
                full_link = link
            elif link.startswith('./'):
                full_link = base_url + link[2:]
            else:
                full_link = base_url + link

            title_text = a_tag.get_text(strip=True)
            if not title_text:
                continue

            if any(item['title'] == title_text for item in existing_data):
                continue

            print(f"明治安田損保: 取得 - {pub_date}: {title_text}")

            # ▼ ここで要約を試し、ダメなら空文字
            summary = ""
            try:
                # PDFかどうか判定
                if is_pdf_link(full_link):
                    # PDF取得にUser-Agent, Refererを付与（403対策）
                    headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/112.0.0.0 Safari/537.36"
                        ),
                        "Referer": "https://www.meijiyasuda-sonpo.co.jp/news/"
                    }
                    pdf_resp = requests.get(full_link, headers=headers, verify=False)
                    if pdf_resp.status_code == 200:
                        content = extract_text_from_pdf(pdf_resp.content)
                    else:
                        print(f"明治安田損保: PDF取得失敗 ({pdf_resp.status_code}) - {full_link}")
                        content = ""
                else:
                    # HTMLの場合
                    resp = requests.get(full_link, verify=False)
                    resp.encoding = 'utf-8'
                    if resp.status_code == 200:
                        content = resp.text
                    else:
                        print(f"明治安田損保: リンク取得失敗 ({resp.status_code}) - {full_link}")
                        content = ""

                if content:
                    # 要約の試行
                    if new_count < max_count:  # 外部 / グローバル定義
                        summary = summarize_text(title_text, content)
                else:
                    print("明治安田損保: コンテンツが無いため要約を諦めます")

            except Exception as e:
                # PDF読み込み失敗 or 要約中エラーなど
                print(f"明治安田損保: 要約エラー - {e}")
                summary = ""  # 要約はあきらめて空欄

            # ▼ 要約できなかった場合、summaryは空文字のまま
            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  
                'organization': "明治安田損保",
                'label': section_label,
                'title': title_text,
                'link': full_link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

    save_json(existing_data, json_file)
    return news_items

def fetch_mitsui_direct_news():
    """三井ダイレクト損保のニュース一覧を取得します。"""
    url = "https://news.mitsui-direct.co.jp/"
    base_url = "https://news.mitsui-direct.co.jp"

    json_file = "./data/mitsui_direct_news.json"
    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)

        # 最大10秒間、「a.md-link-list-news」がDOMに登場するまで待機
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.md-link-list-news"))
            )
        except Exception as w:
            print(f"要素が見つからないままタイムアウト: {w}")

        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"三井ダイレクト損保: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # <a class="md-link-list-news">... </a> を全て取得
    news_links = soup.find_all('a', class_='md-link-list-news')
    if not news_links:
        print("三井ダイレクト損保: md-link-list-news が見つかりませんでした。")
        # デバッグ用にHTMLを保存
        with open("debug_mitsui_direct.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        return []

    for a_tag in news_links:
        # リンク補完
        relative_link = a_tag.get('href', '').strip()
        if relative_link.startswith('http'):
            full_link = relative_link
        else:
            # "/press/20250401/index.html?id=40630" → "https://news.mitsui-direct.co.jp/press/20250401/index.html?id=40630"
            full_link = base_url + relative_link

        # ラベル <span class="md-link-list-news_label">プレスリリース</span>
        label_span = a_tag.find('span', class_='md-link-list-news_label')
        label = label_span.get_text(strip=True) if label_span else ""

        # 日付 <time class="md-link-list-news_title" datetime="2025-04-01">2025年04月01日</time>
        time_tag = a_tag.find('time', class_='md-link-list-news_title')
        pub_date = time_tag.get_text(strip=True) if time_tag else ""

        # タイトル本文 <p class="md-link-list-news_txt">ポイントが得になる…</p>
        p_tag = a_tag.find('p', class_='md-link-list-news_txt')
        title_text = p_tag.get_text(strip=True) if p_tag else ""
        if not title_text:
            continue

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"三井ダイレクト損保: 取得 - {pub_date}: {title_text}")

        try:
            # 要約を行う場合、HTMLを取得
            resp = requests.get(full_link, verify=False)
            resp.encoding = 'utf-8'
            content = resp.text if resp.status_code == 200 else ""

            summary = ""
            if new_count < max_count:  # 外部 or グローバル定義
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # 外部/グローバル定義
                'organization': "三井ダイレクト損保",
                'label': label,  # 例: "プレスリリース"
                'title': title_text,
                'link': full_link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"三井ダイレクト損保: 要約中にエラー - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_yamap_sonpo_news():
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

def fetch_sakura_sonpo_news():
    """
    さくら損保のニューストピックスを収集・要約します。
    """
    url = "https://www.sakura-ins.co.jp/topics/"
    json_file = "./data/sakura_sonpo_news.json"

    # 既存データのロード（外部やグローバルで定義されている想定）
    existing_data = load_existing_data(json_file)

    # Selenium オプション
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"さくら損保: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # <div class="news_list"> を探す
    news_list_div = soup.find('div', class_='news_list')
    if not news_list_div:
        print("さくら損保: news_list が見つかりません。")
        return []

    # その中の <ul> を取得
    ul_tag = news_list_div.find('ul')
    if not ul_tag:
        print("さくら損保: <ul> が見つかりません。")
        return []

    # 各 <li> を走査
    li_tags = ul_tag.find_all('li', recursive=False)  # 直下の<li>だけ
    if not li_tags:
        print("さくら損保: ニュース項目<li>が見つかりません。")
        return []

    for li in li_tags:
        # 日付: <p class="date">2025/03/27</p>
        date_p = li.find('p', class_='date')
        pub_date = date_p.get_text(strip=True) if date_p else ""

        # カテゴリ: <p class="cat info">お知らせ</p> など
        cat_p = li.find('p', class_='cat')
        label = cat_p.get_text(strip=True) if cat_p else ""

        # タイトル・リンク: <a href="https://...">令和7年3月23日に…</a>
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href', '').strip()
        # 絶対URL(https://...) のようなのでそのまま使用
        title_text = a_tag.get_text(strip=True)
        if not title_text:
            continue

        # 重複チェック
        if any(item['title'] == title_text for item in existing_data):
            continue

        print(f"さくら損保: 取得 - {pub_date} [{label}] {title_text}")

        # コンテンツ取得 & 要約（必要に応じてPDF判定など）
        try:
            resp = requests.get(link, verify=False)
            resp.encoding = 'utf-8'
            content = resp.text if resp.status_code == 200 else ""

            summary = ""
            if new_count < max_count:  # 外部 or グローバルで定義されている想定
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル/外部で定義
                'organization': "さくら損保",
                'label': label,
                'title': title_text,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"さくら損保: 要約中にエラー - {e}")

    # JSONなどに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_ja_news():
    """JA共済の最新ニュースを収集・要約します。"""
    url = "https://www.ja-kyosai.or.jp/news/index.html"
    json_file = "./data/ja_news.json"

    # 既存データのロード（トーアのコードと同じ外部関数）
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定（fetch_toa_news と同様）
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)

        # BeautifulSoupでページ内容を取得
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"JA共済: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # 1) 最新ニュース一覧の ul.listRelease を探す
    ul_tag = soup.find('ul', class_='listRelease')
    if not ul_tag:
        print("JA共済: ニュースリリースのリスト(ul.listRelease)が見つかりません。")
        return []

    # 2) li を順番に処理（各 li に p.date と a リンクが入っている想定）
    for li in ul_tag.find_all('li'):
        # 日付 <p class="date">2025年03月28日</p>
        date_tag = li.find('p', class_='date')
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # タイトル・リンク <p><a href="/news/2024/20250328.html">「好きがみつかる...」</a></p>
        # aタグを取得
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href', '')
        title_text = a_tag.get_text(strip=True)

        # 相対URL → 絶対URL
        if link.startswith('/'):
            link = "https://www.ja-kyosai.or.jp" + link
        elif not link.startswith('http'):
            link = "https://www.ja-kyosai.or.jp/" + link

        # 既存データとの重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"JA共済: 記事取得開始 - {title_text}")
        try:
            # PDF or HTML判定 (トーアのコード同様)
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # ▼ verify=False は一時的なSSL回避
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"JA共済: コンテンツ取得失敗 - {link}")
                continue

            # 要約
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル変数
                'organization': "JA共済",
                'label': "",
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"JA共済: 要約中にエラー発生 - {e}")

    # 最後にJSONファイルに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_ja_info():
    """JA共済の最新ニュースを収集・要約します。"""
    url = "https://www.ja-kyosai.or.jp/info/index.html"
    json_file = "./data/ja_info.json"

    # 既存データのロード
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)

        # BeautifulSoupでページ内容を取得
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"JA共済: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # 1) 最新ニュース一覧の ul.listRelease を探す
    ul_tag = soup.find('ul', class_='listRelease')
    if not ul_tag:
        print("JA共済: ニュースリリースのリスト(ul.listRelease)が見つかりません。")
        return []

    # 2) li を順番に処理（各 li に p.date と a リンクが入っている想定）
    for li in ul_tag.find_all('li'):
        # 日付 <p class="date">2025年03月28日</p>
        date_tag = li.find('p', class_='date')
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # タイトル・リンク <p><a href="/news/2024/20250328.html">「好きがみつかる...」</a></p>
        # aタグを取得
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href', '')
        title_text = a_tag.get_text(strip=True)

        # 相対URL → 絶対URL
        if link.startswith('/'):
            link = "https://www.ja-kyosai.or.jp" + link
        elif not link.startswith('http'):
            link = "https://www.ja-kyosai.or.jp/" + link

        # 既存データとの重複チェック
        if any(title_text == item['title'] for item in existing_data):
            continue

        print(f"JA共済: 記事取得開始 - {title_text}")
        try:
            # PDF or HTML判定 (トーアのコード同様)
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # ▼ verify=False は一時的なSSL回避
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"JA共済: コンテンツ取得失敗 - {link}")
                continue

            # 要約
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル変数
                'organization': "JA共済",
                'label': "",
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"JA共済: 要約中にエラー発生 - {e}")

    # 最後にJSONファイルに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_saikyosairen_news():
    """全国労働者共済生活協同組合連合会（さいきょうさいれん）の最新ニュースを収集・要約します。"""
    url = "https://www.saikyosairen.or.jp/"
    json_file = "./data/saikyosairen_news.json"

    # 既存データのロード (fetch_toa_newsと同じ外部関数)
    existing_data = load_existing_data(json_file)

    # Seleniumのオプション設定（fetch_toa_news と同じ流れ）
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"さいきょうさいれん: ページ取得中にエラー - {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    news_items = []
    new_count = 0

    # 1) div#news_load を探す
    news_load_div = soup.find("div", id="news_load")
    if not news_load_div:
        print("さいきょうさいれん: ニュースコンテナ(div#news_load)が見つかりません。")
        return []

    # 2) dl.newsstyle を繰り返し処理 (各ニュース項目)
    dl_list = news_load_div.find_all("dl", class_="newsstyle")
    if not dl_list:
        print("さいきょうさいれん: dl.newsstyle が見つかりません。")
        return []

    for dl in dl_list:
        # 日付は <dt>YYYY.MM.DD</dt>
        dt_tag = dl.find("dt")
        pub_date = dt_tag.get_text(strip=True) if dt_tag else ""

        # タイトルリンクは <dd class="bgseminar"><a href="...">タイトル</a></dd> が多い模様
        # ただし class="bgseminar" でない場合があるかもしれないので、dd → a で探す
        dd_tag = dl.find("dd")
        if not dd_tag:
            continue
        a_tag = dd_tag.find("a")
        if not a_tag:
            continue

        title_text = a_tag.get_text(strip=True)
        link = a_tag.get("href", "")

        # 相対パスなら絶対URL化
        # 例: "news/seminar/2024.html#20250305"
        if link.startswith("/"):
            link = "https://www.saikyosairen.or.jp" + link
        elif not link.startswith("http"):
            # "./" や "news/..." を "https://www.saikyosairen.or.jp/news/..." に
            link = "https://www.saikyosairen.or.jp/" + link.lstrip("./")

        # 既存データとの重複チェック
        if any(title_text == item["title"] for item in existing_data):
            continue

        print(f"さいきょうさいれん: 記事取得開始 - {title_text}")

        try:
            # PDFかどうか判定 (fetch_toa_news と同様)
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # ▼ verify=False はとりあえずSSL回避と同じ理由
                response = requests.get(link, verify=False)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"さいきょうさいれん: コンテンツ取得失敗 - {link}")
                continue

            # 要約（new_count < max_count のときのみ）
            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,  # グローバル or 定義済み
                'organization': "全国労働者共済生活協同組合連合会（さいきょうさいれん）",
                'label': "",
                'title': title_text,
                'link': link,
                'summary': summary
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"さいきょうさいれん: 要約中にエラー - {e}")

    # JSONファイルに保存
    save_json(existing_data, json_file)
    return news_items

def fetch_sonposoken_upcoming():
    """
    損害保険総合研究所（損保総研）の「近日開催講座」ページから
    最新講座情報を収集・要約して返します。
    """
    url = "https://www.sonposoken.or.jp/upcoming"
    json_file = "./data/sonposoken_upcoming.json"
    base_url = "https://www.sonposoken.or.jp"

    # 既存データのロード（ファイルが無ければ空 list）
    existing_data = load_existing_data(json_file)

    # Selenium オプション
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"損保総研: ページ取得中にエラー発生 – {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    # 「_2nd_newslist_row」が各講座 1 行
    rows = soup.find_all("div", class_="_2nd_newslist_row")
    if not rows:
        print("損保総研: 講座リストが見つかりませんでした。")
        return []

    news_items = []
    new_count = 0

    for row in rows:
        # 日付
        date_tag = row.find("div", class_="_2nd_newslist_date")
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # カテゴリー（ない場合もある）
        cat_tag = row.find("div", class_="_2nd_newslist_category")
        category = cat_tag.get_text(strip=True) if cat_tag else ""

        # タイトル & リンク
        a_tag = row.find("a", class_="_2nd_newslist_title_body")
        if not a_tag:
            continue
        title_text = a_tag.get_text(strip=True)
        link = a_tag.get("href") or ""
        if link.startswith("/"):
            link = base_url + link

        # 既読判定
        if any(title_text == item["title"] for item in existing_data):
            continue

        print(f"損保総研: 記事取得開始 – {title_text}")

        try:
            # ▼ PDF なら直接処理
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                # 一部ページで SSL エラーが出る場合があるので verify=False（必要なら適宜変更）
                res = requests.get(link, verify=False, timeout=10)
                res.encoding = res.apparent_encoding or "utf-8"
                content = res.text

            if not content:
                print(f"損保総研: コンテンツ取得失敗 – {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title_text, content)

            news_item = {
                "pubDate": pub_date,
                "execution_timestamp": execution_timestamp,
                "organization": "損害保険総合研究所",
                "label": category,
                "title": title_text,
                "link": link,
                "summary": summary,
            }

            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"損保総研: 要約中にエラー発生 – {e}")

    # 保存
    save_json(existing_data, json_file)
    return news_items

def fetch_sonposoken_news(year: int | None = None, max_count: int = 20):
    """
    損保総研サイト『新着情報 – <year>年』ページから
    ニュースリリース／刊行物／研究活動などの更新を収集・要約します。
    """
    # --- 年度と URL の決定 -------------------------------------------------
    from datetime import datetime
    from urllib.parse import urljoin

    if year is None:
        year = datetime.now().year
    # 2018 年以降は /news/<year>news で統一されている
    url = f"https://www.sonposoken.or.jp/news/{year}news"

    # 年度 TOP（/news）からナビゲーションを辿るパターンも fallback 用に用意
    def fallback_driver_get(driver, target_year: int):
        driver.get("https://www.sonposoken.or.jp/news")
        driver.implicitly_wait(10)
        # ページ下部の年度リンク（テキストが "2025年" など）をクリック
        link = driver.find_elements("link text", f"{target_year}年")
        if link:
            link[0].click()
        else:
            raise RuntimeError("年度切替リンクが見つかりませんでした")

    # --- 永続化ファイル -----------------------------------------------------
    json_file = "./data/sonposoken_news.json"
    existing_data = load_existing_data(json_file)

    # --- Selenium 設定 ------------------------------------------------------
    driver = webdriver.Chrome(options=options)          # ← 既存 options を使用

    try:
        # 直接 URL へアクセス
        driver.get(url)
        driver.implicitly_wait(10)

        # ページタイトルが「404」「Internal Server Error」等なら fallback
        if "404" in driver.title or "Error" in driver.title:
            fallback_driver_get(driver, year)

        soup = BeautifulSoup(driver.page_source, "html.parser")

    except Exception as e:
        print(f"損保総研: ページ取得エラー – {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    # --- ニュースリスト取得 --------------------------------------------------
    rows = soup.find_all("div", class_="_2nd_newslist_row")
    if not rows:
        print("損保総研: ニュース行が見つかりませんでした。")
        return []

    news_items, new_count = [], 0
    base_url = "https://www.sonposoken.or.jp"

    for row in rows:
        # 日付
        date_tag = row.find("div", class_="_2nd_newslist_date")
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # カテゴリー
        cat_body = row.find("span", class_="_2nd_newslist_category_body")
        category = cat_body.get_text(strip=True) if cat_body else ""

        # タイトル & リンク
        a_tag = row.find("a", class_="_2nd_newslist_title_body")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get("href") or ""
        if link.startswith("/"):
            link = base_url + link

        # 重複スキップ
        if any(title == item["title"] for item in existing_data):
            continue

        print(f"損保総研: 記事取得 – {title}")

        try:
            # 本文 or PDF 取得
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                res = requests.get(link, verify=False, timeout=10)
                res.encoding = res.apparent_encoding or "utf-8"
                content = res.text

            if not content:
                print(f"損保総研: コンテンツ取得失敗 – {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            item = {
                "pubDate": pub_date,
                "execution_timestamp": execution_timestamp,
                "organization": "損害保険総合研究所",
                "label": category,
                "title": title,
                "link": link,
                "summary": summary,
            }

            news_items.append(item)
            existing_data.append(item)
            new_count += 1

        except Exception as e:
            print(f"損保総研: 要約エラー – {e}")

    save_json(existing_data, json_file)
    return news_items
    return news_items

def fetch_jibai_important_notices():
    """
    自賠責 ADR トップ > 重要なお知らせ
    タイトル・日付のみ取得版（要約は行わない）
    """
    url       = "https://jibai-adr.or.jp/"
    json_file = "./data/jibai_important.json"
    base_url  = url                        # urljoin 用の基準

    existing_data = load_existing_data(json_file)

    # ---- Selenium ---------------------------------------------------------
    driver = webdriver.Chrome(options=options)          # ← 既存 options を使用

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"自賠責 ADR: ページ取得エラー – {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    # ---- 「重要なお知らせ」ブロック ---------------------------------------
    notice_box = None
    for box in soup.select("div.inner.right"):
        title_div = box.find("div", class_="title")
        if title_div and "重要なお知らせ" in title_div.get_text():
            notice_box = box
            break
    if notice_box is None:
        print("自賠責 ADR: 重要なお知らせが見つかりませんでした。")
        return []

    rows = notice_box.find_all("dl")
    if not rows:
        print("自賠責 ADR: お知らせ行が 0 件でした。")
        return []

    news_items = []
    for dl in rows:
        dt_tag, dd_tag = dl.find("dt"), dl.find("dd")
        if not (dt_tag and dd_tag):
            continue

        pub_date = dt_tag.get_text(strip=True)

        a_tag = dd_tag.find("a")
        if a_tag:
            title = a_tag.get_text(strip=True)
            link  = urljoin(base_url, a_tag.get("href") or "")
        else:
            title = dd_tag.get_text(" ", strip=True)
            link  = ""

        # 既読チェック
        if any(title == item["title"] for item in existing_data):
            continue

        # ここでは本文取得・要約を行わず、summary は空文字のまま
        item = {
            "pubDate": pub_date,
            "execution_timestamp": execution_timestamp,
            "organization": "自賠責保険・共済紛争処理機構",
            "label": "重要なお知らせ",
            "title": title,
            "link": link,
            "summary": ""
        }

        news_items.append(item)
        existing_data.append(item)

    save_json(existing_data, json_file)
    return news_items


def fetch_jibai_important_notices():
    """
    自賠責 ADR トップ > 重要なお知らせ
    タイトル・日付のみ取得版（要約は行わない）
    """
    url       = "https://jibai-adr.or.jp/"
    json_file = "./data/jibai_important.json"
    base_url  = url                        # urljoin 用の基準

    existing_data = load_existing_data(json_file)

    driver = webdriver.Chrome(options=options)          # ← 既存 options を使用

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"自賠責 ADR: ページ取得エラー – {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    notice_box = None
    for box in soup.select("div.inner.right"):
        title_div = box.find("div", class_="title")
        if title_div and "重要なお知らせ" in title_div.get_text():
            notice_box = box
            break
    if notice_box is None:
        print("自賠責 ADR: 重要なお知らせが見つかりませんでした。")
        return []

    rows = notice_box.find_all("dl")
    if not rows:
        print("自賠責 ADR: お知らせ行が 0 件でした。")
        return []

    news_items = []
    for dl in rows:
        dt_tag, dd_tag = dl.find("dt"), dl.find("dd")
        if not (dt_tag and dd_tag):
            continue

        pub_date = dt_tag.get_text(strip=True)

        a_tag = dd_tag.find("a")
        if a_tag:
            title = a_tag.get_text(strip=True)
            link  = urljoin(base_url, a_tag.get("href") or "")
        else:
            title = dd_tag.get_text(" ", strip=True)
            link  = ""

        # 既読チェック
        if any(title == item["title"] for item in existing_data):
            continue

        # ここでは本文取得・要約を行わず、summary は空文字のまま
        item = {
            "pubDate": pub_date,
            "execution_timestamp": execution_timestamp,
            "organization": "自賠責保険・共済紛争処理機構",
            "label": "重要なお知らせ",
            "title": title,
            "link": link,
            "summary": ""
        }

        news_items.append(item)
        existing_data.append(item)

    save_json(existing_data, json_file)
    return news_items


def fetch_jibai_new_updates():
    """
    自賠責 ADR トップページ <div class="new"> … に並ぶ
    “最新情報” の日付とタイトルだけを取得する。

    * 本文取得や要約は行わない
    * 既読判定はタイトル重複で実施
    """
    url       = "https://jibai-adr.or.jp/"
    json_file = "./data/jibai_new_updates.json"
    base_url  = url                        # urljoin 用

    existing = load_existing_data(json_file)

    # ------------ Selenium -----------------------------------------------
    driver = webdriver.Chrome(options=options)          # ← 既存 options を使用

    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"自賠責 ADR: ページ取得エラー – {e}")
        driver.quit()
        return []
    finally:
        driver.quit()

    new_box = soup.find("div", class_="new")
    if not new_box:
        print("自賠責 ADR: div.new が見つかりませんでした。")
        return []

    lis = new_box.find_all("li")
    if not lis:
        print("自賠責 ADR: 最新情報の <li> が 0 件でした。")
        return []

    items = []
    for li in lis:
        text_parts = li.get_text(" ", strip=True).split()
        if not text_parts:
            continue
        pub_date = text_parts[0] 

        a_tag = li.find("a")
        if a_tag:
            title = a_tag.get_text(" ", strip=True)
            link  = urljoin(base_url, a_tag.get("href") or "")
        else:
            # a タグが無い場合は li 全体の残りをタイトルとする
            title = " ".join(text_parts[1:]) if len(text_parts) > 1 else ""
            link  = ""

        # 既読チェック
        if any(title == it["title"] for it in existing):
            continue

        item = {
            "pubDate": pub_date,
            "execution_timestamp": execution_timestamp,
            "organization": "自賠責保険・共済紛争処理機構",
            "label": "最新情報",
            "title": title,
            "link": link,
            "summary": ""           # 要約は作らない
        }

        items.append(item)
        existing.append(item)

    save_json(existing, json_file)
    return items

# ---------------------------------------------------------------------------
def fetch_fnlia_topics():
    """
    外国損害保険協会（FNLIA）の TOPICS を収集し、global max_count 件まで要約する。
    """
    url       = "https://www.fnlia.gr.jp/topics"
    json_file = "./data/fnlia_topics.json"
    os.makedirs(os.path.dirname(json_file), exist_ok=True)

    existing_data        = load_existing_data(json_file)
    new_items, new_count = [], 0

    driver = webdriver.Chrome(options=options) 
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"FNLIA: ページ取得エラー - {e}")
        return []
    finally:
        driver.quit()

    topics_list = soup.find("div", id="topics-list")
    if not topics_list:
        print("FNLIA: トピックス一覧が見つかりません。")
        return []

    for post in topics_list.find_all("div", class_="a-post"):
        a_tag = post.find("a")
        if not a_tag:
            continue

        link = urljoin(url, a_tag.get("href", ""))
        pub_date = a_tag.find("div", class_="pub-date").get_text(strip=True) if a_tag.find("div", class_="pub-date") else ""
        title    = a_tag.find("div", class_="pub-title").get_text(strip=True) if a_tag.find("div", class_="pub-title") else ""

        if any(title == x["title"] for x in existing_data):
            continue

        print(f"FNLIA: 取得 - {title}")

        try:
            content = (
                extract_text_from_pdf(link)
                if is_pdf_link(link)
                else requests.get(link, timeout=10, verify=False).text
            )
        except Exception as e:
            print(f"FNLIA: コンテンツ取得失敗 - {e}")
            continue

        summary = ""
        if new_count < max_count:
            try:
                summary = summarize_text(title, content)
            except Exception as e:
                print(f"FNLIA: 要約失敗 - {e}")

        item = {
            "pubDate"            : pub_date,
            "execution_timestamp": execution_timestamp,
            "organization"       : "一般社団法人 外国損害保険協会",
            "label"              : "TOPICS",
            "title"              : title,
            "link"               : link,
            "summary"            : summary,
        }

        new_items.append(item)
        existing_data.append(item)
        new_count += 1

    save_json(existing_data, json_file)
    return new_items


# ---------------------------------------------------------------------------
def fetch_jcstad_topics():
    """
    交通事故紛争処理センター（JCSTAD）のお知らせを収集し、global max_count 件まで要約する。
    """
    url       = "https://www.jcstad.or.jp/info/"
    json_file = "./data/jcstad_topics.json"
    os.makedirs(os.path.dirname(json_file), exist_ok=True)

    existing_data        = load_existing_data(json_file)
    new_items, new_count = [], 0

    driver = webdriver.Chrome(options=options) 
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"JCSTAD: ページ取得エラー - {e}")
        return []
    finally:
        driver.quit()

    h1_tag = soup.find("h1", string=lambda x: x and "お知らせ" in x)
    ul_tag = h1_tag.find_next("ul") if h1_tag else None
    if not ul_tag:
        print("JCSTAD: お知らせリストが見つかりません。")
        return []

    date_pat = re.compile(r"（(\d{4})年(\d{2})月(\d{2})日）")

    for li in ul_tag.find_all("li"):
        a_tag = li.find("a")
        if not a_tag:
            continue

        raw_text = a_tag.get_text(strip=True)
        m        = date_pat.search(raw_text)
        pub_date = f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else ""
        title    = raw_text[: m.start()].strip() if m else raw_text
        link     = urljoin(url, a_tag.get("href", ""))

        if any(title == x["title"] for x in existing_data):
            continue

        print(f"JCSTAD: 取得 - {title}")

        try:
            content = (
                extract_text_from_pdf(link)
                if is_pdf_link(link)
                else requests.get(link, timeout=10, verify=False).text
            )
        except Exception as e:
            print(f"JCSTAD: コンテンツ取得失敗 - {e}")
            continue

        summary = ""
        if new_count < max_count:
            try:
                summary = summarize_text(title, content)
            except Exception as e:
                print(f"JCSTAD: 要約失敗 - {e}")

        item = {
            "pubDate"            : pub_date,
            "execution_timestamp": execution_timestamp,
            "organization"       : "公益財団法人 交通事故紛争処理センター",
            "label"              : "お知らせ",
            "title"              : title,
            "link"               : link,
            "summary"            : summary,
        }

        new_items.append(item)
        existing_data.append(item)
        new_count += 1

    save_json(existing_data, json_file)
    return new_items

# ───────────────────────────────────────────────────────────
def fetch_nasva_top_news():
    """
    NASVA トップページの最新情報を取得し、global max_count 件まで要約を付けて返す。
    """
    url       = "https://www.nasva.go.jp/"
    json_file = "./data/nasva_top_news.json"
    os.makedirs(os.path.dirname(json_file), exist_ok=True)

    existing_data        = load_existing_data(json_file)
    new_items, new_count = [], 0
    processed_links      = set()

    # ─ Selenium ─────────────────────────────────────────────────────────
    driver = webdriver.Chrome(options=options) 
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, "html.parser")
    except Exception as e:
        print(f"NASVA: ページ取得エラー - {e}")
        return []
    finally:
        driver.quit()

    anchors = soup.select("div.outline.news ul.list li a")
    if not anchors:
        print("NASVA: 最新情報リンクが見つかりません。")
        return []

    date_pat = re.compile(r"^\s*(\d{4})/(\d{2})/(\d{2})\s*$")

    for a in anchors:
        link = urljoin(url, a.get("href", ""))
        if link in processed_links:
            continue
        processed_links.add(link)

        # ─ 日付とタイトル ─────────────────────────────────────────────
        span     = a.find("span")
        pub_date = span.get_text(strip=True).replace("/", ".") if span else ""
        title    = " ".join(
            s for s in a.stripped_strings
            if not date_pat.match(s) and s.upper() != "PDF"
        ).strip()

        if any(title == x["title"] for x in existing_data):
            continue

        print(f"NASVA: 取得 - {title}")

        # ─ 本文取得（PDF／HTML 判定）───────────────────────────────────
        try:
            content = (
                extract_text_from_pdf(link)
                if is_pdf_link(link)
                else requests.get(link, timeout=10, verify=False).text
            )
        except Exception as e:
            print(f"NASVA: コンテンツ取得失敗 - {e}")
            continue

        # ─ 要約（max_count 件まで）─────────────────────────────────────
        summary = ""
        if new_count < max_count:
            try:
                summary = summarize_text(title, content)
            except Exception as e:
                print(f"NASVA: 要約失敗 - {e}")

        # ─ アイテム構築 ─────────────────────────────────────────────
        item = {
            "pubDate"            : pub_date,
            "execution_timestamp": execution_timestamp,
            "organization"       : "独立行政法人 自動車事故対策機構（NASVA）",
            "label"              : "最新情報",
            "title"              : title,
            "link"               : link,
            "summary"            : summary,
        }

        new_items.append(item)
        existing_data.append(item)
        new_count += 1

    save_json(existing_data, json_file)
    return new_items

def save_to_csv(news_list):
    """ニュースリストをCSVファイルに保存します。"""
    if not news_list:
        print("新しいニュースはありません。")
        return

    csv_file = f"./data/output/news_{execution_timestamp}.csv"

    with open(csv_file, 'w', encoding='shift-jis', errors='replace', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["execution_timestamp", "pubDate", "organization", "title", "link", "summary"])
        for item in news_list:
            writer.writerow([
                item['execution_timestamp'],
                item['pubDate'],
                item['organization'],
                item['title'],
                item['link'],
                item['summary']
            ])
    print(f"ニュースの収集と要約が完了しました。CSVファイル: {csv_file}")


def main():
    all_news = []
    all_news = all_news + fetch_aig_news()
    all_news = all_news + fetch_aioi_news()
    all_news = all_news + fetch_aioi_notice()
    all_news = all_news + fetch_americanhome_info()
    all_news = all_news + fetch_americanhome_news()
    all_news = all_news + fetch_au_news()
    all_news = all_news + fetch_axa_news()
    all_news = all_news + fetch_axa_pr()
    all_news = all_news + fetch_axa_sufferers()
    all_news = all_news + fetch_capital_sonpo_news()
    all_news = all_news + fetch_cardif_info()
    all_news = all_news + fetch_cardif_news()
    all_news = all_news + fetch_chubb_info()
    all_news = all_news + fetch_chubb_news()
    all_news = all_news + fetch_daidokasai_news()
    all_news = all_news + fetch_edesign_info()
    all_news = all_news + fetch_edesign_news()
    all_news = all_news + fetch_fnlia_topics()
    all_news = all_news + fetch_hs_news()
    all_news = all_news + fetch_ja_info()
    all_news = all_news + fetch_ja_news()
    all_news = all_news + fetch_jcstad_topics()
    all_news = all_news + fetch_jibai_important_notices()
    all_news = all_news + fetch_jibai_new_updates()
    all_news = all_news + fetch_jihoken_info()
    all_news = all_news + fetch_kyoeikasai_news()
    all_news = all_news + fetch_kyoeikasai_news_release()
    all_news = all_news + fetch_meijiyasuda_sonpo_news()
    all_news = all_news + fetch_meijiyasuda_sonpo_osirase()
    all_news = all_news + fetch_mitsui_direct_news()
    all_news = all_news + fetch_ms_ins_news()
    all_news = all_news + fetch_ms_news()
    all_news = all_news + fetch_msadhd_ir_news()
    all_news = all_news + fetch_msadhd_news()
    all_news = all_news + fetch_nasva_top_news()
    all_news = all_news + fetch_newindia_news()
    all_news = all_news + fetch_nihonjishin()
    all_news = all_news + fetch_nisshinfire_info()
    all_news = all_news + fetch_nisshinfire_news()
    all_news = all_news + fetch_rakuten_news()
    all_news = all_news + fetch_rakuten_sonpo_IRnews()
    all_news = all_news + fetch_rescue_news()
    all_news = all_news + fetch_sakura_sonpo_news()
    all_news = all_news + fetch_saikyosairen_news()
    all_news = all_news + fetch_sbi_news()
    all_news = all_news + fetch_sbi_press()
    all_news = all_news + fetch_secom_news()
    all_news = all_news + fetch_secom_product_news()
    all_news = all_news + fetch_sompo_announce()
    all_news = all_news + fetch_sompo_direct_important_news()
    all_news = all_news + fetch_sompo_direct_news()
    all_news = all_news + fetch_sompo_hd_news()
    all_news = all_news + fetch_sompo_hd_update_news()
    all_news = all_news + fetch_sompo_news()
    all_news = all_news + fetch_sonpohogo_news()
    all_news = all_news + fetch_sonysonpo_news()
    all_news = all_news + fetch_sonysonpo_news_release()
    all_news = all_news + fetch_sonposoken_news()
    all_news = all_news + fetch_sonposoken_upcoming()
    all_news = all_news + fetch_starr_news()
    all_news = all_news + fetch_tokiomarine_hd_news()
    all_news = all_news + fetch_tokiomarine_news()
    all_news = all_news + fetch_tokiomarine_release()
    all_news = all_news + fetch_toa_news()
    all_news = all_news + fetch_yamap_sonpo_news()
    all_news = all_news + fetch_zenkankyo_reiwa_news()
    all_news = all_news + fetch_zenrosai_news()
    all_news = all_news + fetch_zenrosai_tokyo_news()
    all_news = all_news + fetch_zurich_news()

    all_news = remove_news_with_exception_keyword(all_news)

    save_to_csv(all_news)

if __name__ == "__main__":
    main()
