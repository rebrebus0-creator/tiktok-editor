"""Планировщик на Claude: понимает сценарий и сам решает, что искать.

Это то самое «нейронка распознаёт, какие нужны фото и видео». На входе —
свободный текст (бриф, сценарий, закадровый текст), на выходе — готовые
поисковые запросы на английском (стоки ищут по английскому кратно лучше).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..config import Settings
from ..errors import StockMediaError
from ..models import MediaKind, Orientation, SearchQuery
from .base import Planner

SYSTEM_PROMPT = """\
Ты подбираешь стоковые видео и фото под сценарий короткого вертикального ролика.

Разбей сценарий на визуальные сцены и для каждой придумай поисковый запрос \
к стоковым банкам (Pexels, Pixabay).

Правила:
- запрос всегда на английском, 2-4 слова, конкретный и визуальный;
- описывай то, что видно в кадре, а не абстракции: не "успех", а \
"businessman celebrating office";
- никаких имён брендов, знаменитостей и названий компаний — на стоках их нет;
- запросы не должны дублировать друг друга;
- scene_hint — фрагмент исходного текста, под который подобран запрос, \
на языке оригинала.
"""


class _PlannedQuery(BaseModel):
    text: str = Field(description="Поисковый запрос на английском, 2-4 слова")
    scene_hint: str = Field(description="Фрагмент сценария, к которому относится запрос")


class _Plan(BaseModel):
    queries: list[_PlannedQuery]


class LLMPlanner(Planner):
    def __init__(self, settings: Settings) -> None:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            raise StockMediaError(
                "не установлен anthropic (pip install 'stock-media[llm]')"
            ) from exc

        self.settings = settings
        # Без явного ключа SDK сам подтянет ANTHROPIC_API_KEY или профиль `ant auth login`.
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def plan(
        self,
        brief: str,
        *,
        kind: MediaKind = MediaKind.VIDEO,
        orientation: Orientation = Orientation.PORTRAIT,
        max_queries: int = 6,
    ) -> list[SearchQuery]:
        response = self.client.messages.parse(
            model=self.settings.planner_model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Сценарий:\n{brief}\n\n"
                        f"Верни не больше {max_queries} запросов."
                    ),
                }
            ],
            output_format=_Plan,
        )

        if response.stop_reason == "refusal":
            raise StockMediaError("модель отказалась обрабатывать сценарий")

        plan = response.parsed_output
        if plan is None:
            raise StockMediaError("модель не вернула структурированный ответ")

        return [
            SearchQuery(
                text=q.text,
                kind=kind,
                orientation=orientation,
                scene_hint=q.scene_hint,
            )
            for q in plan.queries[:max_queries]
        ]


def build_planner(settings: Settings) -> Planner:
    """LLM, если есть ключ; иначе — эвристика, чтобы модуль не падал."""
    from .heuristic import HeuristicPlanner  # noqa: PLC0415

    if not settings.anthropic_api_key:
        return HeuristicPlanner()
    try:
        return LLMPlanner(settings)
    except StockMediaError:
        return HeuristicPlanner()
