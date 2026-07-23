"""Typed, provider-neutral identifiers."""

from typing import NewType
from uuid import UUID, uuid4

TaskId = NewType("TaskId", UUID)
TransitionId = NewType("TransitionId", UUID)
PlanId = NewType("PlanId", UUID)
RunId = NewType("RunId", UUID)
ApprovalId = NewType("ApprovalId", UUID)
ArtifactId = NewType("ArtifactId", UUID)
ModelResolutionId = NewType("ModelResolutionId", UUID)
TraceLinkId = NewType("TraceLinkId", UUID)


def new_task_id() -> TaskId:
    return TaskId(uuid4())


def new_transition_id() -> TransitionId:
    return TransitionId(uuid4())


def new_plan_id() -> PlanId:
    return PlanId(uuid4())


def new_run_id() -> RunId:
    return RunId(uuid4())


def new_approval_id() -> ApprovalId:
    return ApprovalId(uuid4())


def new_artifact_id() -> ArtifactId:
    return ArtifactId(uuid4())


def new_model_resolution_id() -> ModelResolutionId:
    return ModelResolutionId(uuid4())


def new_trace_link_id() -> TraceLinkId:
    return TraceLinkId(uuid4())
