---
schema: "1.0"
name: debug-security-scan
version: "0.3.0"
description: 扫描项目安全漏洞并生成双轨报告：人类工程师版（kami 排版 HTML/PDF）+ AI 版（结构化 MD）。当用户要求检查代码安全、查找漏洞、安全审计时触发。
domain: security
triggers:
  keywords:
    primary: [安全扫描, 漏洞检测, 安全报告, security scan, vulnerability, security audit]
    secondary: [安全检查, 代码安全, 漏洞, CWE, OWASP, 渗透测试, 安全审计, cybersecurity, debug-security]
---

# Debug-Security 安全扫描 Skill

## 触发条件

当用户提出以下任一请求时，激活此 skill：

- "检查/扫描这个项目的安全漏洞"
- "安全审计" / "代码安全检查"
- "查找代码中的安全问题/漏洞"
- "生成安全报告" / "安全扫描报告"
- 任何包含"安全扫描"、"漏洞检测"、"security scan"、"vulnerability"的请求

## 前置条件

- Node.js >= 20
- debug-security CLI 已全局链接（`npm link` 在项目目录执行过）

## AI 分析策略

**零配置 AI 分析**：本 skill 利用宿主 AI Agent（Claude Code / Codex 等）自身的分析能力，无需用户配置任何 API Key 或 `.debug-security.yml` 文件。

AI 分析分两层：

| 层级 | 执行者 | 触发条件 | 说明 |
|------|--------|----------|------|
| Phase 1 规则扫描 | debug-security CLI | 始终执行 | 确定性规则匹配，快速精准 |
| Phase 2 AI 深度分析 | 宿主 AI Agent | 始终执行 | 语义分析、误报过滤、修复建议生成 |

如果用户配置了 `.debug-security.yml` 中的 API Key，CLI 内部也会执行 AI 分析，skill 层面的分析会检测并跳过已验证的 findings（`aiVerified: true`），避免重复工作。

## 输出架构

本 skill 生成**两份报告**，面向不同受众：

| 报告 | 受众 | 格式 | 说明 |
|------|------|------|------|
| AI 安全报告 | AI Agent / CI/CD | Markdown (.md) | 结构化数据，机器可解析，包含完整 findings 表格 |
| 人类工程师报告 | 安全工程师 / 技术主管 | HTML + PDF | 内嵌 kami 设计系统，可视化风险分布，修复建议优先级排序 |

人类工程师报告使用 skill 内嵌的 `templates/security-report.html` 模板，**无需安装 kami 或任何外部依赖**。

## 执行步骤

### Step 1: 环境检查

确认 debug-security 可用：

```bash
debug-security --version
```

如果命令不存在或报错，需要在 debug-security 项目目录执行 `npm run build && npm link`

### Step 2: 执行扫描（含 AI 分析）

直接运行 CLI 扫描命令，**无需提前检查或创建配置文件**：

```bash
debug-security scan-and-report <project-path> --output security-report-ai.md
```

CLI 的 Phase 1 规则扫描不依赖任何配置即可运行。AI 深度分析由本 skill 在 Step 4 自主完成，**不依赖 `.debug-security.yml` 或任何 API Key 配置**。

**参数说明：**

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `<project-path>` | 要扫描的项目路径 | 当前工作目录 |
| `-o, --output <file>` | 报告输出文件名 | `security-report-ai.md` |
| `--full` | 完整扫描模式 | 增量扫描 |
| `-c, --config <path>` | 自定义配置文件路径 | 当前工作目录 |

**超时设置：** 建议设置 5 分钟超时。大型项目可能需要更长时间。

### Step 3: 解析扫描结果

扫描完成后，CLI 会输出以下机器可读信息：

```
REPORT_PATH:/path/to/security-report-ai.md
FINDINGS_TOTAL:42
FINDINGS_CRITICAL:3
FINDINGS_HIGH:12
```

根据这些信息判断扫描结果：

- **退出码 0** → 无 critical/high 漏洞，项目安全状态良好
- **退出码 1** → 存在 critical 或 high 级别漏洞，需要关注

使用 Read 工具读取生成的 `security-report-ai.md` 文件，提取以下结构化数据用于后续报告生成：

```
必提取字段：
- 项目名称
- 扫描时间
- 扫描器版本
- 总漏洞数 / 各级别数量（Critical / High / Medium / Low）
- 各漏洞详情（编号、严重级别、标题、CWE、文件路径、行号、AI 分析结果、规则）
```

### Step 4: AI 深度分析（宿主 Agent 自主执行）

**这是零配置 AI 分析的核心步骤。** 使用宿主 AI Agent（即执行本 skill 的 AI）自身的分析能力，对 Phase 1 扫描结果进行深度分析。

**对于每个 finding（特别是 Critical 和 High 级别），执行以下分析：**

#### 4.1 误报过滤

对每个 finding，读取对应的源文件上下文（使用 Read 工具读取 finding 所在文件，关注 finding 行号前后 20 行），判断：

- 该 finding 是否为**真正的安全漏洞**？（排除误报）
- 漏洞是否在当前代码路径中**可达**？（死代码中的漏洞降级为 Low）
- 是否存在**缓解措施**？（如已有输入验证、参数化查询等）

对每个 finding 给出判定：
- `confirmed` — 确认为真实漏洞
- `false-positive` — 误报，附原因
- `mitigated` — 已有缓解措施，降级处理

#### 4.2 漏洞深度分析

对 `confirmed` 的漏洞，读取源码上下文后生成：

- **攻击向量分析**：攻击者如何利用此漏洞？具体的攻击路径是什么？
- **影响范围评估**：被攻击后影响哪些数据/功能？波及范围多大？
- **修复建议**：针对当前代码的具体修复方案（含代码示例），不是泛泛而谈
- **CWE 分类确认**：验证 CLI 给出的 CWE 分类是否准确，必要时修正
- **OWASP Top 10 映射**：将漏洞映射到 OWASP Top 10 (2021) 的具体类别

#### 4.3 额外发现

在阅读源码过程中，如果发现 CLI 未检测到的安全风险（如业务逻辑漏洞、不安全的反序列化、权限提升等），主动记录为 `AI-Discovered` 类型的 finding，包含：

- 漏洞标题和严重级别
- 所在文件和行号
- 详细描述和修复建议
- CWE 编号

#### 4.4 分析结果汇总

将 AI 分析结果整理为结构化数据，用于后续报告生成：

```
AI 分析汇总格式：
{
  findings: [
    {
      id: "原 finding 编号",
      verdict: "confirmed | false-positive | mitigated",
      aiVerified: true,
      attackVector: "攻击向量描述",
      impact: "影响范围",
      remediation: "具体修复建议",
      codeFix: "代码修复示例（如适用）",
      cwe: "CWE-XXX",
      owasp: "A01:2021-Broken Access Control"
    }
  ],
  discovered: [
    // AI 额外发现的漏洞
  ],
  stats: {
    total: N,
    confirmed: N,
    falsePositives: N,
    mitigated: N,
    newlyDiscovered: N
  }
}
```

**性能优化：** 对于 findings 超过 20 个的项目，优先分析 Critical 和 High 级别的 findings。Medium/Low 级别可批量简要分析。

### Step 5: 生成 AI 报告（输出一）

基于 CLI 生成的原始报告和 Step 4 的 AI 分析结果，生成增强版 AI 报告。

**首先验证 CLI 报告完整性：**

1. 确认文件包含 Summary 章节
2. 确认漏洞数量与 CLI 输出一致
3. 确认 findings 表格完整（无截断）

**然后用 AI 分析结果增强报告，将最终版回写到 `security-report-ai.md`：**

```markdown
# Security Scan Report
> Generated: 2026/4/29 16:00:00
> Scanner: debug-security v0.1.0
> AI Analysis: Host Agent (Zero-Config)

## Summary
| Metric | Value |
|--------|-------|
| Total Open Findings | **42** |
| AI Confirmed | 35 |
| False Positives | 5 |
| Mitigated | 2 |
| AI Discovered | 3 |
| Critical | 3 |
| High | 12 |
| Medium | 18 |
| Low | 9 |

## 项目名 — Confirmed Findings (35 findings)
| # | Severity | Title | CWE | File | Line | Verdict | OWASP |
|---|----------|-------|-----|------|------|---------|-------|

## False Positives (5 findings)
| # | Title | Reason | File | Line |
|---|-------|--------|------|------|

## AI-Discovered Findings (3 findings)
| # | Severity | Title | CWE | File | Line | Description |
|---|----------|-------|-----|------|------|-------------|

## Detailed Analysis (Critical & High)
### Finding #1: [Title]
- **Attack Vector:** ...
- **Impact:** ...
- **Remediation:** ...
- **Code Fix:** ...

## Scan History
| Time | Project | Status | Findings | Duration |
```

**关键：** AI 分析结果必须回写到 `security-report-ai.md`，使该文件包含完整的 AI 增强信息。

### Step 6: 生成人类工程师报告（输出二）

使用 skill 内嵌模板生成专业排版的安全报告，**零外部依赖**。

#### 6.1 读取内嵌模板

```
模板路径：~/.claude/skills/debug-security-scan/templates/security-report.html
```

使用 Read 工具读取模板，然后复制到目标项目目录，命名为 `security-report-human.html`。

#### 6.2 填充数据

模板中使用 `{{PLACEHOLDER}}` 标记所有需要替换的字段。根据 Step 3 和 Step 4 提取的数据，逐项替换：

**封面区域：**
| 占位符 | 替换为 |
|--------|--------|
| `{{PROJECT_NAME}}` | 项目名称 |
| `{{TOTAL}}` | 漏洞总数 |
| `{{CRITICAL}}` / `{{HIGH}}` / `{{MEDIUM}}` / `{{LOW}}` | 各级别数量 |
| `{{VERSION}}` | debug-security 版本号 |
| `{{SCAN_DATE}}` | 扫描时间 |
| `{{PROJECT_PATH}}` | 扫描路径 |
| `risk-critical` (class) | 根据风险评级切换：`risk-critical` / `risk-warning` / `risk-good` |

**指标卡片和环形图：** 自动根据各级别数量计算 SVG 环形图的比例值。

**高危漏洞详情（Chapter 02）：**
- 为每个 Critical/High finding 复制 `.finding-card` 块
- 填入标题、CWE、文件路径、行号、描述、修复建议
- 按 severity 设置卡片 class：`critical` / `high`

**中低危漏洞表格（Chapter 03）：**
- 为每个 Medium/Low finding 添加表格行
- 设置对应的 `.sev-*` 级别标签

**修复路线图（Chapter 04）：**
- 根据各级别数量填充修复时间线
- 计算截止日期：P0(+1天)、P1(+3天)、P2(+7天)
- 填充 Top 5 文件漏洞分布柱状图

**附录（Chapter 05）：**
- 按 CWE 分类汇总
- OWASP Top 10 映射
- 扫描配置参数

**风险评级计算规则：**

| 条件 | 评级 | risk-badge class |
|------|------|-----------------|
| Critical > 0 | 🔴 高危 | `risk-critical` |
| High > 3 或 (High + Critical) > 5 | 🔴 高危 | `risk-critical` |
| High > 0 且 ≤ 3 | 🟡 中等 | `risk-warning` |
| 仅 Medium/Low | 🟡 中等 | `risk-warning` |
| Total = 0 | 🟢 良好 | `risk-good` |

#### 6.3 构建 PDF

使用 Chrome headless 生成 PDF（零依赖，无需 WeasyPrint）：

```bash
chrome --headless --disable-gpu --no-sandbox --print-to-pdf=security-report-human.pdf security-report-human.html
```

如果 Chrome 不可用，优先尝试以下命令路径：

```bash
# Windows
"C:/Program Files/Google/Chrome/Application/chrome.exe" --headless --disable-gpu --print-to-pdf=security-report-human.pdf security-report-human.html

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --headless --print-to-pdf=security-report-human.pdf security-report-human.html
```

如果 Chrome 不可用，仅输出 HTML 版本，告知用户可在浏览器中打开 HTML 并"打印为 PDF"。

#### 6.4 验证输出

- 确认 HTML 文件生成成功且文件大小 > 0
- 确认所有 `{{PLACEHOLDER}}` 已被替换（无残留占位符）
- 如果生成了 PDF，确认文件大小 > 10KB

### Step 7: 向用户展示结果

展示扫描摘要，包含两份报告路径：

```
┌─ 扫描完成 ──────────────────────────────────────────────┐
│                                                          │
│  项目：{项目名}                                          │
│  漏洞总数：{N}                                           │
│  ├── Critical: {C}  🔴                                   │
│  ├── High: {H}     🟠                                    │
│  ├── Medium: {M}   🟡                                    │
│  └── Low: {L}      🟢                                    │
│                                                          │
│  📄 报告输出：                                           │
│  ├── 人类版：security-report-human.html / .pdf           │
│  └── AI  版：security-report-ai.md                       │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

然后根据扫描结果给出建议：

| 场景 | 建议 |
|------|------|
| 有 critical 漏洞 | 建议立即修复，优先处理 API Key 泄露、硬编码密码等问题 |
| 有 high 漏洞 | 建议尽快修复，关注 SQL 注入、XSS 等 OWASP Top 10 问题 |
| 仅 medium/low | 告知风险可控，建议排期处理 |
| 无漏洞 | 确认项目安全状态良好 |

## 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| 命令超时（>5min） | 建议使用 `--full` 参数，或检查项目大小 |
| CLI 无 AI 配置 | **不影响 AI 分析**。CLI 仅执行 Phase 1 规则扫描，Phase 2 AI 分析由 skill 宿主 Agent 自主完成，无需任何配置 |
| 项目路径不存在 | 明确告知用户检查路径，列出正确路径 |
| Node.js 版本不足 | 提示需要 Node.js >= 20 |
| 数据库锁定 | 建议关闭其他 debug-security 进程后重试 |
| debug-security: command not found | 需要在 debug-security 项目目录执行 `npm run build && npm link` 安装全局链接 |
| 内嵌模板缺失 | 仅生成 AI 版 MD 报告，跳过人类版，提示重新安装 debug-security-scan skill |
| Chrome headless 不可用 | 仅输出 HTML，告知用户可在浏览器中"打印为 PDF" |

## 示例对话

**用户：** 帮我扫描一下这个项目的安全漏洞

**AI 执行流程：**
1. 检测到安全扫描意图 → 激活 debug-security-scan skill
2. 环境检查 → 直接运行扫描（无需配置检查）
3. 运行 `debug-security scan-and-report . --output security-report-ai.md`
4. 等待 CLI Phase 1 完成 → 解析结果
5. **Phase 2 AI 深度分析**（宿主 Agent 自主执行）：读取每个漏洞的源码上下文，进行误报过滤、攻击向量分析、修复建议生成
6. 生成增强版 `security-report-ai.md`（含 AI 分析结果）
7. 填充内嵌模板 → 生成人类版 HTML → Chrome headless 生成 PDF
8. 展示摘要 + 双轨报告路径
9. "扫描完成。发现 42 个漏洞（3 Critical, 12 High），其中 AI 确认 35 个真实漏洞、5 个误报、2 个已有缓解。AI 额外发现 3 个规则未覆盖的安全风险。已生成两份报告：
   - 人类工程师版：`security-report-human.pdf`（专业排版，可视化风险分布）
   - AI 分析版：`security-report-ai.md`（含 AI 深度分析，机器可解析）
   需要我帮你查看高危漏洞的详情和修复方案吗？"
