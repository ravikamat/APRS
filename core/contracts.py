"""
core/contracts.py — Agent Output Contracts & Health Verification.

Every agent MUST write through this module. Enforces:
- Output rows written to expected tables
- Swarm audit log entry created
- Expected row count validation
- Automatic retry on failure
- Escalation to pending_human_decisions on persistent failure
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
from functools import wraps

from core.database import (
    get_connection, log_swarm_audit, get_pending_human_decisions,
    add_pending_human_decision
)

logger = logging.getLogger("aprs.contracts")


@dataclass
class AgentContract:
    """Contract defining expected outputs for an agent."""
    agent_name: str
    required_output_tables: List[str]
    min_rows_per_cycle: int = 1
    max_latency_seconds: int = 300
    retry_count: int = 2
    escalation_target: str = "pending_human_decisions"
    is_active: bool = True
    
    def validate_output(self, actual_rows: Dict[str, int]) -> tuple[bool, List[str]]:
        """Validate agent output meets contract."""
        print(f'DEBUG validate_output: required_output_tables={self.required_output_tables}, type={type(self.required_output_tables)}')
        errors = []
        for table in self.required_output_tables:
            count = actual_rows.get(table, 0)
            if count < self.min_rows_per_cycle:
                errors.append(f"Table {table}: expected >= {self.min_rows_per_cycle} rows, got {count}")
        return len(errors) == 0, errors


class ContractRegistry:
    """Registry of all agent contracts, loaded from DB."""
    
    def __init__(self):
        self._contracts: Dict[str, AgentContract] = {}
        self._loaded = False
    
    def load_from_db(self):
        """Load contracts from agent_contracts table."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM agent_contracts WHERE is_active = 1")
        rows = cur.fetchall()
        conn.close()
        
        for row in rows:
            contract = AgentContract(
                agent_name=row["agent_name"],
                required_output_tables=json.loads(row["required_output_tables"]),
                min_rows_per_cycle=row["min_rows_per_cycle"],
                max_latency_seconds=row["max_latency_seconds"],
                retry_count=row["retry_count"],
                escalation_target=row["escalation_target"],
                is_active=bool(row["is_active"]),
            )
            self._contracts[row["agent_name"]] = contract
        self._loaded = True
        logger.info(f"Loaded {len(self._contracts)} agent contracts from DB")
    
    def get(self, agent_name: str) -> Optional[AgentContract]:
        if not self._loaded:
            self.load_from_db()
        return self._contracts.get(agent_name)
    
    def all(self) -> Dict[str, AgentContract]:
        if not self._loaded:
            self.load_from_db()
        return self._contracts


REGISTRY = ContractRegistry()


def count_rows_written(agent_name: str, cycle_id: str = None) -> Dict[str, int]:
    """Count rows written by agent in current cycle."""
    conn = get_connection()
    cur = conn.cursor()
    
    contract = REGISTRY.get(agent_name)
    if not contract:
        conn.close()
        return {}
    
    # Tables that have cycle_id column
    tables_with_cycle_id = {
        'discovered_sources', 'dynamic_niches', 
        'dynamic_seed_keywords', 'scraped_listings', 'scraper_validations',
        'master_products', 'economics_assessments', 'defect_clusters',
        'gate_logs', 'supplier_profiles', 'outreach_drafts',
        'launchpad_items', 'problem_opportunities', 'winner_scores',
        'pipeline_fsm', 'research_directives', 'agent_health',
        'agent_contracts', 'arbiter_decision_log', 'review_snapshots',
        'supplier_conversations', 'launchpad_outcomes', 'negative_findings',
        'daily_snapshots', 'url_validation_log', 'website_capture_stats',
        'pending_human_decisions', 'swarm_audit_log', 'ai_supervisor_logs',
        'ai_task_improvements', 'product_gate_progress', 'gate_logs',
        'product_suppliers', 'multi_platform_listings'
    }
    
    counts = {}
    for table in contract.required_output_tables:
        try:
            if cycle_id and table in tables_with_cycle_id:
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE cycle_id = ?", (cycle_id,))
            else:
                # Use recent timestamp as proxy
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE created_at > datetime('now', '-5 minutes')")
            counts[table] = cur.fetchone()[0]
        except Exception as e:
            logger.warning(f"Failed to count rows in {table} for {agent_name}: {e}")
            counts[table] = 0
    
    conn.close()
    return counts


def verify_agent_output(agent_name: str, cycle_id: str = None) -> tuple[bool, List[str]]:
    """Verify agent output meets its contract."""
    contract = REGISTRY.get(agent_name)
    if not contract:
        return True, []
    
    actual_rows = count_rows_written(agent_name, cycle_id)
    return contract.validate_output(actual_rows)


def record_agent_health(
    agent_name: str,
    cycle_id: str,
    expected_table: str,
    expected_rows: int,
    actual_rows: int,
    status: str,
    error_message: str = None,
    check_details: dict = None
) -> int:
    """Record agent health check result."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO agent_health (
            agent_name, cycle_id, expected_output_table, expected_row_count,
            actual_row_count, status, error_message, check_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        agent_name, cycle_id, expected_table, expected_rows,
        actual_rows, status, error_message,
        json.dumps(check_details) if check_details else None
    ))
    hid = cur.lastrowid
    conn.commit()
    conn.close()
    return hid


def escalate_to_human(
    agent_name: str,
    cycle_id: str,
    error_message: str,
    context: dict
) -> int:
    """Escalate persistent agent failure to pending_human_decisions."""
    # Use None instead of empty string for product_id to satisfy FK constraint
    product_id = context.get("product_id")
    if product_id == "":
        product_id = None
    return add_pending_human_decision(
        agent_name=agent_name,
        product_id=product_id,
        task_type=f"agent_failure:{agent_name}",
        context_json=json.dumps({
            "cycle_id": cycle_id,
            "error": error_message,
            "context": context,
            "escalation_reason": f"Agent {agent_name} failed contract validation after retries"
        }),
        options_json=json.dumps([
            {"label": "Retry agent", "action": "retry_agent", "params": {"agent_name": agent_name}},
            {"label": "Skip this cycle", "action": "skip_cycle", "params": {}},
            {"label": "Disable agent", "action": "disable_agent", "params": {"agent_name": agent_name}}
        ]),
        priority="HIGH"
    )


def with_contract(agent_name: str, cycle_id: str = None):
    """Decorator to enforce agent contract on async function."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            contract = REGISTRY.get(agent_name)
            if not contract:
                logger.warning(f"No contract for {agent_name}, running without validation")
                return await func(agent_name, *args, **kwargs)
            
            # Generate cycle_id if not provided
            import uuid
            cid = cycle_id or f"{agent_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            
            last_error = None
            for attempt in range(contract.retry_count + 1):
                try:
                    # Pass agent_name as first argument
                    result = await func(agent_name, *args, **kwargs)
                    
                    # Verify output
                    valid, errors = verify_agent_output(agent_name, cid)
                    
                    if valid:
                        logger.info(f"Contract verified for {agent_name} (cycle {cid})")
                        # Record success health checks
                        for table in contract.required_output_tables:
                            count = count_rows_written(agent_name, cid).get(table, 0)
                            record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, count, "OK")
                        return result
                    else:
                        last_error = "; ".join(errors)
                        logger.warning(f"Contract validation failed for {agent_name} (attempt {attempt+1}): {last_error}")
                        
                        # Record failure
                        for table in contract.required_output_tables:
                            count = count_rows_written(agent_name, cid).get(table, 0)
                            record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, count, "FAIL", last_error)
                        
                        if attempt < contract.retry_count:
                            logger.info(f"Retrying {agent_name} (attempt {attempt+2}/{contract.retry_count+1})")
                            continue
                        
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"Agent {agent_name} execution error (attempt {attempt+1}): {e}")
                    if attempt < contract.retry_count:
                        continue
            
            # All retries failed - escalate
            logger.error(f"Agent {agent_name} failed after {contract.retry_count+1} attempts: {last_error}")
            escalate_to_human(agent_name, cid, last_error, {"function": func.__name__, "args": str(args)[:200]})
            
            # Record final failure
            for table in contract.required_output_tables:
                record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, 0, "ESCALATED", last_error)
            
            raise RuntimeError(f"Agent {agent_name} failed contract validation: {last_error}")
        
        return wrapper
    return decorator


async def run_with_contract(agent_name: str, func: Callable, cycle_id: str = None, *args, **kwargs):
    """Run a function with contract enforcement (for non-decorated usage)."""
    import uuid
    cid = cycle_id or f"{agent_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    contract = REGISTRY.get(agent_name)
    if not contract:
        return await func(agent_name, *args, **kwargs)
    
    last_error = None
    for attempt in range(contract.retry_count + 1):
        try:
            # Pass agent_name as first argument to the function
            result = await func(agent_name, *args, **kwargs)
            
            valid, errors = verify_agent_output(agent_name, cid)
            
            if valid:
                for table in contract.required_output_tables:
                    count = count_rows_written(agent_name, cid).get(table, 0)
                    record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, count, "OK")
                return result
            else:
                last_error = "; ".join(errors)
                for table in contract.required_output_tables:
                    count = count_rows_written(agent_name, cid).get(table, 0)
                    record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, count, "FAIL", last_error)
                
                if attempt < contract.retry_count:
                    continue
                    
        except Exception as e:
            last_error = str(e)
            if attempt < contract.retry_count:
                continue
    
    escalate_to_human(agent_name, cid, last_error, {"function": func.__name__})
    for table in contract.required_output_tables:
        record_agent_health(agent_name, cid, table, contract.min_rows_per_cycle, 0, "ESCALATED", last_error)
    raise RuntimeError(f"Agent {agent_name} failed contract validation: {last_error}")


class HealthMonitor:
    """Monitors agent health and reports anomalies."""
    
    def __init__(self):
        self.registry = REGISTRY
    
    def check_all_agents(self, cycle_id: str) -> Dict[str, Any]:
        """Check health of all agents for a cycle."""
        results = {}
        for agent_name, contract in self.registry.all().items():
            if not contract.is_active:
                continue
            
            actual_rows = count_rows_written(agent_name, cycle_id)
            valid, errors = contract.validate_output(actual_rows)
            
            results[agent_name] = {
                "healthy": valid,
                "tables": actual_rows,
                "errors": errors,
            }
            
            # Record health check
            for table, count in actual_rows.items():
                record_agent_health(
                    agent_name, cycle_id, table, 
                    contract.min_rows_per_cycle, count,
                    "OK" if valid else "WARNING", 
                    "; ".join(errors) if errors else None
                )
        
        return results
    
    def get_stuck_agents(self, hours: int = 2) -> List[Dict[str, Any]]:
        """Find agents that haven't written output recently."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f'''
            SELECT agent_name, MAX(checked_at) as last_check, status
            FROM agent_health
            WHERE checked_at < datetime('now', '-{hours} hours')
            GROUP BY agent_name
            HAVING status != 'OK'
        ''')
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


if __name__ == "__main__":
    # Test contract loading
    REGISTRY.load_from_db()
    for name, contract in REGISTRY.all().items():
        print(f"{name}: {contract.required_output_tables} (min {contract.min_rows_per_cycle})")