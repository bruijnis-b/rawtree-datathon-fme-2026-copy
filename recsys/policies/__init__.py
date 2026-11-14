"""Registry of recommendation policies: add a file with a Policy subclass, then list it here."""
from .base import Policy, Request
from .baseline import Baseline
from .category_pop import CategoryPop
from .coview import Coview
from .embed import Embed

REGISTRY: dict[str, type[Policy]] = {cls.name: cls for cls in (Baseline, CategoryPop, Coview, Embed)}

__all__ = ["Policy", "Request", "REGISTRY"]
