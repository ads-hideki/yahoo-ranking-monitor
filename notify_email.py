# -*- coding: utf-8 -*-
"""
毎朝9時の通知メールを組み立てる。
- デイリー: その日のデイリー1位（最新スナップショット＝latest.json）
- リアルタイム: 直近ウィンドウ（前日〜当朝＝直近WINDOW_HOURS時間）に
                「1度でも1位になった」商品をすべて（history.csv から集計）

各1位商品の1位スクショを添付する。
出力（同フォルダ）:
  email_subject.txt  … 件名（1行）
  email_body.html    … 本文HTML
  email_attach.txt   … 添付スクショのパス（カンマ区切り、無ければ空）
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


def find_shot(period, cat_id, code):
    """screenshots/{period}/ から該当商品の最新スクショ(相対パス)を探す"""
    # ファイル名は {日付}_cat{ID}_{カテゴリ名}_{コード}.png
    pat = os.path.join(BASE, "screenshots", period, f"*_cat{cat_id}_*_{code}.png")
    files = sorted(glob.glob(pat))
    if files:
        return os.path.relpath(files[-1], BASE).replace(os.sep, "/")
    return ""


def realtime_wins(now, mapping):
    """直近WINDOW_HOURS時間に1位になったリアルタイム商品を集計（重複排除）"""
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
    # 最初に1位になった時刻順
    return sorted(wins.values(), key=lambda r: r["first"])


def item_html(w, period, extra=""):
    cat = html.escape(w.get("category_name", ""))
    title = html.escape(w.get("title", ""))
    code = w.get("code", "")
    cat_id = w.get("category_id", "")
    rank_url = f"https://shopping.yahoo.co.jp/categoryranking/{cat_id}/list"
    item_url = f"https://store.shopping.yahoo.co.jp/{STORE}/{html.escape(code)}.html"
    shot = find_shot(period, cat_id, code)
    img = (f'<div><img src="{DASH_URL}{html.escape(shot)}" alt="{title}" '
           f'style="max-width:100%;border:1px solid #eee;border-radius:6px;margin:4px 0"></div>'
           if shot else "")
    return (f'<div style="margin:14px 0;padding-bottom:10px;border-bottom:1px solid #eee">'
            f'<div><b style="color:#c8102e">{cat}</b> で1位 🏆{extra}</div>'
            f'{img}'
            f'<div style="font-size:13px;margin-top:4px">{title}</div>'
            f'<div style="font-size:12px"><a href="{item_url}">商品ページ</a>　|　'
            f'<a href="{rank_url}">ランキングページ</a></div></div>'), shot


def main():
    mapping = load_json(PRODUCTS, {})
    latest = load_json(LATEST, {})
    now = datetime.datetime.now(JST)
    dstr = f"{now.month}月{now.day}日"

    daily = latest.get("daily", [])
    rts = realtime_wins(now, mapping)

    attach = []
    daily_html = []
    for w in daily:
        h, shot = item_html(w, "daily")
        daily_html.append(h)
        if shot:
            attach.append(shot)
    rt_html = []
    for w in rts:
        extra = f'（{w["first"].strftime("%m/%d %H:%M")}〜 / 期間中{w["count"]}回）'
        h, shot = item_html(w, "realtime", extra)
        rt_html.append(h)
        if shot:
            attach.append(shot)

    def section(label, n, items):
        head = f'<h3 style="border-left:5px solid #c8102e;padding-left:8px">{label} {n}件</h3>'
        if not items:
            return head + '<p style="color:#888">該当なし</p>'
        return head + "".join(items)

    subject = f"【Yahoo1位】{dstr}分 デイリー{len(daily)}件・リアルタイム{len(rts)}件"
    body = f"""<div style="font-family:'Hiragino Sans','Meiryo',sans-serif;color:#222;max-width:680px">
  <h2 style="margin:0 0 4px">{dstr}分 ランキング1位</h2>
  <p style="color:#666;font-size:13px;margin:0 0 12px">annekor1 カテゴリランキング速報（リアルタイムは直近{WINDOW_HOURS}時間に1度でも1位になった商品）</p>
  {section("デイリー", len(daily), daily_html)}
  {section("リアルタイム", len(rts), rt_html)}
  <hr>
  <p>スクショ付き最新一覧 → <a href="{DASH_URL}">管理画面ダッシュボード</a></p>
  <p style="color:#999;font-size:12px">毎朝9時に自動送信。スクショは本文（表示されない場合は添付）を参照。</p>
</div>"""

    # 重複除去して添付
    seen, attach_u = set(), []
    for a in attach:
        if a and a not in seen and os.path.exists(os.path.join(BASE, a)):
            seen.add(a)
            attach_u.append(a)

    open(os.path.join(BASE, "email_subject.txt"), "w", encoding="utf-8").write(subject)
    open(os.path.join(BASE, "email_body.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(BASE, "email_attach.txt"), "w", encoding="utf-8").write(",".join(attach_u))
    print("件名:", subject)
    print(f"デイリー {len(daily)}件 / リアルタイム {len(rts)}件 / 添付 {len(attach_u)}件")


if __name__ == "__main__":
    main()
