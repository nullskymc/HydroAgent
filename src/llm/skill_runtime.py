"""
HydroAgent skill catalog, installer, and auto matcher.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import yaml

from src.llm.agent_runtime import HydroAgentMode, HydroPhase, mode_tool_names, normalize_mode

logger = logging.getLogger("hydroagent.skills")

SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills"
VALID_PHASES: set[str] = {"evidence", "analysis", "planning", "approval", "execution", "audit"}
DEFAULT_ALLOWED_IMPORT_DOMAINS = {"raw.githubusercontent.com", "gist.githubusercontent.com"}
EXTRA_ALLOWED_IMPORT_DOMAINS: set[str] = set()
SKILL_IMPORT_TIMEOUT_SECONDS = 10
SKILL_IMPORT_MAX_BYTES = 200_000
MANAGED_BY = "hydroagent"

BUILTIN_WRAPPER_SKILLS: tuple[dict[str, Any], ...] = (
    {
        "id": "system-farm-observer",
        "name": "系统包装：农场观测",
        "description": "后端预置的观测包装 skill，统一收口农场、分区、天气、设备状态与知识检索工具。",
        "trigger_hints": ["农场状态", "分区状态", "天气", "观测", "evidence"],
        "mode_allowlist": ["advisor", "planner", "operator", "auditor"],
        "tool_allowlist": [
            "list_farm_context",
            "list_farm_zones",
            "query_sensor_data",
            "query_weather",
            "get_zone_operating_status",
            "search_knowledge_base",
        ],
        "resources": ["hydro://zones", "hydro://irrigation/status"],
        "workflow": {
            "list_farm_context": "evidence",
            "list_farm_zones": "evidence",
            "query_sensor_data": "evidence",
            "query_weather": "evidence",
            "get_zone_operating_status": "evidence",
            "search_knowledge_base": "evidence",
        },
        "instruction_append": (
            "当激活本系统包装 skill 时，优先先读农场上下文、分区状态、天气和设备状态，"
            "确认 zone_id、雨天风险和执行器可用性后再进入后续分析。"
        ),
        "source_type": "generated",
        "managed_by": MANAGED_BY,
        "wrapper_kind": "builtin_tool_bundle",
        "tool_bundle": [
            "list_farm_context",
            "list_farm_zones",
            "query_sensor_data",
            "query_weather",
            "get_zone_operating_status",
            "search_knowledge_base",
        ],
    },
    {
        "id": "system-irrigation-analyst",
        "name": "系统包装：灌溉分析",
        "description": "后端预置的分析包装 skill，统一收口预测、异常检测和灌溉建议工具。",
        "trigger_hints": ["分析", "预测", "异常", "recommend", "analysis"],
        "mode_allowlist": ["advisor", "planner", "operator", "auditor"],
        "tool_allowlist": [
            "predict_soil_moisture",
            "recommend_irrigation_plan",
            "statistical_analysis",
            "anomaly_detection",
            "time_series_forecast",
            "correlation_analysis",
        ],
        "workflow": {
            "predict_soil_moisture": "analysis",
            "recommend_irrigation_plan": "analysis",
            "statistical_analysis": "analysis",
            "anomaly_detection": "analysis",
            "time_series_forecast": "analysis",
            "correlation_analysis": "analysis",
        },
        "instruction_append": (
            "当激活本系统包装 skill 时，优先用预测、统计和异常检测工具形成证据化分析，"
            "避免跳过湿度趋势、样本数量和风险判断直接给执行结论。"
        ),
        "source_type": "generated",
        "managed_by": MANAGED_BY,
        "wrapper_kind": "builtin_tool_bundle",
        "tool_bundle": [
            "predict_soil_moisture",
            "recommend_irrigation_plan",
            "statistical_analysis",
            "anomaly_detection",
            "time_series_forecast",
            "correlation_analysis",
        ],
    },
    {
        "id": "system-plan-lifecycle",
        "name": "系统包装：计划流转",
        "description": "后端预置的计划流转包装 skill，统一收口计划生成、审批、执行与回执相关工具。",
        "trigger_hints": ["计划", "审批", "执行", "plan", "approval"],
        "mode_allowlist": ["planner", "operator", "auditor"],
        "tool_allowlist": [
            "create_irrigation_plan",
            "get_plan_status",
            "approve_irrigation_plan",
            "reject_irrigation_plan",
            "execute_approved_plan",
            "control_irrigation",
            "manage_alarm",
        ],
        "resources": ["hydro://irrigation/status", "hydro://alarm/status"],
        "workflow": {
            "create_irrigation_plan": "planning",
            "get_plan_status": "planning",
            "approve_irrigation_plan": "approval",
            "reject_irrigation_plan": "approval",
            "execute_approved_plan": "execution",
            "control_irrigation": "execution",
            "manage_alarm": "audit",
        },
        "instruction_append": (
            "当激活本系统包装 skill 时，必须遵守计划先行、审批边界和单次执行规则，"
            "任何 start 类动作都只能建立在真实计划和审批状态之上。"
        ),
        "source_type": "generated",
        "managed_by": MANAGED_BY,
        "wrapper_kind": "builtin_tool_bundle",
        "tool_bundle": [
            "create_irrigation_plan",
            "get_plan_status",
            "approve_irrigation_plan",
            "reject_irrigation_plan",
            "execute_approved_plan",
            "control_irrigation",
            "manage_alarm",
        ],
    },
)


@dataclass(slots=True)
class SkillSpec:
    id: str
    name: str
    description: str
    trigger_hints: list[str] = field(default_factory=list)
    mode_allowlist: list[str] = field(default_factory=list)
    tool_allowlist: list[str] = field(default_factory=list)
    instruction_append: str = ""
    resources: list[str] = field(default_factory=list)
    workflow: dict[str, HydroPhase] = field(default_factory=dict)
    workflow_phases: list[HydroPhase] = field(default_factory=list)
    source_type: str = "local"
    source_url: str | None = None
    managed_by: str | None = None
    wrapper_kind: str | None = None
    tool_bundle: list[str] = field(default_factory=list)
    installed_at: str | None = None
    updated_at: str | None = None
    source_path: str = ""

    def to_public_dict(self, *, include_detail: bool = False) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "trigger_hints": self.trigger_hints,
            "mode_allowlist": self.mode_allowlist,
            "tool_allowlist": self.tool_allowlist,
            "resources": self.resources,
            "workflow": self.workflow,
            "workflow_phases": self.workflow_phases,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "managed_by": self.managed_by,
            "wrapper_kind": self.wrapper_kind,
            "tool_bundle": self.tool_bundle,
            "installed_at": self.installed_at,
            "updated_at": self.updated_at,
        }
        if include_detail:
            payload["instruction_append"] = self.instruction_append
            payload["source_path"] = self.source_path
        return payload


@dataclass(slots=True)
class ResolvedSkillContext:
    mode: HydroAgentMode
    active_skills: list[SkillSpec]
    matched_skill_ids: list[str]
    confidence: float
    reason: str
    allowed_tools: list[str]
    prompt_fragments: list[str]
    resources: list[str]
    workflow_overrides: dict[str, HydroPhase]
    workflow_phases: list[HydroPhase]
    conflicts: list[str]

    @property
    def active_skill_ids(self) -> list[str]:
        return [skill.id for skill in self.active_skills]


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n"):
        return {}, raw.strip()
    parts = raw.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, raw.strip()
    metadata = yaml.safe_load(parts[0][4:]) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata, parts[1].strip()


def _parse_workflow(value: Any) -> tuple[dict[str, HydroPhase], list[HydroPhase]]:
    if isinstance(value, dict):
        workflow: dict[str, HydroPhase] = {}
        for tool_name, phase in value.items():
            phase_name = str(phase).strip()
            if phase_name in VALID_PHASES:
                workflow[str(tool_name).strip()] = phase_name  # type: ignore[assignment]
        return workflow, list(dict.fromkeys(workflow.values()))

    phases: list[HydroPhase] = []
    for item in _ensure_list(value):
        candidate = str(item).strip()
        if candidate in VALID_PHASES and candidate not in phases:
            phases.append(candidate)  # type: ignore[arg-type]
    return {}, phases


def _normalize_skill_spec(metadata: dict[str, Any], body: str, *, source_path: Path) -> SkillSpec:
    skill_id = str(metadata.get("id") or source_path.parent.name).strip()
    if not skill_id:
        raise ValueError("skill id is required")
    name = str(metadata.get("name") or skill_id).strip()
    description = str(metadata.get("description") or "").strip()
    if not description:
        raise ValueError("skill description is required")

    mode_allowlist = [normalize_mode(item) for item in _ensure_list(metadata.get("mode_allowlist"))]
    tool_allowlist = [str(item).strip() for item in _ensure_list(metadata.get("tool_allowlist")) if str(item).strip()]
    resources = [str(item).strip() for item in _ensure_list(metadata.get("resources")) if str(item).strip()]
    workflow, workflow_phases = _parse_workflow(metadata.get("workflow"))
    instruction_append = str(metadata.get("instruction_append") or body or "").strip()
    tool_bundle = [str(item).strip() for item in _ensure_list(metadata.get("tool_bundle")) if str(item).strip()]

    return SkillSpec(
        id=skill_id,
        name=name,
        description=description,
        trigger_hints=[str(item).strip() for item in _ensure_list(metadata.get("trigger_hints")) if str(item).strip()],
        mode_allowlist=mode_allowlist,
        tool_allowlist=tool_allowlist,
        instruction_append=instruction_append,
        resources=resources,
        workflow=workflow,
        workflow_phases=workflow_phases,
        source_type=str(metadata.get("source_type") or "local").strip() or "local",
        source_url=str(metadata.get("source_url") or "").strip() or None,
        managed_by=str(metadata.get("managed_by") or "").strip() or None,
        wrapper_kind=str(metadata.get("wrapper_kind") or "").strip() or None,
        tool_bundle=tool_bundle,
        installed_at=str(metadata.get("installed_at") or "").strip() or None,
        updated_at=str(metadata.get("updated_at") or "").strip() or None,
        source_path=str(source_path),
    )


def _render_skill_markdown(metadata: dict[str, Any], body: str) -> str:
    clean_metadata = {key: value for key, value in metadata.items() if value not in (None, "", [], {})}
    yaml_block = yaml.safe_dump(clean_metadata, allow_unicode=True, sort_keys=False).strip()
    content = body.strip()
    return f"---\n{yaml_block}\n---\n\n{content}\n"


def _normalize_import_url(url: str) -> str:
    candidate = (url or "").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme != "https":
        raise ValueError("仅支持 https skill 链接")

    host = parsed.netloc.lower()
    if host == "github.com":
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 5 and path_parts[2] == "blob":
            owner, repo, _, branch = path_parts[:4]
            rest = "/".join(path_parts[4:])
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rest}"
        raise ValueError("GitHub 链接必须指向具体文件")
    return candidate


def _validate_import_domain(url: str):
    host = urlsplit(url).netloc.lower()
    allowed = DEFAULT_ALLOWED_IMPORT_DOMAINS | EXTRA_ALLOWED_IMPORT_DOMAINS
    if host not in allowed:
        raise ValueError(f"skill 导入域名不在白名单中：{host}")


def _download_skill_markdown(url: str) -> str:
    request = Request(url, headers={"User-Agent": "HydroAgentSkillInstaller/1.0"})
    try:
        with urlopen(request, timeout=SKILL_IMPORT_TIMEOUT_SECONDS) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if content_type and not (
                content_type.startswith("text/")
                or "markdown" in content_type
                or "charset" in content_type
            ):
                raise ValueError(f"skill 内容类型不受支持：{content_type}")
            payload = response.read(SKILL_IMPORT_MAX_BYTES + 1)
    except HTTPError as exc:
        raise ValueError(f"skill 下载失败：HTTP {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"skill 下载失败：{exc.reason}") from exc

    if len(payload) > SKILL_IMPORT_MAX_BYTES:
        raise ValueError("skill 文件过大")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("skill 文件必须是 UTF-8 文本") from exc


class HydroSkillRuntime:
    def __init__(self, root: Path | None = None):
        self._root = root or SKILL_ROOT
        self._catalog: dict[str, SkillSpec] | None = None

    def invalidate_catalog(self):
        self._catalog = None

    def list_skills(self) -> list[SkillSpec]:
        return list(self._load_catalog().values())

    def get_skill(self, skill_id: str) -> SkillSpec | None:
        return self._load_catalog().get(skill_id)

    def import_skill_from_url(self, url: str, *, overwrite: bool = False) -> tuple[SkillSpec, str]:
        normalized_url = _normalize_import_url(url)
        _validate_import_domain(normalized_url)
        raw = _download_skill_markdown(normalized_url)
        metadata, body = _split_frontmatter(raw)
        if not metadata:
            raise ValueError("导入的 skill 必须包含 frontmatter")
        if not str(metadata.get("id") or "").strip():
            raise ValueError("导入的 skill frontmatter 必须包含 id")
        if not str(metadata.get("name") or "").strip():
            raise ValueError("导入的 skill frontmatter 必须包含 name")
        if not str(metadata.get("description") or "").strip():
            raise ValueError("导入的 skill frontmatter 必须包含 description")

        now = _utc_now_iso()
        existing = self.get_skill(str(metadata.get("id") or "").strip()) if metadata.get("id") else None
        if existing:
            if existing.source_type == "local":
                raise ValueError("不能覆盖本地维护的 skill")
            if existing.wrapper_kind == "builtin_tool_bundle":
                raise ValueError("不能覆盖系统预置包装 skill")
            if not overwrite:
                raise ValueError(f"skill id 已存在：{existing.id}")

        metadata["source_type"] = "imported"
        metadata["source_url"] = normalized_url
        metadata["managed_by"] = MANAGED_BY
        metadata["installed_at"] = existing.installed_at if existing and existing.installed_at else now
        metadata["updated_at"] = now

        spec = _normalize_skill_spec(metadata, body, source_path=self._root / str(metadata.get("id") or "imported") / "SKILL.md")
        self._write_skill_file(spec, metadata=metadata, body=body or spec.instruction_append)
        self.invalidate_catalog()
        stored = self.get_skill(spec.id)
        if not stored:
            raise RuntimeError("skill 导入后加载失败")
        return stored, "updated" if existing else "installed"

    def delete_skill(self, skill_id: str) -> SkillSpec:
        skill = self.get_skill(skill_id)
        if not skill:
            raise ValueError("skill 不存在")
        if skill.wrapper_kind == "builtin_tool_bundle":
            raise ValueError("系统预置包装 skill 不允许删除")
        if skill.source_type not in {"imported", "generated"}:
            raise ValueError("仅允许删除 imported/generated 类型的 skill")
        skill_dir = Path(skill.source_path).parent
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        self.invalidate_catalog()
        return skill

    def resolve_for_chat(
        self,
        *,
        mode: str | None,
        message: str,
        explicit_skill_ids: list[str] | None = None,
        working_memory: dict[str, Any] | None = None,
        farm_context: list[dict[str, Any]] | None = None,
    ) -> ResolvedSkillContext:
        resolved_mode = normalize_mode(mode)
        catalog = self._load_catalog()
        explicit_skill_ids = [item for item in (explicit_skill_ids or []) if item]
        explicit_skills: list[SkillSpec] = []
        explicit_missing: list[str] = []

        for skill_id in explicit_skill_ids:
            skill = catalog.get(skill_id)
            if not skill:
                explicit_missing.append(skill_id)
                continue
            if skill.mode_allowlist and resolved_mode not in skill.mode_allowlist:
                continue
            explicit_skills.append(skill)

        matched_skills, confidence, reason = self._match_skills(
            message=message,
            mode=resolved_mode,
            working_memory=working_memory,
            farm_context=farm_context,
        )
        ordered_skills = self._merge_skills(explicit_skills, matched_skills)
        conflicts: list[str] = []
        if explicit_missing:
            conflicts.append(f"未找到 skill：{', '.join(explicit_missing)}")

        mode_allowed_tools = list(mode_tool_names(resolved_mode))
        skill_tool_order: list[str] = []
        for skill in ordered_skills:
            for tool_name in skill.tool_allowlist:
                if tool_name in mode_allowed_tools and tool_name not in skill_tool_order:
                    skill_tool_order.append(tool_name)

        # Skill 只调整工具优先级，不剥离当前模式需要的基础观测与分析工具。
        # 模式白名单仍是硬安全边界，因此 planner 不会获得审批或执行工具。
        allowed_tools = [
            *skill_tool_order,
            *[tool_name for tool_name in mode_allowed_tools if tool_name not in skill_tool_order],
        ]

        workflow_overrides: dict[str, HydroPhase] = {}
        workflow_phases: list[HydroPhase] = []
        for skill in ordered_skills:
            for phase in skill.workflow_phases:
                if phase not in workflow_phases:
                    workflow_phases.append(phase)
            for tool_name, phase in skill.workflow.items():
                existing = workflow_overrides.get(tool_name)
                if existing and existing != phase:
                    conflicts.append(f"skill workflow 冲突：{tool_name} -> {existing}/{phase}")
                    workflow_overrides.pop(tool_name, None)
                    continue
                workflow_overrides[tool_name] = phase

        prompt_fragments = [skill.instruction_append for skill in ordered_skills if skill.instruction_append]
        resources: list[str] = []
        for skill in ordered_skills:
            resources.extend([item for item in skill.resources if item not in resources])

        if not ordered_skills:
            reason = reason or "未匹配到高置信度 skill，回退到基础模式。"
        elif not reason:
            reason = f"激活 {len(ordered_skills)} 个 skill。"

        return ResolvedSkillContext(
            mode=resolved_mode,
            active_skills=ordered_skills,
            matched_skill_ids=[skill.id for skill in matched_skills],
            confidence=confidence,
            reason=reason,
            allowed_tools=allowed_tools,
            prompt_fragments=prompt_fragments,
            resources=resources,
            workflow_overrides=workflow_overrides,
            workflow_phases=workflow_phases,
            conflicts=conflicts,
        )

    def _merge_skills(self, explicit_skills: list[SkillSpec], matched_skills: list[SkillSpec]) -> list[SkillSpec]:
        merged: list[SkillSpec] = []
        seen: set[str] = set()
        for skill in [*explicit_skills, *matched_skills]:
            if skill.id in seen:
                continue
            seen.add(skill.id)
            merged.append(skill)
        return merged

    def _match_skills(
        self,
        *,
        message: str,
        mode: HydroAgentMode,
        working_memory: dict[str, Any] | None = None,
        farm_context: list[dict[str, Any]] | None = None,
    ) -> tuple[list[SkillSpec], float, str]:
        message_tokens = self._tokenize(message)
        memory_tokens = self._tokenize(" ".join(map(str, (working_memory or {}).get("open_risks", []))))
        farm_tokens = self._tokenize(" ".join(str(item.get("risk_hint") or "") for item in (farm_context or [])))
        scores: list[tuple[float, SkillSpec, str]] = []

        for skill in self.list_skills():
            if skill.mode_allowlist and mode not in skill.mode_allowlist:
                continue
            skill_text = " ".join([skill.id, skill.name, skill.description, *skill.trigger_hints])
            skill_tokens = self._tokenize(skill_text)
            overlap = len((message_tokens | memory_tokens | farm_tokens) & skill_tokens)
            substring_hits = sum(1 for hint in skill.trigger_hints if hint and hint in message)
            exact_bonus = 1 if skill.id in message or skill.name in message else 0
            if overlap == 0 and substring_hits == 0 and exact_bonus == 0:
                continue
            score = min(1.0, overlap * 0.18 + substring_hits * 0.28 + exact_bonus * 0.35)
            scores.append((score, skill, f"{skill.name} 命中触发词 {substring_hits} 项，关键词重合 {overlap} 项。"))

        scores.sort(key=lambda item: (-item[0], item[1].id))
        active = [item for item in scores if item[0] >= 0.35][:3]
        if not active:
            return [], 0.0, "自动匹配未达到置信度阈值。"
        return [item[1] for item in active], active[0][0], " ".join(item[2] for item in active)

    def _load_catalog(self) -> dict[str, SkillSpec]:
        if self._catalog is not None:
            return self._catalog

        catalog: dict[str, SkillSpec] = {}
        if not self._root.exists():
            self._catalog = catalog
            return catalog

        for skill_file in sorted(self._root.glob("*/SKILL.md")):
            try:
                raw = skill_file.read_text(encoding="utf-8")
                metadata, body = _split_frontmatter(raw)
                skill = _normalize_skill_spec(metadata, body, source_path=skill_file)
            except Exception as exc:
                logger.warning("Skill load failed for %s: %s", skill_file, exc)
                continue
            catalog[skill.id] = skill

        for metadata in BUILTIN_WRAPPER_SKILLS:
            try:
                builtin_skill = _normalize_skill_spec(
                    dict(metadata),
                    str(metadata.get("instruction_append") or ""),
                    source_path=self._root / str(metadata["id"]) / "SKILL.md",
                )
            except Exception as exc:
                logger.warning("Builtin skill load failed for %s: %s", metadata.get("id"), exc)
                continue
            catalog.setdefault(builtin_skill.id, builtin_skill)

        self._catalog = catalog
        return catalog

    def _write_skill_file(self, spec: SkillSpec, *, metadata: dict[str, Any], body: str):
        skill_dir = self._root / spec.id
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = _render_skill_markdown(metadata, body)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def _tokenize(self, text: str) -> set[str]:
        normalized = text.lower()
        ascii_tokens = set(re.findall(r"[a-z0-9_]+", normalized))
        cjk_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}", text))
        return {token for token in ascii_tokens | cjk_tokens if token}


_skill_runtime: HydroSkillRuntime | None = None


def get_skill_runtime() -> HydroSkillRuntime:
    global _skill_runtime
    if _skill_runtime is None:
        _skill_runtime = HydroSkillRuntime()
    return _skill_runtime
