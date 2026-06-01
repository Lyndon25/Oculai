"""IDataSource abstract base class and supporting dataclasses. (Adapted from Oculai-origin)"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawCandidate:
    """Raw candidate data from a data source.

    The MCP layer returns RawCandidate with honest metadata about how the data
    was extracted. The Agent layer uses result_type, confidence, and
    extraction_method to decide whether this is a real person and how to
    verify it.
    """
    name: str
    institution: str | None = None
    email: str | None = None
    orcid: str | None = None
    google_scholar_id: str | None = None
    github_id: str | None = None
    linkedin_url: str | None = None
    dblp_key: str | None = None
    paper_count: int = 0
    h_index: int = 0
    citation_count: int = 0
    research_areas: list[str] | None = None
    profile_url: str | None = None
    raw_metadata: dict[str, Any] | None = None

    # Quality metadata — populated by the source connector to help the Agent
    # classify and filter results. The Agent is the final arbiter.
    result_type: str = "unknown"  # profile_page | article | paper | job_posting | web_page | unknown
    confidence: str = "medium"    # high | medium | low
    extraction_method: str = "direct"  # direct | inferred | fallback | unverified


@dataclass
class SearchQuery:
    """Search query parameters."""
    keywords: list[str]
    institutions: list[str] | None = None
    years: tuple[int, int] | None = None
    limit: int = 100
    offset: int = 0
    source_specific_query: str | None = None
    extra: dict[str, Any] | None = None


@dataclass
class HealthStatus:
    healthy: bool
    latency_ms: float
    quota_remaining: int | None = None
    error_message: str | None = None


@dataclass
class SourceError:
    code: str  # timeout, rate_limited, parse_error, empty_results, unknown_source
    message: str
    source_name: str
    retryable: bool = False


@dataclass
class SearchResult:
    """Uniform wrapper for search results across all data sources."""
    candidates: list[RawCandidate] = field(default_factory=list)
    source_name: str = ""
    query: SearchQuery | None = None
    error: SourceError | None = None
    latency_ms: float = 0.0
    quota_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "error" if self.error else "success",
            "candidates": [
                {
                    "name": c.name, "institution": c.institution, "email": c.email,
                    "orcid": c.orcid, "google_scholar_id": c.google_scholar_id,
                    "github_id": c.github_id, "linkedin_url": c.linkedin_url,
                    "paper_count": c.paper_count, "h_index": c.h_index,
                    "citation_count": c.citation_count, "research_areas": c.research_areas,
                    "profile_url": c.profile_url, "raw_metadata": c.raw_metadata,
                    "result_type": c.result_type, "confidence": c.confidence,
                    "extraction_method": c.extraction_method,
                }
                for c in self.candidates
            ],
            "error": {
                "code": self.error.code, "message": self.error.message,
                "source_name": self.error.source_name, "retryable": self.error.retryable,
            } if self.error else None,
            "meta": {
                "source_name": self.source_name,
                "query": self.query.keywords if self.query else [],
                "limit": self.query.limit if self.query else 0,
                "latency_ms": self.latency_ms,
                "quota_remaining": self.quota_remaining,
            },
        }


class IDataSource(ABC):
    """Abstract base class for data sources."""

    name: str = ""
    source_type: str = "api"
    description: str = ""
    supported_operations: list[str] = ["search", "get_detail"]
    id_field_map: dict[str, str] = {}
    example_queries: list[str] = []
    auth_required: bool = False
    rate_limit_notes: str = ""

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        ...

    @abstractmethod
    async def get_detail(self, external_id: str) -> RawCandidate | None:
        ...

    @abstractmethod
    async def check_health(self) -> HealthStatus:
        ...

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_type": self.source_type,
            "description": self.description,
            "supported_operations": self.supported_operations,
            "example_queries": self.example_queries,
            "auth_required": self.auth_required,
            "rate_limit_notes": self.rate_limit_notes,
            "id_field_map": self.id_field_map,
        }
