# import os

# folder_path = r"C:\\sasase\\WebScraping\\functions"  # 対象フォルダを指定
# target_string = '"C:/sasase/msedgedriver.exe"'
# replacement_string = 'executable_path'

# # フォルダ内すべてのファイルを処理
# for filename in os.listdir(folder_path):
#     file_path = os.path.join(folder_path, filename)
#     if not os.path.isfile(file_path) or not filename.endswith('.py'):
#         continue

#     # ファイルを読み込み
#     with open(file_path, 'r', encoding='utf-8') as f:
#         content = f.read()

#     # 置換処理
#     if target_string in content:
#         new_content = content.replace(target_string, replacement_string)

#         # 上書き保存
#         with open(file_path, 'w', encoding='utf-8') as f:
#             f.write(new_content)

#         print(f"✅ 置換完了: {filename}")
#     else:
#         print(f"― 対象文字列なし: {filename}")


import os

folder_path = r"C:\sasase\WebScraping\functions"
output_file = r"C:\sasase\WebScraping\file_list.txt"

# ファイル一覧取得（ファイルのみ）
file_names = [f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))]

# 書き出し
with open(output_file, 'w', encoding='utf-8') as f:
    for name in file_names:
        f.write(name + '\n')

print(f"✅ ファイル一覧を {output_file} に保存しました。")
