# Yahoo!ショッピング カテゴリランキング 1位監視システム

annekor1 店舗（https://store.shopping.yahoo.co.jp/annekor1/ ）の全商品について、
各商品が属する **Yahoo カテゴリランキングの「デイリー」と「リアルタイム」両方** を
1日2回巡回し、自店商品が **1位** を獲得したら、その **1位の行だけ** を高解像度で
スクリーンショット保存し、**管理画面（index.html）** に一覧表示します。

## 仕組み

1. `search.html` を巡回して全商品（現在88件）とタイトルを取得
2. 各商品ページから Yahoo の `categoryId` を抽出（`data/products.json` にキャッシュ）
3. 商品が属するカテゴリごとに `categoryranking/{id}/list` を開き、
   **デイリー**と**リアルタイム**の両タブで自店商品の順位を判定
4. **自店商品が1位のとき**、その1位の行要素だけを高解像度で
   `screenshots/{daily|realtime}/` に保存
5. 全商品の順位を `data/history.csv` に追記、累計1位回数を `data/wins.json` に集計
6. **管理画面 `index.html`** を再生成（デイリー/リアルタイムの各1位を表示）

商品の追加・削除・カテゴリ変更は毎回の実行で自動反映されます。

## 管理画面（index.html）

実行のたびに `index.html` が作られ、**デイリー / リアルタイムそれぞれの現在の1位**を
カード（1位の行スクショ＋カテゴリ名＋累計1位回数＋更新時刻）で表示します。

- **ローカル**: リポジトリを `git pull` して `index.html` をブラウザで開く
- **GitHub Pages**（任意）: リポジトリを Public にして Settings → Pages で
  ブランチ `main` / ルートを公開すると、URLでいつでも閲覧可能

## 出力

| パス | 内容 |
|------|------|
| `index.html` | **管理画面**（デイリー/リアルタイムの各1位を表示） |
| `screenshots/{daily,realtime}/YYYYMMDD_HHMM_cat{ID}_{カテゴリ名}_{商品コード}.png` | 1位の行だけを切り出した高解像度スクショ |
| `data/history.csv` | 実行ごとの順位履歴（period列あり・Excelで開けるUTF-8 BOM） |
| `data/wins.json` | **商品ごとの累計1位獲得回数**（period別・初回〜最終日・獲得スロット一覧） |
| `data/latest.json` | 直近実行のサマリー（period別の1位一覧） |
| `data/products.json` | 商品→カテゴリの対応表（自動生成・キャッシュ） |

### 「1位獲得回数」の数え方

`wins.json` の `count` は **各集計期間で1位を観測した監視スロット数（朝/夜単位）** です。
監視は1日2回（朝・夜）なので、同じスロット内で手動再実行しても二重カウントされません
（`(集計期間, 商品, 日付, 朝/夜)` で排除）。朝・夜どちらも1位ならその日は最大2回。

## 集計期間について

ランキングページには「リアルタイム / デイリー / 年間」タブがあります。
本システムは **デイリー**（広告で使う「ランキング1位獲得」の定番・1日約2回更新）と
**リアルタイム**（高頻度更新）の**両方**を取得・記録します。年間は対象外です。

## ローカル実行（Windows）

```powershell
# 初回のみ
pip install -r requirements.txt
python -m playwright install chromium

# 実行
python monitor.py            # 通常実行
python monitor.py --refresh  # 商品→カテゴリ対応を作り直してから実行
python monitor.py --map-only # 対応表の生成のみ
```

※このPCでは `python` がストア版スタブの場合があります。その際は実体を指定:
`& "C:\Users\sakur\AppData\Local\Python\bin\python.exe" monitor.py`

## GitHub Actions で1日2回自動実行する手順

1. GitHub で新しいリポジトリを作成（Private 推奨。Pages で公開したい場合は Public）
2. このフォルダを push
   ```bash
   git remote add origin https://github.com/<あなた>/<リポジトリ名>.git
   git branch -M main
   git push -u origin main
   ```
3. リポジトリの **Settings → Actions → General → Workflow permissions** を
   **「Read and write permissions」** に設定（結果を自動コミットするため）
4. **Actions** タブで初回だけワークフローを有効化
5. 以降は自動で **JST 08:30 / 20:30** に実行され、
   1位スクショ・履歴・管理画面がリポジトリに自動コミットされます
   （手動実行は Actions タブの「Run workflow」から）

### 実行時刻の変更

`.github/workflows/monitor.yml` の cron を編集（**UTC 指定**、JST−9時間）。
例: JST 09:00 → `cron: "0 0 * * *"`

## 注意点

- Yahoo 側のHTML構造変更に依存します。取得0件・順位が全て「圏外」になった場合は
  セレクタ（`ranking-crk01_01` / `.line` 等）の見直しが必要です。
- GitHub Actions の runner はデータセンターIPのため、まれに Yahoo 側の表示が
  変わる可能性があります。うまく動かない場合はローカル実行（Windowsタスク
  スケジューラ）に切り替え可能です。
- GitHub の cron は混雑時に数分〜遅延することがあります（仕様）。
