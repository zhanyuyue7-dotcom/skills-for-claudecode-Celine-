# 每月账单汇总 Skill — 仪表盘升级设计

**日期：** 2025-01-27
**状态：** 已批准，待实现

---

## 目标

把现有的「分类汇总 + 交易明细」两表结构，升级为带仪表盘的完整 Base，实现：
1. 点分类行 → 自动筛选出该分类下的全部明细（表间关联已存在，需补视图联动）
2. 仪表盘展示：分类支出柱图（绝对值对比）、分类饼图、按周消费趋势柱图
3. 商务极简视觉风格

---

## 最终结构

```
📊 2025年N月 账单汇总
  ├── 🎯 仪表盘          ← 新增：3 个图表 block
  ├── 📋 分类汇总         ← 已有，保持字段不变，新增「周次分布」视图
  └── 📝 交易明细         ← 已有，新增「按分类筛选」视图 + 「周次」字段
```

---

## 数据结构变更

### 交易明细表：新增字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 周次   | text | 如 "第1周(1-7日)"，parse 时计算，上传时写入 |

> 飞书仪表盘只能按已有字段 group_by，不支持动态日期聚合，所以必须预计算周次。

### 分类汇总表：字段不变

现有字段已满足需求：分类名称、支出总额、收入总额、净支出、笔数、平均每笔、最大单笔、来源渠道。

---

## 仪表盘 Blocks（3个）

### Block 1 — 分类支出对比（柱图）
```json
{
  "type": "column",
  "name": "各分类支出对比",
  "data_config": {
    "table_name": "分类汇总",
    "series": [{"field_name": "支出总额", "rollup": "SUM"}],
    "group_by": [{"field_name": "分类名称"}]
  }
}
```

### Block 2 — 分类支出占比（饼图）
```json
{
  "type": "pie",
  "name": "支出分类占比",
  "data_config": {
    "table_name": "分类汇总",
    "series": [{"field_name": "支出总额", "rollup": "SUM"}],
    "group_by": [{"field_name": "分类名称"}]
  }
}
```

### Block 3 — 按周消费趋势（柱图）
```json
{
  "type": "column",
  "name": "按周消费趋势",
  "data_config": {
    "table_name": "交易明细",
    "series": [{"field_name": "金额", "rollup": "SUM"}],
    "group_by": [{"field_name": "周次"}]
  }
}
```

---

## 视图配置

### 交易明细表：新增「按分类筛选」视图
- 类型：gallery（卡片视图）或 grid
- 分组：按「关联分类」分组
- 排序：交易时间降序
- 目的：从分类汇总点进来时，可以直观看到该分类下所有交易

---

## 实现步骤

1. **parse_bills.py**：`build_record()` 中新增 `周次` 字段计算
2. **upload_to_feishu.py**：
   a. `make_detail_fields()` 新增 `周次` text 字段
   b. `upload_details()` 写入 `周次` 值
   c. 新增 `create_dashboard()` 函数：创建仪表盘 + 3个 block
   d. `main()` 末尾调用 `create_dashboard()`
3. **SKILL.md**：更新文档说明新增的仪表盘功能

---

## 关键 API 格式（已验证）

```bash
# 创建仪表盘
lark-cli base +dashboard-create --base-token <token> --name "仪表盘"

# 创建 block（注意：table_name 不是 table_id；rollup 不是 aggregation）
lark-cli base +dashboard-block-create \
  --base-token <token> --dashboard-id <id> \
  --type column --name "各分类支出对比" \
  --data-config '{"table_name":"分类汇总","series":[{"field_name":"支出总额","rollup":"SUM"}],"group_by":[{"field_name":"分类名称"}]}'
```

---

## 不做的事（范围外）

- 跨月对比（年度汇总 Base）
- 仪表盘自动布局/resize（lark-cli 不支持）
- 收入类图表（用户主要关注支出）
