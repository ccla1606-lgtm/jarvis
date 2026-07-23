from datetime import UTC, datetime

import pytest

from jarvis.domain.entities import Plan, PlanStep
from jarvis.domain.ids import new_task_id

NOW = datetime(2026, 7, 24, 12, tzinfo=UTC)


def test_domain_plan_accepts_finite_dependency_dag() -> None:
    plan = Plan.propose(
        task_id=new_task_id(),
        version=1,
        steps=(
            PlanStep(1, "Inspect", repositories=("owner/repo",)),
            PlanStep(
                2,
                "Change",
                depends_on=(1,),
                tools=("apply_patch",),
                repositories=("owner/repo",),
            ),
        ),
        now=NOW,
    )

    assert plan.steps[1].depends_on == (1,)


@pytest.mark.parametrize(
    "steps",
    (
        (PlanStep(1, "Missing", depends_on=(2,)),),
        (
            PlanStep(1, "One", depends_on=(2,)),
            PlanStep(2, "Two", depends_on=(1,)),
        ),
    ),
)
def test_domain_plan_rejects_missing_or_cyclic_dependencies(
    steps: tuple[PlanStep, ...],
) -> None:
    with pytest.raises(ValueError, match=r"missing|cycle"):
        Plan.propose(
            task_id=new_task_id(),
            version=1,
            steps=steps,
            now=NOW,
        )
