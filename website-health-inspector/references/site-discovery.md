# 受控页面发现机制

页面发现用于减少漏检，不是无限制全站爬虫。

默认规则：

- 仅检查同源页面。
- 默认只发起 GET 请求。
- 不提交表单。
- 不点击危险按钮。
- 限制最大深度。
- 限制最大页面数。
- 过滤危险路径。
- 尽量解析 `sitemap.xml`。

危险关键词示例：

```text
logout
delete
remove
approve
payment
restart
shutdown
disable
drop
truncate
封禁
删除
审批
重启
下发
结算
```

输出文件为 `discovered-pages.json`，包含：

- `pages`：发现并尝试访问的页面。
- `skipped`：被跳过的页面及原因。

被选中的页面可以合并进 `inventory.normalized.json`，随后进入内容审查流程。

