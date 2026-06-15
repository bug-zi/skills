# fanqiang-audit-split 帮助说明

这是 `fanqiang-audit` 的分工版/未内聚版。它本身只做工作流编排和少量 CSV 辅助处理，完整日志调查依赖 `翻墙管理_skill`，SecGate 3600 对象/策略核验和审批后写入依赖 `secgate3600-firewall-api-skill-20260606`。

## 与内聚版的区别

- 内聚版：`D:\Code\skills\fanqiang-audit`
  - 自带日志规则、3600 可读资料和 3600 脚本。
  - 删除另外两个 skill 后仍能覆盖主要审计流程。
- 分工版：`D:\Code\skills\fanqiang-audit-split`
  - 保持原来的三 skill 分工。
  - 必须保留 `翻墙管理_skill` 和 `secgate3600-firewall-api-skill-20260606`。
  - 不复制 3600 API 资料包，不复制发布脚本。

## 文件结构

- `SKILL.md`：分工版工作流和安全边界。
- `agents/openai.yaml`：分工版入口元数据。
- `scripts/build_auth_index.py`：认证索引辅助脚本。
- `scripts/build_quick_audit.py`：快速审计 CSV 辅助脚本。
- `scripts/query_access_windows.py`：行为评估 CSV 辅助脚本。

## 使用方式

1. 用 `翻墙管理_skill` 查询 SFTP `tw_act` 和 172.16.15.20 日志。
2. 用本 skill 的脚本生成快速审计和行为评估 CSV。
3. 用 `secgate3600-firewall-api-skill-20260606` 做 SecGate 3600 只读核验。
4. 需要整改时，本 skill 只生成计划；写入必须由用户当前对话明确批准。
5. 批准后使用 `secgate3600-firewall-api-skill-20260606` 执行精确写入和写后验证。

## 输出约定

快速审计 CSV 不输出：

- `窗口开始`
- `窗口结束`
- `管控情况`

行为评估 CSV 包含：

- `翻墙行为评估`
- `管控情况`

`管控情况` 来自 3600 只读核验，不能从日志推断。

## 注意事项

- 如果缺少 `翻墙管理_skill` 或 `secgate3600-firewall-api-skill-20260606`，这个分工版不完整。
- DOOPS 取回 CSV 后必须本地校验 UTF-8、表头、行宽和是否混入 banner。
- 终端输出乱码不等于文件乱码，要用显式 UTF-8 或原始字节确认。
