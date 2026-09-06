"""
core/learning_engine.py — Learning Engine for APRS V7.

Weekly synthesis agent that analyzes outcomes, generates learned rules,
and continuously improves the system through automated reflection.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    get_connection, get_all_products, get_learned_rules,
    get_gate_status, get_supplier_profiles_for_product,
    add_learned_rule, get_llm_tier_stats,
)
from core.llm_router import LLMRouter, LLMTaskType
from core.rule_engine import create_rule_engine, Rule, RuleAction

logger = logging.getLogger("aprs.learning_engine")


@dataclass
class SynthesisResult:
    """Result of weekly learning synthesis."""
    rules_generated: int = 0
    rules_added: int = 0
    niches_updated: int = 0
    keywords_updated: int = 0
    sources_evaluated: int = 0
    summary: str = ""


class LearningEngine:
    """
    Learning Engine — Weekly Synthesis & Rule Generation.

    Analyzes 30-day research outcomes to:
    1. Identify category gate failure patterns -> learned rules
    2. Evaluate niche performance -> priority score updates
    3. Assess keyword yield -> weight updates
    4. Evaluate supplier response rates -> ranking updates
    6. Assess source yield -> source priority updates
    7. Generate weekly summary for dashboard
    """

    def __init__(self, llm_router: Optional[Any] = None):
        self.llm_router = llm_router
        self.rule_engine = create_rule_engine()

    async def weekly_synthesis(self) -> SynthesisResult:
        """
        Run the complete weekly learning synthesis.

        Returns:
            SynthesisResult with counts and summary
        """
        logger.info("Starting weekly learning synthesis")
        start_time = datetime.now(timezone.utc)

        result = SynthesisResult()

        # 1. Analyze gate failure patterns -> generate learned rules
        rules_added = await self._analyze_gate_failures()
        result.rules_generated = rules_added

        # 2. Evaluate niche performance -> update priorities
        niches_updated = await self._evaluate_niche_performance()
        result.niches_updated = niches_updated

        # 3. Assess keyword yield -> update weights
        keywords_updated = await self._evaluate_keyword_yield()
        result.keywords_updated = keywords_updated

        # 4. Assess supplier response rates -> ranking updates
        # (implemented when supplier conversations exist)

        # 5. Evaluate source yield -> priority updates
        sources_evaluated = await self._evaluate_source_yield()
        result.sources_evaluated = sources_evaluated

        # 6. Generate weekly summary using NIM 550B
        summary = await self._generate_weekly_summary()
        result.summary = summary

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"Weekly synthesis complete in {duration:.1f}s: {result}")

        return result

    async def _analyze_gate_failures(self) -> int:
        """Analyze gate failure patterns and generate learned rules."""
        logger.info("Analyzing gate failure patterns...")

        conn = get_connection()
        cur = conn.cursor()

        # Get products from last 30 days with gate failures
        cur.execute("""
            SELECT p.product_id, p.name, p.category, p.region,
                   p.overall_score, p.net_profit_pct, p.bsr_rank,
                   g.gate_number, g.status, g.blocked_reason
            FROM master_products p
            JOIN product_gate_progress g ON p.product_id = g.product_id
            WHERE g.status = 'FAIL'
              AND g.completed_at >= datetime('now', '-30 days')
            ORDER BY p.category, g.gate_number
        """)

        failures = [dict(r) for r in cur.fetchall()]
        conn.close()

        if not failures:
            logger.info("No gate failures in last 30 days")
            return 0

        # Group by category and gate
        from collections import defaultdict
        patterns = defaultdict(list)
        for f in failures:
            key = (f["category"], f["gate_number"])
            patterns[key].append(f)

        rules_added = 0

        # Generate rules for high-frequency failure patterns
        for (category, gate), items in patterns.items():
            if len(items) >= 3:  # At least 3 failures to form a pattern
                # Use LLM to analyze pattern and generate rule
                rule = await self._generate_rule_from_failures(category, gate, items)
                if rule:
                    try:
                        rule_id = self.rule_engine.evaluator.add_rule(rule)
                        if rule_id:
                            rules_added += 1
                            logger.info(f"Generated rule: {rule.rule_id} for {category} gate {gate}")
                    except Exception as e:
                        logger.warning(f"Failed to add rule: {e}")

        logger.info(f"Gate failure analysis: {rules_added} rules added from {len(patterns)} patterns")
        return rules_added

    def _build_rule_prompt(self, category: str, gate: int, failures: List[Dict]) -> str:
        """Build prompt for rule generation without f-string template issues."""
        failure_summary = "\n".join([
            f"- {f['name']}: {f.get('blocked_reason', 'No reason')}"
            for f in failures[:10]
        ])

        rule_id = f"learned_{category.lower().replace(' ', '_')}_gate{gate}_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        name = f"Prevent {category} Gate {gate} Failures"
        description = f"Auto-generated from {len(failures)} failures"

        prompt_parts = [
            f"Analyze these Gate {gate} failures for {category} products and generate a preventive rule.",
            "",
            "Failures:",
            failure_summary,
            "",
            "Create a rule that prevents similar failures in the future.",
            "The rule should be:",
            "1. Specific and actionable",
            "2. Based on observable product attributes",
            "3. Have a clear condition and action",
            "",
            "Return ONLY valid JSON:",
            "{",
            '    "rule_id": "' + rule_id + '",',
            '    "name": "' + name + '",',
            '    "description": "' + description + '",',
            '    "condition": "specific observable condition",',
            '    "action": "REJECT|WARN|PENALTY|BOOST|FLAG",',
            '    "severity": 1-5,',
            '    "params": {},',
            '    "tags": ["learned", "gate' + str(gate) + '", "' + category.lower() + '"]',
            "}",
        ]
        return "\n".join(prompt_parts)

    async def _generate_rule_from_failures(
        self, category: str, gate: int, failures: List[Dict]
    ) -> Optional[Rule]:
        """Use NIM 550B to generate a learned rule from failure patterns."""
        prompt = self._build_rule_prompt(category, gate, failures)

        try:
            if self.llm_router:
                response = await self.llm_router.chat(
                    messages=[
                        {"role": "system", "content": "You are a pattern recognition engine. Return only valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    agent_name="learning",
                    task_type="deep_reasoning",
                    json_mode=True,
                    max_tokens=500,
                )

                import json
                rule_data = json.loads(response.text)

                return Rule(
                    rule_id=rule_data["rule_id"],
                    name=rule_data["name"],
                    description=rule_data["description"],
                    condition=rule_data["condition"],
                    action=rule_data["action"],
                    severity=rule_data["severity"],
                    params=rule_data.get("params", {}),
                    tags=rule_data.get("tags", []),
                )
        except Exception as e:
            logger.warning(f"Rule generation failed: {e}")

        return None

    async def _analyze_gate_failures(self) -> int:
        """Analyze gate failure patterns and generate learned rules."""
        logger.info("Analyzing gate failure patterns...")

        conn = get_connection()
        cur = conn.cursor()

        # Get products from last 30 days with gate failures
        cur.execute("""
            SELECT p.product_id, p.name, p.category, p.region,
                   p.overall_score, p.net_profit_pct, p.bsr_rank,
                   g.gate_number, g.status, g.blocked_reason
            FROM master_products p
            JOIN product_gate_progress g ON p.product_id = g.product_id
            WHERE g.status = 'FAIL'
              AND g.completed_at >= datetime('now', '-30 days')
            ORDER BY p.category, g.gate_number
        """)

        failures = [dict(r) for r in cur.fetchall()]
        conn.close()

        if not failures:
            logger.info("No gate failures in last 30 days")
            return 0

        # Group by category and gate
        from collections import defaultdict
        patterns = defaultdict(list)
        for f in failures:
            key = (f["category"], f["gate_number"])
            patterns[key].append(f)

        rules_added = 0

        # Generate rules for high-frequency failure patterns
        for (category, gate), items in patterns.items():
            if len(items) >= 3:  # At least 3 failures to form a pattern
                rule = await self._generate_rule_from_failures(category, gate, items)
                if rule:
                    try:
                        rule_id = self.rule_engine.evaluator.add_rule(rule)
                        if rule_id:
                            rules_added += 1
                            logger.info(f"Generated rule: {rule.rule_id} for {category} gate {gate}")
                    except Exception as e:
                        logger.warning(f"Failed to add rule: {e}")

        logger.info(f"Gate failure analysis: {rules_added} rules added from {len(patterns)} patterns")
        return rules_added

    async def _evaluate_niche_performance(self) -> int:
        """Evaluate niche scan performance and update priority scores."""
        from core.database import get_dynamic_niches

        logger.info("Evaluating niche performance...")

        niches = get_dynamic_niches(active_only=True, limit=500)
        updated = 0

        conn = get_connection()
        cur = conn.cursor()

        for niche in niches:
            niche_id = niche.get("niche_id")
            if not niche_id:
                continue

            # Calculate performance metrics
            scans = niche.get("times_scanned", 0)
            found = niche.get("products_found", 0)
            priority = niche.get("priority_score", 50)

            if scans == 0:
                continue

            yield_rate = found / scans

            # Update priority based on yield
            if yield_rate > 0.5:
                new_priority = min(100, priority + 10)
            elif yield_rate > 0.2:
                new_priority = priority
            elif yield_rate > 0:
                new_priority = max(10, priority - 10)
            else:
                new_priority = max(5, priority - 20)

            # Update if changed significantly
            if abs(new_priority - priority) >= 5:
                try:
                    cur.execute("""
                        UPDATE dynamic_niches
                        SET priority_score = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE niche_id = ?
                    """, (new_priority, niche_id))
                    conn.commit()
                    updated += 1
                    logger.debug(f"Updated niche {niche['category']} priority: {priority} -> {new_priority}")
                except Exception as e:
                    logger.warning(f"Failed to update niche {niche_id}: {e}")

        conn.close()
        logger.info(f"Niche performance evaluation: {updated} niches updated")
        return updated

    async def _evaluate_keyword_yield(self) -> int:
        """Evaluate seed keyword performance and update weights."""
        from core.database import get_seed_keywords

        logger.info("Evaluating keyword yield...")

        keywords = get_seed_keywords(active_only=True, limit=200)
        updated = 0

        conn = get_connection()
        cur = conn.cursor()

        for kw in keywords:
            seed_id = kw.get("seed_id")
            if not seed_id:
                continue

            times_used = kw.get("times_used", 0)
            velocity = kw.get("velocity_score", 50)

            if times_used == 0:
                continue

            # Simple heuristic: if used many times but low velocity, reduce
            # if used few times but high velocity, increase
            new_velocity = velocity
            if times_used > 10 and velocity < 40:
                new_velocity = max(10, velocity - 10)
            elif times_used < 3 and velocity > 70:
                new_velocity = min(100, velocity + 10)

            if new_velocity != velocity:
                try:
                    cur.execute("""
                        UPDATE dynamic_seed_keywords
                        SET velocity_score = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE seed_id = ?
                    """, (new_velocity, seed_id))
                    conn.commit()
                    updated += 1
                except Exception as e:
                    logger.warning(f"Failed to update keyword {seed_id}: {e}")

        conn.close()
        logger.info(f"Keyword yield evaluation: {updated} keywords updated")
        return updated

    async def _evaluate_source_yield(self) -> int:
        """Evaluate discovered source yield and update priorities."""
        from core.database import get_discovered_sources

        logger.info("Evaluating source yield...")

        sources = get_discovered_sources(active_only=True, limit=200)
        evaluated = 0

        conn = get_connection()
        cur = conn.cursor()

        for src in sources:
            source_id = src.get("source_id")
            if not source_id:
                continue

            used = src.get("times_used", 0)
            yielded = src.get("times_yielded_results", 0)
            reliability = src.get("reliability_score", 70)

            if used == 0:
                continue

            yield_rate = yielded / used

            # Update reliability based on yield
            new_reliability = reliability
            if yield_rate > 0.5:
                new_reliability = min(100, reliability + 10)
            elif yield_rate > 0.2:
                new_reliability = reliability
            elif yield_rate > 0:
                new_reliability = max(30, reliability - 10)
            else:
                new_reliability = max(10, reliability - 20)

            if new_reliability != reliability:
                try:
                    cur.execute("""
                        UPDATE discovered_sources
                        SET reliability_score = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE source_id = ?
                    """, (new_reliability, source_id))
                    conn.commit()
                    evaluated += 1
                except Exception as e:
                    logger.warning(f"Failed to update source {source_id}: {e}")

        conn.close()
        logger.info(f"Source yield evaluation: {evaluated} sources updated")
        return evaluated

    async def _generate_weekly_summary(self) -> str:
        """Generate human-readable weekly summary using NIM 550B."""
        # Collect key metrics
        conn = get_connection()
        cur = conn.cursor()

        # Products discovered this week
        cur.execute("""
            SELECT COUNT(*) FROM master_products
            WHERE created_at >= datetime('now', '-7 days')
        """)
        new_products = cur.fetchone()[0]

        # Gates passed
        cur.execute("""
            SELECT COUNT(*) FROM product_gate_progress
            WHERE status = 'PASS' AND completed_at >= datetime('now', '-7 days')
        """)
        gates_passed = cur.fetchone()[0]

        # Rules generated
        cur.execute("SELECT COUNT(*) FROM learned_rules WHERE created_at >= datetime('now', '-7 days')")
        rules_added = cur.fetchone()[0]

        # Niches scanned
        cur.execute("SELECT COUNT(*) FROM dynamic_niches WHERE last_scanned_at >= datetime('now', '-7 days')")
        niches_scanned = cur.fetchone()[0]

        conn.close()

        prompt_parts = [
            "Generate a concise weekly summary for the APRS V7 autonomous product research system.",
            "",
            "Weekly Metrics:",
            f"- New products discovered: {new_products}",
            f"- Gates passed: {gates_passed}",
            f"- Learned rules added: {rules_added}",
            f"- Niches scanned: {niches_scanned}",
            "",
            "Generate a concise executive summary (3-4 sentences) highlighting:",
            "1. Key achievements",
            "2. Notable patterns or concerns",
            "3. Recommended focus for next week",
            "",
            "Write in professional business tone."
        ]
        prompt = "\n".join(prompt_parts)

        try:
            if self.llm_router:
                response = await self.llm_router.chat(
                    messages=[
                        {"role": "system", "content": "You are an executive summary writer for an e-commerce research platform."},
                        {"role": "user", "content": prompt}
                    ],
                    agent_name="learning",
                    task_type="weekly_synthesis",
                    max_tokens=300,
                )
                return response.text
        except Exception as e:
            logger.warning(f"Weekly summary generation failed: {e}")

        # Fallback summary
        return f"Weekly Summary: {new_products} new products discovered, {gates_passed} gates passed, {rules_added} learned rules added. {niches_scanned} niches scanned. System operating normally."

    def get_synthesis_status(self) -> Dict[str, Any]:
        """Get status of learning engine components."""
        return {
            "rule_engine_rules": len(self.rule_engine.evaluator.rules),
            "llm_router_health": self.llm_router.get_health_status() if self.llm_router else "not_initialized",
            "last_synthesis": getattr(self, '_last_synthesis_time', None),
        }


async def run_weekly_synthesis() -> SynthesisResult:
    """Run a complete weekly synthesis cycle."""
    engine = LearningEngine()
    return await engine.weekly_synthesis()


if __name__ == "__main__":
    async def test():
        engine = LearningEngine()
        result = await engine.weekly_synthesis()
        print(f"Synthesis complete: {result}")

    asyncio.run(test())