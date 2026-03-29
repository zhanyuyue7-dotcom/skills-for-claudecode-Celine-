---
name: monthly-bill-summary
description: 每月账单汇总助手。当用户提到要分析账单、处理微信/支付宝导出的 CSV/XLSX、或将消费数据整理到飞书多维表格时使用本 skill。功能包括：解析微信/支付宝账单导出文件、自动分类消费、创建飞书多维表格（含分类汇总母表+关联交易明细子表）、数据验收。
license: MIT
---

# 每月账单汇总 Skill

## 整体流程

```
导出账单文件 (CSV)
    ↓
[Step 1] parse_bills.py  →  parsed.json
    ↓
[Step 2] upload_to_feishu.py  →  飞书多维表格 + upload_state.json
    ↓
[Step 3] verify.py  →  验收报告
```

---

## 前置条件检查

**每次开始前先运行：**

```bash
lark-cli auth status
```

若显示未登录，执行：

```bash
lark-cli auth login --domain base --no-wait
# 将返回的授权链接发给用户，用户浏览器完成授权后：
lark-cli auth login --device-code <DEVICE_CODE>
```

**确认 Python 可用：**

```bash
"D:/Anaconda istall/python.exe" --version
# 需要 3.8+，只用标准库，无需额外安装
```

---

## Step 0：导出账单文件

### 微信支付导出方法

1. 微信 → 「我」→「支付」→「钱包」→「账单」
2. 右上角「...」→「账单明细」→「常见问题」→「下载账单」
3. 选择时间范围（建议按月），目的选「个人对账」
4. 邮箱收取 CSV 文件，文件名格式：`微信支付账单(xxxxxx).csv`

**微信 CSV 格式说明：**
- 前几行是说明文字（需跳过），真正数据从含 `交易时间` 的行开始
- 关键列：交易时间、交易类型、交易对方、商品、收/支、金额(元)、支付方式、当前状态、备注
- 金额格式：`¥123.45`（含人民币符号，需去掉）
- **必须过滤**：当前状态含「已全额退款」「对方已退还」「交易关闭」的记录

### 支付宝导出方法

1. 支付宝 App → 「我的」→「账单」→ 右上角「...」
2. 「开具交易流水证明」或「下载账单」
3. 邮箱收取 CSV 文件，文件名通常含 `alipay_record`

**支付宝 CSV 格式说明：**
- 前几行是声明文字，数据从含 `交易时间` 的行开始
- 关键列：交易时间、交易分类、交易对方、商品说明、收/支、金额、收/付款方式、交易状态、交易订单号、备注
- 金额为纯数字（无符号）
- **必须过滤**：交易状态含「退款」「关闭」「撤销」的记录

---

## Step 1：解析账单文件

脚本位置：`scripts/parse_bills.py`

### 用法

```bash
cd D:/Downloads/飞书cli/monthly-bill-summary

# 单个微信账单
"D:/Anaconda istall/python.exe" scripts/parse_bills.py wechat 微信支付账单.csv --output parsed.json

# 单个支付宝账单
"D:/Anaconda istall/python.exe" scripts/parse_bills.py alipay alipay_record.csv --output parsed.json

# 自动识别来源（根据文件名/内容判断）
"D:/Anaconda istall/python.exe" scripts/parse_bills.py auto 微信账单.csv 支付宝账单.csv --output parsed.json
```

### 预期输出（stderr）

```
  微信支付账单(202503).csv: 183 transactions (wechat)
  alipay_record_202503.csv: 47 transactions (alipay)

Total: 230 transactions
  Expenses: 198, total ¥8432.10
  Income:   32,  total ¥1200.00

Saved to parsed.json
```

### parsed.json 格式

```json
[
  {
    "date": "2025-03-15T14:23:00",
    "counterparty": "星巴克",
    "description": "星巴克",
    "amount": 38.0,
    "direction": "支出",
    "category": "餐饮美食",
    "source": "微信",
    "status": "支付成功",
    "payment_method": "零钱",
    "remark": ""
  }
]
```

### 自定义分类规则

如果某笔消费被归到「其他」或分类不准，编辑 `scripts/parse_bills.py` 中的 `CATEGORY_RULES` 列表：

```python
CATEGORY_RULES = [
    # ("分类名称", ["关键词列表"]),  ← 靠前的规则优先匹配
    ("健身运动", ["超级猩猩", "keep", "健身"]),   # ← 在最前面插入新规则
    ("餐饮美食", ["美团", "星巴克", ...]),
    ...
]
```

修改后重新运行 `parse_bills.py` 即可。

---

## Step 2：上传到飞书多维表格

脚本位置：`scripts/upload_to_feishu.py`

### 用法

```bash
# 自动从数据推断年月（取中位月份）
"D:/Anaconda istall/python.exe" scripts/upload_to_feishu.py parsed.json

# 手动指定年月
"D:/Anaconda istall/python.exe" scripts/upload_to_feishu.py parsed.json --year 2025 --month 3

# 续传（上传中断后，用已有 base_token 继续）
"D:/Anaconda istall/python.exe" scripts/upload_to_feishu.py parsed.json --base-token <base_token>
```

### 脚本执行顺序

```
[Step 2.1] 创建 Base："2025年03月 账单汇总"
[Step 2.2] 创建「分类汇总」表（字段：分类名称/支出总额/收入总额/净支出/笔数/平均每笔/最大单笔/来源渠道）
[Step 2.3] 创建「交易明细」表（字段：交易时间/交易对方/商品说明/金额/收支类型/关联分类/来源/交易状态/支付方式/备注）
[Step 2.4] 上传分类汇总行（每个分类一条记录）
[Step 2.5] 上传全部交易明细（每50条一批，有速率限制间隔）
```

### 表结构与关联关系

```
分类汇总表（母表）          交易明细表（子表）
┌──────────────┐           ┌──────────────────────┐
│ 分类名称 [主键]│◄──────────│ 关联分类 [关联字段]    │
│ 支出总额      │           │ 交易时间              │
│ 收入总额      │           │ 交易对方              │
│ 净支出        │           │ 商品说明              │
│ 笔数          │           │ 金额                  │
│ 平均每笔      │           │ 收支类型（单选）       │
│ 最大单笔      │           │ 来源（单选）           │
│ 来源渠道      │           │ 交易状态              │
└──────────────┘           │ 支付方式              │
                           │ 备注                  │
                           └──────────────────────┘
```

**关联字段说明**：「关联分类」是飞书 type=18 的关联字段，点击任意分类行可直接筛选出该分类下所有交易明细。在「分类汇总」表的分类行上点击「关联分类」列，即可展开查看该类别全部消费记录。

### upload_state.json

上传成功后生成，保存关键 token，供 verify.py 和续传使用：

```json
{
  "base_token": "JrFXbXXXXXXX",
  "summary_table_id": "tblXXXXXX",
  "detail_table_id": "tblXXXXXX",
  "year": 2025,
  "month": 3,
  "category_count": 12,
  "transaction_count": 230
}
```

---

## Step 3：验收

脚本位置：`scripts/verify.py`

```bash
"D:/Anaconda istall/python.exe" scripts/verify.py parsed.json
# 自动读取 upload_state.json 中的 base_token 和 table_id
```

### 验收项目

| 检查项 | 方法 | 通过标准 |
|--------|------|----------|
| 分类行数 | lark-cli +record-list 分类汇总表 | == 本地分类数 |
| 交易行数 | lark-cli +record-list 交易明细表 | == parsed.json 条数 |
| 支出总额 | 对比各分类支出总额 | 误差 < ¥0.01 |

### 验收通过输出

```
Checking base JrFXbXXXXXXX...
  Category count:    remote=12, local=12   OK
  Transaction count: remote=230, local=230 OK
  Total expenses:    remote=¥8432.10, local=¥8432.10 OK

ALL CHECKS PASSED
```

---

## 常见问题排查

### 验收失败：Transaction count 不一致

```
Transaction count: remote=180, local=230
```

原因：上传中途中断。处理方式：

```bash
# 1. 查看已上传状态
cat upload_state.json

# 2. 先清理已有明细记录（避免重复），或新建 base 重传
# 方式A：重建（推荐，数据量不大时）
"D:/Anaconda istall/python.exe" scripts/upload_to_feishu.py parsed.json --year 2025 --month 3

# 方式B：追加到已有 base（需确认已有记录数以避免重复）
lark-cli base +record-list --base-token <base_token> --table-id <detail_table_id>
```

### 金额解析错误

症状：解析出的金额为 0 或异常大。原因：CSV 文件编码或格式与预期不同。

```bash
# 检查文件编码
file -i 账单文件.csv
# 检查实际列名（前25行）
head -25 账单文件.csv
```

若列名与脚本预期不同，修改 `parse_bills.py` 中 `WECHAT_COLUMNS` 或 `ALIPAY_COLUMNS` 映射。

### lark-cli 返回 token 位置不确定

不同版本的 lark-cli 返回结构可能有差异，脚本已做多级 fallback 提取