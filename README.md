# Yahoo!ショッピング カテゴリランキング 1位監視システム

annekor1 店舗（https://store.shopping.yahoo.co.jp/annekor1/ ）の全商品について、
各商品が属する **Yahoo カテゴリランキング（デイリー）** を1日2回巡回し、
自店商品が **1位** を獲得したら、その順位を示すスクリーンショットを自動保存します。

## 仕組み

1. `search.html` を巡回して全商品（現在88件）とタイトルを取得
2. 各商品ページから Yahoo の `categoryId` を抽出（`data/products.json` にキャッシュ）
3. 商品が属するカテゴリごとに `https://shopping.yahoo.co.jp/categoryranking/{id}/list`（デイリー）を開く
4. メインランキングの並びから自店商品の順位を判定
5. **自店商品が1位のとき**、ランキング上部（順位・カテゴリ名・更新日が写る範囲）を
   `screenshots/` に保存
6. 全商品の順位を `data/history.csv` に追記、最新結果を `data/latest.json` に保存

商品の追加・削除・カテゴリ変更は毎回の実行で自動反映されます。

## 出力

| パス | 内容 |
|------|------|
| `screenshots/YYYYMMDD_HHMM_cat{ID}_{カテゴリ名}_{商品コード}_1i.png` | 1位獲得時の証跡スクショ |
| `data/history.csv` | 実行ごとの自店商品の順位履歴（Excelで開けるUTF-8 BOM） |
| `data/latest.json` | 直近実行のサマリー（1位獲得一覧） |
| `data/products.json` | 商品→カテゴリの対応表（自動生成・キャッシュ） |

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

※このPCでは `python` がストア版スタブになっている場合があります。その際は実体を指定:
`& "C:\Users\sakur\AppData\Local\Python\bin\python.exe" monitor.py`

## GitHub Actions で1日2回自動実行する手順

1. GitHub で新しいリポジトリを作成（Private 推奨）
2. このフォルダを push
   ```bash
   git init
   git add .
   git commit -m "init: Yahoo ranking monitor"
   git branch -M main
   git remote add origin https://github.com/<あなた>/<リポジトリ名>.git
   git push -u origin main
   ```
3. リポジトリの **Settings → Actions → General → Workflow permissions** を
   **「Read and write permissions」** に設定（結果を自動コミットするため）
4. **Actions** タブで初回だけ緑のボタンからワークフローを有効化
5. 以降は自動で **JST 06:00 / 18:00** に実行され、
   1位獲得スクショと履歴がリポジトリに自動コミットされます
   （手動実行は Actions タブの「Run workflow」から）

### 実行時刻の変更

`.github/workflows/monitor.yml` の cron を編集（**UTC 指定**、JST−9時間）。
例: JST 09:00 にしたい → `cron: "0 0 * * *"`

## 注意点

- **集計期間はデイリー**（1日2回監視向け）。リアルタイム/年間に変えたい場合は
  `monitor.py` の `PERIOD` と `fetch_ranking` を調整。
- Yahoo 側のHTML構造変更に依存します。取得0件・順位が全て「圏外」になった場合は
  セレクタ（`ranking-crk01_01` 等）の見直しが必要です。
- GitHub Actions の runner はデータセンターIPのため、まれに Yahoo 側の表示が
  変わる可能性があります。うまく動かない場合はローカル実行（Windowsタスク
  スケジューラ）に切り替え可能です。
- GitHub の cron は混雑時に数分〜遅延することがあります（仕様）。
