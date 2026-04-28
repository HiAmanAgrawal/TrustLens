"""Product advisor tools — imported and bound to the LLM in graph.py."""
from app.agents.product_advisor.tools.search_web import search_web
from app.agents.product_advisor.tools.lookup_product import lookup_product_db
from app.agents.product_advisor.tools.nutrition_rules import assess_suitability
from app.agents.product_advisor.tools.trust_score import calculate_trust_score

ALL_TOOLS = [search_web, lookup_product_db, assess_suitability, calculate_trust_score]

__all__ = ["ALL_TOOLS", "search_web", "lookup_product_db", "assess_suitability", "calculate_trust_score"]
