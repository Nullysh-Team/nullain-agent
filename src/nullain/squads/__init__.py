"""NULLAIN-SQUADS — orquestração multi-agente com budget."""

from nullain.squads.orchestrator import SquadBudget, SquadOrchestrator, SquadResult
from nullain.squads.roles import ROLE_SPECS, list_roles

__all__ = [
    "ROLE_SPECS",
    "SquadBudget",
    "SquadOrchestrator",
    "SquadResult",
    "list_roles",
]
