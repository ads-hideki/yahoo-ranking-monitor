# -*- coding: utf-8 -*-
"""
毎朝9時の通知メールを組み立てる。
- デイリー: その日のデイリー1位（最新スナップショット＝latest.json）
- リアルタイム: 直近ウィンドウ（前日〜当朝＝直近WINDOW_HOURS時間）に
                「1度でも1位になった」商品をすべて（history.csv から集計）

画像は添付せず、GitHub Pages 上のスクショURLを本文に埋め込む（メール本体は軽量）。
出力（同フォルダ）:
  email_subject.txt  … 件名（1行）
  email_body.html    … 本文HTML（末尾改行あり）
  email_images.txt   … 本文で参照する画像URL（1行1URL。送信前の公開待ちに使用）
"""
import os, csv, json, glob, html, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(BASE, "data", "history.csv")
PRODUCTS = os.path.join(BASE, "data", "products.json")
LATEST = os.path.join(BASE, "data", "latest.json")
STORE = "annekor1"
DASH_URL = "https://ads-hideki.github.io/yahoo-ranking-monitor/"
WINDOW_HOURS = 24  # リアルタイム集計ウィンドウ（前日9時〜当日9時相当）
JST = datetime.timezone(datetime.timedelta(hours=9))


def load_json(path, default):
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return default


def find_shot_url(period, cat_id, code):
    """該当商品の最新スクショの Pages 公開URL（無ければ空）
    新: screenshots/{period}/{code}/*.png ／ 旧: screenshots/{period}/*_{code}.png"""
    files = sorted(glob.glob(os.path.join(BASE, "screenshots", period, code, "*.png")))
    if not files:  # 旧フラット構造も一応拾う
        files = sorted(glob.glob(os.path.join(BASE, "screenshots", period, f"*_cat{cat_id}_*_{code}.png")))
    if not files:
        return ""
    rel = os.path.relpath(files[-1], BASE).replace(os.sep, "/")
    return DASH_URL + rel


def realtime_wins(now, mapping):
    start = now - datetime.timedelta(hours=WINDOW_HOURS)
    wins = {}
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if row.get("period") != "realtime" or str(row.get("rank")) != "1":
                continue
            try:
                dt = datetime.datetime.fromisoformat(row["datetime_jst"])
            except Exception:
                continue
            if dt < start:
                continue
            cat_id = row.get("category_id", "")
            code = row.get("item_code", "")
            key = (cat_id, code)
            rec = wins.get(key)
            if not rec:
                rec = {"category_id": cat_id, "code": code,
                       "category_name": row.get("category_name", ""),
                       "title": mapping.get(code.lower(), {}).get("title") or row.get("title", ""),
                       "count": 0, "first": dt, "last": dt}
                wins[key] = rec
            rec["count"] += 1
            rec["first"] = min(rec["first"], dt)
            rec["last"] = max(rec["last"], dt)
    return sorted(wins.values(), key=lambda r: r["first"])


def item_html(w, period, extra=""):
    cat = html.escape(w.get("category_name", ""))
    title = html.escape(w.get("title", ""))
    code = w.get("code", "")
    cat_id = w.get("category_id", "")
    rank_url = f"https://shopping.yahoo.co.jp/categoryranking/{cat_id}/list"
    item_url = f"https://store.shopping.yahoo.co.jp/{STORE}/{html.escape(code)}.html"
    url = find_shot_url(period, cat_id, code)
    img = (f'<div><img src="{html.escape(url)}" alt="{title}" width="640" '
           f'style="width:100%;max-width:640px;height:auto;border:1px solid #eee;'
           f'border-radius:6px;margin:6px 0"></div>' if url else "")
    body = (f'<div style="margin:16px 0;padding-bottom:12px;border-bottom:1px solid #eee">'
            f'<div style="font-size:15px"><b style="color:#c8102e">{cat}</b> で1位 🏆{extra}</div>'
            f'{img}'
            f'<div style="font-size:13px;margin-top:4px">{title}</div>'
            f'<div style="font-size:12px;margin-top:2px">'
            f'<a href="{item_url}">商品ページ</a>　|　<a href="{rank_url}">ランキングページ</a></div></div>')
    return body, url


def kw_item_html(w):
    kw = html.escape(w.get("keyword", ""))
    catl = html.escape(w.get("cat_label", ""))
    title = html.escape(w.get("title", ""))
    code = w.get("code", "")
    shot = w.get("screenshot", "")
    url = (DASH_URL + shot) if shot else ""
    item_url = f"https://store.shopping.yahoo.co.jp/{STORE}/{html.escape(code)}.html"
    img = (f'<div><img src="{html.escape(url)}" alt="{title}" width="640" '
           f'style="width:100%;max-width:640px;height:auto;border:1px solid #eee;'
           f'border-radius:6px;margin:6px 0"></div>' if url else "")
    label = "「" + kw + "」" + (f"（{catl}）" if catl else "") + " で1位 🏆"
    body = (f'<div style="margin:16px 0;padding-bottom:12px;border-bottom:1px solid #eee">'
            f'<div style="font-size:15px"><b style="color:#c8102e">{label}</b></div>'
            f'{img}'
            f'<div style="font-size:13px;margin-top:4px">{title}</div>'
            f'<div style="font-size:12px;margin-top:2px"><a href="{item_url}">商品ページ</a></div></div>')
    return body, url


def main():
    mapping = load_json(PRODUCTS, {})
    latest = load_json(LATEST, {})
    now = datetime.datetime.now(JST)
    dstr = f"{now.month}月{now.day}日"

    daily = latest.get("daily", [])
    rts = realtime_wins(now, mapping)

    image_urls, daily_html, rt_html = [], [], []
    for w in daily:
        h, url = item_html(w, "daily")
        daily_html.append(h)
        if url:
            image_urls.append(url)
    for w in rts:
        extra = f'（{w["first"].strftime("%m/%d %H:%M")}〜 / 期間中{w["count"]}回）'
        h, url = item_html(w, "realtime", extra)
        rt_html.append(h)
        if url:
            image_urls.append(url)
    # キーワードは件数が多くなるため、商品ごとにまとめたテキスト一覧にする（画像はダッシュボード）
    kw = latest.get("keyword", [])
    kw_groups = {}
    for w in kw:
        g = kw_groups.setdefault(w.get("code", ""), {
            "title": w.get("title", ""), "cat": w.get("cat_label", ""), "kws": []})
        g["kws"].append(w.get("keyword", ""))
    kw_block = ""
    for code, g in kw_groups.items():
        kws = "、".join("「" + html.escape(k) + "」" for k in g["kws"])
        item_url = f"https://store.shopping.yahoo.co.jp/{STORE}/{html.escape(code)}.html"
        kw_block += (f'<div style="margin:10px 0;padding-bottom:8px;border-bottom:1px solid #eee">'
                     f'<b style="color:#c8102e">{html.escape(g["title"][:44])}</b>'
                     f'<span style="font-size:12px;color:#888">（{html.escape(g["cat"])}）</span><br>'
                     f'<span style="font-size:13px">{kws} で🏆1位</span>　'
                     f'<a href="{item_url}" style="font-size:12px">商品ページ</a></div>')
    kw_html = [kw_block] if kw else []

    def section(label, n, items):
        head = (f'<h3 style="border-left:5px solid #c8102e;padding-left:8px;'
                f'font-size:16px">{label} {n}件</h3>')
        if not items:
            return head + '<p style="color:#888">該当なし</p>'
        return head + "".join(items)

    subject = f"【Yahoo1位】{dstr}分 デイリー{len(daily)}件・リアルタイム{len(rts)}件・キーワード{len(kw)}件"
    body = f"""<div style="font-family:'Hiragino Sans','Meiryo',sans-serif;color:#222;max-width:680px">
  <div style="background:#1f2d50;color:#fff;padding:18px 20px;border-radius:8px 8px 0 0">
    <div style="font-size:20px;font-weight:bold">🏆 ランキング1位速報</div>
    <div style="font-size:13px;opacity:.85;margin-top:4px">{dstr}分 / annekor1 カテゴリランキング</div>
  </div>
  <div style="padding:6px 4px">
    <p style="font-size:13px;color:#555">デイリー＝当日の1位／リアルタイム＝直近{WINDOW_HOURS}時間に1度でも1位になった商品／キーワード＝キーワード検索での1位（画像は管理画面）。</p>
    {section("デイリーランキング", len(daily), daily_html)}
    {section("リアルタイムランキング", len(rts), rt_html)}
    {section("キーワードランキング", len(kw), kw_html)}
    <hr>
    <p>最新の一覧はこちら → <a href="{DASH_URL}">管理画面ダッシュボード</a></p>
    <p style="color:#999;font-size:12px">毎朝9時に自動送信。画像が表示されない場合はメール上部の「画像を表示」をクリックしてください。</p>
  </div>
</div>
"""

    # 重複除去した画像URL（送信前の公開待ち用）
    seen, urls = set(), []
    for u in image_urls:
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    open(os.path.join(BASE, "email_subject.txt"), "w", encoding="utf-8").write(subject)
    open(os.path.join(BASE, "email_body.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(BASE, "email_images.txt"), "w", encoding="utf-8").write("\n".join(urls))
    print("件名:", subject)
    print(f"デイリー {len(daily)}件 / リアルタイム {len(rts)}件 / キーワード {len(kw)}件 / 埋め込み画像 {len(urls)}件")


if __name__ == "__main__":
    main()
