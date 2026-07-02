# -*- coding: utf-8 -*-
"""
Yahoo!ショッピング カテゴリランキング 1位監視システム
------------------------------------------------------
annekor1 店舗の全商品について、各商品が属する Yahoo カテゴリの
「カテゴリランキング（デイリー）」を巡回し、自店商品が1位を獲得した場合に
その順位を示すスクリーンショットを保存する。

- 全商品リスト  : /annekor1/search.html を b= オフセットで巡回して取得
- 商品→カテゴリ : 各商品ページの "categoryId":"NNN" を抽出
- 順位判定      : https://shopping.yahoo.co.jp/categoryranking/{cat}/list の
                  メインランキング(crk01_01)の並び順で判定
- 1位検知時     : ランキングページ上部のスクショを screenshots/ に保存

使い方:
    python monitor.py            # 通常実行（マッピングはキャッシュを使用、無ければ自動生成）
    python monitor.py --refresh  # 商品→カテゴリのマッピングを作り直してから実行
    python monitor.py --map-only # マッピング生成のみ（順位チェックしない）
"""
import os, re, sys, csv, json, argparse, datetime
from playwright.sync_api import sync_playwright

# ---- 設定 -----------------------------------------------------------------
STORE = "annekor1"
PERIOD = "daily"  # daily=デイリー（1日2回監視向け）。realtime/annual も指定可
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
SHOT_DIR = os.path.join(BASE, "screenshots")
PRODUCTS_JSON = os.path.join(DATA_DIR, "products.json")
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")
WINS_JSON = os.path.join(DATA_DIR, "wins.json")

NAV_CODES = {"guide", "info", "search", "index", "store", "user",
             "review", "company", "law", "privacy", "category"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst():
    return datetime.datetime.now(JST)


def sanitize(s, n=40):
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
    """商品ページから categoryId を抽出"""
    page.goto(f"https://store.shopping.yahoo.co.jp/{STORE}/{code}.html",
              wait_until="domcontentloaded", timeout=60000)
    html = page.content()
    m = re.search(r'"categoryId"\s*:\s*"?(\d+)"?', html)
    if not m:
        page.wait_for_timeout(1500)
        html = page.content()
        m = re.search(r'"categoryId"\s*:\s*"?(\d+)"?', html)
    return m.group(1) if m else None


def build_mapping(page, refresh=False):
    """products.json を読み込み、無い/未取得のものだけカテゴリ取得"""
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
    # 消えた商品は残しても害はないが、現存フラグを付ける
    for code in mapping:
        mapping[code]["active"] = code in titles
    os.makedirs(DATA_DIR, exist_ok=True)
    json.dump(mapping, open(PRODUCTS_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return mapping


# ---- ランキング取得 --------------------------------------------------------
def fetch_ranking(page, cat_id):
    """カテゴリランキングページを開き、メインランキングの並びを返す。
    return: dict(category_name, update_date, items=[{rank,store,code,url,title}])"""
    url = f"https://shopping.yahoo.co.jp/categoryranking/{cat_id}/list"
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(1200)
    # デイリー以外を選ぶ場合はここでタブ操作（デフォルトはデイリー）
    # 上位を読み込むため軽くスクロール
    for _ in range(3):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(400)
    page.mouse.wheel(0, -20000)
    page.wait_for_timeout(300)

    items = page.eval_on_selector_all(
        "a[href*='ranking-crk01_01']",
        """(as) => as.map(a => {
             const h = a.getAttribute('href') || '';
             const m = h.match(/store\\.shopping\\.yahoo\\.co\\.jp\\/([^\\/]+)\\/([A-Za-z0-9_\\-]+)\\.html/);
             if(!m) return null;
             const img = a.querySelector('img');
             return {store:m[1], code:m[2],
                     url:h.split('?')[0],
                     title:(img?img.getAttribute('alt'):'')||a.innerText||''};
           }).filter(Boolean)""")
    # 出現順で重複排除 → rank付与
    seen, ordered = set(), []
    for it in items:
        key = (it["store"], it["code"])
        if key in seen:
            continue
        seen.add(key)
        it["rank"] = len(ordered) + 1
        it["title"] = (it["title"] or "").strip()
        ordered.append(it)

    title = page.title() or ""
    cat_name = re.sub(r"^【[^】]*】", "", title)
    cat_name = re.sub(r"の(おすすめ人気)?ランキング.*$", "", cat_name).strip()
    md = re.search(r"更新日[:：]?\s*([\d]{4}[/／][\d]{1,2}[/／][\d]{1,2})", page.content())
    return {"category_id": cat_id, "category_name": cat_name,
            "update_date": md.group(1) if md else "", "items": ordered}


def compute_win_stats(mapping):
    """history.csv から各商品の『1位獲得回数』を集計して wins.json に保存。
    1回=監視スロット（朝/夜）単位。Yahooのデイリー更新が1日2回のため、
    同じスロットでの手動再実行を重複カウントしないよう (商品, 日付, 朝/夜) で排除する。"""
    if not os.path.exists(HISTORY_CSV):
        return {}
    stats = {}          # code -> dict
    seen = set()        # (code, date, slot) 重複排除
    with open(HISTORY_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if str(row.get("rank")) != "1":
                continue
            code = (row.get("item_code") or "").lower()
            try:
                dt = datetime.datetime.fromisoformat(row["datetime_jst"])
            except Exception:
                continue
            date = dt.strftime("%Y-%m-%d")
            slot = "朝" if dt.hour < 14 else "夜"
            key = (code, date, slot)
            if key in seen:
                continue
            seen.add(key)
            s = stats.setdefault(code, {"count": 0, "events": [],
                                        "first": date, "last": date})
            s["count"] += 1
            s["events"].append(f"{date} {slot}")
            s["first"] = min(s["first"], date)
            s["last"] = max(s["last"], date)
            s["category_name"] = row.get("category_name", "")
            s["category_id"] = row.get("category_id", "")
    # タイトルは現行マッピング優先
    for code, s in stats.items():
        s["title"] = mapping.get(code, {}).get("title") or ""
    ordered = dict(sorted(stats.items(), key=lambda kv: kv[1]["count"], reverse=True))
    out = {"generated_at": now_jst().isoformat(),
           "note": "count = 1位を観測した監視スロット数（朝/夜単位）。",
           "products": ordered}
    json.dump(out, open(WINS_JSON, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return ordered


def screenshot_top(page, path):
    """ランキングページ上部（順位・カテゴリ名・更新日が写る範囲）を保存"""
    page.mouse.wheel(0, -50000)
    page.wait_for_timeout(500)
    page.screenshot(path=path, clip={"x": 0, "y": 0, "width": 1280, "height": 1500})


# ---- メイン ---------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="商品→カテゴリを作り直す")
    ap.add_argument("--map-only", action="store_true", help="マッピングのみ")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(SHOT_DIR, exist_ok=True)
    ts = now_jst()
    stamp = ts.strftime("%Y%m%d_%H%M")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 1500},
            user_agent=UA, locale="ja-JP")

        mapping = build_mapping(page, refresh=args.refresh)
        if args.map_only:
            browser.close()
            print("map-only 完了")
            return

        # 現存商品を categoryId でグループ化
        our_codes = {c for c, r in mapping.items()
                     if r.get("active") and r.get("categoryId")}
        cats = {}
        for c in our_codes:
            cats.setdefault(mapping[c]["categoryId"], []).append(c)
        print(f"[monitor] 対象カテゴリ {len(cats)} 種 / 対象商品 {len(our_codes)} 件")

        rows, winners = [], []
        for cat_id, codes in sorted(cats.items()):
            try:
                rk = fetch_ranking(page, cat_id)
            except Exception as e:
                print(f"  cat {cat_id}: 取得失敗 {e}")
                continue
            # このカテゴリで自店商品の順位を探す
            our_in_cat = {c.lower() for c in codes}
            hits = [it for it in rk["items"]
                    if it["store"] == STORE and it["code"].lower() in our_in_cat]
            top = rk["items"][0] if rk["items"] else None
            is_top_ours = bool(top and top["store"] == STORE
                               and top["code"].lower() in our_in_cat)
            best = min([h["rank"] for h in hits], default=None)
            print(f"  cat {cat_id} [{rk['category_name']}] "
                  f"自店最高={best if best else '圏外'}位 "
                  f"{'★1位獲得!' if is_top_ours else ''}")

            for it in hits:
                rows.append([ts.isoformat(), cat_id, rk["category_name"],
                             it["code"], it["rank"], mapping.get(it['code'].lower(), {}).get('title', it['title'])])
            if is_top_ours:
                fname = f"{stamp}_cat{cat_id}_{sanitize(rk['category_name'],20)}_{top['code']}_1i.png"
                path = os.path.join(SHOT_DIR, fname)
                screenshot_top(page, path)
                winners.append({"category_id": cat_id,
                                "category_name": rk["category_name"],
                                "code": top["code"], "title": top["title"],
                                "update_date": rk["update_date"],
                                "screenshot": os.path.relpath(path, BASE).replace(os.sep, "/")})
                print(f"    -> スクショ保存: {fname}")

        # 履歴CSV追記
        new_file = not os.path.exists(HISTORY_CSV)
        with open(HISTORY_CSV, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["datetime_jst", "category_id", "category_name",
                            "item_code", "rank", "title"])
            w.writerows(rows)

        json.dump({"run_at": ts.isoformat(), "period": PERIOD,
                   "categories_checked": len(cats),
                   "winners": winners}, open(LATEST_JSON, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        # 1位獲得回数の累計を集計
        wins = compute_win_stats(mapping)

        print(f"\n[結果] 今回1位 {len(winners)} 件 / 順位記録 {len(rows)} 行")
        if wins:
            print("[累計1位獲得回数（朝/夜スロット単位）]")
            for code, s in wins.items():
                print(f"  {s['count']:3d}回  {code} [{s.get('category_name','')}] "
                      f"{s['first']}〜{s['last']}")
        browser.close()


if __name__ == "__main__":
    main()
