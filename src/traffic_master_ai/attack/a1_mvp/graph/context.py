from __future__ import annotations

from dataclasses import dataclass

from ..config import RunConfig
from ..logging.audit import DecisionAuditLogger
from ..browser.worker import BrowserWorker


@dataclass(slots=True)
class AgentContext:
    cfg: RunConfig
    worker: BrowserWorker
    audit: DecisionAuditLogger

