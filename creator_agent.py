from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal protocol for LLM backends (OpenRouter, Claude, etc.)."""

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str: ...


@runtime_checkable
class MarketIO(Protocol):
    """Abstract interface for reading and writing to the market sandbox."""

    def fetch_timelines(self, limit: int = 50) -> List[Dict[str, Any]]: ...

    def post_update(self, content: str,
                    metadata: Dict[str, Any] | None = None) -> Any: ...


@dataclass
class Skill:
    """Declarative description of a Creator Agent skill."""

    name: str
    description: str
    handler: Callable[["BaseCreatorAgent", Dict[str, Any]], Dict[str, Any]]


@dataclass
class CreatorContext:
    """High-level state the Creator Agent can condition on."""

    market_observations: List[Dict[str, Any]] = field(default_factory=list)
    notes: Dict[str, Any] = field(default_factory=dict)
    remaining_budget: float | None = None


class BaseCreatorAgent(ABC):
    """Abstract Creator Agent for OPC-Bench / OASIS."""

    def __init__(
        self,
        llm_backends: Dict[str, LLMBackend],
        market_io: MarketIO,
        initial_budget: float | None = None,
    ) -> None:
        if "general" not in llm_backends:
            raise ValueError("llm_backends must include a 'general' backend.")

        self.llm_backends = llm_backends
        self.market_io = market_io
        self.context = CreatorContext(remaining_budget=initial_budget)
        self.skills: Dict[str, Skill] = {}

        self._register_builtin_skills()

    # ------------------------------------------------------------------
    # Skill system
    # ------------------------------------------------------------------
    def register_skill(self, skill: Skill) -> None:
        self.skills[skill.name] = skill

    def call_skill(self, name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.skills:
            raise KeyError(f"Skill '{name}' is not registered.")
        return self.skills[name].handler(self, payload)

    def _register_builtin_skills(self) -> None:
        """Register a minimal set of generic skills."""

        def summarize_feedback(agent: BaseCreatorAgent,
                               payload: Dict[str, Any]) -> Dict[str, Any]:
            comments: List[str] = payload.get("comments", [])
            if not comments:
                return {
                    "topic": "no_feedback",
                    "pain_points": [],
                    "positive_signals": [],
                }

            prompt = agent._build_feedback_prompt(comments)
            summary = agent._call_llm("general", prompt)
            return {"raw_summary": summary}

        self.register_skill(
            Skill(
                name="summarize_feedback",
                description=(
                    "Aggregate raw user comments into higher-level themes and "
                    "pain points using the general LLM backend."
                ),
                handler=summarize_feedback,
            ))

    # ------------------------------------------------------------------
    # Public high-level actions: Observe / Code / Market
    # ------------------------------------------------------------------
    async def observe(self, limit: int = 50) -> Dict[str, Any]:
        """Read market signals and update internal context."""
        timeline = self.market_io.fetch_timelines(limit=limit)
        self.context.market_observations = timeline

        comments = [item.get("content", "") for item in timeline]
        feedback = self.call_skill("summarize_feedback",
                                   {"comments": comments})
        self.context.notes["last_feedback_summary"] = feedback
        return {
            "raw_timeline": timeline,
            "feedback_summary": feedback,
        }

    @abstractmethod
    async def code(self, repo_root: str) -> Dict[str, Any]:
        """Plan and implement product changes under the current context."""

    async def market(self, message: str, metadata: Dict[str, Any] | None = None
                     ) -> Any:
        """Publish an update to the market."""
        return self.market_io.post_update(content=message, metadata=metadata)

    # ------------------------------------------------------------------
    # LLM helper
    # ------------------------------------------------------------------
    def _call_llm(self, backend_name: str, prompt: str) -> str:
        backend = self.llm_backends[backend_name]
        messages = [{"role": "user", "content": prompt}]
        return backend.chat(messages)

    def _build_feedback_prompt(self, comments: List[str]) -> str:
        joined = "\n".join(f"- {c}" for c in comments)
        return f"""
You are a Creator Agent operating inside an OPC-Bench style simulation.
You are reading noisy social media feedback from simulated users.

Your task:
1. Detect recurring pain points that block Product-Market Fit (PMF).
2. Distinguish functionality vs usability vs performance vs pricing issues.
3. Highlight any strong positive signals.
4. Think in terms of ARR and user retention (Utility, Friction).

User feedback:
{joined}

Write a concise analytical summary with:
- Key themes and pain points
- Evidence snippets (quote short phrases, not full comments)
- At most 5 concrete next actions a solo developer could take in the next iteration.
""".strip()


class SimpleCreatorAgent(BaseCreatorAgent):
    """A minimal concrete implementation suitable for demos/tests."""

    async def code(self, repo_root: str) -> Dict[str, Any]:
        feedback = self.context.notes.get("last_feedback_summary", {})
        prompt = f"""
You are a solo developer Creator Agent with access to a code repository at:
{repo_root}

You just analyzed recent user feedback (high-level summary below):
{feedback}

Propose a small, high-impact change you can implement in the next coding
iteration. Focus on:
- Improving task completion rates (Completion_i)
- Reducing interaction friction (Friction_i)

Return:
- A short natural language plan (3–5 bullet points).
- A brief commit message title.
""".strip()

        plan = self._call_llm("general", prompt)
        self.context.notes["last_code_plan"] = plan
        return {"plan": plan}

