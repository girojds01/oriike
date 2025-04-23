import datetime
import json
import feedparser
import os
from dotenv import load_dotenv
import csv
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from openai import AzureOpenAI
from pypdf import PdfReader
from io import BytesIO
import re

# .envから環境変数を読み込む
load_dotenv()

max_count = 20   # 取得するニュースの最大数

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
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
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

# 以下の関数は、各官公庁の新着情報を取得するための関数です。
def fetch_fsa_news():
    """金融庁の新着情報を収集・要約します。"""
    url = "https://www.fsa.go.jp/fsaNewsListAll_rss2.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/fsa-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"金融庁: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"金融庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "金融庁",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"金融庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_jma_news():
    """気象庁の新着情報を収集・要約します。"""
    url = "https://www.jma.go.jp/jma/press/kako.html?t=1&y=06"
    json_file = f"./data/jma.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"気象庁: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加
    for month_section in soup.find_all('h2')[:2]:  # 最新の2ヶ月分
        for li in month_section.find_next_siblings('li'):

            title_tag = li.find('a')
            if not title_tag:
                continue
            link = title_tag.get('href')
            if link.startswith("/jma"):
                link = "https://www.jma.go.jp" + link
            title = title_tag.get_text(strip=True)
            pub_date = li.get_text().split('　')[0]

            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"気象庁: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"気象庁: コンテンツ取得失敗 - {link}")
                    continue


                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "気象庁",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"気象庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_jishinhonbu():
    """地震本部の新着情報を収集・要約します。"""
    url = "https://www.jishin.go.jp/update/2024/"
    json_file = f"./data/jishinhonbu.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.encoding = 'UTF-8'
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"地震本部: ページ取得中にエラー発生 {e}")
        return []

    news_items = []
    new_count = 0

    # 更新履歴のリストを取得
    updates = soup.find('dl', class_='updates')
    if not updates:
        print("更新履歴のセクションが見つかりません。")
        return []

    for dt, dd in zip(updates.find_all('dt'), updates.find_all('dd')):

        pub_date = dt.get_text(strip=True)
    
        title_tag = dd.find('a')
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.jishin.go.jp" + link

        # 既存のニュースに含まれているか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"地震本部: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"地震本部: コンテンツ取得失敗 - {link}")
                continue


            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "地震本部",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"地震本部: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_mlit_disaster_info():
    """国土交通省の災害・防災情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/saigai/index.html"
    json_file = f"./data/mlit_disaster.json"
    existing_data = load_existing_data(json_file)

    try:
        response = requests.get(url)
        response.encoding = 'UTF-8'
        soup = BeautifulSoup(response.text, 'html.parser')
    except Exception as e:
        print(f"国土交通省: ページ取得中にエラー発生 {e}")
        return []

    news_items = []
    new_count = 0  # カウンターを追加

    # 災害情報のリストを取得
    disaster_section = soup.find('div', class_='SaigaiPressRelease01')
    if not disaster_section:
        print("災害情報のセクションが見つかりません。")
        return []

    for dd in disaster_section.find_all('dd'):
        text_p = dd.find('p', class_='text')
        if not text_p:
            continue
        a_tag = text_p.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.mlit.go.jp" + link

        # 日付の抽出
        # 例: "令和6年9月20日からの大雨による被害状況等について（第11報　2024年9月26日 08時00分現在）"
        try:
            pub_date_str = title.split('（')[1].split('報')[1].split('）')[0].strip()
            pub_date = datetime.datetime.strptime(pub_date_str, '%Y年%m月%d日 %H時%M分現在').strftime('%Y-%m-%d %H:%M:%S')
        except:
            pub_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 既存のニュースに含まれているか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国土交通省: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"国土交通省: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "国土交通省",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国土交通省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_cao_kotsu():
    """内閣府（交通安全対策）の新着情報を収集・要約します。"""
    url = "https://www8.cao.go.jp/koutu/news.html"
    json_file = "./data/cao_kotsu.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"内閣府_交通安全対策: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを初期化

    # 年度ごとのセクションを取得（最新年度から順に）
    for year_section in soup.find_all('h2'):
        dl = year_section.find_next_sibling('dl', class_='topicsList')
        if not dl:
            continue

        # dtとddのペアを取得
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')

        for dt, dd in zip(dts, dds):

            pub_date = dt.get_text(strip=True)
            link_tag = dd.find('a')
            if not link_tag:
                continue

            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')

            # リンクが相対パスの場合は絶対URLに変換
            if not link.startswith('http'):
                link = "https://www8.cao.go.jp/koutu/" + link.lstrip('/')

            # 既存データに存在するかチェック
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在する場合はスキップ

            print(f"内閣府_交通安全対策: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"内閣府_交通安全対策: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "内閣府(交通安全対策)",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"内閣府_交通安全対策: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_nisc_news():
    """NISCの新着情報を収集・要約します。"""
    url = "https://www.nisc.go.jp/news/list/index.html"
    json_file = "./data/nisc.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)     # 新着情報のページのhtmlが1部しか読み込めない。
        # ページ全体が読み込まれるまで待機
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"NISC: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # #newsList 内のニュース項目を取得
    news_list_div = soup.find('div', id='newsList')
    if not news_list_div:
        print("NISC: ニュースリストが見つかりませんでした。")
        return []

    # ニュース項目の仮想的な構造に基づいて解析
    # 例えば、各ニュースが <div class="news-item"> のような構造であると仮定
    # 実際の構造に合わせて調整してください
    for news_item_div in news_list_div.find_all('div', class_='flex gap-2 w-full py-1 md:flex-col border-b border-dotted border-nisc-gray'):

        title_tag = news_item_div.find('a')
        if not title_tag:
            continue  # タイトルリンクが見つからない場合はスキップ

        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.nisc.go.jp" + link  # 相対パスの場合はベースURLを追加

        # 公開日を取得（仮定）
        pub_date_tag = news_item_div.find('span', class_='pub-date')  # 実際のクラス名に合わせて調整
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else "不明"

        # 既存のデータに存在する場合はスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"NISC: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"NISC: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "NISC",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"NISC: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_mlit_jinji():
    """国土交通省（人事異動）の最新情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/about/R6jinji.html"  # 最新年度のURL
    json_file = f"./data/mlit_jinji.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"国土交通省: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 解析対象のセクションを特定
    contents_div = soup.find('div', id='contents')
    if not contents_div:
        print("国土交通省: 'contents' div が見つかりませんでした。")
        return []

    # 人事異動セクション内のリンクを取得
    for section in contents_div.find_all('div', class_='section'):
        # タイトル "人事異動　令和6年度" を探す
        title = section.find('h2', class_='title')
        if title and "人事異動" in title.get_text():
            # このセクション内のすべてのaタグを取得
            links = section.find_all('a', href=True)
            for link_tag in links:

                href = link_tag['href'].strip()
                if not href:
                    continue

                # 完全なURLを構築
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"https://www.mlit.go.jp{href}"  # 相対パスの場合

                # タイトルはリンクのテキスト
                entry_title = link_tag.get_text(strip=True)

                # 発行日を解析（リンクテキストから抽出）
                # 例: "令和６年１０月　１日付　（国土交通省第５０号）"
                pub_date_text = entry_title.split('付')[0].strip() + '付'

                if any(entry_title == item['title'] for item in existing_data):
                    continue  # 既に存在するニュースはスキップ

                print(f"国土交通省: 記事取得開始 - {entry_title}")

                try:
                    if is_pdf_link(full_url):
                        content = extract_text_from_pdf(full_url)
                    else:
                        response = requests.get(full_url)
                        response.encoding = 'UTF-8'
                        content = response.text

                    if not content:
                        print(f"国土交通省: コンテンツ取得失敗 - {full_url}")
                        continue

                    summary = ""
                    if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                        summary = summarize_text(entry_title, content)

                    news_item = {
                        'pubDate': pub_date_text,
                        'execution_timestamp': execution_timestamp,
                        'organization': "国土交通省",
                        'title': entry_title,
                        'link': full_url,
                        'summary': summary
                    }
                    news_items.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1  # カウンターを増加
                except Exception as e:
                    print(f"国土交通省: 要約中にエラー発生 - {e}")

            break  # 対象セクションを見つけたらループを終了

    save_json(existing_data, json_file)
    return news_items


def fetch_cas_kyojin():
    """内閣官房(国土強靭化)の新着情報を収集・要約します。"""
    url = "https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/topics.html"
    json_file = f"./data/cas_kyojin.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"内閣官房_国土強靭化: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    topics_div = soup.find('div', class_='topics')
    if not topics_div:
        print("内閣官房_国土強靭化: 'topics' div が見つかりません。")
        return []

    for dl in topics_div.find_all('dl'):

        dt = dl.find('dt').get_text(strip=True)
        dd = dl.find('dd')

        if dt < 'R6.1.1':  # 2024年1月1日以前の記事はスキップ
            continue

        if not dd:
            continue

        a_tag = dd.find('a')
        if not a_tag:
            continue
        link = a_tag.get('href')

        if link.startswith("//www.kantei.go.jp/"):
            link = "https:" + link
        if link.startswith("/jp/"):
            link = "https://www.cas.go.jp" + link
        if not link.startswith("http"):
            link = "https://www.cas.go.jp/jp/seisaku/kokudo_kyoujinka/" + link

        title = a_tag.get_text(strip=True)

        # 既存データと照合
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"内閣官房_国土強靭化: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"内閣官房_国土強靭化: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': dt,
                'execution_timestamp': execution_timestamp,
                'organization': "内閣官房(国土強靭化)",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"内閣官房_国土強靭化: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_nta_news():
    """国税庁の新着情報を収集・要約します。"""
    url = "https://www.nta.go.jp/information/release/index.htm"
    json_file = f"./data/nta.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"国税庁: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # 国税庁発表分セクションを探す
    nta_section = soup.find('h2', id='nta')
    if nta_section:
        # 発表分内のすべてのテーブルを取得
        tables = nta_section.find_all_next('table', class_='index_news')
        for table in tables:
            for tr in table.find_all('tr'):
                th = tr.find('th')
                td = tr.find('td')
                if not th or not td:
                    continue

                # 日付とタイトル、リンクを抽出
                date = th.get_text(strip=True)
                a_tag = td.find('a')

                year_month = tr.get('id')[3:8]

                if year_month < '24001':  # 2024年1月以前の記事はスキップ
                    continue

                if not a_tag:
                    continue
                link = a_tag.get('href')
                title = a_tag.get_text(strip=True)

                # 絶対URLに変換
                if link.startswith("/information"):
                    link = "https://www.nta.go.jp" + link
                elif link.startswith("http"):
                    pass
                else:
                    link = "https://www.nta.go.jp/information/release/" + link

                # 既存のデータと照合
                if any(title == item['title'] for item in existing_data):
                    continue  # 既に存在するニュースはスキップ

                print(f"国税庁: 記事取得開始 - {title}")
                try:
                    if is_pdf_link(link):
                        content = extract_text_from_pdf(link)
                    else:
                        response = requests.get(link)
                        response.encoding = 'utf-8'
                        content = response.text

                    if not content:
                        print(f"国税庁: コンテンツ取得失敗 - {link}")
                        continue

                    summary = ""
                    if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                        summary = summarize_text(title, content)

                    news_item = {
                        'pubDate': date,
                        'execution_timestamp': execution_timestamp,
                        'organization': "国税庁",
                        'title': title,
                        'link': link,
                        'summary': summary
                    }
                    new_news.append(news_item)
                    existing_data.append(news_item)
                    new_count += 1  # カウンターを増加
                except Exception as e:
                    print(f"国税庁: 要約中にエラー発生 - {e}")

    else:
        print("国税庁: 指定されたセクションが見つかりません。")

    save_json(existing_data, json_file)
    return new_news


def fetch_kensatsu_news():
    """検察庁の最新情報を収集・要約します。"""
    url = "https://www.kensatsu.go.jp/rireki/index.shtml"
    json_file = f"./data/kensatsu.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url) # seleniumアクセス禁止のためかページのhtmlが読み込めない。
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"検察庁: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # 検察庁のページの構造に応じてセレクタを調整してください
    # 例として、ニュースが <ul class="news-list"> 内の <li> にリストされていると仮定
    news_list = soup.find('ul', class_='news-list')
    if not news_list:
        print("検察庁: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        a_tag = li.find('a')
        if not a_tag:
            continue

        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.kensatsu.go.jp" + link

        pub_date_text = li.get_text()
        # 日付形式に合わせてパース。例: "2023年10月01日"
        pub_date = pub_date_text.split('）')[-1].strip() if '）' in pub_date_text else pub_date_text

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"検察庁: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"検察庁: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "検察庁",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"検察庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_courts_news():
    """裁判所の最新情報を収集・要約します。"""
    url = "https://www.courts.go.jp/news/index.html"
    json_file = f"./data/courts_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"裁判所: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_list_div = soup.find('div', class_='module-sub-page-parts-news-parts-1-1')
    if not news_list_div:
        print("裁判所: ニュースリストが見つかりません。")
        return []

    news_items = []
    new_count = 0  # カウンターを追加
    for li in news_list_div.find_all('li'):

        meta_div = li.find('div', class_='module-news-list-meta')
        link_div = li.find('div', class_='module-news-list-link')

        if not meta_div or not link_div:
            continue

        pub_date_span = meta_div.find('span', class_='module-news-pub-time')
        if not pub_date_span:
            continue
        pub_date = pub_date_span.get_text(strip=True)   # 令和6年10月1日の形式

        # '令和6年10月1日' のようなフォーマットを変換
        match = re.match(r'令和(\d+)年(\d+)月(\d+)日', pub_date)
        if not match:
            pub_date = '1000-01-01' # ダミーデータ
        if match:
            # 抽出した年、月、日をゼロ埋め
            year = int(match.group(1)) + 2018
            month = match.group(2).zfill(2)
            day = match.group(3).zfill(2)
            # '2024-10-01' の形式でリストに追加
            pub_date = f'{year}-{month}-{day}'

        if pub_date < '2024-10-01':  # 2024年10月1日以前の記事はスキップ
            continue

        a_tag = link_div.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link:
            continue

        # 相対URLの場合は絶対URLに変換
        if link.startswith('/'):
            link = "https://www.courts.go.jp" + link
        if link.startswith('../'):
            link = "https://www.courts.go.jp" + link[2:]

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"裁判所: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                soup_link = BeautifulSoup(response.text, 'html.parser')
                # ページから本文を抽出するロジックを適宜追加
                content = soup_link.get_text(separator='\n', strip=True)

            if not content:
                print(f"裁判所: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "裁判所",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"裁判所: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_jftc_news():
    """公正取引委員会の最新情報を収集・要約します。"""
    url = "https://www.jftc.go.jp/index.html"
    json_file = f"./data/jftc.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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
                # Seleniumドライバーを初期化
                driver = webdriver.Chrome(options=options)
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


def fetch_ppc_news():
    """個人情報保護委員会の最新情報を収集・要約します。"""
    url = "https://www.ppc.go.jp/information/"
    json_file = f"./data/ppc.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"個人情報保護委員会: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 'ul' タグで class が 'news-list' のものをすべて取得
    news_lists = soup.find_all('ul', class_='news-list')
    for news_list in news_lists:
        for li in news_list.find_all('li'):

            # 'time' タグから日付を取得
            time_tag = li.find('time', class_='news-date')
            if not time_tag:
                continue
            pub_date = time_tag['datetime']

            if pub_date < "2024-01-01":  # 2021年1月1日以降の記事のみ取得
                continue

            # 'div.news-text a' タグからタイトルとリンクを取得
            news_text_div = li.find('div', class_='news-text')
            if not news_text_div:
                continue
            link_tag = news_text_div.find('a')
            if not link_tag:
                continue
            title = link_tag.get_text(strip=True)
            link = link_tag.get('href')
            if link.startswith("/"):
                link = "https://www.ppc.go.jp" + link

            # 既存のデータに存在するかチェック
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"個人情報保護委員会: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"個人情報保護委員会: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "個人情報保護委員会",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"個人情報保護委員会: 要約中にエラー発生 - {e}")


    save_json(existing_data, json_file)
    return news_items


def fetch_env_news():
    """環境省の新着情報を収集・要約します。"""
    url = "https://www.env.go.jp/press/index.html"
    json_file = f"./data/env.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"環境省: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0   # カウンターを追加

    # 全ての報道発表ブロックを取得
    for block in soup.find_all('details', class_='p-press-release-list__block'):
        # 各ブロックの発表日を取得
        summary_block = block.find('summary', class_='p-press-release-list__head')
        date_heading = summary_block.find('span', class_='p-press-release-list__heading').get_text(strip=True)
        date_heading = date_heading.replace('発表', '')

        if date_heading < "2024年10月01日":  # 2024年10月1日以前の記事はスキップ
            continue

        # そのブロック内のニュースリストを取得
        news_list = block.find('ul', class_='p-news-link c-news-link')
        if not news_list:
            continue

        for li in news_list.find_all('li', class_='c-news-link__item'):

            title_tag = li.find('a', class_='c-news-link__link')
            if not title_tag:
                continue
            link = title_tag.get('href')
            if link.startswith("/"):
                link = "https://www.env.go.jp" + link
            title = title_tag.get_text(strip=True)

            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"環境省: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    content = response.text

                if not content:
                    print(f"環境省: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': date_heading,
                    'execution_timestamp': execution_timestamp,
                    'organization': "環境省",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"環境省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_road_to_l4_news():
    """Road-to-the-L4の新着情報を収集・要約します。"""
    url = "https://www.road-to-the-l4.go.jp/news/"
    json_file = "./data/road_to_l4.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"Road-to-the-L4: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    new_news = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('ul', class_='newsList02')
    if not news_list:
        print("Road-to-the-L4: ニュースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):

        # 日付を抽出
        date_p = li.find('p', class_='date01')
        if date_p and date_p.has_attr('datetime'):
            pub_date = date_p['datetime']
            pub_date_text = date_p.get_text(strip=True)
        else:
            pub_date = ""
            pub_date_text = ""

        # カテゴリを抽出
        cat_p = li.find('p', class_='cat01')
        category = cat_p.get_text(strip=True) if cat_p else ""

        # コンテンツを抽出
        text_p = li.find('p', class_='text01')
        if not text_p:
            continue  # テキストがない場合はスキップ

        # タイトルとリンクを抽出
        link_a = text_p.find('a')
        if link_a:
            title = link_a.get_text(strip=True)
            link = link_a.get('href')
            if link.startswith('/'):
                link = "https://www.road-to-the-l4.go.jp" + link
        else:
            # リンクがない場合はテキストの一部をタイトルとして使用
            title = text_p.get_text(strip=True)[:50]  # 最初の50文字をタイトルに
            link = url  # メインニュースページへのリンク

        # 既存データに存在するか確認
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"Road-to-the-L4: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content_text = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content_text = response.text

            if not content_text:
                print(f"Road-to-the-L4: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content_text)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "RoAD to the L4",
                'title': title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"Road-to-the-L4: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_statistics_bureau_news():
    """総務省統計局の新着情報を収集・要約します。"""
    url = "https://www.stat.go.jp/whatsnew/index.html"
    json_file = "./data/statistics_bureau.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"統計局: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得したニュースのカウンター
    current_year = datetime.datetime.now().year

    news_div = soup.find('div', id='news')
    if not news_div:
        print("統計局: 新着情報セクションが見つかりませんでした。")
        return []

    # 現在の年月を基準に年を調整（例: 12月以降に1月の日付が出現した場合）
    def get_full_pub_date(month_day_str):
        try:
            month, day = map(int, month_day_str.replace('日', '').split('月'))
            pub_date = datetime.datetime(current_year, month, day)
            # 過去の日付が未来に見える場合、前年とする
            if pub_date > datetime.datetime.now() + datetime.timedelta(days=1):
                pub_date = datetime.datetime(current_year - 1, month, day)
            return pub_date.strftime("%Y年%m月%d日")
        except ValueError:
            return f"{current_year}年{month_day_str}"

    # イテレーション用のリストを作成
    children = list(news_div.children)
    i = 0
    while i < len(children):
        child = children[i]
        if isinstance(child, str):
            stripped = child.strip()
            if stripped.endswith("日"):
                pub_date = get_full_pub_date(stripped)
                # 次の要素が<ul>であることを確認
                if i + 1 < len(children):
                    next_child = children[i + 1]
                    if next_child.name == 'ul':
                        for li in next_child.find_all('li'):

                            a_tag = li.find('a')
                            if not a_tag:
                                continue

                            link = a_tag.get('href')
                            if not link.startswith('http'):
                                link = "https://www.stat.go.jp" + link
                            title = a_tag.get_text(strip=True).replace("NEW", "").strip()

                            # 既存データに存在するか確認
                            if any(item['title'] == title for item in existing_data):
                                continue  # 既に存在するニュースはスキップ

                            print(f"統計局: 記事取得開始 - {title}")
                            try:
                                if is_pdf_link(link):
                                    content = extract_text_from_pdf(link)
                                else:
                                    response = requests.get(link)
                                    response.encoding = response.apparent_encoding
                                    content = response.text

                                if not content:
                                    print(f"統計局: コンテンツ取得失敗 - {link}")
                                    continue

                                summary = ""
                                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                                    summary = summarize_text(title, content)

                                news_item = {
                                    'pubDate': pub_date,
                                    'execution_timestamp': execution_timestamp,
                                    'organization': "総務省統計局",
                                    'title': title,
                                    'link': link,
                                    'summary': summary
                                }
                                news_items.append(news_item)
                                existing_data.append(news_item)
                                new_count += 1
                            except Exception as e:
                                print(f"統計局: 要約中にエラー発生 - {e}")
        i += 1

    save_json(existing_data, json_file)
    return news_items


def fetch_mlit_news():
    """国土交通省の新着情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/pressrelease.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/mlit-pressrelease.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国土交通省_プレスリリース: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"国土交通省_プレスリリース: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.updated,
                'execution_timestamp': execution_timestamp,
                'organization': "国土交通省_プレスリリース",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国土交通省_プレスリリース: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_mlit_kisha_news():
    """国土交通省_記者会見の新着情報を収集・要約します。"""
    url = "https://www.mlit.go.jp/index.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/mlit_kisha.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        # 既に存在するニュース(タイトルが同じかつ更新日時が同じ場合)はスキップ
        if any(entry.title + entry.updated == item['title'] + item['pubDate'] for item in existing_data):
            continue

        print(f"国土交通省_記者会見: 記事取得開始 - {entry.title}, {entry.updated}")
        try:
            # リンクがPDFの場合はPDFからテキストを抽出、そうでない場合はHTMLコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"国土交通省_記者会見: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            # 新しい記事がmax_count件に達していない場合は要約を実行
            if new_count < max_count:
                summary = summarize_text(entry.title, content)

            # ニュースアイテムを作成
            news_item = {
                'pubDate': entry.updated,
                'execution_timestamp': execution_timestamp,
                'organization': "国土交通省_記者会見",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"国土交通省_記者会見: 要約中にエラー発生 - {e}")

    # 既存データを更新してJSONファイルに保存
    save_json(existing_data, json_file)
    return new_news


def fetch_mof_news():
    """財務省の新着情報を収集・要約します。"""
    url = "https://www.mof.go.jp/news.rss"  # 財務省のRSSフィードURL
    feed = feedparser.parse(url)
    json_file = f"./data/mof-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # 新規ニュースのカウンター
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"財務省: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"財務省: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "財務省",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"財務省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_kantei_news():
    """首相官邸の最新情報を収集・要約します。"""
    url = "https://www.kantei.go.jp/index-jnews.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/kantei.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"首相官邸: 記事取得開始 - {entry.title}")
        try:
            link = entry.link
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"首相官邸: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "首相官邸",
                'title': entry.title,
                'link': link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"首相官邸: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_cao_hodo_news():
    """内閣府_報道発表の新着情報を収集・要約します。"""
    url = "https://www.cao.go.jp/rss/news.rdf"
    json_file = f"./data/cao-rss.json"
    existing_data = load_existing_data(json_file)

    feed = feedparser.parse(url)
    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        # タイトルが既に存在する場合はスキップ
        if any(entry.title == item['title'] for item in existing_data):
            continue

        print(f"内閣府_報道発表: 記事取得開始 - {entry.title}")
        try:
            # リンクがPDFの場合はテキストを抽出、そうでなければHTMLコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"内閣府_報道発表: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # max_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            # 公開日が存在しない場合はupdatedを使用
            pub_date = entry.get('published', entry.get('updated', ''))

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "内閣府_報道発表",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"内閣府_報道発表: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_npa_news():
    """警察庁の最新情報を収集・要約します。"""
    url = "https://www.npa.go.jp/newlyarrived/rss20.xml"
    json_file = f"./data/npa-rss.json"
    existing_data = load_existing_data(json_file)

    feed = feedparser.parse(url)
    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"警察庁: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"警察庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "警察庁",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"警察庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_fdma_news():
    """消防庁の最新情報を収集・要約します。"""
    url = "https://www.fdma.go.jp/index.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/fdma.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"消防庁: 記事取得開始 - {entry.title}")
        try:
            # リンクからコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            # 直接HTMLコンテンツを要約する場合
            if not is_pdf_link(entry.link):
                soup = BeautifulSoup(content, 'html.parser')
                
                # 要約対象のテキストを適切に抽出
                # 具体的なページ構造に応じて調整が必要です
                main_content = soup.find('div', {'class': 'main-content'})  # 例
                if main_content:
                    content_text = main_content.get_text(separator='\n', strip=True)
                else:
                    content_text = content  # フォールバック

            else:
                content_text = content  # PDFテキスト

            if not content_text:
                print(f"消防庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content_text)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "消防庁",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"消防庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_mhlw_news():
    """厚生労働省の新着情報を収集・要約します。"""
    url = "https://www.mhlw.go.jp/stf/news.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/mhlw-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"厚生労働省: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"厚生労働省: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.updated,
                'execution_timestamp': execution_timestamp,
                'organization': "厚生労働省",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"厚生労働省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news

def fetch_mhlw_kinkyu_news():
    """厚生労働省の緊急情報を収集・要約します。"""
    url = "https://www.mhlw.go.jp/stf/kinkyu.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/mhlw_kinkyu.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"厚生労働省_緊急情報: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # 厚生労働省のページから本文を抽出（適宜調整が必要）
                content_elements = soup.find_all(['p', 'div'], class_=lambda x: x and 'content' in x)
                if content_elements:
                    content = "\n".join([elem.get_text(strip=True) for elem in content_elements])
                else:
                    # デフォルトでページ全体のテキストを使用
                    content = soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"厚生労働省_緊急情報: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            # 公開日時の取得（存在しない場合はupdatedを使用）
            pub_date = entry.get('published', entry.get('updated', ''))

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "厚生労働省_緊急情報",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"厚生労働省_緊急情報: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_meti_news():
    """経済産業省の新着情報を収集・要約します。"""
    url = "https://www.meti.go.jp/ml_index_release_atom.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/meti.json"
    existing_data = load_existing_data(json_file)

    new_news = []

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"経済産業省: 記事取得開始 - {entry.title}")

        # リンク先のhtmlがrequests, seleniumともに取得不可。RSSにsummaryがあるのでそちらを利用

        news_item = {
            'pubDate': entry.updated,
            'execution_timestamp': execution_timestamp,
            'organization': "経済産業省",
            'title': entry.title,
            'link': entry.link,
            'summary': entry.summary
        }
        new_news.append(news_item)
        existing_data.append(news_item)

    save_json(existing_data, json_file)
    return new_news


def fetch_e_gov_news():
    """e-Govポータルの最新情報を収集・要約します。"""
    url = "https://www.e-gov.go.jp/news/news.xml"  # e-GovポータルのRSSフィードURL
    feed = feedparser.parse(url)
    json_file = f"./data/e_gov-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"e-Govポータル: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # 要約に必要な本文を抽出（具体的なHTML構造に応じて調整）
                content_div = soup.find('div', class_='article-body')  # 例: 'article-body' クラスを持つdiv
                if content_div:
                    content = content_div.get_text(separator="\n", strip=True)
                else:
                    # 特定のクラスがない場合、全テキストを取得
                    content = soup.get_text(separator="\n", strip=True)

            if not content:
                print(f"e-Govポータル: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "e-Govポータル",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"e-Govポータル: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_egov_comments():
    """e-Govパブリックコメントの新着情報を収集・要約します。"""
    url = "https://public-comment.e-gov.go.jp/rss/pcm_list.xml"
    feed = feedparser.parse(url)
    json_file = "./data/egov.json"
    existing_data = load_existing_data(json_file)

    new_comments = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するコメントはスキップ

        print(f"e-Gov: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # 必要に応じて特定の要素を抽出
                content = soup.get_text(separator='\n')

            if not content:
                print(f"e-Gov: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(entry.title, content)

            # 'updated' フィールドから日付を取得
            pub_date = entry.updated if 'updated' in entry else ''

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "e-Gov",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_comments.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"e-Gov: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_comments


def fetch_moj_news():
    """法務省の新着情報を収集・要約します。"""
    url = "https://www.moj.go.jp/news.xml"
    feed = feedparser.parse(url)
    json_file = "./data/moj-rss.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # 新しい記事のカウンター

    for entry in feed.entries:
        # 既に存在するニュースはスキップ
        if any(entry.title == item['title'] for item in existing_data):
            continue

        print(f"法務省: 記事取得開始 - {entry.title}")
        try:
            # リンクがPDFの場合はテキストを抽出、そうでなければHTMLコンテンツを取得
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"法務省: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            # 最大取得数に達していない場合に要約を実行
            if new_count < max_count:
                summary = summarize_text(entry.title, content)

            # 公開日を取得（存在しない場合は空文字を設定）
            pubDate = entry.get('updated', entry.get('published', ''))

            news_item = {
                'pubDate': pubDate,
                'execution_timestamp': execution_timestamp,
                'organization': "法務省",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"法務省: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_gsi_news():
    """国土地理院の新着情報を収集・要約します。"""
    url = "https://www.gsi.go.jp/index.rdf"
    json_file = f"./data/gsi-rss.json"
    existing_data = load_existing_data(json_file)

    feed = feedparser.parse(url)
    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"国土地理院: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # ページのテキスト部分を抽出（適宜調整が必要です）
                content = soup.get_text(separator='\n')

            if not content:
                print(f"国土地理院: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.updated,
                'execution_timestamp': execution_timestamp,
                'organization': "国土地理院",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"国土地理院: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_caa_news():
    """消費者庁の新着情報を収集・要約します。"""
    url = "https://www.caa.go.jp/news.rss"
    json_file = f"./data/caa-rss.json"
    existing_data = load_existing_data(json_file)

    feed = feedparser.parse(url)
    new_news = []
    new_count = 0  # カウンターを追加

    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"消費者庁: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"消費者庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.updated,  # または entry.published
                'execution_timestamp': execution_timestamp,
                'organization': "消費者庁",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"消費者庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


def fetch_digital_agency_news():
    """デジタル庁の新着情報を収集・要約します。"""
    url = "https://www.digital.go.jp/rss/news.xml"
    feed = feedparser.parse(url)
    json_file = f"./data/digital_agency_news.json"
    existing_data = load_existing_data(json_file)

    exception_category = ["組織情報","申請・届出","採用","調達情報"]

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        if entry.category in exception_category:
            print(f"デジタル庁: 例外カテゴリー - {entry.category}")
            continue # 記事のカテゴリーがexception_categoryに含まれる場合はスキップ

        print(f"デジタル庁: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                # ページから本文を抽出（必要に応じて調整）
                # 例えば、メインコンテンツが<main>タグ内にある場合
                main_content = soup.find('main')
                if main_content:
                    content = main_content.get_text(separator='\n', strip=True)
                else:
                    # 見つからない場合は全文テキストを使用
                    content = soup.get_text(separator='\n', strip=True)

            if not content:
                print(f"デジタル庁: コンテンツ取得失敗 - {entry.link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(entry.title, content)

            news_item = {
                'pubDate': entry.published,
                'execution_timestamp': execution_timestamp,
                'organization': "デジタル庁",
                'title': entry.title,
                'link': entry.link,
                'category': entry.category,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"デジタル庁: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return new_news


# 以下の関数は、各保険会社の新着情報を取得するための関数です。

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
        print(f"あいおいニッセイ同和損害保険: ページ取得中にエラー発生 - {e}")
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

        print(f"あいおいニッセイ同和損害保険: 記事取得開始 - {title}")

        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"あいおいニッセイ同和損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "あいおいニッセイ同和損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"あいおいニッセイ同和損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_axadirect_pr():
    """アクサダイレクトのプレスリリースを収集・要約します。"""
    url = "https://www.axa-direct.co.jp/company/official_info/pr/"
    json_file = f"./data/axa_direct_pr.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"アクサダイレクト_プレスリリース: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新のリリースリストを取得
    release_list = soup.find('div', class_='releaseList-wrapper')
    if not release_list:
        print("アクサダイレクト_プレスリリース: リリースリストが見つかりません。")
        return []

    for li in release_list.find_all('li', class_='releaseList-item'):
        a_tag = li.find('a', class_='releaseList-item-link')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if link.startswith('/'):
            link = "https://www.axa-direct.co.jp" + link
        elif link.startswith('http'):
            pass  # 完全なURL
        else:
            continue  # 不明な形式のリンクはスキップ

        title = a_tag.find('p', class_='releaseList-item-link-title').get_text(strip=True)
        date_tag = a_tag.find('p', class_='releaseList-item-link-date')
        pub_date = date_tag.get_text(strip=True) if date_tag else "不明"

        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"アクサダイレクト_プレスリリース: 記事取得開始 - {title}")
        try:
            # コンテンツの取得
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"アクサダイレクト_プレスリリース: コンテンツ取得失敗 - {link}")
                continue

            # 要約の生成
            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "アクサダイレクト_プレスリリース",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加

        except Exception as e:
            print(f"アクサダイレクト_プレスリリース: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_axa_news():
    """アクサ損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.axa-direct.co.jp/company/official_info/announce/"
    json_file = "./data/axa_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
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

def fetch_americanhome_news():
    """アメリカンホーム医療・損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www2.americanhome.co.jp/v2/news/"
    json_file = f"./data/americanhome_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"アメリカンホーム: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを含む要素を特定
    articles_list = soup.find('div', class_='articleslist')
    if not articles_list:
        print("アメリカンホーム: ニュースリストが見つかりません。")
        return []

    for dl in articles_list.find_all('dl'):
        dt = dl.find('dt')
        dd = dl.find('dd')
        if not dt or not dd:
            continue

        pub_date = dt.get_text(strip=True)
        link_tag = dd.find('a')
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        link = link_tag.get('href')
        if not link.startswith('http'):
            link = "https://www2.americanhome.co.jp" + link

        # 既に存在するニュースはスキップ
        if any(title == item['title'] for item in existing_data):
            continue

        print(f"アメリカンホーム: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"アメリカンホーム: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                # BeautifulSoupで本文を抽出（HTMLの場合）
                page_soup = BeautifulSoup(content, 'html.parser')
                # 本文のクラスやタグは実際のページに合わせて調整してください
                article_body = page_soup.find('div', class_='article-body')
                if article_body:
                    text_content = article_body.get_text(separator="\n", strip=True)
                else:
                    text_content = content  # 必要に応じて他の方法でテキストを抽出

                summary = summarize_text(title, text_content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "アメリカンホーム医療・損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"アメリカンホーム: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items



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

def fetch_edsp_news():
    """イーデザイン損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.e-design.net/company/news/2024/"
    json_file = f"./data/edsp.json"
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
                # ニュース記事の内容を取得
                # 適切なセレクタを使用して本文を抽出してください
                # 以下は仮のセレクタです。実際のHTML構造に合わせて調整してください。
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

def fetch_capital_sonpo_news():
    """キャピタル損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.capital-sonpo.co.jp/"  # 最新情報ページのURLに置き換えてください
    json_file = f"./data/capital_sonpo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページ読み込み待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"キャピタル損害保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュース項目を含むセクションを特定します。
    # 以下は仮のセレクターです。実際のHTML構造に合わせて調整してください。
    # 例: <div class="news-list"><ul><li>...</li></ul></div>
    news_section = soup.find('div', class_='news-list')  # クラス名は実際のものに置き換えてください
    if not news_section:
        print("ニュースセクションが見つかりませんでした。セレクターを確認してください。")
        return []

    for li in news_section.find_all('li'):

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://www.capital-sonpo.co.jp" + link  # 相対URLの場合の対応
        title = title_tag.get_text(strip=True)
        pub_date_tag = li.find('span', class_='date')  # 日付を含むタグのクラス名に置き換えてください
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else "不明"

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"キャピタル損害保険株式会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'  # エンコーディングを必要に応じて調整
                content_soup = BeautifulSoup(response.text, 'html.parser')
                # 記事内容を含むセクションを特定します。以下は仮のセレクターです。
                content_section = content_soup.find('div', class_='article-content')  # 実際のクラス名に置き換えてください
                if content_section:
                    content = content_section.get_text(separator="\n", strip=True)
                else:
                    content = response.text  # セクションが見つからない場合は全体を使用

            if not content:
                print(f"キャピタル損害保険株式会社: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "キャピタル損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"キャピタル損害保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_hdmf_news():
    """現代海上火災保険株式会社の最新情報を収集・要約します。"""
    url = "http://www.hdinsurance.co.jp/"
    json_file = f"./data/hdmf.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"現代海上火災保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # '最新情報'セクションを特定（例としてPDFリンクを探す）
    # 実際のHTML構造に基づいて適宜調整してください
    # ここでは osirase*.pdf のリンクを収集
    osirase_links = soup.find_all('a', href=lambda href: href and href.startswith('./osirase') and href.endswith('.pdf'))

    for link_tag in osirase_links:
        relative_link = link_tag.get('href')
        link = requests.compat.urljoin(url, relative_link)
        title = link_tag.get_text(strip=True) or link.split('/')[-1]
        
        # 公開日の推定（PDF名から取得。例: osirase40.pdf → 40回目のお知らせ）
        # 必要に応じて日付の解析を追加
        pub_date = "不明"

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"現代海上火災保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'shift_jis'
                content = response.text

            if not content:
                print(f"現代海上火災保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "現代海上火災保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"現代海上火災保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_newindia_news():
    """ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッドの最新情報を収集・要約します。"""
    url = "https://www.newindia.co.jp/topics/"  # 最新情報ページのURLを指定
    json_file = f"./data/newindia.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"ニューインディア: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 'div'にid='nProgram'を探し、その中の'dt'と'dd'を取得
    nprogram_div = soup.find('div', id='nProgram')
    if not nprogram_div:
        print("ニューインディア: 最新情報セクションが見つかりませんでした。")
        return []

    dl = nprogram_div.find('dl')
    if not dl:
        print("ニューインディア: 定義リスト（dl）が見つかりませんでした。")
        return []

    dts = dl.find_all('dt')
    dds = dl.find_all('dd')

    if len(dts) != len(dds):
        print("ニューインディア: dtとddの数が一致しません。")
        return []

    for dt, dd in zip(dts, dds):
        pub_date = dt.get_text(strip=True)
        a_tag = dd.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        # 絶対URLに変換
        if link.startswith('/'):
            link = "https://www.newindia.co.jp" + link
        elif not link.startswith('http'):
            link = "https://www.newindia.co.jp/" + link

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"ニューインディア: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'UTF-8'
                content = response.text

            if not content:
                print(f"ニューインディア: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                soup_content = BeautifulSoup(content, 'html.parser')
                # ニュース記事の本文を抽出（具体的なHTML構造に応じて調整が必要）
                # ここでは仮に<div class="article-content">を使用
                article_div = soup_content.find('div', class_='article-content')
                if article_div:
                    text_content = article_div.get_text(separator='\n', strip=True)
                else:
                    # 見つからない場合は全文を使用
                    text_content = soup_content.get_text(separator='\n', strip=True)

                summary = summarize_text(title, text_content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ザ・ニュー・インディア・アシュアランス・カンパニー・リミテッド",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"ニューインディア: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_jai_news():
    """ジェイアイ傷害火災保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.jihoken.co.jp/whats/wh_index.html"
    json_file = "./data/jai_insurance.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"JAI傷害火災保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 最新情報のコンテナを特定
    whats_box = soup.find('div', id='whatsBox2')
    if not whats_box:
        print("JAI傷害火災保険: 最新情報コンテナが見つかりませんでした。")
        return []

    # ニュース記事を抽出（仮定: 各ニュースは<li>タグ内にある）
    for li in whats_box.find_all('li'):
        if new_count >= max_count:
            break

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        # 絶対URLに変換
        if not link.startswith('http'):
            link = "https://www.jihoken.co.jp" + link
        title = title_tag.get_text(strip=True)
        pub_date = li.get_text().split('　')[0].strip()  # 仮に日付がタイトルの前にある場合

        # 既存データに存在するかチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"JAI傷害火災保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"JAI傷害火災保険: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "ジェイアイ傷害火災保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"JAI傷害火災保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_starr_news():
    """スター・インデムニティ・アンド・ライアビリティ・カンパニーの最新情報を収集・要約します。"""
    url = "https://www.starrcompanies.jp/News"
    json_file = "./data/starr_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"スター保険会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # 「大切なお知らせ」セクションを特定
    header = soup.find('h1', text="大切なお知らせ")
    if not header:
        print("スター保険会社: 「大切なお知らせ」セクションが見つかりませんでした。")
        return []

    # ヘッダーの次の兄弟要素として<p>タグを取得
    for p in header.find_next_siblings('p'):
        a_tag = p.find('a')
        if not a_tag:
            continue
        link = a_tag.get('href')
        if not link:
            continue
        # 絶対URLに変換
        if not link.startswith("http"):
            link = "https://www.starrcompanies.jp" + link
        title = a_tag.get_text(strip=True)
        pub_date = datetime.datetime.now().strftime("%Y-%m-%d")  # 公開日が明示されていないため、現在の日付を使用

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"スター保険会社: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # 主要なコンテンツを抽出（例として本文を選択）
                # 適宜、正しいセレクタに調整してください
                content_div = page_soup.find('div', class_='text-content__content')
                content = content_div.get_text(separator='\n', strip=True) if content_div else response.text

            if not content:
                print(f"スター保険会社: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "スター・インデムニティ・アンド・ライアビリティ・カンパニー",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"スター保険会社: 要約中にエラー発生 - {e}")

        if new_count >= max_count:
            break  # max_countに達したらループを終了

    save_json(existing_data, json_file)
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
                    'pubDate': f"{year}年 {pub_date}",
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
    url = "https://from.sonysonpo.co.jp/topics/news/2024/"
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
    """損害保険契約者保護機構の最新情報を収集・要約します。"""
    url = "http://www.sonpohogo.or.jp/"  # 最新情報ページのURLを設定
    json_file = "./data/sonpohogo.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページの読み込みを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"損保機構: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 新規ニュースのカウンターを追加

    # "ºÇ¿·¾ðÊó" セクションを探す（最新情報）
    whatnew_div = soup.find('div', class_='whatnew')
    if not whatnew_div:
        print("損保機構: 'whatnew' セクションが見つかりませんでした。")
        return []

    top_cont_table = whatnew_div.find('table', class_='top_cont')
    if not top_cont_table:
        print("損保機構: 'top_cont' テーブルが見つかりませんでした。")
        return []

    # 各ニュース項目を処理
    for tr in top_cont_table.find_all('tr'):
        tds = tr.find_all('td')
        if len(tds) != 2:
            continue  # 予期しない構造の場合はスキップ

        # 日付を取得
        pub_date = tds[0].get_text(strip=True)

        # タイトルとリンクを取得
        news_td = tds[1]
        title_tag = news_td.find('a')
        if title_tag:
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href')
            if not link.startswith('http'):
                link = "http://www.sonpohogo.or.jp" + link  # 相対リンクの場合の対応
        else:
            title = news_td.get_text(strip=True)
            link = ""

        # 既存のデータに存在するかチェック
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"損保機構: 記事取得開始 - {title}")
        try:
            content = ""
            summary = ""
            if link:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'EUC-JP'  # ソースがEUC-JPエンコーディングのため
                    content = response.text

                if not content:
                    print(f"損保機構: コンテンツ取得失敗 - {link}")
                    continue

                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)
                    new_count += 1  # カウンターを増加

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "損害保険契約者保護機構",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)

        except Exception as e:
            print(f"損保機構: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

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
                'category': category,
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

def fetch_chubb_news():
    """Chubb損害保険株式会社のお知らせページから最新情報を収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-info.html"
    json_file = f"./data/chubb_news.json"
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

def fetch_chubb_news_release():
    """Chubb損害保険株式会社のニュースリリースを収集・要約します。"""
    url = "https://www.chubb.com/jp-jp/news/news-release.html"
    json_file = "./data/chubb_news_release.json"
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

def fetch_tokyo_kaijo_news():
    """東京海上日動火災保険株式会社のお知らせを収集・要約します。"""
    url = "https://www.tokiomarine-nichido.co.jp/company/news/"
    json_file = f"./data/tokyo_kaijo_news.json"
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

def fetch_tokiomarine_news():
    """東京海上日動火災保険のニュースリリースを収集・要約します。"""
    url = "https://www.tokiomarine-nichido.co.jp/company/release/"
    json_file = "./data/tokiomarine_news_release.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページが完全に読み込まれるまで待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"東京海上日動_news_release: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # ニュースリリースリストを取得
    news_list = soup.find('dl', class_='list-detail-07')
    if not news_list:
        print("東京海上日動_news_release: ニュースリリースリストが見つかりません。")
        return []

    for news_div in news_list.find_all('div', class_='list-detail-07__list'):
        # 日付とカテゴリを取得
        dt_term = news_div.find('dt', class_='list-detail-07__term')
        if not dt_term:
            continue
        pub_date_tag = dt_term.find('span', class_='list-detail-07__date')
        category_tag = dt_term.find('span', class_='icon-txt')
        if not pub_date_tag or not category_tag:
            continue
        pub_date = pub_date_tag.get_text(strip=True)
        category = category_tag.get_text(strip=True)

        # タイトルとリンクを取得
        dd_desc = news_div.find('dd', class_='list-detail-07__desc')
        if not dd_desc:
            continue
        a_tag = dd_desc.find('a')
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get('href')
        if not link:
            continue
        # 相対URLを絶対URLに変換
        if link.startswith("/"):
            link = "https://www.tokiomarine-nichido.co.jp" + link

        # 既存データに同じタイトルが存在する場合はスキップ
        if any(item['title'] == title for item in existing_data):
            continue

        print(f"東京海上日動_news_release: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = response.apparent_encoding
                content = response.text

            if not content:
                print(f"東京海上日動_news_release: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "東京海上日動火災保険株式会社_news_release",
                'category': category,
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"東京海上日動_news_release: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items


def fetch_toa_news():
    """トーア再保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.toare.co.jp/newsrelease"
    json_file = f"./data/toa_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"トーア再保険株式会社: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストを取得
    news_list = soup.find('div', class_='news_cont').find('ul')
    if not news_list:
        print("ニュースリリースリストが見つかりませんでした。")
        return []

    for li in news_list.find_all('li'):
        a_tag = li.find('a')
        if not a_tag:
            continue

        link = a_tag.get('href')
        if not link:
            continue
        # 絶対URLに変換
        if link.startswith("/"):
            link = "https://www.toare.co.jp" + link

        date_tag = a_tag.find('span', class_='date')
        label_tag = a_tag.find('span', class_='label')
        p_tag = a_tag.find('p')

        pub_date = date_tag.get_text(strip=True) if date_tag else ""
        label = label_tag.get_text(strip=True) if label_tag else ""
        title = p_tag.get_text(strip=True) if p_tag else ""

        # チェック用タイトル（重複確認）
        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"トーア再保険株式会社: 記事取得開始 - {title}")
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

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "トーア再保険株式会社",
                'label': label,
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加


        except Exception as e:
            print(f"トーア再保険株式会社: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_nisshinfire_news():
    """日新火災海上保険株式会社(お知らせ)の新着情報を収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/info/"
    json_file = f"./data/nisshinfire.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"日新火災: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新しい記事の数
    try:
        # 最新のニューステーブルを取得
        table = soup.find('table', class_='newsinfo__idx__table')
        if not table:
            print("日新火災: ニューステーブルが見つかりません。")
            return []

        for tr in table.find_all('tr'):
            th = tr.find('th', class_='newsinfo__idx__table__th')
            td = tr.find('td', class_='newsinfo__idx__table__td')
            if not th or not td:
                continue

            pub_date = th.get_text(strip=True)
            a_tag = td.find('a', class_='_link')
            if not a_tag:
                continue

            link = a_tag.get('href')
            if not link.startswith('http'):
                link = "https://www.nisshinfire.co.jp" + link
            title = a_tag.get_text(strip=True).split('(')[0].strip()

            # 既存データに存在するか確認
            if any(title == item['title'] for item in existing_data):
                continue  # 既に存在するニュースはスキップ

            print(f"日新火災: 記事取得開始 - {title}")
            try:
                if is_pdf_link(link):
                    content = extract_text_from_pdf(link)
                else:
                    response = requests.get(link)
                    response.encoding = 'UTF-8'
                    soup_detail = BeautifulSoup(response.text, 'html.parser')
                    # 記事の本文を取得（サイト構造に合わせて調整が必要）
                    content = soup_detail.get_text(separator='\n', strip=True)

                if not content:
                    print(f"日新火災: コンテンツ取得失敗 - {link}")
                    continue

                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "日新火災海上保険株式会社",
                    'title': title,
                    'link': link,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加


            except Exception as e:
                print(f"日新火災: 要約中にエラー発生 - {e}")

    except Exception as e:
        print(f"日新火災: ニュース解析中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_nisshin_news():
    """日新火災海上保険株式会社のニュースリリースから最新情報を収集・要約します。"""
    url = "https://www.nisshinfire.co.jp/news_release/"  # ニュースリリースページのURL
    json_file = f"./data/nisshin_fire_news_release.json"  # 保存するJSONファイルのパス
    existing_data = load_existing_data(json_file)  # 既存のデータをロード

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
    except Exception as e:
        print(f"日新火災海上保険_news_release: ページ取得中にエラー発生 - {e}")
        return []

    news_items = []
    new_count = 0  # 取得した新規ニュースのカウンター

    # ニュースはテーブル内の<tr>要素に格納されていると仮定
    table = soup.find('table', class_='newsinfo__idx__table')  # クラス名は実際のHTMLに合わせて調整
    if not table:
        print("日新火災海上保険_news_release: ニューステーブルが見つかりませんでした。")
        return []

    for tr in table.find_all('tr'):
        try:
            ths = tr.find_all('th')
            tds = tr.find_all('td')
            if len(ths) < 2 or len(tds) < 1:
                continue  # 必要なデータが揃っていない場合はスキップ

            pub_date = ths[0].get_text(strip=True)  # 例: '2024年10月8日'
            genre = ths[1].get_text(strip=True)     # 例: 'その他'

            a_tag = tds[0].find('a')
            if not a_tag:
                continue  # リンクが存在しない場合はスキップ

            link = a_tag.get('href')
            if not link.startswith('http'):
                link = "https://www.nisshinfire.co.jp" + link  # 相対URLの場合はベースURLを追加

            title = a_tag.get_text(strip=True)
            size_text = tds[0].get_text(strip=True).split('(')[-1].rstrip(')') if '(' in tds[0].get_text() else ""

            # 既に存在するニュースか確認
            if any(title == item['title'] for item in existing_data):
                continue  # 既存のニュースはスキップ

            print(f"日新火災海上保険_news_release: 記事取得開始 - {title}")

            # コンテンツの取得
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                try:
                    page_response = requests.get(link)
                    page_response.raise_for_status()
                    page_soup = BeautifulSoup(page_response.content, 'html.parser')
                    # ニュース内容の抽出方法は実際のページ構造に合わせて調整
                    # ここでは仮に<p>タグのテキストを結合しています
                    paragraphs = page_soup.find_all('p')
                    content = '\n'.join(p.get_text() for p in paragraphs)
                except Exception as e:
                    print(f"日新火災海上保険_news_release: コンテンツ取得中にエラー発生 - {e}")
                    continue

            if not content:
                print(f"日新火災海上保険_news_release: コンテンツが空です - {link}")
                continue

            # ニュースの要約
            if new_count < max_count:
                summary = summarize_text(title, content)
            else:
                summary = ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'genre': genre,
                'organization': "日新火災海上保険株式会社_news_release",
                'title': title,
                'link': link,
                'size': size_text,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1

        except Exception as e:
            print(f"日新火災海上保険_news_release: ニュース処理中にエラー発生 - {e}")
            continue

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

def fetch_mitsui_direct_news():
    """三井ダイレクト損保の最新情報を収集・要約します。"""
    url = "https://news.mitsui-direct.co.jp/index.html?category=4000"
    json_file = f"./data/mitsui_direct_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)  # ページのロードを待機
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"三井ダイレクト損保: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストのセクションを特定（仮定）
    # 実際のサイトのHTML構造に合わせて変更してください
    # 例えば、ニュースが<div class="news-list">内にある場合
    news_list_section = soup.find('div', class_='news-list')  # クラス名は実際に合わせてください
    if not news_list_section:
        print("ニュースリストのセクションが見つかりませんでした。")
        return []

    for article in news_list_section.find_all('article'):  # タグやクラス名は実際に合わせてください

        title_tag = article.find('h2')  # タイトルのタグを実際に合わせてください
        link_tag = article.find('a', href=True)
        date_tag = article.find('time')  # 日付のタグを実際に合わせてください

        if not title_tag or not link_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = link_tag['href']
        if not link.startswith('http'):
            link = "https://news.mitsui-direct.co.jp" + link
        pub_date = date_tag.get_text(strip=True)

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"三井ダイレクト損保: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"三井ダイレクト損保: コンテンツ取得失敗 - {link}")
                continue

            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ
                summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "三井ダイレクト損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"三井ダイレクト損保: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_meijiyasuda_sonpo():
    """明治安田損害保険株式会社の最新情報を収集・要約します。"""
    url = "https://www.meijiyasuda-sonpo.co.jp/newsrelease/"
    json_file = "./data/meijiyasuda_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"明治安田損害保険: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # カウンターを追加

    # ニュースリストのセクションを特定（例として <ul> 内の <li> を想定）
    news_list = soup.find('div', id='mainContents').find_all('li')
    for li in news_list:

        title_tag = li.find('a')
        if not title_tag:
            continue
        link = title_tag.get('href')
        if not link.startswith("http"):
            link = "https://www.meijiyasuda-sonpo.co.jp" + link
        title = title_tag.get_text(strip=True)
        
        # 公開日の取得（例として <span> タグ内にあると仮定）
        pub_date_tag = li.find('span', class_='date')
        pub_date = pub_date_tag.get_text(strip=True) if pub_date_tag else ""

        if any(title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"明治安田損害保険: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.raise_for_status()
                response.encoding = 'utf-8'
                content = response.text

            if not content:
                print(f"明治安田損害保険: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content) if new_count < max_count else ""

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "明治安田損害保険株式会社",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"明治安田損害保険: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

def fetch_yamap_news():
    """株式会社ヤマップネイチャランス損害保険の最新情報を収集・要約します。"""
    url = "https://yamap-naturance.co.jp/news"
    json_file = "./data/yamap_naturance_news.json"
    existing_data = load_existing_data(json_file)

    # Seleniumドライバーを初期化
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        driver.implicitly_wait(10)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
    except Exception as e:
        print(f"YAMAP NATURANCE: ページ取得中にエラー発生 - {e}")
        driver.quit()
        return []
    driver.quit()

    news_items = []
    new_count = 0  # 取得した新しいニュースのカウンター

    # ニュース一覧のHTML構造に基づいて調整してください。
    # 一般的に、ニュースは <div class="news-item"> のようなクラスで囲まれていることが多いです。
    # 以下は仮の例です。実際のHTML構造に合わせてセレクタを変更してください。
    for news_div in soup.find_all('div', class_='news-item'):

        title_tag = news_div.find('a')
        if not title_tag:
            continue
        title = title_tag.get_text(strip=True)
        link = title_tag.get('href')
        if not link.startswith('http'):
            link = "https://yamap-naturance.co.jp" + link

        # 公開日があれば取得（例: <span class="date">2023-10-01</span>）
        date_tag = news_div.find('span', class_='date')
        pub_date = date_tag.get_text(strip=True) if date_tag else ""

        # 既存データに存在するか確認
        if any(item['title'] == title for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"YAMAP NATURANCE: 記事取得開始 - {title}")
        try:
            if is_pdf_link(link):
                content = extract_text_from_pdf(link)
            else:
                response = requests.get(link)
                response.encoding = 'utf-8'
                page_soup = BeautifulSoup(response.text, 'html.parser')
                # ニュース本文のHTML構造に基づいて調整してください。
                # 例えば、<div class="news-content">内に本文がある場合：
                content_div = page_soup.find('div', class_='news-content')
                content = content_div.get_text(separator='\n', strip=True) if content_div else ""
            
            if not content:
                print(f"YAMAP NATURANCE: コンテンツ取得失敗 - {link}")
                continue

            summary = summarize_text(title, content)

            news_item = {
                'pubDate': pub_date,
                'execution_timestamp': execution_timestamp,
                'organization': "株式会社ヤマップネイチャランス損害保険",
                'title': title,
                'link': link,
                'summary': summary
            }
            news_items.append(news_item)
            existing_data.append(news_item)
            new_count += 1
        except Exception as e:
            print(f"YAMAP NATURANCE: 要約中にエラー発生 - {e}")

    save_json(existing_data, json_file)
    return news_items

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


def save_to_csv(news_list):
    """ニュースリストをCSVファイルに保存します。"""
    if not news_list:
        print("新しいニュースはありません。")
        return

#    today_str = datetime.date.today().strftime('%Y-%m-%d')
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
    all_news = all_news + fetch_fsa_news()
    all_news = all_news + fetch_jma_news()
    all_news = all_news + fetch_jishinhonbu()
    all_news = all_news + fetch_mlit_disaster_info()
    all_news = all_news + fetch_cao_kotsu()
    all_news = all_news + fetch_mlit_jinji()
    all_news = all_news + fetch_cas_kyojin()    
    all_news = all_news + fetch_nta_news()      
    all_news = all_news + fetch_jftc_news()     
    all_news = all_news + fetch_ppc_news()     
    all_news = all_news + fetch_env_news() 
    all_news = all_news + fetch_road_to_l4_news()
    all_news = all_news + fetch_statistics_bureau_news()
    all_news = all_news + fetch_mlit_news()
    all_news = all_news + fetch_mlit_kisha_news()
    all_news = all_news + fetch_mof_news()
    all_news = all_news + fetch_kantei_news()
    all_news = all_news + fetch_cao_hodo_news()
    all_news = all_news + fetch_npa_news()
    all_news = all_news + fetch_fdma_news()
    all_news = all_news + fetch_mhlw_news()
    all_news = all_news + fetch_mhlw_kinkyu_news()
    all_news = all_news + fetch_e_gov_news()
    all_news = all_news + fetch_egov_comments()
    all_news = all_news + fetch_moj_news()
    all_news = all_news + fetch_gsi_news()
    all_news = all_news + fetch_caa_news()
    all_news = all_news + fetch_digital_agency_news()

    all_news = all_news + fetch_courts_news()
    print("fetch_courts_news() done")
#    all_news = all_news + fetch_meti_news()    # 20241105 この関数を回すと処理が止まるためコメントアウト
    print("fetch_meti_news() done")

    all_news = all_news + fetch_axadirect_pr()
    all_news = all_news + fetch_aig_news()
    all_news = all_news + fetch_ms_ins_news()
    all_news = all_news + fetch_aioi_news()
    print("fetch_aioi_news() done")
#    all_news = all_news + fetch_axa_news() # fail
    all_news = all_news + fetch_americanhome_news()
    all_news = all_news + fetch_edsp_news()
    all_news = all_news + fetch_hs_news()
    all_news = all_news + fetch_au_news()
    all_news = all_news + fetch_sbi_press()
    all_news = all_news + fetch_sbi_news()
    print("fetch_sbi_news() done")
    all_news = all_news + fetch_cardif_news()
#   all_news = all_news + fetch_capital_sonpo_news() # fail 全然別のページを誤って情報収集しようとしてしまっている
    all_news = all_news + fetch_hdmf_news()
#   all_news = all_news + fetch_newindia_news()  # fail
#   all_news = all_news + fetch_jai_news()   # fail
#   all_news = all_news + fetch_starr_news() # fail
    all_news = all_news + fetch_secom_news()
    all_news = all_news + fetch_secom_product_news()
    all_news = all_news + fetch_zenkankyo_reiwa_news()
    all_news = all_news + fetch_sonysonpo_news()
    print("fetch_sonysonpo_news() done")
    all_news = all_news + fetch_sonysonpo_news_release()
    all_news = all_news + fetch_sonpohogo_news()
    all_news = all_news + fetch_sompo_news()
    all_news = all_news + fetch_sompo_direct_news()
    all_news = all_news + fetch_sompo_direct_important_news()
    all_news = all_news + fetch_daidokasai_news()
    all_news = all_news + fetch_chubb_news()
    print("fetch_chubb_news() done")
    all_news = all_news + fetch_chubb_news_release()
    all_news = all_news + fetch_zurich_news()
    all_news = all_news + fetch_tokyo_kaijo_news()
    all_news = all_news + fetch_tokiomarine_news()
    all_news = all_news + fetch_toa_news()
#   all_news = all_news + fetch_nisshinfire_news()   # fail
#   all_news = all_news + fetch_nisshin_news()   # fail
    all_news = all_news +    fetch_nihonjishin()
#   all_news = all_news + fetch_mitsui_direct_news() # fail
#   all_news = all_news + fetch_meijiyasuda_sonpo() # fail
#   all_news = all_news + fetch_yamap_news()  # fail
    all_news = all_news +    fetch_rakuten_news()
    all_news = all_news +   fetch_rescue_news() # レスキュー損害保険: コンテンツ取得失敗 - https://www.rescue-sonpo.jp/upload_files/news/disclo2023.pdf
    print("fetch_rescue_news() done")
# failed to fetch news
#    all_news = all_news + fetch_nisc_news()    # 新着情報のページのhtmlが1部しか読み込めない。そのため、記事の取得が不可。
#    all_news = all_news + fetch_kensatsu_news() # seleniumアクセス禁止のためかページのhtmlが読み込めない。
#    all_news = all_news + fetch_e_design_news()

    all_news = remove_news_with_exception_keyword(all_news)

    save_to_csv(all_news)

if __name__ == "__main__":
    main()
