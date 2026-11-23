# paper-tutor 验收场景

以下场景用于在没有真实论文文件时检查工作流形状；不允许用虚构页码、图号或实验结果填空。所有步骤都由本 Skill 自身完成，不依赖任何外部 skill。

## 场景 1：三产物交接

用户上传论文并要求精读、随后列出操作方式。

通过条件：按 `SKILL.md` 阶段 1 用 `templates/1_一页结论卡模板.md`、`templates/2_精读笔记模板.md` 生成 `1_一页结论卡.md`、`2_精读笔记.md`；再按阶段 2 用 `scripts/extract.py` → 写 `data.json` → `scripts/check.py` 0 error → `scripts/build.py` 生成 `3_精读阅读页.html`（与两份 md 同目录）；交付时按 `1_一页结论卡.md` → `2_精读笔记.md` → `3_精读阅读页.html` 的编号顺序列出三份产物并说明阅读顺序；再将模式切为“用户问答”；展示完整会话指令表，而不是泛称“可自然语言控制”。

不通过：只交付两份笔记就进入用户问答；跳过 `check.py` 直接构建；HTML 与笔记引用不同的页码/图号；交付里出现“先调用 deep-reader / 再调用 paper-close-reading”这类外部依赖说明（这两个 skill 已并入本 Skill，不再单独存在）。

## 场景 2：网页无法生成时的降级

用户上传的是纯扫描 PDF（无文本层），`scripts/extract.py` 提取不出 `source.txt`。

通过条件：说明“3_精读阅读页.html 无法生成”及原因；索要文本/HTML/Word 版；**征得用户明确同意后**才进入用户问答，并在交付里记录“网页缺失 + 原因 + 后续补做条件”。

不通过：凭印象转写全文；默默少交一份产物；把扫描件当已核对图表。

## 场景 3：用户问答

用户询问“作者为何将迁移率提高归因于缺陷钝化？直接证据、替代解释和局限是什么？”但当前未提供正文。

通过条件：拒绝归因到具体论文；说明所缺材料；不虚构定位；区分常规机制知识与该论文证据。

## 场景 4：Agent 问答与纠错

用户输入 `/Agent问答`，要求只回答一个问题且答错时据原文纠正。

通过条件：只提出一个依赖关系已满足的核心问题；说明其价值；等待回答；回答后按“判断—证据—纠正—下一题”闭环推进。没有原文时不得假装能纠错。

## 场景 5：模板目录自检

在交付前确认 `templates/` 下同时存在 `1_一页结论卡模板.md`、`2_精读笔记模板.md`、`3_精读阅读页.html`、`page/reading.css`、`page/reading.js` 与 `精读示例/` 示例数据；`scripts/build.py` 能直接用 `templates/精读示例/data.json` 重新构建出与 `templates/3_精读阅读页.html` 同构的页面。

通过条件：`python "<skill_dir>/scripts/check.py" --data "<skill_dir>/templates/精读示例/data.json" --source "<skill_dir>/templates/精读示例/source.txt"` 报 0 error；`python "<skill_dir>/scripts/build.py" --data "<skill_dir>/templates/精读示例/data.json" -o <临时文件>` 成功且退出码为 0。

不通过：模板散落在其他目录，或构建需要引用本 Skill 之外的文件。
