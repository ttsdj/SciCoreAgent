# BiocoreagentV2.0

BiocoreagentV2.0 是一个面向科研与生物信息编程场景的本地 Coding Agent。它不是单纯把大模型接到终端，而是采用 **harness 框架**：模型负责提出动作，运行时负责工具校验、工作区边界、用户审批、执行轨迹、多 Agent 调度和确定性分析路由。

## 面试官 3 分钟版

### S - Situation：背景

生物信息编程任务通常同时包含脆弱的本地环境、大体量数据文件、R/Python 依赖冲突、文献证据、长时间运行脚本和复杂分析流程。普通聊天式 Agent 很容易出现这些问题：

- 反复读取同一个文件，进入低进展工具循环；
- 脚本失败后仍然声称“分析完成”；
- 在没有审批的情况下修改环境或安装依赖；
- 把真实密钥、原始数据或大文件混入仓库；
- 缺少可审计的分析轨迹和结果验证。

### T - Task：目标

本项目的目标是把一个轻量级本地 Coding Agent 升级为更安全、可审计、科研导向的 Agent Harness，使它能够：

- 在任意项目目录中启动和工作；
- 将常见生物分析任务路由到受控工作流；
- 保护 `.env`、原始数据、大文件和隐私信息不进入 Git；
- 支持本地 Skill、自沉淀 Wiki、PubMed 文献调研和代码-文献 provenance；
- 使用 explorer、planner、executor、verifier、bio_worker 等角色化子 Agent；
- 在 OmicVerse、DESeq2 等重型后端不可用时，给出可诊断的降级路径，而不是盲目循环。

### A - Architecture：架构

```text
CLI: biocoreagent-v2
  |
  +-- 运行时身份: BiocoreagentV2.0
  |
  +-- Agent Harness 控制层
  |     +-- 模型客户端: DeepSeek / OpenAI-compatible / Anthropic-compatible / Ollama
  |     +-- 工具执行器: 参数校验、审批、重复调用防护、trace 记录
  |     +-- 工作区沙箱: 所有路径都解析在 --cwd 指定目录下
  |     +-- 最终答案校验: 未验证结果文件时禁止声称成功
  |
  +-- 科研工作流层
  |     +-- analysis_router: bulk RNA-seq / 蛋白组 / 单细胞 / 表格 / coding
  |     +-- transcriptome capabilities: OmicVerse 检查、DESeq2 fallback、计划产物
  |     +-- fallback_script_runner: 生成一个脚本、运行一次、分类错误
  |     +-- result_exporter: CSV 确定性导出，避免模型工具死循环
  |
  +-- 知识沉淀层
  |     +-- .biocoreagent/wiki
  |     +-- .biocoreagent/skills
  |     +-- 代码-文献 provenance 链接
  |     +-- PubMed 与 Red-Blue 文献审查工具
  |
  +-- 多 Agent 调度层
        +-- explorer / planner / executor / verifier / bio_worker
        +-- jobs、teams、messages、retry、cancel 持久化
```

### R - Result：当前完成度

已经完成：

- CLI 入口和项目级状态目录 `.biocoreagent/`。
- 角色化多 Agent worker 和权限边界。
- Skill / Wiki 自沉淀、检索、读取工具。
- PubMed、文献调研、Red-Blue 对抗审查、XLSX 导出工具。
- Bulk RNA-seq 路由：OmicVerse 后端检查 + DESeq2 fallback。
- 非注册分析类型的受控 fallback runner。
- CSV 结果导出快捷路径，避免反复 `read_file/run_shell`。
- SSH 远程执行工具雏形和工作目录策略。
- 发布前安全检查脚本和基础测试。

当前限制：

- OmicVerse 是可选隔离后端，不作为主环境依赖。
- 蛋白组、单细胞目前已有路由和 fallback 控制，但还没有完整确定性分析后端。
- 内部仍保留 `pico/`、`corecoder/` 兼容模块名；公开项目身份、命令、README 和环境变量统一为 BiocoreagentV2.0 / `biocoreagent-v2` / `BIOCOREAGENT_*`。

## 快速开始

### 1. 克隆并安装

```powershell
git clone https://github.com/ttsdj/Biocoreagent.git BiocoreagentV2.0
cd BiocoreagentV2.0
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### 2. 配置模型服务

```powershell
Copy-Item .env.example .env
notepad .env
```

只在本机 `.env` 中填写密钥，不要提交 `.env`：

```env
BIOCOREAGENT_PROVIDER=deepseek
BIOCOREAGENT_DEEPSEEK_API_KEY=replace-me
BIOCOREAGENT_DEEPSEEK_API_BASE=https://api.deepseek.com/anthropic
BIOCOREAGENT_DEEPSEEK_MODEL=deepseek-chat
```

### 3. 在任意工作目录启动

指定工作目录：

```powershell
biocoreagent-v2 --cwd D:\path\to\your\project --approval ask
```

或者先进入工作目录再启动：

```powershell
cd D:\path\to\your\project
biocoreagent-v2 --approval ask
```

一次性任务：

```powershell
biocoreagent-v2 --cwd D:\path\to\project "检查 counts.txt，并规划 el vs rest 的 RNA-seq 差异分析"
```

## 可选：OmicVerse 后端

不建议把 OmicVerse 安装到主 Agent 环境。推荐使用独立 conda 环境，避免 torch、scanpy、anndata、setuptools 等重依赖互相污染。

```powershell
.\scripts\setup_omicverse_env.ps1 -EnvName biocore-omicverse
```

然后在 `.env` 中加入：

```env
BIOCOREAGENT_OMICVERSE_ENABLED=1
BIOCOREAGENT_OMICVERSE_PYTHON=C:\path\to\conda\envs\biocore-omicverse\python.exe
```

Agent 会在执行 OmicVerse-backed transcriptome 流程前检查该后端。如果 OmicVerse 不可用，bulk RNA-seq 会降级到 DESeq2 fallback，或者给出可诊断的环境修复建议。

## Docker

Docker 用于快速启动轻量 Agent 运行时，不打包大型生物数据。

```powershell
docker compose build
docker compose run --rm biocoreagent-v2 --help
```

挂载一个工作目录：

```powershell
docker compose --env-file .env run --rm -v D:\path\to\project:/workspace biocoreagent-v2 --cwd /workspace --approval ask
```

## GitHub 发布前安全检查

提交或推送前运行：

```powershell
python scripts\check_repo_safety.py
python -m pytest tests\test_fused_runtime.py tests\test_cli_welcome.py -q
```

安全脚本会拦截常见问题：

- `.env` 或 `.biocoreagent/` 等本地状态被提交；
- 形态像真实密钥的 token；
- 大文件；
- FASTQ/BAM/CRAM/H5AD/RDS 等原始组学数据；
- build、dist、egg-info、测试缓存等生成物。

## 仓库卫生规则

应该提交：

- `biocoreagent/`
- `pico/`
- `corecoder/`
- `mcp_servers/`
- `tests/`
- `scripts/`
- `README.md`
- `pyproject.toml`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `Dockerfile`
- `docker-compose.yml`

禁止提交：

- `.env`
- `.biocoreagent/`
- `.tmp/`、`.verify*/`、`.test-tmp*/`
- build 输出、wheel、egg-info
- 真实分析数据、原始组学数据、结果目录
- 私有 token、用户隐私数据

## 常用命令

```powershell
biocoreagent-v2 --help
biocoreagent-v2 --cwd . --approval ask
biocoreagent-v2 --cwd . --max-steps 40 "总结这个仓库的架构"
biocore-doctor
```

`biocoreagent` 仍作为兼容别名保留，但新的文档、演示和部署推荐使用 `biocoreagent-v2`。
