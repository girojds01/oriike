# 以下の関数は、各官公庁の新着情報を取得するための関数です。
import sys
sys.path.append('c:/sasase/packages')
sys.path.append('C:\sasase\ichiyasa\codespaces-jupyter-fsa-rss')
import requests
from utilities_oriike import client,summarize_text,load_existing_data,save_json,is_pdf_link,extract_text_from_pdf
from bs4 import BeautifulSoup
import re
import urljoin
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
# Seleniumのオプションを設定
options = Options()
options.add_argument("--headless")
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--no-sandbox")
options.add_argument("--lang=ja")
# options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
options.add_argument("--start-maximized")
options.add_argument("--disable-gpu")
options.add_argument("--disable-features=EdgeML,EdgeLLM")
options.add_argument("--log-level=3")  # 静かに実行
options.use_chromium = True

def fetch_meti_oshirase(max_count, execution_timestamp, executable_path):
    """経済産業省お知らせの新着情報を収集・要約します。"""
    url = "https://www.meti.go.jp/"
    json_file = f"./data/meti_oshirase.json"
    # 既存のデータをロード
    existing_data = load_existing_data(json_file)

    # 明示的に Chromium ベースを指定する capabilities は もう不要（Seleniumが自動対応）
    # ただし options.set_capability を加えると安定性UP
    options.set_capability("browserName", "MicrosoftEdge")

    # Edgeドライバのパス（バージョン135に対応したmsedgedriver.exeを配置済み）
    service = EdgeService(executable_path=executable_path)

    # ドライバ起動
    driver = webdriver.Edge(service=service, options=options)    

    news_items = []
    new_count = 0  # カウンターを追加

    # お知らせ一覧の親要素を取得
    try:
        driver.get("https://www.meti.go.jp")
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(2)

        # ✅ 「お知らせ」タブをクリックして表示させる
        release_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "お知らせ"))
        )
        
        release_tab.click()
        time.sleep(2)

        # ✅ 「お知らせ」タブ内が表示されるまで待機
        container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "oshirase_list"))
        )

        # <dt> 日付と <dd> リンクをセットで取得
        dts = container.find_elements(By.TAG_NAME, "dt")
        dds = container.find_elements(By.TAG_NAME, "dd")

        # 日付とリンクの数が一致している前提でペアで処理
        for dt, dd in zip(dts, dds):
            pub_date = dt.text.strip()
            link = dd.find_element(By.TAG_NAME, "a")
            title = driver.execute_script("return arguments[0].textContent;", link)
            # print("タイトルは" + title)
            href = link.get_attribute("href")
            href = href if href.startswith("http") else "https://www.meti.go.jp" + href
            print(f"{pub_date} - {title} → {href}")
            
            if any(title == item['title'] for item in existing_data):
                continue
            print(f"経済産業省お知らせ: 記事取得開始 - {title}")
            try:
                if is_pdf_link(href):
                    content = extract_text_from_pdf(href)
                else:
                    response = requests.get(href)
                    response.encoding = 'UTF-8'
                    content = response.text
                    print(content)
                if not content:
                    print(f"経済産業省お知らせ: コンテンツ取得失敗 - {href}")
                    continue
            
                summary = ""
                if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ ここは5ではなく、max_countだったが、20もいらないだろうということで5にした
                    summary = summarize_text(title, content)
                print(summary)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': "経済産業省お知らせ",
                    'title': title,
                    'link': href,
                    'summary': summary
                }
                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1  # カウンターを増加
            except Exception as e:
                print(f"経済産業省お知らせ: 要約中にエラー発生 - {e}")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        
    driver.quit()


    save_json(existing_data, json_file)
    return news_items