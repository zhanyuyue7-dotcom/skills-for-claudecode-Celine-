#!/usr/bin/env python3
"""Upload parsed bill JSON to Feishu Bitable.

Creates:
  Base: "YYYY年MM月 账单汇总"
  Table 1 (分类汇总): one row per category, totals + expense/income breakdown
  Table 2 (交易明细): one row per transaction, 关联分类 links to Table 1

Usage:
    python upload_to_feishu.py parsed.json
    python upload_to_feishu.py parsed.json --year 2025 --month 3
    python upload_to_feishu.py parsed.json --base-token <token>  # append to existing

Requires: lark-cli authenticated (lark-cli auth status)
"""

import sys
import json
import time
import argparse
import subprocess
import os
from collections import defaultdict

LARK = "D:/npm-global/lark-cli.cmd"
SLEEP = 1.2  # seconds between API calls


def lark(args: list) -> dict:
    """Run lark-cli, return parsed JSON output. Writes large payloads via temp file."""
    cmd = [LARK] + args
    result = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"LARK ERROR: {' '.join(str(a) for a in args)}", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


# CWD for lark-cli calls — @file paths must be relative to this
_CWD = os.path.dirname(os.path.abspath(__file__))
_TMP_JSON = "_tmp_payload.json"


def lark_with_json(args: list, payload: dict) -> dict:
    """Pass JSON payload via temp file to avoid Windows encoding issues with inline JSON."""
    json_str = json.dumps(payload, ensure_ascii=False)
    tmp_path = os.path.join(_CWD, _TMP_JSON)
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(json_str)
    try:
        cmd = [LARK] + args + ["--json", f"@{_TMP_JSON}"]
        result = subprocess.run(cmd, capture_output=True, encoding="utf-8", cwd=_CWD)
        if result.returncode != 0:
            print(f"LARK ERROR: {' '.join(str(a) for a in args)}", file=sys.stderr)
            print(result.stderr[-2000:], file=sys.stderr)
            sys.exit(1)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_token(resp: dict, *keys) -> str:
    """Extract a token from nested response dict."""
    data = resp.get("data", resp)
    for k in keys:
        if k in data:
            return data[k]
    # Fallback: flatten one level
    for v in data.values():
        if isinstance(v, dict):
            for k in keys:
                if k in v:
                    return v[k]
    return ""


def chunk(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


# ---------------------------------------------------------------------------
# Create base
# ---------------------------------------------------------------------------

def create_base(name: str) -> str:
    print(f"  Creating base: {name}")
    resp = lark(["base", "+base-create", "--name", name])
    token = get_token(resp, "base_token", "appToken")
    if not token:
        print("Could not find base_token in:", resp, file=sys.stderr)
        sys.exit(1)
    print(f"  base_token: {token}")
    return token


# ---------------------------------------------------------------------------
# Create Table 1: 分类汇总
# ---------------------------------------------------------------------------

SUMMARY_FIELDS = json.dumps([
    {"name": "分类名称",   "type": "text"},
    {"name": "支出总额",   "type": "number"},
    {"name": "收入总额",   "type": "number"},
    {"name": "净支出",     "type": "number"},
    {"name": "笔数",       "type": "number"},
    {"name": "平均每笔",   "type": "number"},
    {"name": "最大单笔",   "type": "number"},
    {"name": "来源渠道",   "type": "text"},
], ensure_ascii=False)


def create_summary_table(base_token: str) -> str:
    print("  Creating table: 分类汇总")
    resp = lark(["base", "+table-create",
                 "--base-token", base_token,
                 "--name", "分类汇总",
                 "--fields", SUMMARY_FIELDS])
    tid = get_token(resp, "table_id", "tableId")
    if not tid:
        print("Could not find table_id in:", resp, file=sys.stderr)
        sys.exit(1)
    print(f"  summary table_id: {tid}")
    return tid


# ---------------------------------------------------------------------------
# Create Table 2: 交易明细
# ---------------------------------------------------------------------------

def make_detail_fields(summary_table_id: str, base_token: str) -> str:
    fields = [
        {"name": "交易时间",   "type": "datetime"},
        {"name": "交易对方",   "type": "text"},
        {"name": "商品说明",   "type": "text"},
        {"name": "金额",       "type": "number"},
        {"name": "收支类型",   "type": "select",
         "options": [{"name": "支出"}, {"name": "收入"}]},
        {"name": "关联分类",   "type": "link",
         "property": {
             "link_table_id": summary_table_id,
             "multiple": False
         }},
        {"name": "来源",       "type": "select",
         "options": [{"name": "微信"}, {"name": "支付宝"}]},
        {"name": "交易状态",   "type": "text"},
        {"name": "支付方式",   "type": "text"},
        {"name": "备注",       "type": "text"},
    ]
    return json.dumps(fields, ensure_ascii=False)


def create_detail_table(base_token: str, summary_table_id: str) -> str:
    print("  Creating table: 交易明细")
    resp = lark(["base", "+table-create",
                 "--base-token", base_token,
                 "--name", "交易明细",
                 "--fields", make_detail_fields(summary_table_id, base_token)])
    tid = get_token(resp, "table_id", "tableId")
    if not tid:
        print("Could not find table_id in:", resp, file=sys.stderr)
        sys.exit(1)
    print(f"  detail table_id: {tid}")
    return tid


# ---------------------------------------------------------------------------
# Upload summary rows
# ---------------------------------------------------------------------------

def compute_summary(transactions: list) -> list:
    """Aggregate transactions by category."""
    stats = defaultdict(lambda: {
        "支出总额": 0.0, "收入总额": 0.0, "笔数": 0,
        "最大单笔": 0.0, "来源集": set()
    })
    for t in transactions:
        cat = t.get("category", "其他")
        s = stats[cat]
        s["笔数"] += 1
        if t["direction"] == "支出":
            s["支出总额"] += t["amount"]
            s["最大单笔"] = max(s["最大单笔"], t["amount"])
        else:
            s["收入总额"] += t["amount"]
        s["来源集"].add(t.get("source", ""))

    rows = []
    for cat, s in sorted(stats.items(), key=lambda x: -x[1]["支出总额"]):
        sources = "/".join(sorted(s["来源集"] - {""})) or "未知"
        net = round(s["支出总额"] - s["收入总额"], 2)
        avg = round(s["支出总额"] / s["笔数"], 2) if s["笔数"] > 0 else 0
        rows.append({
            "分类名称": cat,
            "支出总额": round(s["支出总额"], 2),
            "收入总额": round(s["收入总额"], 2),
            "净支出":   net,
            "笔数":     s["笔数"],
            "平均每笔": avg,
            "最大单笔": round(s["最大单笔"], 2),
            "来源渠道": sources,
        })
    return rows


def upload_summary(base_token: str, table_id: str, summary_rows: list) -> dict:
    """Upload summary rows, return {category_name: record_id}."""
    cat_to_record = {}
    print(f"  Uploading {len(summary_rows)} category rows...")
    for row in summary_rows:
        resp = lark_with_json(
            ["base", "+record-upsert",
             "--base-token", base_token,
             "--table-id", table_id],
            row
        )
        rec_id = get_token(resp, "record_id", "recordId")
        cat_to_record[row["分类名称"]] = rec_id
        time.sleep(SLEEP)
    return cat_to_record


# ---------------------------------------------------------------------------
# Upload detail rows (batch)
# ---------------------------------------------------------------------------

def upload_details(base_token: str, table_id: str, transactions: list,
                   cat_to_record: dict):
    """Upload all transaction rows in batches of 50."""
    total = len(transactions)
    print(f"  Uploading {total} transactions in batches...")
    uploaded = 0
    for batch in chunk(transactions, 50):
        for t in batch:
            rec_id = cat_to_record.get(t.get("category", "其他"))
            fields = {
                "交易时间": t["date"],        # ISO string; Feishu accepts it
                "交易对方": t.get("counterparty", "")[:200],
                "商品说明": t.get("description", "")[:200],
                "金额":     t["amount"],
                "收支类型": t["direction"],
                "来源":     t.get("source", ""),
                "交易状态": t.get("status", ""),
                "支付方式": t.get("payment_method", ""),
                "备注":     t.get("remark", ""),
            }
            if rec_id:
                fields["关联分类"] = {"link_record_ids": [rec_id]}
            resp = lark_with_json(
                ["base", "+record-upsert",
                 "--base-token", base_token,
                 "--table-id", table_id],
                fields
            )
            uploaded += 1
            time.sleep(SLEEP)
        print(f"  Progress: {uploaded}/{total}", flush=True)
    return uploaded


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="parsed.json from parse_bills.py")
    parser.add_argument("--year",  type=int, help="Override year")
    parser.add_argument("--month", type=int, help="Override month")
    parser.add_argument("--base-token", help="Append to existing base (skip creation)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        transactions = json.load(f)

    if not transactions:
        print("No transactions found in input.", file=sys.stderr)
        sys.exit(1)

    # Determine year/month
    if args.year and args.month:
        year, month = args.year, args.month
    else:
        dates = sorted(t["date"][:7] for t in transactions)
        ym = dates[len(dates) // 2]  # median month
        year, month = int(ym[:4]), int(ym[5:7])
    base_name = f"{year}年{month:02d}月 账单汇总"

    print(f"\n=== {base_name} ===")
    print(f"  Transactions: {len(transactions)}")

    # Step 1: base
    if args.base_token:
        base_token = args.base_token
        print(f"  Using existing base: {base_token}")
        tables = lark(["base", "+table-list", "--base-token", base_token])
        tlist = tables.get("data", {}).get("items", [])
        summary_table_id = next((t["table_id"] for t in tlist if t["name"] == "分类汇总"), None)
        detail_table_id  = next((t["table_id"] for t in tlist if t["name"] == "交易明细"), None)
        if not summary_table_id or not detail_table_id:
            print("Could not find existing tables. Run without --base-token to create fresh.", file=sys.stderr)
            sys.exit(1)
    else:
        base_token = create_base(base_name)
        time.sleep(2)
        summary_table_id = create_summary_table(base_token)
        time.sleep(1)
        detail_table_id  = create_detail_table(base_token, summary_table_id)
        time.sleep(1)

    # Step 2: compute + upload summary
    print("\n[Step 2] Uploading category summary...")
    summary_rows = compute_summary(transactions)
    cat_to_record = upload_summary(base_token, summary_table_id, summary_rows)

    # Step 3: upload detail
    print("\n[Step 3] Uploading transaction details...")
    total_uploaded = upload_details(base_token, detail_table_id, transactions, cat_to_record)

    # Save state for verify.py
    state = {
        "base_token":        base_token,
        "summary_table_id":  summary_table_id,
        "detail_table_id":   detail_table_id,
        "year":              year,
        "month":             month,
        "category_count":    len(summary_rows),
        "transaction_count": total_uploaded,
    }
    with open("upload_state.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print(f"\nDone. State saved to upload_state.json")
    print(f"Base URL: https://feishu.cn/base/{base_token}")
    print(f"\nRun verify.py to check results:")
    print(f"  python scripts/verify.py parsed.json")


if __name__ == "__main__":
    main()
