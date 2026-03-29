#!/usr/bin/env python3
"""Parse WeChat and Alipay CSV exports into unified JSON.

Usage:
    python parse_bills.py wechat bill1.csv [bill2.csv ...] --output parsed.json
    python parse_bills.py alipay bill1.csv [bill2.csv ...] --output parsed.json
    python parse_bills.py auto   bill1.csv bill2.csv      --output parsed.json

Auto mode detects source by filename or file content.
"""

import sys
import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
try:
    import openpyxl
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

# ---------------------------------------------------------------------------
# Categorization rules — (category, [keywords])
# Order matters: first match wins.
# ---------------------------------------------------------------------------
CATEGORY_RULES = [
    ("餐饮美食",  ["美团", "饿了么", "肯德基", "麦当劳", "星巴克", "瑞幸", "外卖",
                   "餐饮", "超市", "便利店", "711", "罗森", "全家", "沙县", "火锅",
                   "奶茶", "喜茶", "蜜雪", "咖啡", "快餐", "盒马", "叮咚", "朴朴"]),
    ("交通出行",  ["滴滴", "地铁", "公交", "加油", "停车", "打车", "顺风车", "高铁",
                   "铁路", "12306", "机票", "高速", "ETC", "航空", "携程", "飞猪",
                   "曹操", "T3出行", "神州"]),
    ("购物消费",  ["淘宝", "天猫", "京东", "拼多多", "抖音小店", "闲鱼", "唯品会",
                   "得物", "苏宁", "当当", "亚马逊", "SHEIN"]),
    ("生活缴费",  ["水电", "燃气", "物业", "话费", "宽带", "电费", "水费",
                   "中国电信", "中国移动", "中国联通", "国家电网", "自来水"]),
    ("医疗健康",  ["药店", "医院", "诊所", "健身", "医疗", "大药房", "体检",
                   "药房", "keep", "clinic"]),
    ("娱乐休闲",  ["电影", "游戏", "爱奇艺", "优酷", "腾讯视频", "哔哩哔哩", "B站",
                   "网易云音乐", "Spotify", "Netflix", "Steam", "KTV", "剧本",
                   "密室", "livehouse"]),
    ("教育学习",  ["课程", "培训", "教育", "图书", "Kindle", "得到", "知乎",
                   "樊登", "掌阅", "多邻国", "新东方"]),
    ("数字服务",  ["阿里云", "腾讯云", "AWS", "OpenAI", "Anthropic", "Claude",
                   "ChatGPT", "GitHub", "Notion", "域名", "vercel", "Cloudflare",
                   "iCloud", "Google One", "百度网盘", "会员"]),
    ("住房居家",  ["房租", "租金", "家居", "宜家", "家电", "物业费", "中介"]),
    ("转账红包",  ["转账", "红包", "还款", "借款", "二维码收款"]),
]

SKIP_STATUSES = {
    "已全额退款", "对方已退还", "交易关闭", "已关闭",
    "退款成功", "TRADE_CLOSED", "closed",
}


def categorize(counterparty: str, description: str) -> str:
    text = (counterparty + " " + description).lower()
    for category, keywords in CATEGORY_RULES:
        if any(k.lower() in text for k in keywords):
            return category
    return "其他"


def week_label(date_str: str) -> str:
    """Return week label like '第1周(1-7日)' from an ISO or '2025-01-15 ...' date string."""
    try:
        day = int(date_str[8:10])
        if day <= 7:
            return "第1周(1-7日)"
        elif day <= 14:
            return "第2周(8-14日)"
        elif day <= 21:
            return "第3周(15-21日)"
        elif day <= 28:
            return "第4周(22-28日)"
        else:
            return "第5周(29日+)"
    except Exception:
        return "未知"


def _clean_amount(raw: str) -> float:
    """Strip currency symbols and convert to float."""
    return float(raw.strip().lstrip("¥").lstrip("￥").replace(",", ""))


def parse_wechat(path: str) -> list:
    """Parse WeChat Pay CSV export.

    WeChat CSV structure:
      - First ~16 lines: metadata / summary block (skip until line starting with '交易时间')
      - Columns: 交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注
    """
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        lines = f.readlines()

    # Find header row
    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("交易时间")),
        None
    )
    if header_idx is None:
        raise ValueError(f"Cannot find header row in WeChat file: {path}")

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        status = row.get("当前状态", "").strip()
        if status in SKIP_STATUSES:
            continue
        direction = row.get("收/支", "").strip()
        if direction not in ("支出", "收入"):
            continue
        try:
            amount = _clean_amount(row["金额(元)"])
        except (ValueError, KeyError):
            continue
        counterparty = row.get("交易对方", "").strip()
        description = row.get("商品", "").strip()
        rows.append({
            "date":         row["交易时间"].strip(),
            "counterparty": counterparty,
            "description":  description,
            "direction":    direction,
            "amount":       amount,
            "method":       row.get("支付方式", "").strip(),
            "status":       status,
            "tx_id":        row.get("交易单号", "").strip(),
            "source":       "微信",
            "category":     categorize(counterparty, description),
            "week":         week_label(row["交易时间"].strip()),
        })
    return rows


def parse_alipay(path: str) -> list:
    """Parse Alipay CSV export.

    Alipay CSV structure:
      - First ~24 lines: metadata block (skip until line starting with '交易时间')
      - Columns: 交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注
    """
    rows = []
    with open(path, encoding="gbk", errors="replace") as f:
        lines = f.readlines()

    header_idx = next(
        (i for i, line in enumerate(lines) if line.strip().startswith("交易时间")),
        None
    )
    if header_idx is None:
        raise ValueError(f"Cannot find header row in Alipay file: {path}")

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        status = row.get("交易状态", "").strip()
        if any(s in status for s in SKIP_STATUSES):
            continue
        direction = row.get("收/支", "").strip()
        if direction not in ("支出", "收入"):
            continue
        try:
            amount = _clean_amount(row["金额"])
        except (ValueError, KeyError):
            continue
        counterparty = row.get("交易对方", "").strip()
        description = row.get("商品说明", "").strip()
        alipay_category = row.get("交易分类", "").strip()
        rows.append({
            "date":             row["交易时间"].strip(),
            "counterparty":     counterparty,
            "description":      description,
            "direction":        direction,
            "amount":           amount,
            "method":           row.get("收/付款方式", "").strip(),
            "status":           status,
            "tx_id":            row.get("交易订单号", "").strip(),
            "source":           "支付宝",
            "alipay_category":  alipay_category,
            "category":         categorize(counterparty, description),
            "week":             week_label(row["交易时间"].strip()),
        })
    return rows


def detect_source(path: str) -> str:
    name = Path(path).name.lower()
    if "wechat" in name or "微信" in name:
        return "wechat"
    if "alipay" in name or "支付宝" in name:
        return "alipay"
    # Peek at first line
    try:
        with open(path, encoding="utf-8-sig") as f:
            first = f.read(200)
        if "微信支付" in first:
            return "wechat"
    except Exception:
        pass
    try:
        with open(path, encoding="gbk") as f:
            first = f.read(200)
        if "支付宝" in first:
            return "alipay"
    except Exception:
        pass
    raise ValueError(f"Cannot detect source for: {path}. Use 'wechat' or 'alipay' mode explicitly.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["wechat", "alipay", "auto"])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--output", default="parsed.json")
    args = parser.parse_args()

    all_rows = []
    for path in args.files:
        src = args.source if args.source != "auto" else detect_source(path)
        if src == "wechat":
            rows = parse_wechat(path)
        else:
            rows = parse_alipay(path)
        all_rows.extend(rows)
        print(f"  {Path(path).name}: {len(rows)} transactions ({src})", file=sys.stderr)

    # Sort by date descending
    all_rows.sort(key=lambda r: r["date"], reverse=True)

    # Summary stats
    expenses = [r for r in all_rows if r["direction"] == "支出"]
    income   = [r for r in all_rows if r["direction"] == "收入"]
    print(f"\nTotal: {len(all_rows)} transactions", file=sys.stderr)
    print(f"  Expenses: {len(expenses)}, total ¥{sum(r['amount'] for r in expenses):.2f}", file=sys.stderr)
    print(f"  Income:   {len(income)},   total ¥{sum(r['amount'] for r in income):.2f}", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
