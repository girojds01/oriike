import sys
import time
import tempfile
import re
import requests
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utilities_oriike import (
    client, summarize_text, load_existing_data,
    save_json, is_pdf_link, extract_text_from_pdf
)
from urllib.parse import urljoin


def safe_get(driver, url, timeout=15):
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        return True
    except Exception as e:
        print(f"❌ safe_get失敗: {url} - {e}")
        return False


def fetch_meti_oshirase(max_count, execution_timestamp, executable_path):
    """経済産業省お知らせの新着情報を収集・要約します。"""
    base_url = "https://www.meti.go.jp"
    json_file = "./data/meti_oshirase.json"
    existing_data = load_existing_data(json_file)
    organization = "経済産業省お知らせ"
    news_items = []
    new_count = 0

    options = Options()
    options.use_chromium = True
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=ja")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-features=EdgeML,EdgeLLM")
    options.add_argument("--log-level=3")
    user_data_dir = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={user_data_dir}")
    options.set_capability("browserName", "MicrosoftEdge")
    options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    service = EdgeService(executable_path=executable_path)
    driver = webdriver.Edge(service=service, options=options)

    try:
        if not safe_get(driver, base_url):
            driver.quit()
            return []

        release_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.LINK_TEXT, "お知らせ"))
        )
        release_tab.click()
        time.sleep(2)

        container = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "oshirase_list"))
        )

        dts = container.find_elements(By.TAG_NAME, "dt")
        dds = container.find_elements(By.TAG_NAME, "dd")

        link_info_list = []
        for dt, dd in zip(dts, dds):
            pub_date = dt.text.strip()
            link = dd.find_element(By.TAG_NAME, "a")
            title = driver.execute_script("return arguments[0].textContent;", link).strip()
            href = link.get_attribute("href")
            href = href if href.startswith("http") else urljoin(base_url, href)

            if any(title == item['title'] for item in existing_data):
                continue

            link_info_list.append((pub_date, title, href))

        for pub_date, title, href in link_info_list:
            print(f"\u2605 {pub_date} - {title} → {href}")

            try:
                if is_pdf_link(href):
                    content = extract_text_from_pdf(href)
                elif href.startswith("https://wwws.meti.go.jp"):
                    try:
                        response = requests.get(href, timeout=10)
                        response.encoding = "utf-8"
                        content = response.text
                    except Exception as e:
                        print(f"❌ requests取得失敗: {href} - {e}")
                        continue
                else:
                    if not safe_get(driver, href):
                        continue
                    content = driver.page_source

                if not content:
                    print(f"\u26a0\ufe0f コンテンツ取得失敗: {href}")
                    continue

                summary = ""
                if new_count < max_count:
                    summary = summarize_text(title, content)

                news_item = {
                    'pubDate': pub_date,
                    'execution_timestamp': execution_timestamp,
                    'organization': organization,
                    'title': title,
                    'link': href,
                    'summary': summary
                }

                news_items.append(news_item)
                existing_data.append(news_item)
                new_count += 1

            except Exception as e:
                print(f"\u26a0\ufe0f 要約中にエラー発生: {e}")

    except Exception as e:
        print(f"\u274c 全体処理エラー: {e}")

    finally:
        try:
            driver.quit()
        except Exception as e:
            print(f"\u26a0\ufe0f driver.quit()失敗: {e}")

    save_json(existing_data, json_file)
    return news_items
