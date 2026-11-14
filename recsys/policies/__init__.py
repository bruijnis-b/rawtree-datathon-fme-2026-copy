"""Registry of recommendation policies: add a file with a Policy subclass, then list it here."""
from .base import Policy, Request
from .baseline import Baseline
from .category_pop import CategoryPop
from .coview import Coview
from .trend_boost import TrendBoost

REGISTRY: dict[str, type[Policy]] = {cls.name: cls for cls in (Baseline, CategoryPop, Coview, TrendBoost)}

__all__ = ["Policy", "Request", "REGISTRY"]
