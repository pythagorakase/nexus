"""Plan an owner host's setup from its readiness report (issue #803).

The plan applies no setup changes. Readiness checks retain their existing
diagnostic failure receipts when configuration loading fails.
"""

from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict

from nexus.runtime.readiness import (
    REGISTRY,
    CheckSpec,
    ReadinessContext,
    ReadinessReport,
    run_readiness,
)

INIT_PLAN_SCHEMA_VERSION: Literal[1] = 1


class PlanStep(BaseModel):
    """One failed readiness check and its complete remediation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int
    check_id: str
    observed: str
    remediation: str


class InitPlan(BaseModel):
    """Ordered owner-host setup steps and the checks they block."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = INIT_PLAN_SCHEMA_VERSION
    target: Literal["owner-host"]
    ok: bool
    steps: list[PlanStep]
    blocked: list[str]


def plan_from_report(report: ReadinessReport) -> InitPlan:
    """Copy failures in report order without splitting their remediations."""
    if report.target != "owner-host":
        raise ValueError("An init plan requires an owner-host readiness report")
    if report.omitted:
        raise ValueError("An init plan cannot use a report with omitted checks")
    steps: list[PlanStep] = []
    blocked: list[str] = []
    for check in report.checks:
        if check.status == "fail":
            if check.remediation is None:
                raise RuntimeError(
                    f"Failed readiness check {check.id} has no remediation"
                )
            steps.append(
                PlanStep(
                    number=len(steps) + 1,
                    check_id=check.id,
                    observed=check.observed,
                    remediation=check.remediation,
                )
            )
        elif check.status == "skip":
            blocked.append(check.id)
    return InitPlan(target="owner-host", ok=report.ok, steps=steps, blocked=blocked)


def build_init_plan(
    context: ReadinessContext, *, registry: Sequence[CheckSpec] = REGISTRY
) -> InitPlan:
    """Evaluate the owner's host checks without applying their setup steps."""
    return plan_from_report(run_readiness("owner-host", context, registry=registry))


def render_plan(plan: InitPlan) -> list[str]:
    """Render numbered remediations followed by the checks waiting on them."""
    if not plan.steps:
        return ["No setup steps: every owner-host check passes."]
    lines = [
        f"{step.number}. {step.check_id}: {step.remediation}" for step in plan.steps
    ]
    if plan.blocked:
        lines.append(
            "Then run nexus init --plan again; these checks wait on the steps "
            f"above: {', '.join(plan.blocked)}"
        )
    return lines
