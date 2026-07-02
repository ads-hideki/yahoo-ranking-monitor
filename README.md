# Yahoo!ショッピング カテゴリランキング 1位監視システム

annekor1 店舗（https://store.shopping.yahoo.co.jp/annekor1/ ）の全商品について、
各商品が属する **Yahoo カテゴリランキングの「デイリー」と「リアルタイム」両方** を巡回し
（**デイリーは1日1回・リアルタイムは2時間おき**）、自店商品が **1位** を獲得したら、
その **1位の行だけ** を高解像度でスクリーンショット保存し、
**管理画面（index.html）** に一覧表示します。

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
| `screenshots/{daily,realtime}/YYYYMMDD_cat{ID}_{カテゴリ名}_{商品コード}.png` | 1位の行だけを切り出した高解像度スクショ（日付単位・1日1枚） |
| `data/history.csv` | 実行ごとの順位履歴（period列あり・Excelで開けるUTF-8 BOM） |
| `data/wins.json` | **デイリーで1位になった累計日数**（初回〜最終日・獲得日一覧）。リアルタイムは対象外 |
| `data/latest.json` | 直近状態のサマリー（period別の1位一覧・period別の最終取得時刻） |
| `data/products.json` | 商品→カテゴリの対応表（自動生成・キャッシュ） |

### 「1位獲得回数」の数え方（デイリーのみ）

`wins.json` の `count` は **デイリーで1位になった日数** です（`(商品, 日付)` で重複排除＝1日最大1回）。
デイリーランキングは実質1日1回更新のため、取得回数に関係なく1日=1回で正確に数えます。
**リアルタイムは変動が速く累計に馴染まないため、累計カウントは行いません**（現在の1位のみ表示）。

## 集計期間と取得頻度

ランキングページには「リアルタイム / デイリー / 年間」タブがあります。本システムは:

- **デイリー**（広告で使う「ランキング1位獲得」の定番）… Yahoo公式で「1日1回以上更新」。**1日1回取得**。
- **リアルタイム**（過去72時間の購入データ・高頻度で変動）… **2時間おきに取得**（現在の1位のみ／累計なし）。
- 年間タブは対象外。

参考: [ランキングについて - Yahoo!ヘルプ](https://support.yahoo-net.jp/PccShopping/s/article/H000005892)

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

## GitHub Actions での自動実行について

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
5. 以降は自動で実行され、1位スクショ・履歴・管理画面がリポジトリに自動コミットされます
   - **JST 08:30**：全取得（デイリー＋リアルタイム）
   - **2時間おき**：リアルタイムのみ取得
   - 手動実行（Actions タブの「Run workflow」）は全取得

### スケジュールの変更

`.github/workflows/monitor.yml` の cron を編集（**UTC 指定**、JST−9時間）。
- 全取得の時刻：`"30 23 * * *"`（=JST 08:30）
- リアルタイム間隔：`"0 */2 * * *"`（2時間おき。3時間なら `"0 */3 * * *"`）

## 毎朝9時のメール通知

毎朝 **JST 09:00** に、その時点のデイリー1位・リアルタイム1位の商品を
メールで通知します（Gmail の SMTP から送信、1位スクショを添付）。

送信を有効にするには、GitHub リポジトリに **3つのシークレット** を登録してください
（**Settings → Secrets and variables → Actions → New repository secret**）。

| シークレット名 | 値 |
|---|---|
| `MAIL_USERNAME` | 送信元の Gmail アドレス（例: ads.hideki@gmail.com） |
| `MAIL_PASSWORD` | Gmail の **アプリパスワード**（後述。通常のログインPWは不可） |
| `MAIL_TO` | 送信先アドレス（複数はカンマ区切り可） |

### Gmail アプリパスワードの取得

1. Google アカウントで **2段階認証** を有効化（未設定の場合）
2. https://myaccount.google.com/apppasswords を開く
3. 「アプリ名」を入力（例: `yahoo-ranking`）して作成 → **16桁のパスワード**が表示される
4. それを `MAIL_PASSWORD` に登録（スペースは詰めても可）

### 動作
- シークレット3つが揃っていれば、毎朝9時の実行で自動送信されます
- シークレット未設定の間は送信ステップはスキップ（実行は成功のまま）
- テスト送信: Actions → Run workflow → **send_email に true** を指定して実行

## 注意点

- Yahoo 側のHTML構造変更に依存します。取得0件・順位が全て「圏外」になった場合は
  セレクタ（`ranking-crk01_01` / `.line` 等）の見直しが必要です。
- GitHub Actions の runner はデータセンターIPのため、まれに Yahoo 側の表示が
  変わる可能性があります。うまく動かない場合はローカル実行（Windowsタスク
  スケジューラ）に切り替え可能です。
- GitHub の cron は混雑時に数分〜遅延することがあります（仕様）。
