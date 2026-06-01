"""Role-type dimension weights and must-pass gates for candidate assessment.

Weights are calibrated per role type. They MUST sum to 1.0.
Gates define minimum dimension scores; failing any gate caps overall at 5.0.
"""

from typing import Any

# fmt: off
ROLE_WEIGHTS: dict[str, dict[str, float]] = {
    "research_scientist": {
        "academic": 0.25,
        "engineering": 0.10,
        "leadership": 0.08,
        "communication": 0.12,
        "culture_fit": 0.08,
        "skill_match": 0.18,
        "location": 0.07,
        "career_stage": 0.07,
        "mobility": 0.05,
    },
    "engineer": {
        "academic": 0.08,
        "engineering": 0.28,
        "leadership": 0.08,
        "communication": 0.10,
        "culture_fit": 0.10,
        "skill_match": 0.22,
        "location": 0.07,
        "career_stage": 0.05,
        "mobility": 0.02,
    },
    "ml_engineer": {
        "academic": 0.12,
        "engineering": 0.26,
        "leadership": 0.06,
        "communication": 0.10,
        "culture_fit": 0.10,
        "skill_match": 0.24,
        "location": 0.07,
        "career_stage": 0.03,
        "mobility": 0.02,
    },
    "tech_lead": {
        "academic": 0.06,
        "engineering": 0.22,
        "leadership": 0.20,
        "communication": 0.14,
        "culture_fit": 0.12,
        "skill_match": 0.16,
        "location": 0.05,
        "career_stage": 0.03,
        "mobility": 0.02,
    },
    "product_manager": {
        "academic": 0.04,
        "engineering": 0.14,
        "leadership": 0.18,
        "communication": 0.20,
        "culture_fit": 0.14,
        "skill_match": 0.18,
        "location": 0.07,
        "career_stage": 0.03,
        "mobility": 0.02,
    },
    "data_scientist": {
        "academic": 0.18,
        "engineering": 0.16,
        "leadership": 0.06,
        "communication": 0.12,
        "culture_fit": 0.10,
        "skill_match": 0.24,
        "location": 0.07,
        "career_stage": 0.05,
        "mobility": 0.02,
    },
    "default": {
        "academic": 0.12,
        "engineering": 0.16,
        "leadership": 0.10,
        "communication": 0.12,
        "culture_fit": 0.12,
        "skill_match": 0.20,
        "location": 0.08,
        "career_stage": 0.06,
        "mobility": 0.04,
    },
}
# fmt: on


# Minimum dimension scores required. Failing any gate caps overall at 5.0.
MUST_PASS_GATES: dict[str, dict[str, float]] = {
    "research_scientist": {"skill_match": 4.0, "academic": 3.0},
    "engineer": {"skill_match": 5.0, "engineering": 4.0},
    "ml_engineer": {"skill_match": 5.0, "engineering": 4.0},
    "tech_lead": {"skill_match": 5.0, "leadership": 4.0, "engineering": 4.0},
    "product_manager": {"skill_match": 4.0, "leadership": 3.0, "communication": 3.0},
    "data_scientist": {"skill_match": 4.0, "academic": 3.0},
    "default": {"skill_match": 4.0},
}


def validate_weights() -> None:
    """Validate that all weight profiles sum to 1.0 (within tolerance)."""
    for role, weights in ROLE_WEIGHTS.items():
        total = sum(weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Role '{role}' weights sum to {total}, expected 1.0")


def get_weights(role_type: str) -> dict[str, float]:
    """Get dimension weights for a role type. Falls back to 'default'."""
    return ROLE_WEIGHTS.get(role_type, ROLE_WEIGHTS["default"])


def get_gates(role_type: str) -> dict[str, float]:
    """Get must-pass gates for a role type. Falls back to 'default'."""
    return MUST_PASS_GATES.get(role_type, MUST_PASS_GATES["default"])


def check_gates(dimensions: dict[str, float], role_type: str) -> dict[str, Any]:
    """Check which gates are passed/failed for a given dimension score set.

    Returns {"status": "passed" | "failed", "failures": [...]}
    """
    gates = get_gates(role_type)
    failures = []
    for dim, required in gates.items():
        actual = dimensions.get(dim, 0.0)
        if actual < required:
            failures.append({"dimension": dim, "required": required, "actual": actual})
    return {
        "status": "failed" if failures else "passed",
        "failures": failures,
    }


# Run validation on import
validate_weights()
