"""Virtual-MCP configuration: which upstream MCP services + which of their tools
this virtual server exposes.

The selection is decided at app-creation time and baked into the deployed app:
it is read once at startup from the VIRTUAL_MCP_CONFIG env var (a JSON string) if
set, else from the bundled config.json. The running app never edits it.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field

_CONFIG_PATH = os.environ.get(
    "VIRTUAL_MCP_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "config.json"),
)
_lock = threading.Lock()


@dataclass
class ServiceSelection:
    """One upstream MCP service and the subset of its tools to expose."""

    name: str  # fully-qualified UC name, e.g. system.ai.github
    alias: str = ""  # short prefix in the merged namespace; derived from name if empty
    # A tool is included if it appears in ``include_tools`` OR matches
    # ``include_regex``. If both are empty/absent, ALL of the service's tools
    # are exposed.
    include_tools: list[str] = field(default_factory=list)
    include_regex: str = ""

    def matches(self, tool_name: str) -> bool:
        if not self.include_tools and not self.include_regex:
            return True
        if tool_name in self.include_tools:
            return True
        if self.include_regex:
            try:
                return re.search(self.include_regex, tool_name, re.IGNORECASE) is not None
            except re.error:
                return False
        return False


@dataclass
class VirtualMcpConfig:
    display_name: str = "Virtual MCP Server"
    services: list[ServiceSelection] = field(default_factory=list)

    def by_alias(self, alias: str) -> ServiceSelection | None:
        return next((s for s in self.services if s.alias == alias), None)


_current: VirtualMcpConfig | None = None


def _slugify_alias(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.split(".")[-1].lower()).strip("_") or "svc"
    alias, i = base, 2
    while alias in taken:
        alias = f"{base}{i}"
        i += 1
    return alias


def _parse(raw: dict) -> VirtualMcpConfig:
    services = [ServiceSelection(**s) for s in raw.get("services", [])]
    # Assign unique aliases for any entry that didn't specify one.
    taken = {s.alias for s in services if s.alias}
    for s in services:
        if not s.alias:
            s.alias = _slugify_alias(s.name, taken)
            taken.add(s.alias)
    return VirtualMcpConfig(
        display_name=raw.get("display_name", "Virtual MCP Server"),
        services=services,
    )


def load() -> VirtualMcpConfig:
    global _current
    with _lock:
        if _current is not None:
            return _current
        # Precedence: the VIRTUAL_MCP_CONFIG env var (set at app-creation time so
        # the template's "mix & match" selection bakes into the deployed app),
        # then the seed config.json, then empty.
        env_cfg = os.environ.get("VIRTUAL_MCP_CONFIG", "").strip()
        if env_cfg:
            try:
                _current = _parse(json.loads(env_cfg))
                return _current
            except (json.JSONDecodeError, TypeError):
                pass
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH) as f:
                _current = _parse(json.load(f))
        else:
            _current = VirtualMcpConfig()
        return _current
