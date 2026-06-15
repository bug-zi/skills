# 2026-05-13 十轮逻辑与可读性升级记录

本轮升级针对两个高频问题：评分机制重复扣分、报告表达让管理读者看不清结论。升级目标是把“同一根因只扣一次”落实到更多真实 URL 形态，并把空泛占位话术挡在质量审计阶段。

## 10 轮迭代

1. 系统标识归一：`system_id` 与 `system_name` 统一 slug 化，避免 `Admin Platform` 和 `admin-platform` 被拆成两个扣分簇。
2. 请求方法归一：endpoint 聚类会去掉 `GET/POST/...` 方法前缀。
3. URL 噪声归一：endpoint 聚类会去掉 query、hash 和尾部斜杠。
4. 动态 ID 归一：数字 ID、UUID、ObjectId 统一替换为 `:id`，同一接口族只扣一次。
5. 静态资源 hash 归一：`chunk.abcdef12.js` 等构建 hash 归并到同一资源族。
6. 人工确认正常清零：`confidence=manual-confirmed-normal` 优先清零，即使标题或严重度像故障。
7. 低可信高危降权：低可信 `high-confidence-risk` 或高严重度信号先按复核权重处理。
8. 旧标题兜底归因：旧报告中的“浏览器捕获到异常 HTTP 响应”按规范化 endpoint 归并，不再按每个动态 URL 重复扣分。
9. 评分解释修正：当分数不是 100 但没有可逐项展示的问题簇时，报告不再写“为什么是 100 分”或“未发现扣分项”，而是提示查看覆盖缺口、未运行模块或上游汇总扣分。
10. 可读性门禁：质量审计新增空泛话术检查，识别“可能影响部分页面体验或需要后续排查”“请检查”“建议尽快排查”“Review needed”等占位句。

## 新增回归测试

新增 `tests/test_20260513_logic_readability_iterations.py`，覆盖：

- 系统名变体不会导致同一根因重复扣分。
- endpoint 方法、query、hash、尾部斜杠、动态 ID 和静态资源 hash 归一。
- 人工确认正常清零、低可信高危降权。
- 旧 HTTP 响应标题按 endpoint 家族归并。
- 分数残差解释不再误写 100 分。
- 默认业务影响和建议动作不再使用空泛占位句。
- 质量审计可识别可读性占位句。

## 验证结果

已执行：

```bash
python -m pytest tests/test_20260513_logic_readability_iterations.py -q
python -m pytest tests/test_root_cause_scoring.py tests/test_scoring_policy_20_iterations.py -q
python -m pytest tests -q
```

结果：

- 新增 10 轮测试：10 passed
- 评分回归测试：24 passed
- 全量测试：79 passed

## 使用影响

- 评分解释应展示问题簇数量和同类证据数量，而不是重复日志数量。
- 同一接口族、动态业务对象或静态资源构建版本不应重复扣分。
- 管理报告缺少证据时应说明“影响范围尚未确认”，同时给出责任角色、复测证据、服务端日志和业务预期，不应写泛泛的“请检查”。
