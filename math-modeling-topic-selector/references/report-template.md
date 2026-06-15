# Decision Report Template

Use this structure for the default Chinese output.

## 结论先行

- 推荐选择：`题目名称`
- 推荐理由：用 2-4 句话说明为什么它比其他候选更稳。
- 最大风险：点明最可能拖垮进度的风险。
- 是否需要复核：如果队伍信息缺失，说明这是基于默认队伍画像的初判。

## 各题快速解读

For each problem:

- 题目定位：一句话说明它属于什么类型的问题。
- 核心任务：列出需要解决的主要子问题。
- 附件与数据：说明数据/模板/文件类型如何影响建模。
- 可能路线：给出可完成的 v1 建模路线。
- 主要风险：指出最容易卡住的地方。

## 评分矩阵

Use the rubric dimensions as columns and candidate problems as rows. Include total score out of 40.

Required columns:

`题目 | 题意清晰度 | 数据可用性 | 建模可解释性 | 代码实现难度 | 结果可验证性 | 论文表达空间 | 时间风险 | 队伍匹配度 | 总分`

## 推荐排序

Rank all candidate problems. For each rank, give the decisive reason:

1. `第一推荐`：why it should be chosen.
2. `第二选择`：when it might become better than the first.
3. `不优先`：why it is risky or mismatched.

## 选题后的最低可行路线

For the recommended problem only:

- 最小模型闭环：what can produce a complete first result.
- 代码与数据工作：what must be implemented or cleaned.
- 图表与论文表达：what figures/tables should appear in the paper.
- 半天内检查点：how to know quickly whether this choice is viable.

## 需要补充的信息

Ask only for missing information that could change the ranking:

- 队伍成员擅长：数学推导、编程、优化、机器学习、写作、专业背景。
- 可用时间：剩余小时数和是否能连续工作。
- 工具限制：Python、MATLAB、Excel、CAD/STP 处理工具等。
- 比赛限制：是否有 AI 工具、外部资料、提交格式限制。
