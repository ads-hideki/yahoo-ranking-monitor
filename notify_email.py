# -*- coding: utf-8 -*-
"""
data/latest.json を読み、デイリー/リアルタイムの1位商品を通知メール用に整形する。
出力（同フォルダ）:
  email_subject.txt  … 件名（1行）
  email_body.html    … 本文HTML
  email_attach.txt   … 添付する1位スクショのパス（カンマ区切り、無ければ空）
GitHub Actions のメール送信ステップがこれらを読み込む。
"""
import os, re, json, html, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LATEST = os.path.join(BASE, "data", "latest.json")
STORE = "annekor1"
DASH_URL = "https://ads-hideki.github.io/yahoo-ranking-monitor/"

PERIOD_LABELS = [("daily", "デイリー"), ("realtime", "リアルタイム")]


def load():
    if os.path.exists(LATEST):
        return json.load(open(LATEST, encoding="utf-8"))
    return {}


def item_html(w):
    cat = html.escape(w.get("category_name", ""))
    title = html.escape(w.get("title", ""))
    code = w.get("code", "")
    cat_id = w.get("category_id", "")
    rank_url = f"https://shopping.yahoo.co.jp/categoryranking/{cat_id}/list"
    item_url = f"https://store.shopping.yahoo.co.jp/{STORE}/{html.escape(code)}.html"
    return (f'<li style="margin:8px 0;line-height:1.5">'
            f'<b style="color:#c8102e">{cat}</b> で1位 🏆<br>'
            f'<span style="font-size:13px">{title}</span><br>'
            f'<a href="{item_url}">商品ページ</a>　|　'
            f'<a href="{rank_url}">ランキングページ</a></li>')


def section_html(label, winners):
    if not winners:
        return f'<h3>{label}</h3><p style="color:#888">本日、1位の商品はありません。</p>'
    lis = "\n".join(item_html(w) for w in winners)
    return f'<h3>{label}（{len(winners)}件）</h3><ul style="padding-left:18px">{lis}</ul>'


def main():
    latest = load()
    daily = latest.get("daily", [])
    realtime = latest.get("realtime", [])

    # 日付（run_at から）
    try:
        d = datetime.datetime.fromisoformat(latest.get("run_at", "")).strftime("%-m/%-d")
    except Exception:
        try:
            d = datetime.datetime.fromisoformat(latest.get("run_at", "")).strftime("%m/%d")
        except Exception:
            d = ""

    subject = f"【Yahoo1位】デイリー{len(daily)}件・リアルタイム{len(realtime)}件 {d}".strip()

    sections = "\n".join(
        section_html(lbl, latest.get(k, [])) for k, lbl in PERIOD_LABELS)
    body = f"""<div style="font-family:'Hiragino Sans','Meiryo',sans-serif;color:#222">
  <p>annekor1 のカテゴリランキング 1位速報です。</p>
  {sections}
  <hr>
  <p>スクショ付きの一覧はこちら → <a href="{DASH_URL}">管理画面ダッシュボード</a></p>
  <p style="color:#999;font-size:12px">このメールは毎朝9時に自動送信されています。</p>
</div>"""

    # 添付（現在の1位スクショ）
    attach = []
    for k, _ in PERIOD_LABELS:
        for w in latest.get(k, []):
            p = w.get("screenshot", "")
            if p and os.path.exists(os.path.join(BASE, p)):
                attach.append(p)

    open(os.path.join(BASE, "email_subject.txt"), "w", encoding="utf-8").write(subject)
    open(os.path.join(BASE, "email_body.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(BASE, "email_attach.txt"), "w", encoding="utf-8").write(",".join(attach))
    print("件名:", subject)
    print("添付:", len(attach), "件")


if __name__ == "__main__":
    main()
