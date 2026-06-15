---
name: doops-server
description: |
  用 doops 连接和操作 doops-agent 节点。doops 是 SSH 的替代入口，支持两种模式：
  直连 agent 模式，以及通过公网 doops-gateway 进入内网集群的隧道模式。
---

## 核心原则

- 优先使用 PATH 中的 `doops`；标准安装路径是 `~/.local/bin/doops`
- 本 skill 的权威源码在 doops.sh 仓库 `skills/SKILL.md`；项目里的 `.agent/skills/doops/SKILL.md` 只是安装副本
- 修改 skill 时先改 doops.sh 源码，再通过 `scripts/install.sh` 同步到业务项目，不要只改安装副本
- 必须先判断目标配置属于哪种模式，再执行命令
- 直连 agent 模式：配置里有 `ip`/`port`，CLI 直接连 `doops-agent:42222`
- Gateway 隧道模式：配置里有 `gateway`/`cluster`/`instance`，CLI 连接公网 `doops-gateway`，gateway 再转发到内网 agent；gateway 登录既支持 user token，也支持用户名密码换 token
- target 可以通过 `name` 或 `aliases` 操作；例如 `jm`、`jy` 可以指向同一个 `doops-jm/jm-228`
- 直连鉴权使用 agent token；gateway 鉴权使用 user token 和 scope/action 权限。不要混用两类 token
- gateway 主动升级 agent 必须使用 `agent:upgrade` 或 `admin` 权限，优先 dry-run 后再执行
- 如果用户是在做 gateway 管理员工作（发账号、发 token、grant 权限、查审计），必须把它和普通 target 运维动作区分开。产品化入口应收敛到 `doops admin ...`；不要在业务 skill 中引导用户直接调用 gateway 内部维护命令。
- SSH 只用于首次安装或自恢复 agent，不是日常操作入口
- 所有远端调用都必须带 `-session <name>`

## 配置位置

Doops CLI 会按这个顺序读取配置：

1. 当前项目的 `.agent/skills/doops/config.json`
2. `~/.config/doops/config.json`

### 模式一：直连 agent

适用场景：客户端可以直接访问目标 `doops-agent` 的 `42222` 端口。

配置示例：

```json
{
  "servers": [
    {
      "name": "gpu-ampere01",
      "ip": "89.250.81.244",
      "port": "42222",
      "use": "GPU node",
      "token": "<TOKEN_FROM_DOOPS_AGENT_TOKEN>"
    }
  ]
}
```

添加配置：

```bash
doops add \
  --name gpu-ampere01 \
  --ip 89.250.81.244 \
  --port 42222 \
  --token '<AGENT_TOKEN_FROM_DOOPS_AGENT_TOKEN>' \
  --use 'GPU node direct agent'
```

使用：

```bash
doops list
doops -session smoke exec --target gpu-ampere01 --cmd "hostname"
doops -session smoke ask --target gpu-ampere01 --msg "用一句话说明当前执行环境"
```

### 模式二：Gateway 隧道

适用场景：agent 在内网，不能暴露公网端口；内网 agent 主动长连接到公网 gateway，CLI/skill 只连接 gateway。

配置示例：

```json
{
  "servers": [
    {
      "name": "jm",
      "aliases": ["jy"],
      "gateway": "https://gateway.example.com",
      "cluster": "doops-jm",
      "instance": "jm-228",
      "use": "JM via gateway",
      "token": "<GATEWAY_USER_TOKEN>"
    }
  ]
}
```

添加配置：

```bash
doops add \
  --name jm \
  --gateway https://gateway.example.com \
  --cluster doops-jm \
  --instance jm-228 \
  --aliases jy \
  --token '<GATEWAY_USER_TOKEN>' \
  --use 'JM via gateway'
```

使用：

```bash
doops targets --target jm
doops -session smoke exec --target jy --cmd "hostname"
doops -session smoke exec --target jm --cmd "hostname"
doops -session smoke ask --target jm --msg "只读检查当前 Kubernetes 节点状态"
doops -session build push --target jm --src .
```

### 批量升级 Agent

```bash
doops -session upgrade_20260511 upgrade \
  --target jm \
  --cluster doops-jm \
  --image repo.aiedulab.cn:8443/lab/doops-agent:latest \
  --mode k8s \
  --namespace oilan-system \
  --workload daemonset/doops-agent \
  --container doops-agent \
  --dry-run
```

确认 dry-run 输出正确后再去掉 `--dry-run`。裸二进制 agent 不执行镜像升级。

Gateway 模式下：

- `token` 是 gateway user token，不是 agent 注册 token
- agent 注册 token 只放在内网 agent 启动参数里：`doops-agent -gateway-url ... -cluster ... -instance ... -agent-token ...`
- `doops targets --target <name>` 能看到该 gateway 下当前在线的 `cluster/instance`
- `exec/read/write/info/check/clean/push/pull/ask` 都继续使用同一个 `--target`

兼容说明：

- agent/gateway 鉴权统一写 `token`
- `ssh_user`、`ssh_port`、`ssh_password` 只在 `doops install` 或 `deploy.sh` 自恢复时有意义

## 安装 CLI 和 Skill

从 doops.sh 仓库安装到一个业务项目：

```bash
git clone https://cnb.cool/l8ai/ai/doops.sh.git
cd doops.sh
bash scripts/install.sh --project /absolute/path/to/project
```

一次性安装并写入直连配置：

```bash
bash scripts/install.sh \
  --project /absolute/path/to/project \
  --target-name gpu-ampere01 \
  --target-ip 89.250.81.244 \
  --target-token '<AGENT_TOKEN>' \
  --use 'GPU direct agent'
```

一次性安装并写入 gateway 配置：

```bash
bash scripts/install.sh \
  --project /absolute/path/to/project \
  --target-name jm \
  --target-gateway https://gateway.example.com \
  --target-cluster doops-jm \
  --target-instance jm-228 \
  --target-token '<GATEWAY_USER_TOKEN>' \
  --use 'JM via gateway'
```

安装结果：

- CLI: `~/.local/bin/doops`
- Skill: `<project>/.agent/skills/doops/SKILL.md`
- Project config: `<project>/.agent/skills/doops/config.json`

CLI 安装包固定来自 doops.sh 仓库 `skills/doops-cli/bin/doops-<os>-<arch>`。普通用户安装只复制这个预构建包；如果缺少对应平台包，应由维护者先构建并提交到 doops.sh 仓库，而不是让用户在业务项目或 target 机器上编译。

如果 `doops` 不在 PATH：

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Gateway 管理员操作

当用户目标是“发账号 / 发 token / grant 权限 / 查审计 / 清理旧审计”时，应视为 gateway 管理动作，而不是普通 target 运维动作。

目标产品入口应是 `doops admin ...`。在该入口完全落地前，不要让普通用户、业务 skill 或自动化任务直接操作 gateway 内部维护命令；需要发账号、发 token、授权或查审计时，应交给平台管理员按 gateway 管理 SOP 执行，并把结果记录到变更/审计上下文。

管理员动作必须记录：

- 操作人和目标用户。
- 目标 `cluster/instance` 范围。
- 授权 action 列表，例如 `targets:list,exec,ask,read,pull,info,push`。
- token 名称、用途、有效期和轮换计划。
- 审计查询条件与清理截止时间。

解释：

- `401 Unauthorized`：认证失败，token 无效/过期/没登录
- `403 Forbidden`：认证通过，但该用户对目标 `cluster/instance` 没有授权
- 审计记录已经按 `user_id`、`token_id`、`cluster`、`instance`、`action`、`session` 记录，可按这些字段查询

## 服务端安装优先级

生产上先选容器化安装：

1. K8s/K3s DaemonSet
2. Docker/nerdctl 容器，容器名固定 `doops-agent`
3. 只在老节点或临时恢复时才用裸二进制

判断当前节点是不是容器化安装，直接看：

```bash
kubectl get pod -A -l app=doops-agent
docker ps --filter name=doops-agent
nerdctl ps --filter name=doops-agent
ps -ef | grep '[d]oops-agent'
```

如果只看到 `/usr/local/bin/doops-agent -port ...`，而没有 Pod 或容器，那就不是容器化安装。这样的节点不会自动具备镜像里的 doagent、BuildKit 和自恢复能力，想进 gateway 需要重新按 `-gateway-url ... -agent-token ...` 启动，或者迁移成容器/K8s 安装。

## 首次接入一个已运行的直连 agent

### 1. 在服务端取 token

在 agent 所在机器或容器中执行：

```bash
doops-agent token
```

常见容器路径：

```bash
/app/doops-agent token
```

K8s 里可以这样拿：

```bash
POD="$(kubectl -n doops-system get pod -l app=doops-agent -o jsonpath='{.items[0].metadata.name}')"
kubectl -n doops-system exec "$POD" -- /app/doops-agent token
```

token 会持久化在服务端 `/root/.doops/agent-token`。首次读取时如果文件不存在，agent 会自动生成。

### 2. 在客户端添加直连节点

```bash
doops add \
  --name gpu-ampere01 \
  --ip 89.250.81.244 \
  --port 42222 \
  --token '<AGENT_TOKEN_FROM_DOOPS_AGENT_TOKEN>' \
  --use 'GPU node'
```

之后就直接用 doops，不再需要 SSH：

```bash
doops list
doops targets --target gpu-ampere01
doops -session smoke exec --target gpu-ampere01 --cmd "hostname"
doops -session smoke ask --target gpu-ampere01 --msg "用一句话说明当前执行环境"
```

## 常用操作

### 命令选择表

| 需求 | 首选命令 | 说明 |
| :--- | :--- | :--- |
| 看本地已配置 target | `doops list` | 只看客户端配置，不代表 gateway 在线 |
| 看 gateway 在线 agent | `doops targets --target <gateway-target>` | gateway 模式排障先看这里 |
| 执行确定性 shell | `doops -session <s> exec --target <t> --cmd '<cmd>'` | 适合明确命令、只读检查、部署脚本 |
| 交给 AI 自主分析执行 | `doops -session <s> ask --target <t> --msg '<task>'` | 适合巡检、排障、需要多步判断的任务 |
| 推送本地目录到远端工作区 | `doops -session <s> push --target <t> --src <dir>` | 落到 `/root/ws/<session>` |
| 拉取远端工作区到本地 | `doops -session <s> pull --target <t> --dest <dir>` | 基于 Git，用于大文件/二进制/课程资源包 |
| 查看远端小文本 | `doops -session <s> read --target <t> --path <file>` | 只看小文本，不下载大文件/二进制 |
| 写入远端小文本 | `doops -session <s> write --target <t> --path <file> '<content>'` | 适合小脚本/配置片段 |
| 查看节点信息 | `doops -session <s> info --target <t>` | 获取 CPU/内存/磁盘等基础信息 |
| 检查镜像是否一致 | `doops -session <s> check --target <t> ...` | 用于上线后核验部署镜像 |
| 清理远端工作区 | `doops -session <s> clean --target <t>` | 清理 `/root/ws/<session>` |
| 登录/缓存 token | `doops login ...` | gateway 可用用户名密码换 user token |
| 登出/清理缓存 token | `doops logout --target <t>` | 清掉本地缓存 token |
| 升级在线 agent | `doops -session <s> upgrade ... --dry-run` | 需要 `agent:upgrade` 或 `admin` |

下载大文件、压缩包、数据库导出、图片、视频、课程资源包等资产时，用 `pull` 拉取整个 session 工作区。不要用 `read`，也不要让 `exec` 输出 base64。远端生成大文件后，应记录路径和 sha256，再用同一个 session 执行 `pull`。

### 执行确定性命令

```bash
doops -session ops exec --target gpu-ampere01 --cmd "top -bn1 | head -10 && df -h && free -h"
```

### 发送自然语言任务

```bash
doops -session ops ask --target gpu-ampere01 --msg "检查磁盘和内存压力，告诉我结论并给出建议"
```

### 推送代码到远端工作区

```bash
doops -session build push --target gpu-ampere01 --src .
doops -session build exec --target gpu-ampere01 --cmd "ls -la /root/ws/build | head"
```

直连模式下 `push` 走 agent 直连文件同步路径；gateway 模式下 `push` 走 WebSocket 分块上传到目标 agent，不要求内网 agent 暴露 Git HTTP 或公网端口。

### 拉取远端工作区

```bash
doops -session build pull --target gpu-ampere01 --dest ./doops-build-output
```

`pull` 和 `push` 一样属于工作区同步能力，基于 Git 快照语义。它会拉取 `/root/ws/<session>` 整个远端工作区，适合拿回 tgz/zip/sql/图片/课程资源包等大文件或二进制产物。不要用 `read` 或 `exec base64` 做下载。

### 查看远端小文本

```bash
doops -session ops read --target gpu-ampere01 --path /root/ws/ops/deploy.sh
```

`read` 只用于查看小文本，例如脚本、配置、JSON/YAML、短日志片段。不要用 `read` 下载 tgz/zip/sql/图片/视频/课程资源包，也不要用 `exec` 输出 base64 来绕过这个限制；这类资产需要走专门的下载能力。

### 写入远端小文本

```bash
doops -session ops write --target gpu-ampere01 --path /root/ws/ops/notes.txt "hello from doops"
doops -session ops read --target gpu-ampere01 --path /root/ws/ops/notes.txt
```

`write` 适合小文本和短脚本。不要用它传大目录、压缩包或二进制资产；代码和目录同步走 `push`。

### 节点信息与镜像核验

```bash
doops -session ops info --target gpu-ampere01
doops -session ops check --target gpu-ampere01 \
  --namespace default \
  --deployment app \
  --image repo.example.com/team/app:latest
```

`info` 是轻量只读检查。`check` 用于确认线上 deployment 当前镜像是否符合预期。

### 清理远端工作区

```bash
doops -session build clean --target gpu-ampere01
```

`clean` 清理当前 session 的远端工作区。清理前确认 session 名正确，不要把多个任务混用同一个 session。

### 登录与登出

直连 agent 通常直接在配置里放 agent token。Gateway 模式可以缓存 user token：

```bash
doops login --target jm --gateway https://gateway.example.com --username alice
doops logout --target jm
```

登录缓存只影响本地 CLI，不会修改 gateway 权限。权限不足仍然要由管理员 grant 对应 `cluster/instance/action`。

### 远端 BuildKit 构建

```bash
doops -session build exec --target gpu-ampere01 --cmd \
  "cd /root/ws/build && buildctl --addr unix:///run/buildkit/buildkitd.sock build \
   --progress=plain \
   --frontend dockerfile.v0 \
   --local context=. \
   --local dockerfile=. \
   --opt filename=Dockerfile \
   --output type=image,name=repo.example.com/team/app:latest,push=true"
```

## 首次安装 agent

只有在目标机器还没有 `doops-agent` 时才用 SSH：

```bash
doops install \
  --name gpu-ampere01 \
  --ip 89.250.81.244 \
  --ssh-user root \
  --ssh-password '<SSH_PASSWORD>' \
  --ssh-port 22 \
  --agent-token '<OPTIONAL_AGENT_TOKEN>'
```

说明：

- `--agent-token` 不传时，CLI 会自动生成 token
- 安装完成后，后续使用一律走 `doops add --token` / `doops exec` / `doops ask`
- 不要把 SSH 密码当成 agent token 理解

## 故障提示

- 如果返回 `Unauthorized`，优先检查 token 是否正确
- 如果 gateway 返回 `forbidden`，说明 user token 没有对应 action 或 target scope 权限
- 如果返回 `Connection refused`，检查服务端 `42222` 是否监听
- 如果 gateway target 不在线，先跑 `doops targets --target <gateway-target>`，确认 `cluster/instance` 是否已注册
- 如果 gateway `push` 失败，先确认用户有 `push` action；直连 `push` 再检查远端 agent 的 `/git/` 端点和 token
- 如果 gateway `pull` 失败，先确认用户有 `pull` action；再确认远端 `/root/ws/<session>` 存在，且 agent 能执行 `git bundle`
- 如果用户让你“连机器看看”，优先用 `doops exec`，不要先退回 SSH
