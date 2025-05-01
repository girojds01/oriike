import ast
import os
from textwrap import dedent

# ===== 設定 =====
input_file_path = "collect_4.py"  # 元ファイル（同じフォルダに置く）
output_dir = "functions"         # 出力フォルダ
os.makedirs(output_dir, exist_ok=True)

# ===== 共通インポートコード =====
common_header = '''\
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
# options.binary_location = r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
options.add_argument("--start-maximized")
options.use_chromium = True
'''

# ===== 元コード読み込み =====
with open(input_file_path, 'r', encoding='utf-8') as f:
    source_code = f.read()

tree = ast.parse(source_code)
lines = source_code.splitlines()

# ===== 関数分割・加工 =====
for node in tree.body:
    if isinstance(node, ast.FunctionDef):
        func_name = node.name
        start_line = node.lineno - 1
        end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1
        func_lines = lines[start_line:end_line]

        # 引数の調整（カンマ処理）
        def_line = func_lines[0].strip()
        if def_line.startswith("def"):
            # 引数がない場合
            if def_line.endswith("():" or "( ):"):
                def_line = def_line.replace("()", "(max_count, execution_timestamp, executable_path)")
            else:
                def_line = def_line.rstrip("):") + "max_count, execution_timestamp, executable_path):"
            func_lines[0] = def_line

        # 組み立てて保存
        func_body = "\n".join(func_lines)
        func_body = dedent(func_body)
        final_code = f"{common_header}\n\n{func_body}"

        output_path = os.path.join(output_dir, f"{func_name}.py")
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write(final_code)

        print(f"✅ {output_path} を生成しました")
