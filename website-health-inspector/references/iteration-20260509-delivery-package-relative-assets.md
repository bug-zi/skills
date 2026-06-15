# 2026-05-09 交付包与相对图片路径升级

## 目标

- 将 HTML 报告从图片内嵌改回相对路径引用。
- 新增干净交付包 `delivery/`，方便用户整包转发给其他人。
- 将 HTML 实际引用图片和完整截图证据分目录管理，减少运行目录图片堆叠感。

## 变更

- `delivery/final-report.html` 成为正式对外交付入口。
- `delivery/html-assets/` 保存 HTML 正文实际引用图片。
- `delivery/screenshots/` 保存完整截图证据。
- 质量审计不再要求 self-contained HTML，改为检查相对路径、交付包、图片目录和截图目录。

## 交付口径

发送报告时请发送整个 `delivery/` 文件夹。只发送单个 HTML 文件会导致相对路径图片缺失。
