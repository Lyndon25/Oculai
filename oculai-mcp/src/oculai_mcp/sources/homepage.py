"""Personal homepage / personal website data source.

Discovers and scrapes personal academic/industry homepages for
profile enrichment: bio, research interests, publications, projects,
contact info, social links.

Uses the browser evidence tool internally for page capture.
"""

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.db.quotas import check_quota, consume_quota
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery

logger = logging.getLogger(__name__)

# Known academic homepage URL patterns
_HOMEPAGE_PATTERNS = [
    r"github\.io",
    r"\.edu/~",
    r"\.edu/people/",
    r"\.edu/faculty/",
    r"scholar\.google\.com/citations",
    r"researchgate\.net/profile",
    r"linkedin\.com/in/",
    r"dblp\.org/pid/",
    r"orcid\.org/",
]


class PersonalHomepageSource(IDataSource):
    """Personal homepage scraper for candidate profile enrichment.

    Given a homepage URL (discovered via other sources like Semantic Scholar,
    DBLP, or GitHub), fetches the page and extracts structured profile data:
    name, bio, research interests, institution, publications list, contact info.

    Uses the lightweight httpx text capture (no Playwright required for basic
    text extraction). For JavaScript-heavy pages, use oculai_capture_page_evidence
    with mode="screenshot" or mode="full".
    """

    name = "personal_homepage"
    source_type = "crawl"
    description = (
        "Fetch and extract structured profile data from personal academic/industry "
        "homepages. Discovers bio, research interests, publications, projects, and "
        "contact information. Lightweight text extraction via httpx."
    )
    supported_operations = ["get_detail"]
    id_field_map = {}
    example_queries = ["homepage URL from DBLP/Semantic Scholar/GitHub profile"]
    auth_required = False
    rate_limit_notes = "Be polite. Rate limited by target servers."

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                },
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def search(self, query: SearchQuery) -> list[RawCandidate]:
        """Homepage source does not support search — use get_detail with a URL."""
        logger.warning("PersonalHomepageSource.search() is not supported. Use get_detail(url).")
        return []

    async def get_detail(self, external_id: str) -> RawCandidate | None:
        """Fetch and extract structured profile data from a personal homepage URL.

        Args:
            external_id: Full URL of the homepage to scrape
        """
        start = time.perf_counter()

        try:
            client = await self._get_client()
            resp = await client.get(external_id)
            resp.raise_for_status()
            html = resp.text

            # Parse structured data from HTML
            profile = self._extract_profile(html, external_id)

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"url": external_id},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=profile.get("name") or self._guess_name_from_url(external_id),
                institution=profile.get("institution"),
                email=profile.get("email"),
                profile_url=external_id,
                research_areas=profile.get("research_areas"),
                raw_metadata={
                    "source": "personal_homepage",
                    "url": external_id,
                    "domain": urlparse(external_id).netloc,
                    "extracted": profile,
                },
            )

        except httpx.HTTPStatusError as e:
            logger.warning("Homepage fetch failed for %s: HTTP %s", external_id, e.response.status_code)
            return None
        except Exception as e:
            logger.exception("Homepage fetch failed for %s", external_id)
            return None

    def _extract_profile(self, html: str, url: str) -> dict[str, Any]:
        """Extract structured profile fields from homepage HTML."""
        # Strip scripts/styles
        html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', html_clean)
        text = re.sub(r'\s+', ' ', text).strip()

        # Try to extract name from <title>
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        page_title = title_match.group(1).strip() if title_match else None

        # Try meta tags
        meta_name = None
        meta_match = re.search(
            r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html, re.IGNORECASE
        )
        if meta_match:
            meta_name = meta_match.group(1)

        # Extract email addresses
        emails = list(set(re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)))

        # Infer institution from domain
        domain = urlparse(url).netloc
        institution = None
        domain_institution_map = {
            # Western universities
            "csail.mit.edu": "MIT CSAIL",
            "cs.stanford.edu": "Stanford University",
            "eecs.berkeley.edu": "UC Berkeley",
            "cs.cmu.edu": "Carnegie Mellon University",
            "cs.washington.edu": "University of Washington",
            "cs.princeton.edu": "Princeton University",
            "cs.cornell.edu": "Cornell University",
            "cs.utexas.edu": "University of Texas at Austin",
            "cs.illinois.edu": "University of Illinois Urbana-Champaign",
            "cs.ucla.edu": "UCLA",
            "cs.columbia.edu": "Columbia University",
            "cs.nyu.edu": "New York University",
            "cs.umd.edu": "University of Maryland",
            "cs.umich.edu": "University of Michigan",
            "cc.gatech.edu": "Georgia Tech",
            "cs.ox.ac.uk": "University of Oxford",
            "cam.ac.uk": "University of Cambridge",
            "ethz.ch": "ETH Zurich",
            "epfl.ch": "EPFL",
            # Chinese universities (C9 League + major institutions)
            "tsinghua.edu.cn": "Tsinghua University (清华大学)",
            "pku.edu.cn": "Peking University (北京大学)",
            "sjtu.edu.cn": "Shanghai Jiao Tong University (上海交通大学)",
            "zju.edu.cn": "Zhejiang University (浙江大学)",
            "ustc.edu.cn": "University of Science and Technology of China (中国科学技术大学)",
            "fudan.edu.cn": "Fudan University (复旦大学)",
            "nju.edu.cn": "Nanjing University (南京大学)",
            "hit.edu.cn": "Harbin Institute of Technology (哈尔滨工业大学)",
            "xjtu.edu.cn": "Xi'an Jiaotong University (西安交通大学)",
            "buaa.edu.cn": "Beihang University (北京航空航天大学)",
            "bit.edu.cn": "Beijing Institute of Technology (北京理工大学)",
            "nudt.edu.cn": "National University of Defense Technology (国防科技大学)",
            "whu.edu.cn": "Wuhan University (武汉大学)",
            "hust.edu.cn": "Huazhong University of Science and Technology (华中科技大学)",
            "tongji.edu.cn": "Tongji University (同济大学)",
            "scu.edu.cn": "Sichuan University (四川大学)",
            "seu.edu.cn": "Southeast University (东南大学)",
            # Chinese CS-specific subdomains
            "iiis.tsinghua.edu.cn": "Tsinghua IIIS (清华交叉信息研究院)",
            "keg.cs.tsinghua.edu.cn": "Tsinghua KEG (清华知识工程组)",
            "eecs.pku.edu.cn": "Peking University EECS (北大信科)",
        }
        for domain_key, inst_name in domain_institution_map.items():
            if domain_key in domain:
                institution = inst_name
                break

        # Extract research areas from common keywords in text
        research_areas = self._extract_research_areas(text)

        return {
            "name": meta_name or (page_title.split("|")[0].split("-")[0].strip() if page_title else None),
            "page_title": page_title,
            "emails": emails[:3],
            "institution": institution,
            "research_areas": research_areas if research_areas else None,
            "text_preview": text[:1000],
        }

    def _extract_research_areas(self, text: str) -> list[str]:
        """Infer research areas from keyword matches in text."""
        keyword_to_area = {
            "machine learning": "machine_learning",
            "deep learning": "deep_learning",
            "natural language processing": "natural_language_processing",
            "computer vision": "computer_vision",
            "reinforcement learning": "reinforcement_learning",
            "large language model": "large_language_models",
            "generative model": "generative_models",
            "graph neural": "graph_neural_networks",
            "robotics": "robotics",
            "human-computer interaction": "human_computer_interaction",
            "security": "security_privacy",
            "systems": "systems",
            "programming language": "programming_languages",
            "database": "databases",
            "computer graphics": "computer_graphics",
            "bioinformatics": "bioinformatics",
            "quantum computing": "quantum_computing",
            "data mining": "data_mining",
            "information retrieval": "information_retrieval",
            "speech": "speech_processing",
        }
        text_lower = text.lower()
        found: set[str] = set()
        for kw, area in keyword_to_area.items():
            if kw in text_lower:
                found.add(area)
        return sorted(found)[:5] if found else []

    def _guess_name_from_url(self, url: str) -> str:
        """Try to guess a person's name from their homepage URL."""
        path = urlparse(url).path.strip("/")
        if "~" in path:
            name_part = path.split("~")[-1].split("/")[0]
            return name_part.replace("_", " ").title()
        parts = path.split("/")
        if parts:
            return parts[-1].replace("-", " ").replace("_", " ").title()
        return urlparse(url).netloc

    async def check_health(self) -> HealthStatus:
        """Basic health check."""
        return HealthStatus(healthy=True, latency_ms=0)
