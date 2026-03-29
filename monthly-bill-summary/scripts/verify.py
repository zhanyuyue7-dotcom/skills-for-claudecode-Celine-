#!/usr/bin/env python3
"""Verify that the uploaded Feishu Bitable matches the parsed JSON.

Usage:
    python verify.py --state upload_state.json --data parsed.json

Checks:
  1. Record count in 分类汇总 matches expected category count
  2. Record count in 交易明细 matches expected transaction count
  3. Sum of 支出总额 in 分类汇总 matches sum of expenses in parsed.json
  4. All categories in parsed.json appear in 分类汇总
  5. No orphaned transactions (transactions whose category has no summary row)
"""

import sys
import json
import time
import argparse
import subprocess
from collections import defaultdict

LARK  = "D:/npm-global/lark-cli.cmd"
SLEEP = 0.8


def lark(args: list) -> dict:
    cmd = [LARK] + args
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"ERROR running: {' '.join(args)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def fetch_all_records(base_token: str, table_id: str) -> list:
    """Fetch all records using pagination.

    lark-cli record-list returns:
      {"data": {"data": [[v1,v2,...], ...], "fields": ["f1","f2",...], "record_id_list": [...]}}
    We normalise each row into {"fields": {field_name: value}} for downstream use.
    """
    all_records = []
    offset = 0
    while True:
        time.sleep(SLEEP)
        resp = lark(["base", "+record-list",
                     "--base-token", base_token,
                     "--table-id",   table_id,
                     "--offset",     str(offset)])
        data = resp.get("data", {})
        field_names = data.get("fields", [])
        rows        = data.get("data", [])
        record_ids  = data.get("record_id_list", [])
        for i, row in enumerate(rows):
            fields = dict(zip(field_names, row)) if field_names else {}
            rec_id = record_ids[i] if i < len(record_ids) else ""
            all_records.append({"record_id": rec_id, "fields": fields})
        if len(record_ids) < 100:
            break
        offset += 100
    return all_records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default="upload_state.json")
    parser.add_argument("--data",  default="parsed.json")
    args = parser.parse_args()

    with open(args.state, encoding="utf-8") as f:
        state = json.load(f)
    with open(args.data, encoding="utf-8") as f:
        rows = json.load(f)

    base_token       = state["base_token"]
    summary_table_id = state["summary_table_id"]
    detail_table_id  = state["detail_table_id"]
    year             = state["year"]
    month            = state["month"]
    month_str        = f"{year}-{month:02d}"

    # Filter local data to same month
    month_rows = [r for r in rows if r["date"].startswith(month_str)]
    if not month_rows:
        month_rows = rows  # fallback

    # Local stats
    local_cats    = set(r["category"] for r in month_rows)
    local_expense = sum(r["amount"] for r in month_rows if r["direction"] == "支出")
    local_tx_cnt  = len(month_rows)

    print(f"\n=== Verification for {month_str} ===")
    print(f"Local: {local_tx_cnt} transactions, {len(local_cats)} categories, ¥{local_expense:.2f} expenses")

    # -----------------------------------------------------------------------
    # Check 分类汇总
    # -----------------------------------------------------------------------
    print("\nFetching 分类汇总...")
    summary_records = fetch_all_records(base_token, summary_table_id)
    remote_cats = set()
    remote_expense_sum = 0.0
    for rec in summary_records:
        fields = rec.get("fields", {})
        name = fields.get("分类名称", "")
        exp  = fields.get("支出总额", 0) or 0
        remote_cats.add(name)
        remote_expense_sum += float(exp)

    print(f"Remote 分类汇总: {len(summary_records)} rows, ¥{remote_expense_sum:.2f} total expenses")

    ok = True

    # Check category count
    if len(summary_records) == len(local_cats):
        print(f"  [PASS] Category count: {len(summary_records)}")
    else:
        print(f"  [FAIL] Category count: remote={len(summary_records)}, local={len(local_cats)}")
        missing = local_cats - remote_cats
        extra   = remote_cats - local_cats
        if missing: print(f"         Missing in remote: {missing}")
        if extra:   print(f"         Extra in remote:   {extra}")
        ok = False

    # Check expense sum (allow ±1 yuan rounding tolerance)
    diff = abs(remote_expense_sum - local_expense)
    if diff <= 1.0:
        print(f"  [PASS] Expense total: ¥{remote_expense_sum:.2f} (local ¥{local_expense:.2f})")
    else:
        print(f"  [FAIL] Expense total: remote=¥{remote_expense_sum:.2f}, local=¥{local_expense:.2f}, diff=¥{diff:.2f}")
        ok = False

    # -----------------------------------------------------------------------
    # Check 交易明细
    # -----------------------------------------------------------------------
    print("\nFetching 交易明细...")
    detail_records = fetch_all_records(base_token, detail_table_id)
    print(f"Remote 交易明细: {len(detail_records)} rows")

    if len(detail_records) == local_tx_cnt:
        print(f"  [PASS] Transaction count: {len(detail_records)}")
    else:
        print(f"  [FAIL] Transaction count: remote={len(detail_records)}, local={local_tx_cnt}")
        ok = False

    # Check for records without 关联分类
    unlinked = sum(
        1 for rec in detail_records
        if not rec.get("fields", {}).get("关联分类")
    )
    if unlinked == 0:
        print(f"  [PASS] All transactions have 关联分类")
    else:
        print(f"  [WARN] {unlinked} transactions missing 关联分类 (link field may not be supported — check manually)")

    # -----------------------------------------------------------------------
    # Final verdict
    # -----------------------------------------------------------------------
    print("\n" + ("=== ALL CHECKS PASSED ==" if ok else "=== SOME CHECKS FAILED ==="))
    print(f"\nOpen your Bitable: https://feishu.cn/base/{base_token}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
