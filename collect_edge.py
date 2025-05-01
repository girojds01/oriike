
import sys
# sys.path.append('C:\sasase\ichiyasa\codespaces-jupyter-fsa-rss')
sys.path.append('c:/sasase/packages')
import datetime
import csv
import importlib
import os

max_count = 0   # 取得するニュースの最大数
news_list: list[dict] = []
# 実行日時を取得
execution_timestamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H;%M;%S')
executable_path = "C:/sasase/msedgedriver.exe"
# csv_file = f"./data/output/news_{execution_timestamp}.csv"

def save_to_csv(news_list: list[dict]) -> None:
    """ニュースリストを CSV ファイルに保存する。"""
    if not news_list:
        print("新しいニュースはありません。")
        return

    os.makedirs("./data/output", exist_ok=True)
    
    csv_file = f"./data/output/news_{execution_timestamp}.csv"
    file_exists = os.path.isfile(csv_file)

    with open(csv_file, "a", encoding="shift-jis",
              errors="replace", newline="") as f:
        writer = csv.writer(f)
            
        # 新規作成時のみヘッダを書き込む
        if not file_exists:
            writer.writerow([
                "execution_timestamp", "pubDate",
                "organization", "title", "link", "summary"
            ])
            
        for item in news_list:
            writer.writerow([
                item.get("execution_timestamp", execution_timestamp),
                item.get("pubDate", ""),
                item.get("organization", ""),
                item.get("title", ""),
                item.get("link", ""),
                item.get("summary", "")
            ])

    print(f"ニュースの収集と要約が完了しました。CSVファイル: {csv_file}")
    print(os.path.abspath(csv_file))


# ファイルから org_func_map を読み込む
org_func_map = {}
with open("未確認情報取得源と関数.txt", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or ":" not in line:
            continue
        org, func = line.split(":", 1)
        # 空白やカンマ、クォートを除去
        org = org.strip()
        func = func.strip().strip(",").strip("'").strip('"')
        org_func_map[org] = func

# 各関数を実行して result.txt に追記
for org, func in org_func_map.items():
    print(f"# {org} から情報取得")

    try:
        module = importlib.import_module(f"functions.{func}")
        # 各取得関数は list[dict] を返す前提
        items = getattr(module, func)(
            max_count, execution_timestamp, executable_path
        )
        news_list.extend(items)

    except Exception as e:
        print(f"⚠️ {org} の取得でエラー発生: {e}")

# 全組織の処理が終わったら CSV 出力
save_to_csv(news_list)

        
        