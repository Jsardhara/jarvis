"""Real OutlookProvider — MSAL device-code auth + Microsoft Graph REST.

Implements the OutlookProvider Protocol from providers.py. Drop-in
replacement for MockOutlook; same return shapes so Tempo is unchanged.

Auth: MSAL public-client device-code flow. Token cache persisted to
state/.msal_cache.json (state/ is gitignored). Silent refresh on every
call; falls back to device flow only when no cached account.

Constructed with all-optional kwargs so tests can instantiate without
env. First auth attempt raises if OUTLOOK_CLIENT_ID is missing.
"""
from __future__ import annotations

import contextlib
import logging
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}"
DEFAULT_TENANT = "consumers"
DEFAULT_CACHE_PATH = "state/.msal_cache.json"

SCOPES = [
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
    "User.Read",
]


class OutlookGraphError(RuntimeError):
    """Raised when MSAL or Graph returns an unrecoverable error."""

    def __init__(self, status: int, body: Any):
        super().__init__(f"Graph error {status}: {body!r}")
        self.status = status
        self.body = body


class OutlookProvider:
    """Microsoft Graph adapter satisfying the OutlookProvider Protocol."""

    def __init__(
        self,
        client_id: str | None = None,
        tenant: str | None = None,
        authority: str | None = None,
        cache_path: Path | str | None = None,
        http: httpx.Client | None = None,
        msal_app: Any | None = None,
    ):
        self._client_id = client_id or os.environ.get("OUTLOOK_CLIENT_ID")
        self._tenant = tenant or os.environ.get("OUTLOOK_TENANT", DEFAULT_TENANT)
        self._authority = (
            authority
            or os.environ.get("OUTLOOK_AUTHORITY")
            or DEFAULT_AUTHORITY_TEMPLATE.format(tenant=self._tenant)
        )
        cache_env = os.environ.get("OUTLOOK_TOKEN_CACHE", DEFAULT_CACHE_PATH)
        self._cache_path = Path(cache_path) if cache_path is not None else Path(cache_env)
        self._http = http or httpx.Client(timeout=30.0)
        self._msal_app = msal_app
        self._token: str | None = None
        self._default_todo_list_id: str | None = None

    # ---------- Auth ----------

    def _build_msal_app(self) -> Any:
        if self._msal_app is not None:
            return self._msal_app
        if not self._client_id:
            raise OutlookGraphError(
                0, "OUTLOOK_CLIENT_ID is not set; cannot acquire token"
            )
        import msal  # local import keeps tests free of MSAL

        cache = msal.SerializableTokenCache()
        if self._cache_path.exists():
            cache.deserialize(self._cache_path.read_text())
        app = msal.PublicClientApplication(
            self._client_id,
            authority=self._authority,
            token_cache=cache,
        )
        self._msal_app = app
        return app

    def _persist_cache(self) -> None:
        app = self._msal_app
        cache = getattr(app, "token_cache", None)
        if cache is None or not getattr(cache, "has_state_changed", False):
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(cache.serialize())
        with contextlib.suppress(OSError):
            os.chmod(self._cache_path, 0o600)

    def _acquire_token(self, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token
        app = self._build_msal_app()

        result: dict | None = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(SCOPES, account=accounts[0])

        if not result:
            flow = app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise OutlookGraphError(0, f"device flow init failed: {flow!r}")
            # Single visible prompt; never log token contents.
            print(flow["message"], flush=True)
            result = app.acquire_token_by_device_flow(flow)

        if not result or "access_token" not in result:
            raise OutlookGraphError(0, f"token acquisition failed: {result!r}")

        self._persist_cache()
        self._token = result["access_token"]
        return self._token

    def _invalidate_token(self) -> None:
        self._token = None

    # ---------- HTTP ----------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: Any = None,
        expect_status: tuple[int, ...] = (200, 201, 202, 204),
    ) -> httpx.Response:
        url = f"{GRAPH_BASE}{path}"
        for attempt in range(2):
            token = self._acquire_token()
            headers = {"Authorization": f"Bearer {token}"}
            resp = self._http.request(
                method, url, params=params, json=json, headers=headers
            )
            if resp.status_code == 401 and attempt == 0:
                self._invalidate_token()
                continue
            if resp.status_code == 429 and attempt == 0:
                retry_after = int(resp.headers.get("Retry-After", "0") or 0)
                if retry_after > 0:
                    time.sleep(retry_after)
                continue
            if resp.status_code in expect_status:
                return resp
            raise OutlookGraphError(resp.status_code, self._safe_body(resp))
        raise OutlookGraphError(resp.status_code, self._safe_body(resp))

    @staticmethod
    def _safe_body(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except Exception:
            return resp.text

    # ---------- Mappers ----------

    @staticmethod
    def _map_message(m: dict) -> dict:
        labels: list[str] = ["INBOX"]
        if not m.get("isRead", True):
            labels.append("UNREAD")
        for cat in m.get("categories") or []:
            labels.append(str(cat).upper())
        sender = (m.get("from") or {}).get("emailAddress") or {}
        return {
            "id": m.get("id"),
            "from": sender.get("address"),
            "subject": m.get("subject"),
            "snippet": m.get("bodyPreview") or "",
            "labels": labels,
        }

    @staticmethod
    def _iso(dt_obj: dict | None) -> str:
        if not dt_obj:
            return ""
        s = dt_obj.get("dateTime", "")
        tz = dt_obj.get("timeZone", "UTC")
        if not s:
            return ""
        if tz.upper() == "UTC" and not s.endswith("Z") and "+" not in s:
            return s + "+00:00"
        return s

    @classmethod
    def _map_event(cls, e: dict) -> dict:
        attendees = [
            (a.get("emailAddress") or {}).get("address")
            for a in (e.get("attendees") or [])
        ]
        return {
            "id": e.get("id"),
            "summary": e.get("subject"),
            "start": cls._iso(e.get("start")),
            "end": cls._iso(e.get("end")),
            "attendees": [a for a in attendees if a],
        }

    @classmethod
    def _map_slot(cls, s: dict, duration_min: int) -> dict:
        slot = s.get("meetingTimeSlot") or {}
        return {
            "start": cls._iso(slot.get("start")),
            "end": cls._iso(slot.get("end")),
            "duration_min": duration_min,
        }

    @staticmethod
    def _map_task(t: dict) -> dict:
        status = "done" if t.get("status") == "completed" else "open"
        due_obj = t.get("dueDateTime") or {}
        return {
            "id": t.get("id"),
            "title": t.get("title"),
            "due": due_obj.get("dateTime"),
            "status": status,
        }

    # ---------- Mail ----------

    def list_unread(self, max_results: int = 25) -> list[dict]:
        resp = self._request(
            "GET",
            "/me/messages",
            params={
                "$filter": "isRead eq false",
                "$top": str(max_results),
                "$select": "id,from,subject,bodyPreview,categories,isRead",
            },
        )
        body = resp.json()
        return [self._map_message(m) for m in body.get("value", [])]

    def get_message(self, msg_id: str) -> dict:
        resp = self._request("GET", f"/me/messages/{msg_id}")
        return self._map_message(resp.json())

    def draft_reply(self, msg_id: str, body: str) -> dict:
        created = self._request(
            "POST", f"/me/messages/{msg_id}/createReply", expect_status=(200, 201)
        ).json()
        draft_id = created.get("id")
        self._request(
            "PATCH",
            f"/me/messages/{draft_id}",
            json={"body": {"contentType": "Text", "content": body}},
            expect_status=(200,),
        )
        return {"draft_id": draft_id, "in_reply_to": msg_id, "body": body}

    def send(self, to: str, subject: str, body: str) -> dict:
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": True,
        }
        self._request("POST", "/me/sendMail", json=payload, expect_status=(202,))
        from datetime import UTC, datetime

        return {
            "id": f"sent-{uuid4().hex[:8]}",
            "to": to,
            "subject": subject,
            "body": body,
            "ts": datetime.now(UTC).isoformat(),
        }

    # ---------- Calendar ----------

    def list_events(self, start_iso: str, end_iso: str) -> list[dict]:
        resp = self._request(
            "GET",
            "/me/calendarView",
            params={"startDateTime": start_iso, "endDateTime": end_iso},
        )
        return [self._map_event(e) for e in resp.json().get("value", [])]

    def create_event(
        self, summary: str, start_iso: str, end_iso: str, attendees: list[str]
    ) -> dict:
        payload = {
            "subject": summary,
            "start": {"dateTime": start_iso, "timeZone": "UTC"},
            "end": {"dateTime": end_iso, "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ],
        }
        resp = self._request(
            "POST", "/me/events", json=payload, expect_status=(201, 200)
        )
        return self._map_event(resp.json())

    def find_free(
        self, duration_min: int, window_start_iso: str, window_end_iso: str
    ) -> list[dict]:
        payload = {
            "meetingDuration": f"PT{duration_min}M",
            "timeConstraint": {
                "timeslots": [
                    {
                        "start": {"dateTime": window_start_iso, "timeZone": "UTC"},
                        "end": {"dateTime": window_end_iso, "timeZone": "UTC"},
                    }
                ]
            },
        }
        resp = self._request(
            "POST", "/me/findMeetingTimes", json=payload, expect_status=(200,)
        )
        suggestions = resp.json().get("meetingTimeSuggestions", [])
        return [self._map_slot(s, duration_min) for s in suggestions]

    def cancel_event(self, event_id: str) -> dict:
        try:
            self._request(
                "DELETE", f"/me/events/{event_id}", expect_status=(204, 200)
            )
            return {"cancelled": event_id, "found": True}
        except OutlookGraphError as exc:
            if exc.status == 404:
                return {"cancelled": event_id, "found": False}
            raise

    # ---------- Tasks (Microsoft To Do) ----------

    def _resolve_default_list(self) -> str:
        if self._default_todo_list_id:
            return self._default_todo_list_id
        resp = self._request("GET", "/me/todo/lists")
        lists = resp.json().get("value", [])
        if not lists:
            raise OutlookGraphError(0, "no To Do lists found")
        chosen = next(
            (lst for lst in lists if lst.get("wellknownListName") == "defaultList"),
            lists[0],
        )
        self._default_todo_list_id = chosen["id"]
        return self._default_todo_list_id

    def list_tasks(self) -> list[dict]:
        list_id = self._resolve_default_list()
        resp = self._request("GET", f"/me/todo/lists/{list_id}/tasks")
        return [self._map_task(t) for t in resp.json().get("value", [])]

    def add_task_remote(self, title: str, due: str | None) -> dict:
        list_id = self._resolve_default_list()
        payload: dict = {"title": title}
        if due:
            payload["dueDateTime"] = {"dateTime": due, "timeZone": "UTC"}
        resp = self._request(
            "POST",
            f"/me/todo/lists/{list_id}/tasks",
            json=payload,
            expect_status=(201, 200),
        )
        return self._map_task(resp.json())

    def complete_task_remote(self, task_id: str) -> dict:
        list_id = self._resolve_default_list()
        try:
            resp = self._request(
                "PATCH",
                f"/me/todo/lists/{list_id}/tasks/{task_id}",
                json={"status": "completed"},
                expect_status=(200,),
            )
            return self._map_task(resp.json())
        except OutlookGraphError as exc:
            if exc.status == 404:
                return {"id": task_id, "status": "not_found"}
            raise
