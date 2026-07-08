# -*- coding: utf-8 -*-
"""
GitHub 上の screenshots/ から、KEEP_DAYS 日より古いスクショを削除する。
（クラウド軽量化用。Z: 側は sync スクリプトが別途アーカイブ保存するため消えない）
ファイル名先頭の YYYYMMDD で判定。空になった品番フォルダも削除。
"""
import os, re, glob, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
SHOT_DIR = os.path.join(BASE, "screenshots")
KEEP_DAYS = 14
JST = datetime.timezone(datetime.timedelta(hours=9))


def main():
    cutoff = (datetime.datetime.now(JST).date()
              - datetime.timedelta(days=KEEP_DAYS))
    removed = 0
    for period in ("daily", "realtime", "keyword"):
        pdir = os.path.join(SHOT_DIR, period)
        if not os.path.isdir(pdir):
            continue
        for f in glob.glob(os.path.join(pdir, "*", "*.png")):
            m = re.match(r"(\d{8})_", os.path.basename(f))
            if not m:
                continue
            try:
                d = datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
            except ValueError:
                continue
            if d < cutoff:
                os.remove(f)
                removed += 1
        # 空になった品番フォルダを削除
        for code_dir in glob.glob(os.path.join(pdir, "*")):
            if os.path.isdir(code_dir) and not os.listdir(code_dir):
                os.rmdir(code_dir)
    print(f"[prune] {KEEP_DAYS}日より古いスクショ {removed} 件を削除（cutoff={cutoff}）")


if __name__ == "__main__":
    main()
