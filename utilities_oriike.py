
from openai import AzureOpenAI
import os
import sys
sys.path.append('c:/sasase/packages')
import json
import requests
from pypdf import PdfReader
from io import BytesIO
import re
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import feedparser
import csv



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
            "content": f"『{title}』に関する次の記事を100文字の日本語で要約してください。",
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

def is_pdf_link(url): #拡張子が.pdfなだけで、中を開くとhtmlということもあるみたいなので、これは改良の余地がある
    #invalid pdf header: b'<!DOC'
    # EOF marker not found
    """リンクがPDFファイルかどうかを判定します。"""
    return url.lower().endswith('.pdf')

def extract_text_from_pdf(url):
    """PDFリンクからテキストを抽出します。"""
    try:
        response = requests.get(url, timeout=15)  # ✅ timeoutを設定
        response.raise_for_status()
        # 応答がPDFか確認（まれにHTMLで404など返る）
        if not response.content.startswith(b'%PDF'):
            print(f"❌ PDFヘッダー不正: {url}")
            return ""
        pdf_file = BytesIO(response.content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"PDFからのテキスト抽出中にエラーが発生しました: {e}")
        return ""
    
    
def save_to_csv(news_listmax_count, news_list, execution_timestamp):
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
    
    
def save_to_csv(news_list, execution_timestamp):
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