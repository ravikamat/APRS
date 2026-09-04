"""
integrations/evolution_go.py — Evolution-Go WhatsApp API Client for APRS V7.

Wrapper for Evolution-Go WhatsApp API (localhost:8080).
Enables sending WhatsApp messages, receiving replies, and webhook handling.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
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

logger = logging.getLogger("aprs.evolution_go")


@dataclass
class EvolutionGoResponse:
    """Response from Evolution-Go API."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    message_id: Optional[str] = None


class EvolutionGoClient:
    """
    Client for Evolution-Go WhatsApp API (localhost:8080).
    
    Features:
    - Send text, image, document, video messages
    - Receive incoming messages via webhook
    - Manage contacts and groups
    - Message status tracking (sent, delivered, read)
    - Media upload/download
    - Group management
    """
    
    def __init__(self, base_url: str = "http://localhost:8080", apikey: str = ""):
        self.base_url = base_url.rstrip("/")
        self.apikey = apikey or getattr(settings, 'evolution_go_apikey', '')
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "Content-Type": "application/json",
                "apikey": self.apikey,
            },
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_session(self):
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Content-Type": "application/json",
                    "apikey": self.apikey,
                },
            )
        return self._session
    
    async def _call(self, method: str, endpoint: str, payload: Dict = None) -> EvolutionGoResponse:
        """Call Evolution-Go API endpoint."""
        if not self._session or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={
                    "Content-Type": "application/json",
                    "apikey": self.apikey,
                },
            )
        
        url = f"{self.base_url}{endpoint}"
        payload = payload or {}
        
        try:
            async with self._session.request(method, f"{self.base_url}{endpoint}", json=payload) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return EvolutionGoResponse(
                        success=True,
                        data=data,
                        message_id=data.get("key", {}).get("id"),
                    )
                else:
                    text = await resp.text()
                    return EvolutionGoResponse(
                        success=False,
                        error=f"HTTP {resp.status}: {text}",
                    )
        except asyncio.TimeoutError:
            return EvolutionGoResponse(success=False, error="Request timeout")
        except aiohttp.ClientError as e:
            return EvolutionGoResponse(success=False, error=f"Client error: {e}")
        except Exception as e:
            return EvolutionGoResponse(success=False, error=str(e))
    
    # ── Instance Management ──────────────────────────────────────────────────
    
    async def create_instance(self, instance_name: str, webhook_url: str = "") -> EvolutionGoResponse:
        """Create a new WhatsApp instance."""
        payload = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": webhook_url,
            "webhook_by_events": True,
            "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
        }
        return await self._call("POST", "/instance/create", payload)
    
    async def connect_instance(self, instance_name: str) -> EvolutionGoResponse:
        """Connect an instance (generates QR code)."""
        return await self._call("GET", f"/instance/connect/{instance_name}")
    
    async def get_instance_state(self, instance_name: str) -> EvolutionGoResponse:
        """Get instance connection state."""
        return await self._call("GET", f"/instance/connectionState/{instance_name}")
    
    async def logout_instance(self, instance_name: str) -> EvolutionGoResponse:
        """Logout and disconnect instance."""
        return await self._call("DELETE", f"/instance/logout/{instance_name}")
    
    async def delete_instance(self, instance_name: str) -> EvolutionGoResponse:
        """Delete an instance."""
        return await self._call("DELETE", f"/instance/delete/{instance_name}")
    
    async def get_qrcode(self, instance_name: str) -> EvolutionGoResponse:
        """Get QR code for instance connection."""
        return await self._call("GET", f"/instance/qrcode/{instance_name}")
    
    # ── Message Sending ──────────────────────────────────────────────────────
    
    async def send_text_message(
        self,
        instance_name: str,
        number: str,
        text: str,
        quoted_msg_id: str = None,
    ) -> EvolutionGoResponse:
        """Send a text message."""
        payload = {
            "number": number,
            "text": text,
        }
        if quoted_msg_id:
            payload["quoted"] = {"key": {"id": quoted_msg_id}}
        
        return await self._call("POST", f"/message/sendText/{instance_name}", payload)
    
    async def send_image_message(
        self,
        instance_name: str,
        number: str,
        image_url: str,
        caption: str = "",
        quoted_msg_id: str = None,
    ) -> EvolutionGoResponse:
        """Send an image message."""
        payload = {
            "number": number,
            "url": image_url,
            "caption": caption,
        }
        if quoted_msg_id:
            payload["quoted"] = {"key": {"id": quoted_msg_id}}
        
        return await self._call("POST", f"/message/sendImage/{instance_name}", payload)
    
    async def send_document_message(
        self,
        instance_name: str,
        number: str,
        document_url: str,
        filename: str,
        caption: str = "",
    ) -> EvolutionGoResponse:
        """Send a document message."""
        payload = {
            "number": number,
            "url": document_url,
            "fileName": filename,
            "caption": caption,
        }
        return await self._call("POST", f"/message/sendDocument/{instance_name}", payload)
    
    async def send_video_message(
        self,
        instance_name: str,
        number: str,
        video_url: str,
        caption: str = "",
    ) -> EvolutionGoResponse:
        """Send a video message."""
        payload = {
            "number": number,
            "url": video_url,
            "caption": caption,
        }
        return await self._call("POST", f"/message/sendVideo/{instance_name}", payload)
    
    async def send_audio_message(
        self,
        instance_name: str,
        number: str,
        audio_url: str,
        ptt: bool = False,
    ) -> EvolutionGoResponse:
        """Send an audio message."""
        payload = {
            "number": number,
            "url": audio_url,
            "ptt": ptt,
        }
        return await self._call("POST", f"/message/sendAudio/{instance_name}", payload)
    
    async def send_location_message(
        self,
        instance_name: str,
        number: str,
        latitude: float,
        longitude: float,
        name: str = "",
        address: str = "",
    ) -> EvolutionGoResponse:
        """Send a location message."""
        payload = {
            "number": number,
            "latitude": latitude,
            "longitude": longitude,
            "name": name,
            "address": address,
        }
        return await self._call("POST", f"/message/sendLocation/{instance_name}", payload)
    
    async def send_contact_message(
        self,
        instance_name: str,
        number: str,
        contacts: List[Dict],
    ) -> EvolutionGoResponse:
        """Send contact card(s)."""
        payload = {
            "number": number,
            "contacts": contacts,
        }
        return await self._call("POST", f"/message/sendContact/{instance_name}", payload)
    
    async def send_buttons_message(
        self,
        instance_name: str,
        number: str,
        text: str,
        buttons: List[Dict],
        footer: str = "",
    ) -> EvolutionGoResponse:
        """Send interactive buttons message."""
        payload = {
            "number": number,
            "text": text,
            "buttons": buttons,
            "footer": footer,
        }
        return await self._call("POST", f"/message/sendButtons/{instance_name}", payload)
    
    async def send_list_message(
        self,
        instance_name: str,
        number: str,
        title: str,
        description: str,
        button_text: str,
        sections: List[Dict],
    ) -> EvolutionGoResponse:
        """Send a list message (WhatsApp list picker)."""
        payload = {
            "number": number,
            "title": title,
            "description": description,
            "buttonText": button_text,
            "sections": sections,
        }
        return await self._call("POST", f"/message/sendList/{instance_name}", payload)
    
    # ── Message Management ───────────────────────────────────────────────────
    
    async def get_messages(
        self,
        instance_name: str,
        limit: int = 50,
        page: int = 1,
    ) -> EvolutionGoResponse:
        """Get message history."""
        return await self._call("GET", f"/message/findMessages/{instance_name}", {
            "limit": limit,
            "page": page,
        })
    
    async def get_message_by_id(
        self,
        instance_name: str,
        message_id: str,
    ) -> EvolutionGoResponse:
        """Get a specific message by ID."""
        return await self._call("GET", f"/message/find/{instance_name}/{message_id}")
    
    async def mark_as_read(
        self,
        instance_name: str,
        message_ids: List[str],
    ) -> EvolutionGoResponse:
        """Mark messages as read."""
        return await self._call("POST", f"/message/read/{instance_name}", {
            "messages": message_ids,
        })
    
    async def delete_message(
        self,
        instance_name: str,
        message_id: str,
        for_everyone: bool = False,
    ) -> EvolutionGoResponse:
        """Delete a message."""
        return await self._call("DELETE", f"/message/delete/{instance_name}/{message_id}", {
            "forEveryone": for_everyone,
        })
    
    # ── Contact Management ───────────────────────────────────────────────────
    
    async def check_number_on_whatsapp(self, instance_name: str, number: str) -> EvolutionGoResponse:
        """Check if a phone number exists on WhatsApp."""
        return await self._call("POST", f"/chat/checkNumber/{instance_name}", {
            "number": number,
        })
    
    async def get_contact_profile(self, instance_name: str, number: str) -> EvolutionGoResponse:
        """Get contact profile info."""
        return await self._call("GET", f"/chat/profile/{instance_name}/{number}")
    
    async def get_chats(self, instance_name: str, limit: int = 50) -> EvolutionGoResponse:
        """Get list of chats."""
        return await self._call("GET", f"/chat/findChats/{instance_name}", {
            "limit": limit,
        })
    
    async def get_chat_messages(
        self,
        instance_name: str,
        chat_id: str,
        limit: int = 50,
    ) -> EvolutionGoResponse:
        """Get messages from a specific chat."""
        return await self._call("GET", f"/chat/findMessages/{instance_name}/{chat_id}", {
            "limit": limit,
        })
    
    # ── Group Management ─────────────────────────────────────────────────────
    
    async def create_group(
        self,
        instance_name: str,
        subject: str,
        participants: List[str],
    ) -> EvolutionGoResponse:
        """Create a new group."""
        return await self._call("POST", f"/group/create/{instance_name}", {
            "subject": subject,
            "participants": participants,
        })
    
    async def update_group_subject(
        self,
        instance_name: str,
        group_id: str,
        subject: str,
    ) -> EvolutionGoResponse:
        """Update group subject."""
        return await self._call("POST", f"/group/updateSubject/{instance_name}/{group_id}", {
            "subject": subject,
        })
    
    async def add_participants(
        self,
        instance_name: str,
        group_id: str,
        participants: List[str],
    ) -> EvolutionGoResponse:
        """Add participants to group."""
        return await self._call("POST", f"/group/addParticipants/{instance_name}/{group_id}", {
            "participants": participants,
        })
    
    async def remove_participants(
        self,
        instance_name: str,
        group_id: str,
        participants: List[str],
    ) -> EvolutionGoResponse:
        """Remove participants from group."""
        return await self._call("POST", f"/group/removeParticipants/{instance_name}/{group_id}", {
            "participants": participants,
        })
    
    async def promote_participants(
        self,
        instance_name: str,
        group_id: str,
        participants: List[str],
    ) -> EvolutionGoResponse:
        """Promote participants to admin."""
        return await self._call("POST", f"/group/promoteParticipants/{instance_name}/{group_id}", {
            "participants": participants,
        })
    
    async def demote_participants(
        self,
        instance_name: str,
        group_id: str,
        participants: List[str],
    ) -> EvolutionGoResponse:
        """Demote admins to regular participants."""
        return await self._call("POST", f"/group/demoteParticipants/{instance_name}/{group_id}", {
            "participants": participants,
        })
    
    # ── Media Management ─────────────────────────────────────────────────────
    
    async def upload_media(
        self,
        instance_name: str,
        media_url: str,
        media_type: str,  # image, document, video, audio
    ) -> EvolutionGoResponse:
        """Upload media and get media key."""
        return await self._call("POST", f"/message/uploadMedia/{instance_name}", {
            "url": media_url,
            "type": media_type,
        })
    
    async def download_media(
        self,
        instance_name: str,
        media_key: str,
    ) -> EvolutionGoResponse:
        """Download media by key."""
        return await self._call("GET", f"/message/downloadMedia/{instance_name}/{media_key}")
    
    # ── Webhook Management ───────────────────────────────────────────────────
    
    async def set_webhook(self, instance_name: str, webhook_url: str) -> EvolutionGoResponse:
        """Set webhook URL for instance."""
        return await self._call("POST", f"/webhook/set/{instance_name}", {
            "url": webhook_url,
            "byEvents": True,
            "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "CONNECTION_UPDATE", "QRCODE_UPDATED"],
        })
    
    async def remove_webhook(self, instance_name: str) -> EvolutionGoResponse:
        """Remove webhook from instance."""
        return await self._call("DELETE", f"/webhook/remove/{instance_name}")
    
    # ── Profile & Presence ───────────────────────────────────────────────────
    
    async def set_profile_name(self, instance_name: str, name: str) -> EvolutionGoResponse:
        """Set profile name."""
        return await self._call("POST", f"/profile/setName/{instance_name}", {"name": name})
    
    async def set_profile_picture(self, instance_name: str, image_url: str) -> EvolutionGoResponse:
        """Set profile picture from URL."""
        return await self._call("POST", f"/profile/setPicture/{instance_name}", {
            "url": image_url,
        })
    
    async def set_presence(self, instance_name: str, state: str) -> EvolutionGoResponse:
        """Set presence state: available, unavailable, composing, recording."""
        return await self._call("POST", f"/profile/setPresence/{instance_name}", {
            "state": state,
        })
    
    # ── Status (WhatsApp Stories) ────────────────────────────────────────────
    
    async def post_status(
        self,
        instance_name: str,
        text: str = "",
        image_url: str = "",
        video_url: str = "",
    ) -> EvolutionGoResponse:
        """Post a status (WhatsApp story)."""
        payload = {}
        if text:
            payload["text"] = text
        if image_url:
            payload["image"] = image_url
        if video_url:
            payload["video"] = video_url
        return await self._call("POST", f"/status/post/{instance_name}", payload)
    
    async def get_status(self, instance_name: str) -> EvolutionGoResponse:
        """Get own status updates."""
        return await self._call("GET", f"/status/find/{instance_name}")
    
    async def delete_status(self, instance_name: str, status_id: str) -> EvolutionGoResponse:
        """Delete a status update."""
        return await self._call("DELETE", f"/status/delete/{instance_name}/{status_id}")
    
    # ── Utility ──────────────────────────────────────────────────────────────
    
    async def health_check(self) -> bool:
        """Check if Evolution-Go server is healthy."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False


# Convenience functions for common operations

async def send_whatsapp_message(
    instance_name: str,
    number: str,
    text: str,
    base_url: str = "http://localhost:8080",
    apikey: str = "",
) -> EvolutionGoResponse:
    """Quick function to send a WhatsApp text message."""
    async with EvolutionGoClient(base_url=base_url, apikey=apikey) as client:
        return await client.send_text_message(instance_name, number, text)


async def send_whatsapp_with_image(
    instance_name: str,
    number: str,
    image_url: str,
    caption: str = "",
    base_url: str = "http://localhost:8080",
    apikey: str = "",
) -> EvolutionGoResponse:
    """Quick function to send WhatsApp image message."""
    async with EvolutionGoClient(base_url=base_url, apikey=apikey) as client:
        return await client.send_image_message(instance_name, number, image_url, caption)


if __name__ == "__main__":
    async def test():
        async with EvolutionGoClient() as client:
            print("Testing Evolution-Go Client...")
            
            # Health check
            healthy = await client.health_check()
            print(f"Evolution-Go Health: {'OK' if healthy else 'FAILED'}")
            
            if healthy:
                # Test instance creation (would need valid instance name)
                # result = await client.create_instance("test_instance")
                # print(f"Create instance: {result.success}")
                pass
            
            print("Evolution-Go client test complete")
    
    asyncio.run(test())