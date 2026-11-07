"""
CarbonLedger AI — Health Check Schemas
"""

from __future__ import annotations

from enum import Enum
from typing import Dict

from pydantic import BaseModel


class ServiceStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
    UNCONFIGURED = "unconfigured"


class HealthResponse(BaseModel):
    status: ServiceStatus
    version: str
    timestamp: str
    environment: str
    services: Dict[str, ServiceStatus]

    model_config = {"use_enum_values": True}
