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
import urllib.request
import ssl
import urllib3, certifi
# Seleniumのオプションを設定
options = Options()
options.add_argument("--headless")
options.add_argument('--disable-dev-shm-usage')
options.add_argument("--no-sandbox")
options.add_argument("--lang=ja")
# options.binary_location = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
options.add_argument("--start-maximized")
options.use_chromium = True
import re
from email.message import Message

def charset_from_headers(headers, default="utf-8"):
    """HTTPHeaderDict | Mapping[str,str] → charset 文字列"""
    ct = headers.get("Content-Type")
    if not ct:
        return default

    # email.message.Message を使うと RFC に沿って安全にパースできる
    msg = Message()
    msg["Content-Type"] = ct
    return msg.get_content_charset() or default



def fetch_gsi_news(max_count, execution_timestamp, executable_path):
    url = "https://www.gsi.go.jp/index.rdf"
    json_file = "./data/gsi-rss.json"
    existing_data = load_existing_data(json_file)

    # ---- 共通 SSLContext ----
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)

    # ---- RSS 取得 (urllib.request でも可) ----
    with urllib.request.urlopen(url, context=ctx) as f:
        feed = feedparser.parse(f.read())

    http = urllib3.PoolManager(ssl_context=ctx, retries=False)
    new_news, new_count = [], 0

    for entry in feed.entries:
        if any(entry.title == n["title"] for n in existing_data):
            continue

        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                r = http.request("GET", entry.link, timeout=10)
                enc = charset_from_headers(r.headers)
                text = r.data.decode(enc, "replace")
                soup = BeautifulSoup(text, "html.parser")
                content = soup.get_text("\n")
                r.release_conn()

            if not content:
                continue

            summary = summarize_text(entry.title, content) if new_count < max_count else ""
            item = {
                "pubDate": entry.updated,
                "execution_timestamp": execution_timestamp,
                "organization": "国土地理院",
                "title": entry.title,
                "link": entry.link,
                "summary": summary,
            }
            new_news.append(item)
            existing_data.append(item)
            new_count += 1

        except Exception as e:
            print("国土地理院: 要約中にエラー発生 -", e)

    save_json(existing_data, json_file)
    return new_news

