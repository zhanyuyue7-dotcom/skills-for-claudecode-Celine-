---
name: douyin-content-system
description: Douyin content creation system for an AI/embedded-systems college student. This skill should be used when the user asks to create Douyin content, write oral delivery scripts (口播稿), generate image-text posts (图文), plan content topics, or review content before publishing. Triggers on keywords like 口播, 稿子, 抖音, 选题, 图文, 文案, 发布.
---

# Douyin Content System — 抖音内容操作系统

A complete content creation and distribution system for a college freshman building embodied AI projects. Covers topic evaluation, script generation, image-text post creation, and pre-publish distribution checks.

## Workflow

```
选题评估 → 确定内容类型 → 生成内容 → 分发检查 → 输出终稿
```

### Phase 1: Topic Evaluation

Before creating any content, evaluate the topic against three criteria. All three must score at least 2/3:

| 维度 | 评分标准 |
|------|----------|
| **我想讲** | 1=勉强 2=有话说 3=非讲不可 |
| **有人搜** | 1=冷门 2=有需求 3=热点/刚需 |
| **能引发讨论** | 1=纯知识点 2=有争议空间 3=必然引发站队 |

总分 < 6 → 建议换题或调整角度
总分 6-7 → 可以做，注意补强弱项
总分 8-9 → 立刻做

To assess "有人搜", consider: recent AI news cycles, Douyin trending topics, common beginner questions in AI/embedded systems.

To boost "能引发讨论", reframe the topic as a debate, comparison, or personal take rather than a tutorial.

### Phase 2: Content Type Selection

Two content formats are available:

**口播稿 (Oral Delivery Script)**
- Duration: 60-120 seconds
- Use when: sharing opinions, reacting to news, project progress with storytelling
- Structure: hook (3s) → body (50-100s) → ending (10-15s)

**图文 (Image-Text Post)**
- Format: 3-6 images + music + short copy
- Use when: sharing tips, tool comparisons, tutorials, quick knowledge dumps
- Structure: cover image (with hook text) → content slides → final slide (with CTA or question)

### Phase 3: Content Generation

#### For 口播稿

1. Load [persona.md](references/persona.md) — apply persona voice and avoid all items on the prohibition list
2. Load [hooks.md](references/hooks.md) — select one of the 5 opening hooks based on content type:
   - News/tool review → Hook B (事件驱动)
   - Opinion piece → Hook A (反直觉) or Hook E (提问式)
   - Project update → Hook C (过程展示)
   - Targeting specific audience → Hook D (数字筛人)
3. Write the body — follow these rules:
   - One core message only (one takeaway the audience walks away with)
   - Use specific numbers, tool names, and concrete examples — never vague
   - Include at least one personal experience ("我试了一下..." / "我踩了一个坑...")
   - For style reference, consult [style-analysis.md](references/style-analysis.md)
4. Select one of the 4 ending templates from hooks.md:
   - Tutorial/tool content → Ending A (回归人性) or C (金句定格)
   - Project update → Ending B (未完成的故事)
   - Opinion/reflection → Ending D (自我对话)
5. Output format:

```
## 口播稿

**选题评分**: [X/9] ([我想讲X] [有人搜X] [能引发讨论X])
**钩子类型**: [A/B/C/D/E]
**结尾类型**: [A/B/C/D]
**预估时长**: [X秒]
**评论触发器**: [具体描述埋了什么触发器]

---

[完整口播稿文本，用 / 标注停顿，用 **加粗** 标注重音]

---

**标题建议**: [3个备选标题]
**发布时段**: [推荐时间]
```

#### For 图文

1. Load persona.md — maintain voice consistency
2. Design cover image text — must contain a hook (number + information gap)
3. Write each slide's core text (one point per slide, under 30 characters)
4. Write the post caption — include a question or debate prompt to trigger comments
5. Output format:

```
## 图文内容

**选题评分**: [X/9]
**评论触发器**: [具体描述]

---

**封面文字**: [大字标题]
**Slide 1**: [文字内容]
**Slide 2**: [文字内容]
...
**文案**: [配文，包含评论引导]

---

**标题建议**: [3个备选]
**发布时段**: [推荐时间]
```

### Phase 4: Distribution Check

Before delivering the final output, run through every item in [distribution-checklist.md](references/distribution-checklist.md). This is mandatory — never skip.

Key gates (content MUST NOT be delivered if any fail):

1. **前3秒钩子** — first sentence must be completable in 3 seconds and contain information gap
2. **评论触发器** — at least one comment trigger mechanism must be embedded
3. **社交货币** — forwarding this content must make the sharer look smart/informed/tasteful
4. **结尾记忆点** — last sentence must be quotable or thought-provoking

If any gate fails, revise the content before delivering.

### Phase 5: Output

Deliver the final formatted content with all metadata. If the user has not specified a topic, first propose 3 topic options with evaluation scores before generating content.
