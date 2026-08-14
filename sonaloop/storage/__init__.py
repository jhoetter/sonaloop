from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..config import DATA_DIR, database_path, utc_now_iso
from ._base import StoreBase
from ._chats import ChatsMixin
from ._corpora import CorporaMixin, PredictionOutcomesMixin
from ._councils import CouncilsMixin
from ._decisions import DecisionsMixin
from ._feedback import FeedbackMixin
from ._hooks import HooksMixin
from ._hypotheses import HypothesesMixin
from ._memory import MemoryMixin
from ._personas import PersonasMixin
from ._persona_lifecycle import PersonaLifecycleMixin
from ._prototypes import PrototypesMixin
from ._research import ResearchMixin
from ._schema import SCHEMA
from ._simulation import SimulationMixin
from ._surveys import SurveysMixin
from ._usability_sessions import UsabilitySessionsMixin


class Store(
    PersonasMixin,
    PersonaLifecycleMixin,
    SimulationMixin,
    CouncilsMixin,
    ResearchMixin,
    PrototypesMixin,
    SurveysMixin,
    HypothesesMixin,
    DecisionsMixin,
    FeedbackMixin,
    UsabilitySessionsMixin,
    ChatsMixin,
    CorporaMixin,
    PredictionOutcomesMixin,
    HooksMixin,
    MemoryMixin,
    StoreBase,
):
    pass


# Public backend seam for downstream backends (sonaloop-cloud's Postgres control plane):
# the SQLite→Postgres schema translator and the tenant-aware connection wrapper. Importing
# these does not pull psycopg — the driver is imported lazily inside _PgConnection's methods.
from ._backend import port_sqlite_schema_to_postgres  # noqa: E402
from ._backend import _PgConnection as PgConnection  # noqa: E402

__all__ = ["Store", "SCHEMA", "PgConnection", "port_sqlite_schema_to_postgres"]
