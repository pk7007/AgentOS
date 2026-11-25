"""Task complexity score (0-100) and staffing band. Heuristic and uncalibrated until benchmarks exist."""

from pydantic import BaseModel, Field

# factor -> (normalizer, weight); weights sum to 100
FACTORS: dict[str, tuple[float, int]] = {
    "task_count": (20, 15),
    "dependency_depth": (6, 10),
    "workstreams": (6, 15),
    "files_touched": (50, 10),
    "domain_difficulty": (5, 15),
    "uncertainty": (5, 10),
    "risk": (5, 15),
    "verification_effort": (5, 10),
}

# (upper bound inclusive, band, agents)
BANDS = [
    (15, "single", 1),
    (30, "small_team", 2),
    (50, "specialist_team", 3),
    (70, "multi_workstream", 4),
    (85, "department", 4),
    (100, "hierarchical", 4),
]


class ComplexityInput(BaseModel):
    task_count: int = Field(ge=0)
    dependency_depth: int = Field(ge=0)
    workstreams: int = Field(ge=0)
    files_touched: int = Field(ge=0)
    domain_difficulty: int = Field(ge=0, le=5)
    uncertainty: int = Field(ge=0, le=5)
    risk: int = Field(ge=0, le=5)
    verification_effort: int = Field(ge=0, le=5)


class ComplexityResult(BaseModel):
    score: int
    band: str
    suggested_agents: int
    uncalibrated: bool = True


def score(inp: ComplexityInput) -> ComplexityResult:
    total = 0.0
    for name, (norm, weight) in FACTORS.items():
        total += min(getattr(inp, name) / norm, 1.0) * weight
    value = round(total)
    for upper, band, agents in BANDS:
        if value <= upper:
            break
    return ComplexityResult(score=value, band=band, suggested_agents=min(agents, max(1, inp.workstreams)))
