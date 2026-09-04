"""
integrations/crm_client.py — Supplier CRM Client for APRS V7.

Wrapper for CRM system (local SQLite or external API).
Manages supplier contacts, interactions, and deal pipeline.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import sys
from pathlib import Path

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings

logger = logging.getLogger("aprs.crm_client")


@dataclass
class CRMResponse:
    """Response from CRM API."""
    success: bool
    data: Any = None
    error: Optional[str] = None


@dataclass
class SupplierContact:
    """Supplier contact information."""
    contact_id: Optional[int] = None
    supplier_id: int = 0
    name: str = ""
    role: str = ""  # owner, manager, sales, technical
    email: str = ""
    phone: str = ""
    whatsapp: str = ""
    is_primary: bool = False
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SupplierDeal:
    """Supplier deal/opportunity pipeline."""
    deal_id: Optional[int] = None
    supplier_id: int = 0
    product_id: str = ""
    stage: str = "LEAD"  # LEAD, QUALIFIED, PROPOSAL, NEGOTIATION, CLOSED_WON, CLOSED_LOST
    value_usd: float = 0.0
    currency: str = "USD"
    probability: int = 0  # 0-100
    expected_close_date: Optional[datetime] = None
    notes: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


class CRMClient:
    """
    Supplier CRM Client.
    
    Can work in two modes:
    1. Embedded SQLite (default) - no external dependency
    2. External CRM API (if CRM_URL configured) - e.g., HubSpot, Pipedrive, custom
    """
    
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._use_external = bool(settings.crm_url and settings.crm_url != "http://localhost:3000")
        self._local_db = None
    
    async def __aenter__(self):
        import aiohttp
        import aiosqlite
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"},
        )
        if not self._use_external:
            await self._init_local_db()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
        if hasattr(self, '_local_db') and self._local_db:
            await self._local_db.close()
    
    async def _init_local_db(self):
        """Initialize local SQLite CRM database."""
        import aiosqlite
        self._local_db = await aiosqlite.connect("data/crm.db")
        await self._local_db.execute("""
            CREATE TABLE IF NOT EXISTS crm_contacts (
                contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT,
                email TEXT,
                phone TEXT,
                whatsapp TEXT,
                is_primary INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id)
            )
        """)
        await self._local_db.execute("""
            CREATE TABLE IF NOT EXISTS crm_deals (
                deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'LEAD',
                value_usd REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                probability INTEGER DEFAULT 0,
                expected_close_date TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id)
            )
        """)
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_contacts_supplier ON crm_contacts(supplier_id)")
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_deals_supplier ON crm_deals(supplier_id)")
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_deals_stage ON crm_deals(stage)")
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"},
        )
        if not self._use_external:
            await self._init_local_db()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
        if hasattr(self, '_local_db') and self._local_db:
            await self._local_db.close()
    
    @property
    def _use_external(self) -> bool:
        return self._use_external
    
    async def _init_local_db(self):
        """Initialize local SQLite CRM database."""
        import aiosqlite
        self._local_db = await aiosqlite.connect("data/crm.db")
        await self._local_db.execute("""
            CREATE TABLE IF NOT EXISTS crm_contacts (
                contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT,
                email TEXT,
                phone TEXT,
                whatsapp TEXT,
                is_primary INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id)
            )
        """)
        await self._local_db.execute("""
            CREATE TABLE IF NOT EXISTS crm_deals (
                deal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'LEAD',
                value_usd REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                probability INTEGER DEFAULT 0,
                expected_close_date TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id)
            )
        """)
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_contacts_supplier ON crm_contacts(supplier_id)")
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_deals_supplier ON crm_deals(supplier_id)")
        await self._local_db.execute("CREATE INDEX IF NOT EXISTS idx_crm_deals_stage ON crm_deals(stage)")
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"},
        )
        if not self._use_external:
            await self._init_local_db()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
        if hasattr(self, '_local_db') and self._local_db:
            await self._local_db.close()
    
    @property
    def _use_external(self) -> bool:
        return self._use_external
    
    # ── Contact Management ──────────────────────────────────────────────────
    
    async def add_contact(self, contact: 'SupplierContact') -> Optional[int]:
        """Add a new contact for a supplier."""
        if self._use_external:
            return await self._external_add_contact(contact)
        else:
            return await self._local_add_contact(contact)
    
    async def _local_add_contact(self, contact) -> Optional[int]:
        try:
            async with self._local_db.execute("""
                INSERT INTO crm_contacts (supplier_id, name, role, email, phone, whatsapp, is_primary, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contact.supplier_id,
                contact.name,
                contact.role,
                contact.email,
                contact.phone,
                contact.whatsapp,
                1 if contact.is_primary else 0,
                contact.notes,
            )) as cursor:
                await self._local_db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.warning(f"Failed to add contact: {e}")
            return None
    
    async def get_contacts(self, supplier_id: int) -> List[Dict]:
        """Get all contacts for a supplier."""
        if self._use_external:
            return await self._external_get_contacts(supplier_id)
        else:
            async with self._local_db.execute(
                "SELECT * FROM crm_contacts WHERE supplier_id = ? ORDER BY is_primary DESC",
                (supplier_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    
    async def update_contact(self, contact_id: int, **kwargs) -> bool:
        """Update contact information."""
        if self._use_external:
            return await self._external_update_contact(contact_id, kwargs)
        else:
            # Build dynamic update query
            set_clauses = []
            params = []
            for key, value in kwargs.items():
                if key != 'contact_id':
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            if not set_clauses:
                return False
            params.append(contact_id)
            try:
                query = f"UPDATE crm_contacts SET {', '.join(set_clauses)} WHERE contact_id = ?"
                await self._local_db.execute(query, params)
                await self._local_db.commit()
                return True
            except Exception as e:
                logger.warning(f"Failed to update contact: {e}")
                return False
    
    async def get_contacts(self, supplier_id: int) -> List[Dict]:
        """Get all contacts for a supplier."""
        if self._use_external:
            return await self._external_get_contacts(supplier_id)
        else:
            async with self._local_db.execute(
                "SELECT * FROM crm_contacts WHERE supplier_id = ? ORDER BY is_primary DESC",
                (supplier_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    
    async def update_contact(self, contact_id: int, **kwargs) -> bool:
        """Update contact information."""
        if self._use_external:
            return await self._external_update_contact(contact_id, kwargs)
        else:
            # Build dynamic update query
            set_clauses = []
            params = []
            for key, value in kwargs.items():
                if key != 'contact_id':
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            if not set_clauses:
                return False
            params.append(contact_id)
            try:
                query = f"UPDATE crm_contacts SET {', '.join(set_clauses)} WHERE contact_id = ?"
                await self._local_db.execute(query, params)
                await self._local_db.commit()
                return True
            except Exception as e:
                logger.warning(f"Failed to update contact: {e}")
                return False
    
    async def get_contacts(self, supplier_id: int) -> List[Dict]:
        """Get all contacts for a supplier."""
        if self._use_external:
            return await self._external_get_contacts(supplier_id)
        else:
            async with self._local_db.execute(
                "SELECT * FROM crm_contacts WHERE supplier_id = ? ORDER BY is_primary DESC",
                (supplier_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    
    async def update_contact(self, contact_id: int, **kwargs) -> bool:
        """Update contact information."""
        if self._use_external:
            return await self._external_update_contact(contact_id, kwargs)
        else:
            # Build dynamic update query
            set_clauses = []
            params = []
            for key, value in kwargs.items():
                if key != 'contact_id':
                    set_clauses.append(f"{key} = ?")
                    params.append(value)
            if not set_clauses:
                return False
            params.append(contact_id)
            try:
                query = f"UPDATE crm_contacts SET {', '.join(set_clauses)} WHERE contact_id = ?"
                await self._local_db.execute(query, params)
                await self._local_db.commit()
                return True
            except Exception as e:
                logger.warning(f"Failed to update contact: {e}")
                return False
    
    async def get_primary_contact(self, supplier_id: int) -> Optional[Dict]:
        """Get primary contact for a supplier."""
        async with self._local_db.execute(
            "SELECT * FROM crm_contacts WHERE supplier_id = ? AND is_primary = 1 LIMIT 1",
            (supplier_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    # ── Deal Pipeline ────────────────────────────────────────────────────────
    
    async def create_deal(self, deal) -> Optional[int]:
        """Create a new deal/opportunity."""
        if self._use_external:
            return await self._external_create_deal(deal)
        else:
            try:
                async with self._local_db.execute("""
                    INSERT INTO crm_deals (
                        supplier_id, product_id, stage, value_usd, currency,
                        probability, expected_close_date, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    deal.supplier_id,
                    deal.product_id,
                    deal.stage,
                    deal.value_usd,
                    deal.currency,
                    deal.probability,
                    deal.expected_close_date.isoformat() if deal.expected_close_date else None,
                    deal.notes,
                )) as cursor:
                    await self._local_db.commit()
                    return cursor.lastrowid
            except Exception as e:
                logger.warning(f"Failed to create deal: {e}")
                return None
    
    async def get_deals(self, supplier_id: int = None, stage: str = None) -> List[Dict]:
        """Get deals, optionally filtered by supplier or stage."""
        if self._use_external:
            return await self._external_get_deals(supplier_id, stage)
        else:
            query = "SELECT * FROM crm_deals WHERE 1=1"
            params = []
            if supplier_id:
                query += " AND supplier_id = ?"
                params.append(supplier_id)
            if stage:
                query += " AND stage = ?"
                params.append(stage)
            query += " ORDER BY created_at DESC"
            
            async with self._local_db.execute(query, tuple([p for p in params if p is not None] + [None])) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]
    
    async def update_deal_stage(self, deal_id: int, stage: str) -> bool:
        """Update deal stage."""
        if self._use_external:
            return await self._external_update_deal(deal_id, stage)
        else:
            try:
                await self._local_db.execute(
                    "UPDATE crm_deals SET stage = ?, updated_at = CURRENT_TIMESTAMP WHERE deal_id = ?",
                    (stage, deal_id)
                )
                await self._local_db.commit()
                return True
            except Exception as e:
                logger.warning(f"Failed to update deal stage: {e}")
                return False
    
    async def get_deal(self, deal_id: int) -> Optional[Dict]:
        """Get deal by ID."""
        async with self._local_db.execute(
            "SELECT * FROM crm_deals WHERE deal_id = ?",
            (deal_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get pipeline summary by stage."""
        async with self._local_db.execute("""
            SELECT stage, COUNT(*) as count, SUM(value_usd) as total_value
            FROM crm_deals
            GROUP BY stage
        """) as cursor:
            rows = await cursor.fetchall()
            return {row['stage']: {'count': row['count'], 'total_value': row['total_value'] or 0} for row in rows}
    
    # ── Activity Logging ────────────────────────────────────────────────────
    
    async def log_activity(
        self,
        supplier_id: int,
        activity_type: str,  # call, email, meeting, whatsapp, note
        summary: str,
        user: str = "system",
        related_deal_id: int = None,
    ) -> bool:
        """Log an activity/interaction with supplier."""
        # Would need an activities table - simplified for now
        logger.info(f"Activity for supplier {supplier_id}: {activity_type} - {summary}")
        return True
    
    # ── Supplier Enrichment ─────────────────────────────────────────────────
    
    async def enrich_supplier_profile(self, supplier_id: int) -> Dict[str, Any]:
        """Enrich supplier profile with external data."""
        # Placeholder for enrichment logic
        # Could integrate with: Clearbit, Hunter, LinkedIn, etc.
        return {"enriched": True, "data_sources": []}
    
    # ── External CRM Integration (Stub) ──────────────────────────────────────
    
    async def _external_add_contact(self, contact) -> Optional[int]:
        """Add contact via external CRM API."""
        if not self._session:
            import aiohttp
            self._session = aiohttp.ClientSession()
        
        try:
            async with self._session.post(
                f"{self.base_url}/contacts",
                json=contact.__dict__,
                headers={"Authorization": f"Bearer {settings.crm_apikey}"}
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return data.get("id")
        except Exception as e:
            logger.error(f"External CRM add contact failed: {e}")
        return None
    
    async def _external_get_contacts(self, supplier_id: int) -> List[Dict]:
        """Get contacts from external CRM."""
        return []
    
    async def _external_create_deal(self, deal) -> Optional[int]:
        """Create deal in external CRM."""
        return None
    
    async def _external_update_deal(self, deal_id: int, stage: str) -> bool:
        """Update deal in external CRM."""
        return False
    
    async def _external_get_contacts(self, supplier_id: int) -> List[Dict]:
        """Get contacts from external CRM."""
        return []
    
    async def _external_update_contact(self, contact_id: int, kwargs: Dict) -> bool:
        """Update contact in external CRM."""
        return False
    
    def get_pipeline_summary(self) -> Dict[str, Any]:
        """Get pipeline summary by stage."""
        # This would query the local DB
        return {
            "LEAD": {"count": 0, "value": 0},
            "QUALIFIED": {"count": 0, "value": 0},
            "PROPOSAL": {"count": 0, "value": 0},
            "NEGOTIATION": {"count": 0, "value": 0},
            "CLOSED_WON": {"count": 0, "value": 0},
            "CLOSED_LOST": {"count": 0, "value": 0},
        }


async def get_crm_client() -> CRMClient:
    """Get CRM client instance."""
    return CRMClient()


if __name__ == "__main__":
    async def test():
        async with CRMClient() as crm:
            print("CRM Client initialized")
            
            # Test contact creation
            from core.supplier_models import SupplierContact
            contact = SupplierContact(
                supplier_id=1,
                name="Rajesh Kumar",
                role="Sales Manager",
                email="rajesh@supplier.com",
                phone="+91-9876543210",
                is_primary=True,
            )
            contact_id = await crm.add_contact(contact)
            print(f"Created contact: {contact_id}")
            
            contacts = await crm.get_contacts(1)
            print(f"Contacts: {len(contacts)}")
    
    asyncio.run(test())