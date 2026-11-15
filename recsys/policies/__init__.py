"""Registry of recommendation policies: add a file with a Policy subclass, then list it here."""
from .base import Policy, Request
from .baseline import Baseline
from .category_pop import CategoryPop
from .cold import ColdCombined, ColdEmbed
from .combined import Combined
from .coview import Coview
from .discount_boost import DiscountBoost
from .embed import Embed
from .embed_score import EmbedScore
from .price_discount import PriceDiscount
from .shopper_discount import ShopperDiscount
from .shopper_profile import ShopperProfile
from .shopper_score import ShopperScore
from .trend_boost import TrendBoost

REGISTRY: dict[str, type[Policy]] = {cls.name: cls for cls in (Baseline, CategoryPop, Coview, TrendBoost,
                                                                DiscountBoost, PriceDiscount, ShopperProfile,
                                                                ShopperScore, ShopperDiscount, Combined, Embed,
                                                                EmbedScore, ColdCombined, ColdEmbed)}

__all__ = ["Policy", "Request", "REGISTRY"]
