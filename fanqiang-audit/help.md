# fanqiang-audit 帮助说明

## 这个 skill 是做什么的

`fanqiang-audit` 是浙江音乐学院翻墙/代理/VPN 审计工作流 skill。它现在是自足型审计 skill，可以独立完成：

- 查询 SFTP `tw_act` 主日志，确认翻墙/代理/VPN 事件。
- 通过 172.16.15.20 `authlog` 关联 MAC、账号/学号和认证时间。
- 生成快速审计 CSV。
- 基于事件窗口查询 `ssl_log`、`web`、`app_conn`、`proxy_identify` 等访问上下文，生成行为评估 CSV。
- 只读核验 SecGate 3600 防火墙对象和策略，判断相关对象是否已管控。
- 生成候选处置清单、整改计划和审批前审计包。
- 在用户当前对话明确批准后，执行限定范围的防火墙对象发布，并做写后验证。

它不再把 `翻墙管理_skill` 或 `secgate3600-firewall-api-skill-20260606` 作为运行依赖；那两个 skill 可以继续保留作独立参考或其它工作流使用。

## 文件结构

- `SKILL.md`：核心工作流说明，包含日志路径、证据规则、行为评估、SecGate 3600 核验和写入审批边界。
- `agents/openai.yaml`：OpenAI/Codex 侧显示名、简介和默认提示。
- `scripts/build_quick_audit.py`：快速审计 CSV 生成脚本。
- `scripts/query_access_windows.py`：行为评估 CSV 生成脚本。
- `scripts/build_auth_index.py`：172.16.15.20 认证日志 SQLite 索引构建脚本。
- `scripts/nsg_control_check.py`：SecGate 3600 只读管控对象核验脚本。
- `scripts/nsg_snapshot.py`：SecGate 3600 只读快照脚本。
- `scripts/netentsecctl.py`：SecGate 3600 CLI，支持只读查询和审批后对象发布。
- `scripts/publish_block_objects.py`：审批后发布 `翻墙风险IP`、`翻墙风险域名` 的工作簿发布脚本。
- `references/`：SecGate 3600 操作说明、API 摘要和覆盖矩阵。
- `resources/nsg-firewall/`：SecGate/NSG REST API 的提取文本、索引和摘要。

大型 PDF、历史 DOOPS 记录、缓存文件、一次性 payload 和真实配置没有纳入本 skill。
3600 脚本不内置真实密码；运行时需要通过本地 `config/connection.local.json`、命令行参数或经批准的交互式秘密路径提供凭据。

## 工作流

1. 把用户给出的日期或相对时间转换成明确的 Asia/Shanghai 时间范围。
2. 判断日志访问方式：优先直连 `/raid5/...`，不可用时走 DOOPS target `zy` 的 `/proc/1/root/raid5/...`。
3. 查询 SFTP `tw_act_YYYYMMDD*.txt`，提取翻墙时间、内网 IP、访问对象、协议/类型和证据样例。
4. 构建或复用当天 172.16.15.20 `authlog` 索引，按 `内网IP + 翻墙时间` 关联 MAC 和账号/学号。
5. 输出快速审计 CSV。该表不展示 `窗口开始`、`窗口结束`，也不展示 `管控情况`。
6. 如果用户要求行为评估，再用快速审计结果做事件窗口查询，输出行为评估 CSV。
7. 行为评估 CSV 包含 `翻墙行为评估` 和 `管控情况`。
8. 如果需要整改计划，使用本 skill 自带的 SecGate 3600 脚本做只读对象/策略核验。
9. 生成候选处置清单和整改计划。
10. 防火墙写入必须停止等待用户在当前对话明确批准。
11. 批准后只执行批准范围内的命令，并做写后对象和策略验证。

## DOOPS 文件取回规则

从 DOOPS 远端取回 CSV、压缩包或其它交付物时，必须使用字节安全方式。

macOS/Linux 用户只有在确认本机 `doops read` stdout 只包含文件字节时，才可以使用普通 shell 重定向：

```bash
doops -session fetch read --target zy --path /tmp/result.csv > ~/Desktop/result.csv
```

有些 DOOPS 版本会把 targeting/status banner 写到 stdout，并出现在 CSV 字节前面。如果取回文件不是以 UTF-8 BOM/表头开头，必须截掉 BOM/表头前的所有内容，或改用明确 payload 标记的取回方式。取回后仍必须做 UTF-8 和 CSV 结构校验。

Windows PowerShell 用户不要直接执行：

```powershell
doops read --target zy --path /tmp/result.csv > C:\Users\Administrator\Desktop\result.csv
```

PowerShell 的 `>` 是文本重定向，可能重编码字节，也可能把 DOOPS 状态行或 WSL 警告混进文件，导致本地 CSV 不是有效 UTF-8。

正确做法：

- macOS/Linux：普通 shell 重定向可以使用，但前提是 `doops read` stdout 没有状态行或告警文本；如果有 banner，必须从 CSV BOM/表头处重写文件或改用 payload 标记取回。
- Windows：优先用能写原始字节的本地 helper，最终用 `[System.IO.File]::WriteAllBytes(...)` 落盘。
- Windows + WSL：可在 WSL 内执行 `doops read`，重定向到 `/mnt/c/Users/Administrator/Desktop/...`，让 Linux shell 写原始字节。
- 任意系统：如果输出可能混入状态文本，远端先压缩或 base64，并用明确标记截取 payload；本地只解码 payload 后按字节写入。
- 取回后必须本地校验：按 `utf-8-sig` 解码、检查表头、确认无 DOOPS banner/WSL warning、确认所有 CSV 行列数一致、检查是否出现 `锟`、`�`、`Ã`、`Â` 等 mojibake 标记；如果 banner 位于有效 BOM/表头之前，先从 BOM/表头处重写本地文件再交付。

## DOOPS 执行注意事项

- 如果 DOOPS 报 `insecure gateway URL ... is not allowed`，只在当前命令/进程临时设置 `DOOPS_ALLOW_INSECURE_GATEWAY=1`，不要默认写成全局环境变量。
- macOS/Linux 下优先使用普通 POSIX 路径和 shell 引号，例如从 skill 目录执行 `doops ... push --src scripts`。
- Windows 下 `doops push` 优先使用相对路径或 WSL 路径。例如在 `D:\Code\skills\fanqiang-audit` 下使用 `--src scripts`，不要直接传 `D:\...` 绝对路径。
- `doops push --src scripts` 后必须先用 `find /root/ws/<session> -maxdepth 2 -type f` 确认远端目录结构；脚本可能在远端工作区根目录，不一定在 `scripts/` 子目录。
- 跨本地 shell、DOOPS、远端 shell 传参时，尽量避免带空格的时间参数。全天审计优先只传 `--date YYYY-MM-DD`，让脚本使用默认全天范围。
- macOS/Linux 单层 shell 通常可以安全传递单引号参数；Windows 或多层 shell 场景下，如果必须传复杂参数，优先写入远端临时 shell 脚本或参数文件再执行。

## 证据口径

- `确认翻墙`：以 SFTP `tw_act` 主日志为准，或有强代理/VPN 协议证据且能匹配终端上下文。
- `高疑似代理/需复核`：172.16.15.20 有代理隧道标签或代理型目的地，但缺少 SFTP 主证据。
- `国外网站访问线索`：访问 Google、YouTube、OpenAI、X、Facebook 等，不等于确认翻墙。
- `涉政访问线索`：SFTP `web_act` 或 20 日志有涉政分类/域名，不等于确认翻墙。
- `挖矿线索`：矿池、stratum、xmrig、monero 等证据，需过滤弱关键词误报。
- `误判剔除`：无 SFTP、零 MAC、更新/遥测/白名单/普通应用背景流量或弱关键词。

不要把 “Google = 翻墙”。Chrome 更新、安全浏览、Android 连通性检测、Google 公共服务、DNS/SNI-only 记录都只能作为弱线索。

## 输出约定

快速审计 CSV 保留：

- `学号/账号`
- `翻墙时间`
- `内网IP`
- `翻墙协议/类型`
- `访问IP/对象`
- `身份时间匹配`
- `学号匹配`
- `备注`

行为评估 CSV 必须包含：

- `翻墙行为评估`
- `管控情况`

`管控情况` 的含义：

- `已管控`：对应内网 IP 或风险对象已在预期防火墙对象中。
- `未管控`：不在预期防火墙对象中。
- `对象不存在`：预期对象不存在。
- `核验失败`：只读 API 核验失败或返回不可用。
- `不适用`：该行没有可核验的管控目标。

## 安全边界

默认允许：

- 读取日志。
- 读取防火墙对象和策略。
- 生成快速审计、行为评估、候选清单和整改计划。

默认禁止：

- 修改防火墙对象。
- 修改安全策略。
- 删除或修改日志。
- 自动封禁 IP。
- 未经批准添加 `--apply`。
- 下载大型原始日志到本地。

防火墙写入必须同时满足：

- 已生成整改计划。
- 用户在当前对话明确批准。
- 执行范围与批准内容完全一致。
- 写入后重新核验对象成员和策略引用。
- 执行记录中脱敏密码、token、cookie 和其它秘密。

## 适合与不适合

适合：

- 浙江音乐学院当前日志和 SecGate 3600 环境下的翻墙审计。
- 需要快速审计 CSV、行为评估 CSV、管控核验和整改计划的场景。
- 熟悉 DOOPS、日志主机、防火墙对象和处置流程的管理员。

不适合：

- 没有对应 SFTP、172.16.15.20 日志或 SecGate 3600 环境的人。
- 只想问通用防火墙 API 文档问题的人。
- 想跳过审批直接写入防火墙的人。

## 风险与限制

- 日志体量可能很大，必须在日志主机或 DOOPS 目标上预过滤。
- 账号/学号依赖 172.16.15.20 认证日志；如果认证日志没有覆盖命中时间，必须标记未匹配或需复核。
- 行为评估是事件窗口研判，不应扩展成无限制全量扫描。
- SecGate 3600 API 可能因权限、对象不存在或网络问题返回失败；失败时只能报告失败，不能推断对象状态。
- 写入脚本虽然已纳入本 skill，但只能作为审批后工具使用。

## Prompt 污染与效率

这个 skill 的主提示词较长，因为它承担审计闭环和高风险安全边界。为了降低负担，完整 API 手册正文放在 `resources/`，脚本放在 `scripts/`，主文档只保留执行流程和必要口径。正常快速审计时不需要读取全部 SecGate API 资料；只有 API 模块、策略对象或写入流程不清楚时，才读取 `references/` 或 `resources/nsg-firewall/`。
