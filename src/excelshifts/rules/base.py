"""
Minimal rule contracts.

- RuleSpec: metadata + params for a rule instance.
- BuilderFn: function type that injects a rule into the model and returns the rule's
  enable literal (BoolVar). All constraints in the rule should be guarded with
  `.OnlyEnforceIf(enable)` so we can use solver assumptions/unsat cores later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["RuleSpec"]


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """
    Declarative specification of a rule instance.

    Attributes
    ----------
    id:         Stable identifier (e.g., "no_R_on_fridays").
    enabled:    Whether this rule is active for this run.
    priority:   Integer priority (0 by default). Higher means more relaxable.
    params:     Free-form parameters consumed by the concrete rule builder.
    description:Optional human-readable text for reports (can be empty).
    """

    id: str
    enabled: bool = True
    params: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""
