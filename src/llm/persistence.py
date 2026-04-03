"""
HydroAgent 官方 LangGraph SQLite persistence 适配层。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import aiosqlite
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, messages_from_dict
from langgraph.checkpoint.base import Checkpoint, CheckpointTuple
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

WORKSPACE_DIR = Path(__file__).resolve().parents[2] / ".hydro_workspace"
PERSISTENCE_DB_PATH = WORKSPACE_DIR / "langgraph-persistence.sqlite"

THREAD_META_CHANNEL = "hydro.thread.meta"
CHAT_TURN_CHANNEL = "hydro.chat.turn"
TRACE_EVENT_CHANNEL = "hydro.trace.event"
DECISION_CHANNEL = "hydro.decision"

AUDIT_THREAD_ID = "__hydro_audit__"


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _base_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


def _new_checkpoint() -> Checkpoint:
    return {
        "v": 1,
        "id": str(uuid.uuid4()),
        "ts": _utc_now_iso(),
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": [],
    }


def _truncate_title(text: str | None, default: str = "新对话") -> str:
    value = (text or "").strip()
    if not value:
        return default
    return value[:40] + ("..." if len(value) > 40 else "")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_safe_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
    return str(value)


def _coerce_message_objects(raw_messages: Any) -> list[BaseMessage]:
    if not isinstance(raw_messages, list):
        return []
    if all(isinstance(message, BaseMessage) for message in raw_messages):
        return list(raw_messages)
    if all(isinstance(message, dict) and "type" in message and "data" in message for message in raw_messages):
        try:
            return list(messages_from_dict(raw_messages))
        except Exception:
            return []
    return []


def _message_to_payload(message: BaseMessage) -> dict[str, Any] | None:
    if isinstance(message, HumanMessage):
        return {"role": "user", "content": _safe_text(message.content)}
    if isinstance(message, AIMessage):
        return {"role": "assistant", "content": _safe_text(message.content)}
    return None


def _extract_messages(checkpoint_tuple: CheckpointTuple | None) -> list[dict[str, Any]]:
    if not checkpoint_tuple:
        return []
    raw_messages = checkpoint_tuple.checkpoint.get("channel_values", {}).get("messages")
    messages = []
    for message in _coerce_message_objects(raw_messages):
        payload = _message_to_payload(message)
        if payload:
            messages.append(payload)
    return messages


def _thread_meta_from_history(history: list[CheckpointTuple]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    earliest_ts: str | None = None
    for checkpoint_tuple in reversed(history):
        checkpoint_ts = checkpoint_tuple.checkpoint.get("ts")
        if isinstance(checkpoint_ts, str):
            earliest_ts = checkpoint_ts
        for _, channel, value in checkpoint_tuple.pending_writes or []:
            if channel == THREAD_META_CHANNEL and isinstance(value, dict):
                meta = {**meta, **value}
    if earliest_ts and "created_at" not in meta:
        meta["created_at"] = earliest_ts
    return meta


def _build_trace_step(event: dict[str, Any]) -> dict[str, Any]:
    tone = "success" if event.get("status") == "success" else "warning" if event.get("status") == "running" else "danger"
    return {
        "step_index": int(event.get("step_index") or 0),
        "event_type": event.get("event_type") or "unknown",
        "status": event.get("status") or "running",
        "tool_name": event.get("tool_name"),
        "subagent_name": event.get("subagent_name"),
        "title": event.get("title") or "工具链事件",
        "detail": event.get("detail") or "",
        "input_preview": event.get("input_preview"),
        "output_preview": event.get("output_preview"),
        "zone_id": event.get("zone_id"),
        "plan_id": event.get("plan_id"),
        "created_at": event.get("created_at"),
        "duration_ms": event.get("duration_ms"),
        "agent_name": event.get("agent_name"),
        "node_name": event.get("node_name"),
        "layer": event.get("layer") or "tool",
        "tone": tone,
    }


def _build_trace_payload(trace_id: str, events: list[dict[str, Any]], conversation_id: str, conversation_title: str | None) -> dict[str, Any]:
    ordered = sorted(
        events,
        key=lambda item: (
            int(item.get("step_index") or 0),
            str(item.get("created_at") or ""),
        ),
    )
    steps = [_build_trace_step(event) for event in ordered]
    latest = steps[-1] if steps else None
    statuses = {step["status"] for step in steps}
    if "error" in statuses:
        status = "error"
    elif steps and steps[-1]["status"] == "running":
        status = "running"
    else:
        status = "completed"

    return {
        "trace_id": trace_id,
        "conversation_id": conversation_id,
        "conversation_title": conversation_title,
        "status": status,
        "steps": steps,
        "started_at": steps[0]["created_at"] if steps else None,
        "ended_at": None if status == "running" or not steps else steps[-1]["created_at"],
        "duration_ms": sum(int(step.get("duration_ms") or 0) for step in steps) or None,
        "tool_count": sum(1 for step in steps if step["event_type"] in {"tool_call", "tool_result"}),
        "latest_step": latest,
        "zone_id": next((step.get("zone_id") for step in reversed(steps) if step.get("zone_id")), None),
        "plan_id": next((step.get("plan_id") for step in reversed(steps) if step.get("plan_id")), None),
    }


class HydroGraphPersistence:
    """统一管理 LangGraph 官方 SQLite checkpointer 与审计写入。"""

    def __init__(self):
        self._db_path = str(PERSISTENCE_DB_PATH)
        self._async_conn: aiosqlite.Connection | None = None
        self._sync_conn: sqlite3.Connection | None = None
        self._async_saver: AsyncSqliteSaver | None = None
        self._sync_saver: SqliteSaver | None = None
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def async_saver(self) -> AsyncSqliteSaver:
        if not self._async_saver:
            raise RuntimeError("HydroGraphPersistence 尚未初始化")
        return self._async_saver

    @property
    def sync_saver(self) -> SqliteSaver:
        if not self._sync_saver:
            raise RuntimeError("HydroGraphPersistence 尚未初始化")
        return self._sync_saver

    async def initialize(self):
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            self._ensure_sync_initialized()
            self._async_conn = await aiosqlite.connect(self._db_path)
            self._async_saver = AsyncSqliteSaver(self._async_conn)
            await self._async_saver.setup()
            self._initialized = True

    def _ensure_sync_initialized(self):
        if self._sync_conn and self._sync_saver:
            return
        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        self._sync_conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._sync_saver = SqliteSaver(self._sync_conn)
        self._sync_saver.setup()

    async def close(self):
        if self._async_conn:
            await self._async_conn.close()
            self._async_conn = None
        if self._sync_conn:
            self._sync_conn.close()
            self._sync_conn = None
        self._async_saver = None
        self._sync_saver = None
        self._initialized = False

    async def thread_exists(self, thread_id: str) -> bool:
        await self.initialize()
        checkpoint_tuple = await self.async_saver.aget_tuple(_base_config(thread_id))
        return checkpoint_tuple is not None

    async def ensure_thread(self, thread_id: str, title: str = "新对话") -> dict[str, Any]:
        await self.initialize()
        checkpoint_tuple = await self.async_saver.aget_tuple(_base_config(thread_id))
        config = checkpoint_tuple.config if checkpoint_tuple else await self.async_saver.aput(
            _base_config(thread_id),
            _new_checkpoint(),
            {"source": "update", "step": -1},
            {},
        )
        if checkpoint_tuple is None:
            await self.async_saver.aput_writes(
                config,
                [(
                    THREAD_META_CHANNEL,
                    {
                        "title": title,
                        "created_at": _utc_now_iso(),
                    },
                )],
                task_id=f"thread-meta-{uuid.uuid4().hex[:12]}",
            )
        history = await self._list_thread_history(thread_id)
        return self._build_conversation_summary(thread_id, history)

    async def delete_thread(self, thread_id: str):
        await self.initialize()
        await self.async_saver.adelete_thread(thread_id)

    async def record_trace_event(self, thread_id: str, event: dict[str, Any]):
        await self.initialize()
        config = await self._get_anchor_or_latest_config_async(thread_id)
        await self.async_saver.aput_writes(
            config,
            [(TRACE_EVENT_CHANNEL, event)],
            task_id=event.get("event_id") or f"trace-{uuid.uuid4().hex[:12]}",
        )

    async def record_chat_turn(
        self,
        thread_id: str,
        *,
        trace_id: str | None,
        user_content: str,
        assistant_content: str,
    ):
        await self.initialize()
        config = await self._get_anchor_or_latest_config_async(thread_id)
        await self.async_saver.aput_writes(
            config,
            [
                (
                    CHAT_TURN_CHANNEL,
                    {
                        "turn_id": f"turn_{uuid.uuid4().hex[:12]}",
                        "trace_id": trace_id,
                        "user_content": user_content,
                        "assistant_content": assistant_content,
                        "assistant_preview": assistant_content[:280] if assistant_content else "",
                        "created_at": _utc_now_iso(),
                    },
                )
            ],
            task_id=f"turn-{uuid.uuid4().hex[:12]}",
        )

    async def record_decision_async(self, payload: dict[str, Any], thread_id: str | None = None):
        await self.initialize()
        target_thread = thread_id or AUDIT_THREAD_ID
        config = await self._get_anchor_or_latest_config_async(target_thread)
        await self.async_saver.aput_writes(
            config,
            [(DECISION_CHANNEL, payload)],
            task_id=payload.get("decision_id") or f"decision-{uuid.uuid4().hex[:12]}",
        )

    def record_decision_sync(self, payload: dict[str, Any], thread_id: str | None = None):
        self._ensure_sync_initialized()
        target_thread = thread_id or AUDIT_THREAD_ID
        config = self._get_anchor_or_latest_config_sync(target_thread)
        self.sync_saver.put_writes(
            config,
            [(DECISION_CHANNEL, payload)],
            task_id=payload.get("decision_id") or f"decision-{uuid.uuid4().hex[:12]}",
        )

    async def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        await self.initialize()
        histories = await self._list_histories(limit=500)
        summaries = []
        for thread_id, history in histories.items():
            if thread_id == AUDIT_THREAD_ID:
                continue
            summaries.append(self._build_conversation_summary(thread_id, history))
        summaries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return summaries[:limit]

    async def get_conversation(self, thread_id: str) -> dict[str, Any] | None:
        await self.initialize()
        history = await self._list_thread_history(thread_id)
        if not history:
            return None

        summary = self._build_conversation_summary(thread_id, history)
        chat_turns = self._collect_channel_records(history, CHAT_TURN_CHANNEL)
        trace_payloads = self._build_trace_map(history, conversation_filter=thread_id)
        ordered_turns = sorted(
            [item for item in chat_turns if isinstance(item, dict)],
            key=lambda item: str(item.get("created_at") or ""),
        )
        messages: list[dict[str, Any]] = []
        for turn in ordered_turns:
            user_content = str(turn.get("user_content") or "").strip()
            assistant_content = str(turn.get("assistant_content") or turn.get("assistant_preview") or "").strip()
            created_at = turn.get("created_at")
            if user_content:
                messages.append({"role": "user", "content": user_content, "created_at": created_at})
            if assistant_content:
                payload = {"role": "assistant", "content": assistant_content, "created_at": created_at}
                trace_id = turn.get("trace_id")
                if trace_id:
                    payload["trace_id"] = trace_id
                    payload["tool_trace"] = trace_payloads.get(trace_id)
                messages.append(payload)

        return {"conversation": summary, "messages": messages}

    async def list_tool_traces(self, limit: int = 20, conversation_id: str | None = None) -> list[dict[str, Any]]:
        await self.initialize()
        histories = await self._list_histories(limit=800, thread_id=conversation_id)
        trace_map: dict[str, dict[str, Any]] = {}
        for thread_key, history in histories.items():
            if thread_key == AUDIT_THREAD_ID:
                continue
            trace_map.update(self._build_trace_map(history, conversation_filter=thread_key))
        traces = list(trace_map.values())
        traces.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        return traces[:limit]

    async def list_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        await self.initialize()
        histories = await self._list_histories(limit=800)
        decisions: list[dict[str, Any]] = []
        for history in histories.values():
            for item in self._collect_channel_records(history, DECISION_CHANNEL):
                if isinstance(item, dict):
                    decisions.append(item)
        decisions.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return decisions[:limit]

    async def _list_thread_history(self, thread_id: str) -> list[CheckpointTuple]:
        history: list[CheckpointTuple] = []
        async for checkpoint_tuple in self.async_saver.alist(_base_config(thread_id), limit=200):
            history.append(checkpoint_tuple)
        return history

    async def _list_histories(self, *, limit: int = 500, thread_id: str | None = None) -> dict[str, list[CheckpointTuple]]:
        histories: dict[str, list[CheckpointTuple]] = {}
        config = _base_config(thread_id) if thread_id else None
        async for checkpoint_tuple in self.async_saver.alist(config, limit=limit):
            key = str(checkpoint_tuple.config["configurable"]["thread_id"])
            histories.setdefault(key, []).append(checkpoint_tuple)
        return histories

    async def _get_anchor_or_latest_config_async(self, thread_id: str) -> dict[str, Any]:
        checkpoint_tuple = await self.async_saver.aget_tuple(_base_config(thread_id))
        if checkpoint_tuple:
            return checkpoint_tuple.config
        return await self.async_saver.aput(
            _base_config(thread_id),
            _new_checkpoint(),
            {"source": "update", "step": -1},
            {},
        )

    def _get_anchor_or_latest_config_sync(self, thread_id: str) -> dict[str, Any]:
        checkpoint_tuple = self.sync_saver.get_tuple(_base_config(thread_id))
        if checkpoint_tuple:
            return checkpoint_tuple.config
        return self.sync_saver.put(
            _base_config(thread_id),
            _new_checkpoint(),
            {"source": "update", "step": -1},
            {},
        )

    def _build_conversation_summary(self, thread_id: str, history: list[CheckpointTuple]) -> dict[str, Any]:
        latest = history[0] if history else None
        meta = _thread_meta_from_history(history)
        chat_turns = [
            item
            for item in self._collect_channel_records(history, CHAT_TURN_CHANNEL)
            if isinstance(item, dict)
        ]
        chat_turns.sort(key=lambda item: str(item.get("created_at") or ""))
        first_user_content = next((str(item.get("user_content") or "").strip() for item in chat_turns if item.get("user_content")), None)
        updated_at = (
            chat_turns[-1].get("created_at")
            if chat_turns
            else latest.checkpoint.get("ts") if latest else meta.get("created_at")
        )
        message_count = sum(
            (1 if str(item.get("user_content") or "").strip() else 0) +
            (1 if str(item.get("assistant_content") or item.get("assistant_preview") or "").strip() else 0)
            for item in chat_turns
        )
        return {
            "session_id": thread_id,
            "title": _truncate_title(first_user_content, default=str(meta.get("title") or "新对话")),
            "message_count": message_count,
            "created_at": meta.get("created_at"),
            "updated_at": updated_at,
        }

    def _collect_channel_records(self, history: list[CheckpointTuple], channel: str) -> list[Any]:
        items: list[Any] = []
        for checkpoint_tuple in history:
            for _, write_channel, value in checkpoint_tuple.pending_writes or []:
                if write_channel == channel:
                    items.append(value)
        return items

    def _build_trace_map(self, history: list[CheckpointTuple], *, conversation_filter: str) -> dict[str, dict[str, Any]]:
        summary = self._build_conversation_summary(conversation_filter, history)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in self._collect_channel_records(history, TRACE_EVENT_CHANNEL):
            if not isinstance(item, dict):
                continue
            trace_id = str(item.get("trace_id") or "")
            if not trace_id:
                continue
            grouped.setdefault(trace_id, []).append(item)

        return {
            trace_id: _build_trace_payload(
                trace_id,
                events,
                conversation_filter,
                summary.get("title"),
            )
            for trace_id, events in grouped.items()
        }


_hydro_persistence: HydroGraphPersistence | None = None


def get_hydro_persistence() -> HydroGraphPersistence:
    global _hydro_persistence
    if _hydro_persistence is None:
        _hydro_persistence = HydroGraphPersistence()
    return _hydro_persistence
