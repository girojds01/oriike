# 以下の関数は、各官公庁の新着情報を取得するための関数です。
import sys
sys.path.append('c:/sasase/packages')
sys.path.append('C:\sasase\ichiyasa\codespaces-jupyter-fsa-rss')
import requests
from utilities_oriike import client,summarize_text,load_existing_data,save_json,is_pdf_link,extract_text_from_pdf
from bs4 import BeautifulSoup
import re
import urljoin
import feedparser



def fetch_mic_news(max_count, execution_timestamp, executable_path):
    """総務省のリリースの新着情報を収集・要約します。"""
    url = "https://www.soumu.go.jp/news.rdf"
    feed = feedparser.parse(url)
    json_file = f"./data/soumu_release.json"
    existing_data = load_existing_data(json_file)

    new_news = []
    new_count = 0  # カウンターを追加
    for entry in feed.entries:
        if any(entry.title == item['title'] for item in existing_data):
            continue  # 既に存在するニュースはスキップ

        print(f"総務省: 記事取得開始 - {entry.title}")
        
        if any(entry.title == item['title'] for item in existing_data):
            continue
        print(f"総務省お知らせ: 記事取得開始 - {entry.title}")
        try:
            if is_pdf_link(entry.link):
                content = extract_text_from_pdf(entry.link)
            else:
                response = requests.get(entry.link)
                response.encoding = 'UTF-8'
                content = response.text
                #print(content)
            
            if not content:
                print(f"総務省お知らせ: コンテンツ取得失敗 - {entry.link}")
                continue
        
            summary = ""
            if new_count < max_count:  # 新しい記事がmax_count件に達したら要約をスキップ ここは5ではなく、max_countだったが、20もいらないだろうということで5にした
                summary = summarize_text(entry.title, content)
                print(summary)

            news_item = {
                'pubDate': entry.updated,
                'execution_timestamp': execution_timestamp,
                'organization': "総務省お知らせ",
                'title': entry.title,
                'link': entry.link,
                'summary': summary
            }
            new_news.append(news_item)
            existing_data.append(news_item)
            new_count += 1  # カウンターを増加
        except Exception as e:
            print(f"総務省お知らせ: 要約中にエラー発生 - {e}")
        


    save_json(existing_data, json_file)
    return new_news