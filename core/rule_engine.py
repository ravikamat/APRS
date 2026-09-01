"""
core/rule_engine.py — Human-Curated Rule Accumulator for APRS V6 Pro.

Applies human-validated rules to products during pipeline processing.
Instead of "AI self-improvement," we use human-validated rule accumulation:
after each batch, the operator analyzes rejections and adds rules.
The system applies these rules automatically to future batches.

Safety:
- Conditions are evaluated using ast.parse + eval with restricted builtins
- Only safe comparison, arithmetic, boolean operators, and string methods allowed
- No execution of arbitrary Python functions or imports
"""
import ast
import logging
import sqlite3
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


# Allowed AST node types for safe expression evaluation
_ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
    ast.Not,
    ast.In,
    ast.NotIn,
    ast.Attribute,
    ast.Call,
)

_SAFE_METHODS = {"lower", "upper", "strip", "startswith", "endswith", "replace", "split", "find"}


class RuleEngine:
    """
    Evaluates and applies accumulated rules to products.

    Usage:
        engine = RuleEngine(db_conn)
        adjusted_product = engine.evaluate(product_dict)
    """

    def __init__(self, db_conn: sqlite3.Connection):
        self.conn = db_conn
        self._ensure_table()
        self.rules = self._load_active_rules()

    def _ensure_table(self):
        """Ensure learned_rules table exists."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                condition_expr TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_value REAL,
                hit_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source TEXT DEFAULT 'manual'
            )
        """)
        self.conn.commit()

    def _load_active_rules(self) -> List[Dict[str, Any]]:
        """Load all active rules from database."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, rule_name, condition_expr, action_type, action_value, hit_count
            FROM learned_rules
            WHERE is_active = 1
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()
        rules = []
        for r in rows:
            rules.append({
                "id": r[0],
                "name": r[1],
                "condition": r[2],
                "action": r[3],
                "value": r[4],
                "hit_count": r[5],
            })
        return rules

    def reload(self):
        """Reload active rules from the database."""
        self.rules = self._load_active_rules()

    def evaluate(self, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply all active rules to a product dictionary.

        Args:
            product: Product dictionary with fields like category, price,
                     weight, review_count, net_margin_pct, etc.

        Returns:
            The product dictionary, potentially modified with rule adjustments
            and with a 'rule_adjustments' list appended.
        """
        adjustments = []
        hit_rule_ids = []

        for rule in self.rules:
            try:
                if self._safe_eval(rule["condition"], product):
                    adjustments.append({
                        "rule": rule["name"],
                        "action": rule["action"],
                        "value": rule["value"],
                    })
                    hit_rule_ids.append(rule["id"])

                    # Apply action
                    if rule["action"] == "MARGIN_ADJUST":
                        product["margin_threshold_override"] = rule["value"]
                    elif rule["action"] == "CATEGORY_BLOCK":
                        product["blocked_by_rule"] = True
                        product["block_reason"] = rule["name"]
                    elif rule["action"] == "SCORE_PENALTY":
                        product["score_penalty"] = product.get("score_penalty", 0.0) + (rule["value"] or 0.0)
                    elif rule["action"] == "SCORE_BONUS":
                        product["score_bonus"] = product.get("score_bonus", 0.0) + (rule["value"] or 0.0)
                    elif rule["action"] == "REQUIRE_CERT":
                        product["required_certifications"] = rule.get("value", "BIS")
            except Exception as e:
                logger.warning("Error evaluating rule '%s': %s", rule["name"], e)
                continue

        # Update hit counts in DB
        if hit_rule_ids:
            try:
                placeholders = ",".join(["?"] * len(hit_rule_ids))
                self.conn.execute(
                    f"UPDATE learned_rules SET hit_count = hit_count + 1 WHERE id IN ({placeholders})",
                    hit_rule_ids,
                )
                self.conn.commit()
            except Exception as e:
                logger.warning("Failed to update rule hit counts: %s", e)

        product["rule_adjustments"] = adjustments
        return product

    def _safe_eval(self, expr: str, context: Dict[str, Any]) -> bool:
        """
        Safely evaluate a Python expression against the product context.

        Only allows basic math, comparisons, boolean logic, membership tests,
        and safe string methods (.lower(), .strip(), etc.).
        """
        safe_context: Dict[str, Any] = {"__builtins__": {}}
        for k, v in context.items():
            if isinstance(v, (int, float, str, bool, list, type(None))):
                safe_context[k] = v

        try:
            tree = ast.parse(expr, mode="eval")
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    logger.warning("Disallowed AST node '%s' in rule: %s", type(node).__name__, expr)
                    return False
                if isinstance(node, ast.Attribute):
                    if node.attr.startswith("_") or node.attr not in _SAFE_METHODS:
                        logger.warning("Disallowed attribute '%s' in rule: %s", node.attr, expr)
                        return False
            compiled = compile(tree, "<rule>", "eval")
            result = eval(compiled, safe_context)
            return bool(result)
        except Exception as e:
            logger.debug("Safe eval failed for '%s': %s", expr, e)
            return False

    def add_rule(
        self,
        name: str,
        condition: str,
        action: str,
        value: Optional[float] = None,
        source: str = "manual",
    ) -> int:
        """
        Add a new rule to the database and reload the active rule cache.

        Args:
            name: Human-readable name (e.g. "Heavy Kitchen Items")
            condition: Safe Python expression (e.g. "category == 'home_kitchen' and weight_kg > 1.2")
            action: Action type (MARGIN_ADJUST, CATEGORY_BLOCK, SCORE_PENALTY, SCORE_BONUS)
            value: Numeric value for the action (e.g. 0.35 for 35% margin threshold)
            source: Rule origin ("manual", "analysis", "rejection_pattern")

        Returns:
            The ID of the newly created rule.
        """
        # Validate expression syntax before saving
        try:
            tree = ast.parse(condition, mode="eval")
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    raise ValueError(f"Disallowed expression element: {type(node).__name__}")
                if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr not in _SAFE_METHODS):
                    raise ValueError(f"Disallowed attribute method: {node.attr}")
        except Exception as e:
            raise ValueError(f"Invalid rule condition '{condition}': {e}")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO learned_rules (rule_name, condition_expr, action_type, action_value, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, condition, action, value, source),
        )
        self.conn.commit()
        self.reload()
        logger.info("Added rule '%s' (ID: %d)", name, cursor.lastrowid)
        return cursor.lastrowid

    def seed_default_rules(self):
        """Seed default high-confidence rules if table is empty."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM learned_rules")
        if cursor.fetchone()[0] > 0:
            return  # Already seeded

        default_rules = [
            (
                "Heavy Kitchen Items",
                "category == 'home_kitchen' and weight_kg > 1.2",
                "MARGIN_ADJUST",
                0.35,
                "manual",
            ),
            (
                "Low Review Count",
                "review_count < 30",
                "CATEGORY_BLOCK",
                0.0,
                "manual",
            ),
            (
                "Silicone Low Price High RTO",
                "'silicone' in canonical_title.lower() and retail_price_inr < 499",
                "MARGIN_ADJUST",
                0.40,
                "manual",
            ),
            (
                "Apparel High Return Buffer",
                "category == 'fashion' or category == 'apparel'",
                "MARGIN_ADJUST",
                0.30,
                "manual",
            ),
            (
                "Electronics Low Price Margin Risk",
                "category == 'electronics' and retail_price_inr < 500",
                "SCORE_PENALTY",
                10.0,
                "manual",
            ),
            (
                "High Rating Review Quality Bonus",
                "rating >= 4.5 and review_count >= 200",
                "SCORE_BONUS",
                5.0,
                "manual",
            ),
            (
                "High BSR Weak Signal Penalty",
                "amazon_bsr > 40000",
                "SCORE_PENALTY",
                5.0,
                "manual",
            ),
            (
                "Cheap Fragile Glassware",
                "'glass' in canonical_title.lower() and retail_price_inr < 399",
                "CATEGORY_BLOCK",
                0.0,
                "manual",
            ),
        ]

        for name, cond, act, val, src in default_rules:
            try:
                self.add_rule(name, cond, act, val, src)
            except Exception as e:
                logger.warning("Failed to seed rule '%s': %s", name, e)

        logger.info("Seeded %d default rules", len(default_rules))
