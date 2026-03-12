# OPC-Bench OASIS 快速上手

本文档说明如何在本地运行 Twitter 多智能体模拟，并通过 Dashboard 可视化结果。

## 环境准备

**依赖要求：** Python 3.11，已通过 Poetry/venv 管理。

```bash
cd /path/to/oasis
source .venv/bin/activate
```

**配置 API Key：**

```bash
cp .env.example .env
# 编辑 .env，填入你的 OpenRouter API Key
# OPENROUTER_API_KEY=sk-or-v1-...
```

> OpenRouter Key 申请地址：https://openrouter.ai/keys

---

## 运行模拟

### 快速测试（2 个 agent，5 步）

```bash
cd /path/to/oasis
source .venv/bin/activate
export $(cat .env | xargs)
python examples/quick_start.py
```

生成数据库：`./reddit_simulation.db`

---

### Twitter 完整模拟（10 个 agent，50 轮）

```bash
cd /path/to/oasis
source .venv/bin/activate
export $(cat .env | xargs)
python examples/twitter_complex_demo.py
```

生成数据库：`./data/twitter_50rounds.db`

**模拟流程：**
1. Agent 0 发起争议性推文（"AI 将替代 80% 工程师"）
2. Agents 1-4 第一波反应
3. Agent 5 发起反叙事推文
4. 所有 agent 循环运行 47 轮 LLM 决策

**Agent 行为说明：**
- Agent 使用 OpenRouter StepFun 3.5 Flash 模型驱动
- 10 个 agent 来自真实 Twitter 数据集（CSV 文件）
- 每轮 agent 自主选择：发帖、评论、点赞、转发、关注，或什么都不做
- 系统 prompt 已调优为更接近真实用户分布（大多数时候选择不操作）

---

## 启动 Dashboard

```bash
cd /path/to/oasis
source .venv/bin/activate
streamlit run dashboard.py
```

打开浏览器：http://localhost:8501

**使用方式：**
在左侧边栏的文件输入框中填入数据库的**完整绝对路径**，例如：

```
/Users/yourname/workspace/oasis/data/twitter_50rounds.db
```

**Dashboard 包含：**
- Twitter 风格 Feed（左栏）
- 行为分布饼图、每轮活跃度柱状图、Agent 排行榜（中栏）
- 社交关系图谱、Agent 详情面板、行为日志（右栏）
- 帖子量时间线、热门帖子（底部）

---

## 数据库说明

所有模拟结果保存为 SQLite 文件，主要表结构：

| 表名 | 内容 |
|------|------|
| `user` | Agent 用户信息 |
| `post` | 所有帖子（含点赞数、转发数） |
| `comment` | 评论 |
| `follow` | 关注关系 |
| `trace` | 每个 agent 每轮的完整行为记录 |

直接用 SQLite 工具（如 DB Browser for SQLite）也可以查看原始数据。

---

## 常见问题

**Q: 报错 `Missing or empty required API keys: OPENROUTER_API_KEY`**
A: 没有加载 .env，运行前需要 `export $(cat .env | xargs)`

**Q: Dashboard 找不到数据库文件**
A: 侧边栏需要填写**完整绝对路径**，不支持相对路径

**Q: 模拟跑完但报 `sqlite3.OperationalError`**
A: 不影响数据，只是打印摘要时的格式问题，数据库本身是完整的
