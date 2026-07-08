# -*- coding: utf-8 -*-
"""
Yahoo!ショッピング カテゴリランキング 1位監視システム
------------------------------------------------------
annekor1 店舗の全商品について、各商品が属する Yahoo カテゴリランキングの
「デイリー」と「リアルタイム」の両方を1日2回巡回し、自店商品が1位を獲得したら
その1位の行だけを高解像度でスクリーンショット保存し、管理画面(index.html)に表示する。

- 全商品リスト  : /annekor1/search.html を b= オフセットで巡回して取得
- 商品→カテゴリ : 各商品ページの "categoryId":"NNN" を抽出
- 順位判定      : https://shopping.yahoo.co.jp/categoryranking/{cat}/list の
                  メインランキング(crk01_01)の並び順で判定（デイリー/リアルタイム両方）
- 1位検知時     : 1位の行要素だけを screenshots/{period}/ に高解像度で保存
- 表示          : index.html（管理画面）にデイリー/リアルタイムの各1位を表示

使い方:
    python monitor.py            # 通常実行
    python monitor.py --refresh  # 商品→カテゴリのマッピングを作り直してから実行
    python monitor.py --map-only # マッピング生成のみ
"""
import os, re, csv, json, argparse, datetime, html
from playwright.sync_api import sync_playwright

# ---- 設定 -----------------------------------------------------------------
STORE = "annekor1"
# 監視する集計期間（label はタブ文言）。両方監視する。
PERIODS = [("daily", "デイリー"), ("realtime", "リアルタイム")]

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
SHOT_DIR = os.path.join(BASE, "screenshots")
PRODUCTS_JSON = os.path.join(DATA_DIR, "products.json")
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")
WINS_JSON = os.path.join(DATA_DIR, "wins.json")
DASHBOARD = os.path.join(BASE, "index.html")

NAV_CODES = {"guide", "info", "search", "index", "store", "user",
             "review", "company", "law", "privacy", "category"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst():
    return datetime.datetime.now(JST)


def sanitize(s, n=30):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", (s or "").strip())
    return s[:n].strip("_") or "x"


# ---- 商品リスト取得 --------------------------------------------------------
def crawl_products(page):
    """search.html を巡回して {code: title} を取得（88件想定）"""
    products = {}
    for off in range(1, 400, 30):
        page.goto(f"https://store.shopping.yahoo.co.jp/{STORE}/search.html?b={off}",
                  wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(800)
        data = page.eval_on_selector_all(
            f"a[href*='/{STORE}/']",
            """(as, store) => as.map(a => {
                 const h = a.getAttribute('href') || '';
                 const m = h.match(new RegExp('/'+store+'/([A-Za-z0-9_\\\\-]+)\\\\.html'));
                 if(!m) return null;
                 const img = a.querySelector('img');
                 return {code:m[1], hasImg: !!img,
                         title:(a.getAttribute('title') || (img?img.getAttribute('alt'):'') || '').trim()};
               }).filter(Boolean)""",
            STORE)
        new = 0
        for d in data:
            c = d["code"].lower()
            if c in NAV_CODES or not d["hasImg"] or not d["title"]:
                continue
            if c not in products:
                products[c] = d["title"]
                new += 1
        if new == 0 and off > 1:
            break
    return products


# ---- 商品→カテゴリ抽出 -----------------------------------------------------
def fetch_category(page, code):
    page.goto(f"https://store.shopping.yahoo.co.jp/{STORE}/{code}.html",
              wait_until="domcontentloaded", timeout=60000)
    html_ = page.content()
    m = re.search(r'"categoryId"\s*:\s*"?(\d+)"?', html_)
    if not m:
        page.wait_for_timeout(1500)
        m = re.search(r'"categoryId"\s*:\s*"?(\d+)"?', page.content())
    return m.group(1) if m else None


def build_mapping(page, refresh=False):
    mapping = {}
    if os.path.exists(PRODUCTS_JSON) and not refresh:
        mapping = json.load(open(PRODUCTS_JSON, encoding="utf-8"))
    titles = crawl_products(page)
    print(f"[products] {len(titles)} 件の商品を検出")
    for i, (code, title) in enumerate(sorted(titles.items()), 1):
        rec = mapping.get(code, {})
        rec["title"] = title
        if not rec.get("categoryId"):
            cat = fetch_category(page, code)
            rec["categoryId"] = cat
            print(f"  [{i}/{len(titles)}] {code} -> cat {cat}")
        mapping[code] = rec
    for code in mapping:
        mapping[code]["active"] = code in titles
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(mapping, open(PRODUCTS_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return mapping


# ---- ランキング取得 --------------------------------------------------------
def open_ranking(page, cat_id):
    """カテゴリランキングページを開く（デフォルト=デイリー）"""
    url = f"https://shopping.yahoo.co.jp/categoryranking/{cat_id}/list"
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1000)


def select_period(page, period):
    """realtime のときリアルタイムタブをクリック。daily はデフォルトのまま。"""
    if period == "realtime":
        try:
            page.get_by_text("リアルタイム", exact=True).first.click()
            page.wait_for_timeout(2500)
        except Exception as e:
            print(f"    リアルタイム切替失敗: {e}")
    # 上位読み込みのため軽くスクロールして最上部へ戻す
    for _ in range(2):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(300)
    page.mouse.wheel(0, -30000)
    page.wait_for_timeout(300)


def parse_ranking(page, cat_id):
    """現在表示中のランキングを『行(=順位)単位』で返す。
    価格比較リスト（最安値を見る）等の行も1件として数え、
    店舗商品でない行は store/code=None（＝自店ではない）とする。
    これにより実際の表示順位で1位判定できる（比較リストを飛ばして数える誤りを防ぐ）。"""
    rows = page.evaluate(
        """() => {
             const anchors = [...document.querySelectorAll("a[href*='ranking-crk01_01']")];
             const seen = new Set(), out = [];
             for (const a of anchors) {
               const line = a.closest('.line') || a.closest('li');
               if (!line || seen.has(line)) continue;
               seen.add(line);
               const links = [...line.querySelectorAll('a')].map(x => x.getAttribute('href') || '');
               const item = links.find(h => /store\\.shopping\\.yahoo\\.co\\.jp\\/[^\\/]+\\/[A-Za-z0-9_\\-]+\\.html/.test(h));
               let store = null, code = null, url = '';
               if (item) {
                 const m = item.match(/store\\.shopping\\.yahoo\\.co\\.jp\\/([^\\/]+)\\/([A-Za-z0-9_\\-]+)\\.html/);
                 store = m[1]; code = m[2]; url = item.split('?')[0];
               }
               const img = line.querySelector('img');
               out.push({store, code, url, title: (img ? img.getAttribute('alt') : '') || ''});
             }
             return out;
           }""")
    ordered = []
    for it in rows:
        it["rank"] = len(ordered) + 1
        it["title"] = (it["title"] or "").strip()
        ordered.append(it)

    title = page.title() or ""
    cat_name = re.sub(r"^【[^】]*】", "", title)
    cat_name = re.sub(r"の(おすすめ人気)?ランキング.*$", "", cat_name).strip()
    md = re.search(r"更新[日時][:：]?\s*([0-9]{4}[/／][0-9]{1,2}[/／][0-9]{1,2}"
                   r"(?:\s*[0-9]{1,2}[:：][0-9]{1,2})?)", page.content())
    return {"category_id": cat_id, "category_name": cat_name,
            "update_label": (md.group(1).strip() if md else ""), "items": ordered}


def shot_top_row(page, path):
    """メインランキング1位の行要素だけを高解像度で保存（リトライ付き）"""
    for attempt in range(3):
        try:
            a = page.query_selector("a[href*='ranking-crk01_01']")
            if not a:
                page.wait_for_timeout(1000)
                continue
            row = a.evaluate_handle(
                "el => el.closest('.line') || el.closest('li') "
                "|| el.closest('[class*=item]') || el.parentElement").as_element()
            if not row:
                page.wait_for_timeout(800)
                continue
            row.scroll_into_view_if_needed(timeout=6000)
            page.wait_for_timeout(500)
            row.screenshot(path=path)
            return True
        except Exception as e:
            print(f"    行スクショ再試行{attempt+1}: {e}")
            page.wait_for_timeout(800)
    return False


# ---- 集計 -----------------------------------------------------------------
def compute_win_stats(mapping):
    """history.csv から『デイリーで1位になった日数』を集計して wins.json に保存。
    count = デイリー1位の日数（1日1回まで＝(商品,日付)で重複排除）。
    デイリーは実質1日1回更新のため、取得回数に関係なく1日=最大1回で数える。
    リアルタイムは累計対象外。"""
    daily = {}
    if os.path.exists(HISTORY_CSV):
        seen = set()
        with open(HISTORY_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                if str(row.get("rank")) != "1":
                    continue
                if (row.get("period") or "daily") != "daily":
                    continue
                code = (row.get("item_code") or "").lower()
                try:
                    date = datetime.datetime.fromisoformat(
                        row["datetime_jst"]).strftime("%Y-%m-%d")
                except Exception:
                    continue
                if (code, date) in seen:
                    continue
                seen.add((code, date))
                s = daily.setdefault(
                    code, {"count": 0, "days": [], "first": date, "last": date})
                s["count"] += 1
                s["days"].append(date)
                s["first"] = min(s["first"], date)
                s["last"] = max(s["last"], date)
                s["category_name"] = row.get("category_name", "")
                s["category_id"] = row.get("category_id", "")
    for code, s in daily.items():
        s["title"] = mapping.get(code, {}).get("title") or ""
    daily = dict(sorted(daily.items(), key=lambda kv: kv[1]["count"], reverse=True))
    out = {"generated_at": now_jst().isoformat(),
           "note": "count = デイリーで1位になった日数（1日1回まで）。リアルタイムは累計対象外。",
           "daily": daily}
    json.dump(out, open(WINS_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return {"daily": daily}


# ---- 管理画面(HTML)生成 ----------------------------------------------------
def _card(w, wins_for_period, show_count=True):
    code = w["code"].lower()
    img = html.escape(w.get("screenshot", ""))
    title = html.escape(w["title"])
    cat = html.escape(w["category_name"])
    upd = html.escape(w.get("update_label", ""))
    badge = ""
    if show_count:  # デイリーのみ累計を表示（リアルタイムは累計対象外）
        cnt = wins_for_period.get(code, {}).get("count", 0)
        badge = f'<span class="badge">累計1位 {cnt}日</span>'
    img_html = (f'<a href="{img}" target="_blank"><img src="{img}" alt="{title}"></a>'
                if img else '<div style="color:#aaa;font-size:12px">（スクショ取得待ち）</div>')
    return f"""
    <div class="card">
      <div class="cat">{cat}</div>
      {img_html}
      <div class="meta">
        {badge}<span class="upd">更新: {upd}</span>
      </div>
      <div class="title">{title}</div>
      <div class="code">{html.escape(w['code'])}</div>
    </div>"""


def _fmt_dt(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%m/%d %H:%M")
    except Exception:
        return ""


def _section(period_key, period_label, latest, wins):
    winners = latest.get(period_key, [])
    upd = _fmt_dt(latest.get(period_key + "_updated", ""))
    upd_txt = f"／最終取得 {upd}" if upd else ""
    if winners:
        cards = "\n".join(
            _card(w, wins.get(period_key, {}), show_count=(period_key == "daily"))
            for w in winners)
        body = f'<div class="grid">{cards}</div>'
    else:
        body = '<p class="none">現在このランキングで1位の商品はありません。</p>'
    return f"""
  <section>
    <h2>{period_label} <small>1位獲得中 {len(winners)}件{upd_txt}</small></h2>
    {body}
  </section>"""


def generate_dashboard(latest, wins):
    run_at = latest.get("run_at", "")
    try:
        run_disp = datetime.datetime.fromisoformat(run_at).strftime("%Y/%m/%d %H:%M")
    except Exception:
        run_disp = run_at
    sections = "\n".join(_section(k, lbl, latest, wins) for k, lbl in PERIODS)
    doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>annekor1 ランキング1位 監視ダッシュボード</title>
<style>
  :root {{ font-family: "Segoe UI", "Hiragino Sans", "Meiryo", sans-serif; }}
  body {{ margin:0; background:#f5f6f8; color:#222; }}
  header {{ background:#c8102e; color:#fff; padding:16px 24px; }}
  header h1 {{ margin:0; font-size:20px; }}
  header .sub {{ font-size:13px; opacity:.9; margin-top:4px; }}
  main {{ max-width:1080px; margin:0 auto; padding:20px; }}
  section {{ margin-bottom:28px; }}
  h2 {{ font-size:18px; border-left:6px solid #c8102e; padding-left:10px; margin:18px 0 12px; }}
  h2 small {{ font-weight:normal; font-size:13px; color:#666; margin-left:8px; }}
  .grid {{ display:grid; grid-template-columns:1fr; gap:14px; }}
  .card {{ background:#fff; border:1px solid #e2e4e8; border-radius:10px; padding:12px 14px;
           box-shadow:0 1px 3px rgba(0,0,0,.05); }}
  .card .cat {{ font-size:13px; color:#c8102e; font-weight:bold; margin-bottom:6px; }}
  .card img {{ width:100%; max-width:1000px; height:auto; border:1px solid #eee; border-radius:6px; display:block; }}
  .card .meta {{ display:flex; gap:10px; align-items:center; margin-top:8px; }}
  .badge {{ background:#fff4e5; color:#b26a00; border:1px solid #ffd591; border-radius:12px;
            padding:2px 10px; font-size:13px; font-weight:bold; }}
  .upd {{ font-size:12px; color:#888; }}
  .title {{ font-size:13px; color:#333; margin-top:6px; line-height:1.4; }}
  .code {{ font-size:11px; color:#aaa; margin-top:2px; }}
  .none {{ color:#888; background:#fff; border:1px dashed #ccc; border-radius:8px; padding:16px; }}
  footer {{ text-align:center; color:#999; font-size:12px; padding:20px; }}
</style>
</head>
<body>
<header>
  <h1>annekor1 カテゴリランキング 1位監視</h1>
  <div class="sub">最終更新: {html.escape(run_disp)}（JST）｜デイリー=1日1回 / リアルタイム=2時間おき 自動更新</div>
</header>
<main>
{sections}
</main>
<footer>Yahoo!ショッピング annekor1 / 自動生成ダッシュボード</footer>
</body>
</html>"""
    open(DASHBOARD, "w", encoding="utf-8").write(doc)


# ---- メイン ---------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="商品→カテゴリを作り直す")
    ap.add_argument("--map-only", action="store_true", help="マッピングのみ")
    ap.add_argument("--only", choices=["daily", "realtime"], default=None,
                    help="指定した集計期間だけ取得（省略時は両方）")
    args = ap.parse_args()

    # 今回取得する集計期間（--only 指定時はその1つだけ）
    run_periods = [(k, l) for k, l in PERIODS if (args.only is None or k == args.only)]

    os.makedirs(DATA_DIR, exist_ok=True)
    for pk, _ in PERIODS:
        os.makedirs(os.path.join(SHOT_DIR, pk), exist_ok=True)
    ts = now_jst()
    stamp = ts.strftime("%Y%m%d")  # スクショは日付単位（同日同一1位は上書き＝1日1枚）

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1500, "height": 1600},
            device_scale_factor=2, user_agent=UA, locale="ja-JP")

        mapping = build_mapping(page, refresh=args.refresh)
        if args.map_only:
            browser.close()
            print("map-only 完了")
            return

        our_codes = {c for c, r in mapping.items()
                     if r.get("active") and r.get("categoryId")}
        cats = {}
        for c in our_codes:
            cats.setdefault(mapping[c]["categoryId"], []).append(c)
        print(f"[monitor] 対象カテゴリ {len(cats)} 種 / 対象商品 {len(our_codes)} 件")

        rows = []
        winners = {pk: [] for pk, _ in run_periods}
        for cat_id, codes in sorted(cats.items()):
            our_in_cat = {c.lower() for c in codes}
            try:
                open_ranking(page, cat_id)
            except Exception as e:
                print(f"  cat {cat_id}: 取得失敗 {e}")
                continue
            line = [f"  cat {cat_id}"]
            for period, label in run_periods:
                try:
                    select_period(page, period)
                    rk = parse_ranking(page, cat_id)
                except Exception as e:
                    print(f"  cat {cat_id} {label}: 失敗 {e}")
                    continue
                hits = [it for it in rk["items"]
                        if it["store"] == STORE and it["code"].lower() in our_in_cat]
                top = rk["items"][0] if rk["items"] else None
                is_top_ours = bool(top and top["store"] == STORE
                                   and top["code"].lower() in our_in_cat)
                best = min([h["rank"] for h in hits], default=None)
                line.append(f"{label}={best if best else '圏外'}位"
                            f"{'★1位' if is_top_ours else ''}")
                for it in hits:
                    rows.append([ts.isoformat(), period, cat_id, rk["category_name"],
                                 it["code"], it["rank"],
                                 mapping.get(it['code'].lower(), {}).get('title', it['title'])])
                if is_top_ours:
                    # 品番ごとのフォルダに格納: screenshots/{period}/{code}/{日付}_cat{ID}_{カテゴリ}.png
                    code = top["code"]
                    subdir = os.path.join("screenshots", period, code)
                    os.makedirs(os.path.join(BASE, subdir), exist_ok=True)
                    rel = os.path.join(subdir, f"{stamp}_cat{cat_id}_{sanitize(rk['category_name'])}.png")
                    shot_ok = shot_top_row(page, os.path.join(BASE, rel))
                    if not shot_ok:
                        print(f"    ※ {period} 1位 {code} のスクショ取得失敗（受賞は記録）")
                    # スクショ成否に関わらず受賞は記録（画像は撮れた場合のみパス）
                    winners[period].append({
                        "category_id": cat_id,
                        "category_name": rk["category_name"],
                        "code": code, "title": top["title"],
                        "update_label": rk["update_label"],
                        "screenshot": rel.replace(os.sep, "/") if shot_ok else ""})
            print(" ".join(line) + f" [{mapping.get(next(iter(our_in_cat)),{}).get('title','')[:14]}]")

        # 履歴CSV追記（period 列を含む）
        new_file = not os.path.exists(HISTORY_CSV)
        with open(HISTORY_CSV, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["datetime_jst", "period", "category_id",
                            "category_name", "item_code", "rank", "title"])
            w.writerows(rows)

        # latest.json は既存を読み込み、今回取得した期間だけ差し替える（分割実行対応）
        latest = {}
        if os.path.exists(LATEST_JSON):
            try:
                latest = json.load(open(LATEST_JSON, encoding="utf-8"))
            except Exception:
                latest = {}
        latest["run_at"] = ts.isoformat()
        latest["categories_checked"] = len(cats)
        for pk, _ in run_periods:
            latest[pk] = winners[pk]
            latest[pk + "_updated"] = ts.isoformat()
        for pk, _ in PERIODS:               # 未実行期間もキーは保持
            latest.setdefault(pk, [])
        json.dump(latest, open(LATEST_JSON, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        wins = compute_win_stats(mapping)
        generate_dashboard(latest, wins)

        print("\n[結果] (取得: " + "/".join(l for _, l in run_periods) + ")")
        for pk, label in run_periods:
            print(f"  {label}: 今回1位 {len(winners[pk])}件")
        print(f"  順位記録 {len(rows)} 行 / 管理画面: index.html")
        browser.close()


if __name__ == "__main__":
    main()
