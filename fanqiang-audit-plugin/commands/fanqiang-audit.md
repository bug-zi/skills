---
description: "Use the installed 翻墙审核 skill for proxy/VPN audit workflows"
---

Use the `fanqiang-audit` skill for this request.

If the user included arguments after `/fanqiang-audit`, treat them as the audit task,
time range, mode, or output requirement.

Follow the skill safety rules:

- Default to read-only investigation.
- Do not modify firewall objects, policies, logs, or other data.
- Firewall writes require explicit user approval for the exact action.
- Use DOOPS target `zy` when remote log access is needed.
- Use 快速审核模式 unless the user asks for behavior/risk evaluation.
- In 行为评估模式, query access logs by `内网IP + 翻墙时间` event windows and output CSV by default.

Keep the response focused on the audit result, explain key concepts plainly, and record
executed actions and important outcomes for user verification.
