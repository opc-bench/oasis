import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from camel.models import BaseModelBackend, ModelFactory
from camel.types import ModelPlatformType, ModelType

# 确保可以从本地 oasis 目录导入 creator_agent，而不是环境里的其他包
OASIS_ROOT = Path(__file__).resolve().parents[1]
if str(OASIS_ROOT) not in sys.path:
    sys.path.insert(0, str(OASIS_ROOT))

from creator_agent import LLMBackend, SimpleCreatorAgent

from twitter_market_io import (
    TwitterDbMarket,
    get_twitter_db_path,
    ensure_twitter_db_seeded,
)


class CamelLLMBackend(LLMBackend):
    """适配 CAMEL BaseModelBackend -> 通用 LLMBackend 接口."""

    def __init__(self, backend: BaseModelBackend) -> None:
        self.backend = backend

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        resp = self.backend.run(messages, **kwargs)
        choice = resp.choices[0]
        return choice.message.content


def _demand_from_feedback(feedback_summary: Dict[str, Any]) -> str:
    """从 observe 的 feedback_summary 提炼出需求描述，供 build_game_prompt 使用。"""
    raw = feedback_summary.get("raw_summary")
    if raw and isinstance(raw, str) and raw.strip():
        return raw.strip()
    parts = []
    if feedback_summary.get("topic") and feedback_summary["topic"] != "no_feedback":
        parts.append(f"主题/话题：{feedback_summary['topic']}")
    if feedback_summary.get("pain_points"):
        parts.append("痛点：" + "；".join(str(p) for p in feedback_summary["pain_points"]))
    if feedback_summary.get("positive_signals"):
        parts.append("正面信号：" + "；".join(str(s) for s in feedback_summary["positive_signals"]))
    return "\n".join(parts) if parts else "（暂无结构化反馈，请根据下方原始反馈自行提炼需求）"


def build_game_prompt(
    demand_text: str,
    raw_timeline: List[Dict[str, Any]],
    previous_code: str | None,
    last_error: str | None,
) -> str:
    """
    需求由外部传入（来自社交媒体信息提炼结果），本函数只规范代码输出格式与约束。
    不包含任何具体游戏类型或玩法描述。
    """
    if previous_code is None:
        raw_block = "\n".join(
            f"- {item.get('content', '').strip() or '(无内容)'}"
            for item in raw_timeline
        )
        if not raw_block.strip():
            raw_block = "（当前无原始反馈条目）"
        return f"""
你是一名资深 Python 独立开发者。请根据下面「由社交媒体/用户反馈提炼出的需求」实现一个可运行的 Python 终端小游戏。具体玩法和类型完全由需求决定，不要被本提示词限定。

=== 提炼后的需求（据此设计游戏） ===
{demand_text}

=== 原始反馈（供参考） ===
{raw_block}

=== 代码输出规范（必须遵守） ===
1. 只输出纯 Python 源码，不要输出任何解释、说明或 Markdown。
2. 严禁输出任何代码块标记（如 ```python、```），只输出源码本身。
3. 代码必须能通过：python -m py_compile mini_game.py

常见错误：首行输出 ```python 会导致 SyntaxError，请勿出现。
""".strip()

    return f"""
你之前生成的终端小游戏 Python 代码在语法检查时出错，请输出修正后的完整源码。

=== 上一版代码 ===
{previous_code}

=== 语法检查错误（py_compile） ===
{last_error}

=== 代码输出规范（必须遵守） ===
1. 只输出修正后的完整 Python 源码，不要解释。
2. 严禁输出 Markdown 或代码块标记，只输出源码本身。
3. 修复上述错误，确保 python -m py_compile mini_game.py 通过。

常见错误：首行输出 ```python 会导致 SyntaxError，请勿出现。
""".strip()


async def main() -> None:
    # 以 oasis 目录作为根目录，所有相关文件都保存在 oasis 下
    oasis_root = Path(__file__).resolve().parents[1]
    sandbox_dir = oasis_root / "tests" / "mini_game_sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    out_path = sandbox_dir / "mini_game.py"

    # 1. 构建 Creator Agent（Observe / Code / Market 三段式）
    # 与 creator_agent_openrouter_demo 一致：从 twitter_complex_demo 的 DB 读取时间线
    db_path = get_twitter_db_path()
    market = TwitterDbMarket(db_path=db_path)
    print(f"[Market] 使用 Twitter 仿真 DB: {db_path}")
    if ensure_twitter_db_seeded(db_path):
        print("[Market] 检测到 DB 无数据，已写入种子数据以保证获取信息链路可打通")

    model_backend = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_LLAMA_3_1_70B,
    )
    llm_backend = CamelLLMBackend(model_backend)

    agent = SimpleCreatorAgent(
        llm_backends={"general": llm_backend},
        market_io=market,
        initial_budget=10_000.0,
    )

    # === 1) Observe: 读取「市场」上的需求 ===
    print("=== OBSERVE 阶段：收集小游戏需求 ===")
    observe_result = await agent.observe(limit=10)
    print("反馈原文：", observe_result["raw_timeline"])
    feedback = observe_result["feedback_summary"]
    raw_summary = feedback.get("raw_summary", feedback.get("topic", "无反馈"))
    # 完整反馈总结：来自 creator_agent.observe() -> summarize_feedback -> LLM 的整段输出
    print("反馈总结（raw LLM 输出）完整内容：")
    print("-" * 60)
    print(raw_summary)
    print("-" * 60)

    # === 2) Code: 基于需求+GAME_BRIEF 设计并实现小游戏（带自反纠错） ===
    print("\n=== CODE 阶段：生成并在沙盒中测试 mini_game.py ===")
    max_rounds = 3
    last_code: str | None = None
    last_error: str | None = None

    demand_text = _demand_from_feedback(observe_result["feedback_summary"])
    for round_idx in range(1, max_rounds + 1):
        print(f"[Agent] 代码生成/修复轮次 {round_idx}/{max_rounds} ...")
        game_prompt = build_game_prompt(
            demand_text=demand_text,
            raw_timeline=observe_result["raw_timeline"],
            previous_code=last_code,
            last_error=last_error,
        )
        code_text = llm_backend.chat([{
            "role": "user",
            "content": game_prompt
        }])

        out_path.write_text(code_text, encoding="utf-8")
        print(f"[Agent] 已在沙盒目录写入小游戏代码文件: {out_path}")

        print("[Sandbox] 正在进行语法检查...")
        compile_result = subprocess.run(
            ["python", "-m", "py_compile", "mini_game.py"],
            cwd=sandbox_dir,
            capture_output=True,
            text=True,
        )
        if compile_result.returncode == 0:
            print("[Sandbox] 语法检查通过。")
            last_code = code_text
            break

        last_error = compile_result.stderr
        last_code = code_text
        print("[Sandbox] 语法检查失败，将尝试自我修复：")
        print(last_error)
    else:
        print("[Agent] 多轮自我修复后仍未通过语法检查，请人工查看 "
              f"{out_path}")
        return

    print("[Sandbox] 正在进行短暂运行测试...")
    run_result = subprocess.run(
        ["python", "mini_game.py"],
        cwd=sandbox_dir,
        input="50\nq\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    if run_result.returncode != 0:
        if "EOFError: EOF when reading a line" in run_result.stderr:
            print("[Sandbox] 检测到 EOFError（输入耗尽），在沙盒测试场景下视为可接受。")
            print("[Sandbox] 部分输出为：")
            print(run_result.stdout[:400])
        else:
            print("[Sandbox] 运行测试返回非零退出码，stderr 为：")
            print(run_result.stderr)
    else:
        print("[Sandbox] 运行测试通过，部分输出为：")
        print(run_result.stdout[:400])

    # === 3) Market: 发布更新 + 宣传文案 ===
    print("\n=== MARKET 阶段：发布更新与宣传文案 ===")
    marketing_prompt = """
你已根据社交媒体/用户反馈完成了一个基于命令行的 Python 终端小游戏（具体玩法由反馈需求决定）。请按以下规范输出，不要编造具体游戏名称或类型：

1. 输出一段 3~5 句的「更新说明 / Release Note」，中文，面向 GitHub README 用户，概括本次更新与反馈的对应关系。
2. 输出 3 条适合发在 Twitter/X 的英文推广文案，每条不超过 240 字符，可带少量 Emoji 和 1~2 个 Hashtag。

仅规范格式：请使用清晰分段，便于直接复制使用；不要在本提示词中给出具体游戏名或玩法描述。
""".strip()

    marketing_text = llm_backend.chat([{
        "role": "user",
        "content": marketing_prompt
    }])
    await agent.market(
        message="Shipped a terminal mini-game based on user feedback.",
        metadata={"type": "release_note"},
    )

    print("\n[Agent] 发布说明和宣传文案：\n")
    print(marketing_text)


if __name__ == "__main__":
    asyncio.run(main())



