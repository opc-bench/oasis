import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from camel.models import BaseModelBackend, ModelFactory
from camel.types import ModelPlatformType, ModelType

# Force using the local oasis package (this folder) rather than any installed one.
THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent  # D:/python_file/opc-bench/oasis
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from creator_agent import LLMBackend, SimpleCreatorAgent

from twitter_market_io import TwitterDbMarket, get_twitter_db_path


class CamelLLMBackend(LLMBackend):
    """Adapter to use a CAMEL BaseModelBackend as an LLMBackend."""

    def __init__(self, backend: BaseModelBackend) -> None:
        self.backend = backend

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        # CAMEL BaseModelBackend expects a list of OpenAI-style dict messages.
        resp = self.backend.run(messages, **kwargs)
        # OpenAI-compatible response: choices[0].message.content
        choice = resp.choices[0]
        message = choice.message
        return message.content


async def main() -> None:
    # Create a real StepFun OpenRouter model via CAMEL.
    openrouter_model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENROUTER,
        model_type=ModelType.OPENROUTER_LLAMA_3_1_70B,
    )

    llm_backend = CamelLLMBackend(openrouter_model)
    # Read timelines from the same db as twitter_complex_demo (set OASIS_DB_PATH
    # when running that demo, or use default examples/data/twitter_50rounds.db).
    db_path = get_twitter_db_path()
    market = TwitterDbMarket(db_path=db_path)
    print(f"[Market] using Twitter simulation db: {db_path}")

    agent = SimpleCreatorAgent(
        llm_backends={"general": llm_backend},
        market_io=market,
        initial_budget=10_000.0,
    )

    print("=== OBSERVE (OpenRouter) ===")
    observe_result = await agent.observe(limit=10)
    print("Feedback summary (raw LLM output):")
    print(observe_result["feedback_summary"]["raw_summary"])

    print("\n=== CODE (OpenRouter) ===")
    code_result = await agent.code(repo_root="D:/python_file/opc-bench")
    print("Proposed plan:")
    print(code_result["plan"])

    print("\n=== MARKET (TwitterDb) ===")
    await agent.market(
        message="Shipped improvements to onboarding and analytics reliability "
        "based on latest user feedback.",
        metadata={"type": "release_note"},
    )


if __name__ == "__main__":
    asyncio.run(main())

