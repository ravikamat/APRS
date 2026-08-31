"""
core/team_meeting.py — AI War Room: Single-Speaker Targeted Chat Router.

Routes user messages to the correct specialist agent persona,
calls NIM LLM with that persona's system prompt, and returns
a structured response list. All turns are logged to SQLite.

Usage:
    from core.team_meeting import AITeamMeetingRoom, MEMBERS
    room = AITeamMeetingRoom()
    replies = room.chat("Sales: how is demand?", target_speaker="auto")
"""
import re
import uuid
from typing import Dict, Any, List, Optional

# ── Team member roster ─────────────────────────────────────────────────────
MEMBERS: Dict[str, Dict[str, Any]] = {
    "sales": {
        "name":        "Maya — Sales Intelligence",
        "title":       "Head of Demand & Growth",
        "avatar":      "📈",
        "agent_id":    "sales",
        "system_prompt": (
            "You are Maya, the Head of Sales Intelligence for an e-commerce product research firm. "
            "You specialise in Amazon BSR velocity, TikTok/Meta viral ad performance, demand seasonality, "
            "and revenue projections. Answer concisely and cite numbers where possible. "
            "If asked about a product, assess BSR rank, estimated monthly units, and top ad hooks. "
            "Format your response in clear bullet points. Keep it under 250 words."
        ),
    },
    "quality": {
        "name":        "Rajan — Quality & Engineering",
        "title":       "Head of Product Quality & v2.0 Engineering",
        "avatar":      "🛡️",
        "agent_id":    "quality",
        "system_prompt": (
            "You are Rajan, the Head of Product Quality Engineering. "
            "You specialise in dissecting 3-star Amazon reviews and Reddit complaints to find the top product defects. "
            "For every defect, you specify an exact engineering fix (material, dimension, process). "
            "Always structure your response as: "
            "(1) Top 3 Defects Found, (2) Root Cause Analysis, (3) v2.0 Engineering Spec. "
            "Be precise — name materials, tolerances, and testing standards. Under 300 words."
        ),
    },
    "supplier": {
        "name":        "Priya — Sourcing & Supply Chain",
        "title":       "Head of Global Sourcing",
        "avatar":      "🏭",
        "agent_id":    "supplier",
        "system_prompt": (
            "You are Priya, the Head of Global Sourcing. "
            "You know Indian manufacturing clusters (Surat GIDC, Moradabad, Rajkot, Tirupur, Okhla), "
            "Chinese sourcing hubs (Ningbo, Shenzhen, Yiwu, Dongguan), and Middle East free-trade zones. "
            "When asked about a product, recommend the best cluster, explain why, "
            "give realistic FOB price range, MOQ, and sample lead time. "
            "Always advise on certifications required (BIS, CE, ISO9001, etc.). Under 250 words."
        ),
    },
    "finance": {
        "name":        "Arjun — Unit Economics",
        "title":       "Head of Financial Modelling",
        "avatar":      "💰",
        "agent_id":    "finance",
        "system_prompt": (
            "You are Arjun, the Head of Unit Economics and P&L Modelling. "
            "You specialise in 12-factor landed COGS, GST input credit, Amazon Easy Ship fee tiers, "
            "TACoS blended CAC, RTO reserve, and worst-case stress margin calculations. "
            "When given a product, compute: Landed COGS, Gross Margin %, Net Profit %, "
            "and Worst-Case Stress Margin % (35% CAC surge, 15% MSRP compression). "
            "Show workings. Flag if product fails the 15% minimum net margin threshold. Under 300 words."
        ),
    },
    "tech": {
        "name":        "Antigravity — Tech Systems",
        "title":       "Chief Technology Architect",
        "avatar":      "💻",
        "agent_id":    "tech",
        "system_prompt": (
            "You are the Antigravity AI system, the Chief Technology Architect for APRS V5. "
            "You have full knowledge of the APRS V5 codebase: SQLite SSOT, 6-gate pipeline orchestrator, "
            "NIM cluster, Amazon curl_cffi scraper, Keepa API client, background daemon, "
            "Reddit/Google Trends intelligence, and Streamlit dashboard. "
            "Answer technical questions about the system architecture, code quality, scraper status, "
            "database schema, and deployment. Be precise and reference actual module names. Under 300 words."
        ),
    },
    "secretary": {
        "name":        "Kavya — Chief Scribe",
        "title":       "Chief Scribe & Action Item Tracker",
        "avatar":      "📝",
        "agent_id":    "secretary",
        "system_prompt": (
            "You are Kavya, the Chief Scribe and Action Item Tracker. "
            "Your role is to summarise meeting discussions, extract action items with owners, "
            "format minutes into clear sections, and prepare the Word document content. "
            "When asked to summarise, provide: (1) Key Decisions, (2) Action Items with owner and deadline, "
            "(3) Open Questions. Write in formal meeting minutes style. Under 400 words."
        ),
    },
}

# ── Speaker keyword detection map ─────────────────────────────────────────
_SPEAKER_KEYWORDS: Dict[str, List[str]] = {
    "sales":     ["sales", "maya", "demand", "bsr", "revenue", "ads", "tiktok", "meta", "velocity", "units"],
    "quality":   ["quality", "rajan", "defect", "3-star", "3star", "engineering", "v2", "fix", "material", "review"],
    "supplier":  ["supplier", "priya", "factory", "fob", "moq", "ningbo", "surat", "moradabad", "sourcing", "cluster", "oem"],
    "finance":   ["finance", "arjun", "margin", "profit", "cogs", "stress", "economics", "cac", "gst", "unit economics"],
    "tech":      ["tech", "antigravity", "code", "codebase", "scraper", "database", "api", "bug", "pipeline", "daemon"],
    "secretary": ["secretary", "kavya", "minutes", "summary", "action", "word doc", "scribe"],
}


class AITeamMeetingRoom:
    """
    Single-speaker AI team router.
    Detects target speaker from text or explicit selector,
    calls NIM with the appropriate system prompt,
    and logs the exchange to SQLite.
    """

    def __init__(self):
        from models.nim_cluster import SupremeNIMCluster
        self._cluster = SupremeNIMCluster()
        self._session_id = str(uuid.uuid4())[:8]

    def detect_target_speaker(self, query: str, manual_target: str = "auto") -> List[str]:
        """
        Returns list of agent_ids that should respond.
        'all' → all 6 members.
        'auto' → detect from query text.
        explicit → single member.
        """
        if manual_target == "all" or "@all" in query.lower():
            return list(MEMBERS.keys())

        if manual_target and manual_target != "auto" and manual_target in MEMBERS:
            return [manual_target]

        # Auto-detect from query text
        query_lower = query.lower()
        for agent_id, keywords in _SPEAKER_KEYWORDS.items():
            for kw in keywords:
                # Word boundary check to avoid partial matches
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, query_lower):
                    return [agent_id]

        # Default: route to finance if numbers mentioned, else sales
        if any(c.isdigit() for c in query) or "%" in query or "₹" in query or "$" in query:
            return ["finance"]
        return ["sales"]

    def _call_member(self, agent_id: str, user_query: str) -> Dict[str, Any]:
        """Call NIM with a specific team member's persona."""
        member = MEMBERS[agent_id]
        result = self._cluster.query(
            prompt=user_query,
            system_prompt=member["system_prompt"],
            task_type="adversarial_critic",  # moderate reasoning tier
            temperature=0.3,
            max_tokens=512,
            timeout=15.0,
        )
        message = result.get("content", "").strip()
        if not message or not result.get("success"):
            message = (
                f"[{member['name']}] NIM cluster unavailable right now. "
                f"Please check API key status in the banner above and retry."
            )
        return {
            "agent_id":    agent_id,
            "agent_name":  member["name"],
            "title":       member["title"],
            "avatar":      member["avatar"],
            "message":     message,
            "cached":      result.get("cached", False),
            "latency_sec": result.get("latency_sec", 0),
        }

    def chat(self, user_query: str, target_speaker: str = "auto") -> List[Dict[str, Any]]:
        """
        Route a user message to the appropriate speaker(s) and return responses.

        Args:
            user_query: The raw user input string.
            target_speaker: 'auto', 'all', or a specific agent_id.

        Returns:
            List of response dicts (one per speaker that responded).
        """
        from core.database import log_meeting_turn

        target_ids = self.detect_target_speaker(user_query, manual_target=target_speaker)
        responses = []

        for agent_id in target_ids:
            member = MEMBERS[agent_id]
            resp = self._call_member(agent_id, user_query)
            responses.append(resp)

            # Log to SQLite (non-fatal if it fails)
            try:
                log_meeting_turn(
                    session_id=self._session_id,
                    speaker_name=member["name"],
                    speaker_role=member["title"],
                    avatar=member["avatar"],
                    user_prompt=user_query,
                    response_text=resp["message"],
                )
            except Exception as log_err:
                import logging
                logging.getLogger("aprs.team_meeting").warning("Meeting log failed: %s", log_err)

        return responses
