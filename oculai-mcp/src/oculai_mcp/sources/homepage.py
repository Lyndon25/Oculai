"""Personal homepage / personal website data source.

Discovers and scrapes personal academic/industry homepages for
profile enrichment: bio, research interests, publications, projects,
contact info, social links.

Supports both static (httpx) and dynamic (Playwright) rendering for
JavaScript-heavy pages. Uses fit_markdown-style content denoising to
remove navigation, ads, and noise — inspired by crawl4ai.
"""

import logging
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from oculai_mcp.db.provenance import log_source_call
from oculai_mcp.sources.base import HealthStatus, IDataSource, RawCandidate, SearchQuery
from oculai_mcp.utils.html_denoise import html_to_fit_markdown, is_likely_dynamic_page

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright  # type: ignore[import-untyped]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

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

    Uses lightweight httpx text capture for static pages. Automatically falls
    back to Playwright dynamic rendering for JavaScript-heavy pages (React,
    Vue, Angular, etc.). Content is denoised via fit_markdown extraction to
    remove navigation, ads, and noise before profile parsing.
    """

    name = "personal_homepage"
    source_type = "crawl"
    description = (
        "Fetch and extract structured profile data from personal academic/industry "
        "homepages. Supports static (httpx) and dynamic (Playwright) rendering. "
        "Uses fit_markdown denoising to remove navigation/ads and extract clean "
        "content. Discovers bio, research interests, publications, projects, and contact."
    )
    supported_operations = ["get_detail"]
    id_field_map = {}
    example_queries = ["homepage URL from DBLP/Semantic Scholar/GitHub profile"]
    auth_required = False
    rate_limit_notes = "Be polite. Rate limited by target servers. Dynamic rendering is slower."

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

        Strategy:
        1. Quick static fetch via httpx
        2. If page is likely dynamic (low text density, SPA markers) and
           Playwright is available, re-fetch with dynamic rendering
        3. Denoise HTML to fit_markdown
        4. Extract structured profile fields from clean content

        Args:
            external_id: Full URL of the homepage to scrape
        """
        start = time.perf_counter()
        url = external_id

        html: str | None = None
        used_dynamic = False

        try:
            # Step 1: Static fetch
            client = await self._get_client()
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text

            # Step 2: Check if dynamic rendering is needed
            if html and is_likely_dynamic_page(html):
                if _PLAYWRIGHT_AVAILABLE:
                    logger.info("Page %s appears dynamic — switching to Playwright rendering", url)
                    dynamic_html = await self._capture_dynamic(url)
                    if dynamic_html:
                        html = dynamic_html
                        used_dynamic = True
                else:
                    logger.warning(
                        "Page %s appears dynamic but Playwright not installed. "
                        "Consider: pip install playwright && playwright install chromium",
                        url,
                    )

            if not html:
                logger.warning("No HTML content retrieved for %s", url)
                return None

            # Step 3: Denoise to fit_markdown
            markdown = html_to_fit_markdown(html, url=url, max_length=20000)

            # Step 4: Extract profile from clean content
            profile = self._extract_profile(html, markdown, url)

            duration_ms = int((time.perf_counter() - start) * 1000)
            await log_source_call(
                source_name=self.name,
                source_type=self.source_type,
                query_params={"url": url, "dynamic": used_dynamic},
                status="success",
                duration_ms=duration_ms,
                records_count=1,
            )

            return RawCandidate(
                name=profile.get("name") or self._guess_name_from_url(url),
                institution=profile.get("institution"),
                email=profile.get("email"),
                profile_url=url,
                research_areas=profile.get("research_areas"),
                raw_metadata={
                    "source": "personal_homepage",
                    "url": url,
                    "domain": urlparse(url).netloc,
                    "dynamic_rendered": used_dynamic,
                    "extracted": profile,
                    "content_preview": markdown[:2000],
                },
            )

        except httpx.HTTPStatusError as e:
            logger.warning("Homepage fetch failed for %s: HTTP %s", url, e.response.status_code)
            return None
        except Exception as e:
            logger.exception("Homepage fetch failed for %s", url)
            return None

    async def _capture_dynamic(self, url: str) -> str | None:
        """Capture page HTML after JavaScript rendering via Playwright."""
        if not _PLAYWRIGHT_AVAILABLE:
            return None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    # Additional wait for lazy-loaded content
                    await page.wait_for_timeout(1000)
                    html = await page.content()
                    return html
                finally:
                    await browser.close()
        except Exception as e:
            logger.warning("Dynamic capture failed for %s: %s", url, e)
            return None

    def _extract_profile(self, html: str, markdown: str, url: str) -> dict[str, Any]:
        """Extract structured profile fields from homepage content.

        Uses both raw HTML (for structured data like meta tags) and
        denoised markdown (for clean text analysis).
        """
        # Extract name from HTML meta/title (more reliable than markdown)
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        page_title = title_match.group(1).strip() if title_match else None

        meta_name = None
        meta_match = re.search(
            r'<meta[^>]+name="author"[^>]+content="([^"]+)"', html, re.IGNORECASE
        )
        if meta_match:
            meta_name = meta_match.group(1)

        # Also try schema.org Person name
        schema_name_match = re.search(
            r'"@type"\s*:\s*"Person"[^}]*"name"\s*:\s*"([^"]+)"', html, re.IGNORECASE
        )
        schema_name = schema_name_match.group(1) if schema_name_match else None

        # Extract emails from both HTML and markdown
        emails = list(set(re.findall(
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html + " " + markdown
        )))
        # Filter out common false positives
        emails = [
            e for e in emails
            if not any(x in e.lower() for x in ["example.com", "test.com", "domain.com", "noreply"])
        ]

        # Infer institution from domain
        domain = urlparse(url).netloc
        institution = self._infer_institution(domain)

        # Extract research areas from clean markdown text
        research_areas = self._extract_research_areas(markdown)

        # Determine name priority: meta author > schema.org > title heuristic
        name = meta_name or schema_name
        if not name and page_title:
            # Clean title: split on common separators and take first part
            name = page_title.split("|")[0].split("-")[0].split("")[0].strip()
            # If title looks like "John Doe - Homepage", use "John Doe"
            if len(name.split()) > 4:
                name = " ".join(name.split()[:3])

        return {
            "name": name,
            "page_title": page_title,
            "emails": emails[:3],
            "email": emails[0] if emails else None,
            "institution": institution,
            "research_areas": research_areas if research_areas else None,
            "text_preview": markdown[:1500],
        }

    def _infer_institution(self, domain: str) -> str | None:
        """Map a domain to an institution name."""
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
            # Chinese universities — C9 League
            "tsinghua.edu.cn": "Tsinghua University (清华大学)",
            "pku.edu.cn": "Peking University (北京大学)",
            "sjtu.edu.cn": "Shanghai Jiao Tong University (上海交通大学)",
            "zju.edu.cn": "Zhejiang University (浙江大学)",
            "ustc.edu.cn": "University of Science and Technology of China (中国科学技术大学)",
            "fudan.edu.cn": "Fudan University (复旦大学)",
            "nju.edu.cn": "Nanjing University (南京大学)",
            "hit.edu.cn": "Harbin Institute of Technology (哈尔滨工业大学)",
            "xjtu.edu.cn": "Xi'an Jiaotong University (西安交通大学)",
            # Major Chinese universities
            "buaa.edu.cn": "Beihang University (北京航空航天大学)",
            "bit.edu.cn": "Beijing Institute of Technology (北京理工大学)",
            "nudt.edu.cn": "National University of Defense Technology (国防科技大学)",
            "whu.edu.cn": "Wuhan University (武汉大学)",
            "hust.edu.cn": "Huazhong University of Science and Technology (华中科技大学)",
            "tongji.edu.cn": "Tongji University (同济大学)",
            "scu.edu.cn": "Sichuan University (四川大学)",
            "seu.edu.cn": "Southeast University (东南大学)",
            "bnu.edu.cn": "Beijing Normal University (北京师范大学)",
            "ruc.edu.cn": "Renmin University of China (中国人民大学)",
            "cqu.edu.cn": "Chongqing University (重庆大学)",
            "dlut.edu.cn": "Dalian University of Technology (大连理工大学)",
            "tju.edu.cn": "Tianjin University (天津大学)",
            "lzu.edu.cn": "Lanzhou University (兰州大学)",
            "nankai.edu.cn": "Nankai University (南开大学)",
            "shandong.edu.cn": "Shandong University (山东大学)",
            "xmu.edu.cn": "Xiamen University (厦门大学)",
            "csu.edu.cn": "Central South University (中南大学)",
            "neu.edu.cn": "Northeastern University (中国东北大学)",
            "nwpu.edu.cn": "Northwestern Polytechnical University (西北工业大学)",
            "ecnu.edu.cn": "East China Normal University (华东师范大学)",
            "bupt.edu.cn": "Beijing University of Posts and Telecommunications (北京邮电大学)",
            "ucas.ac.cn": "University of Chinese Academy of Sciences (中国科学院大学)",
            # Chinese CS-specific subdomains
            "iiis.tsinghua.edu.cn": "Tsinghua IIIS (清华交叉信息研究院)",
            "keg.cs.tsinghua.edu.cn": "Tsinghua KEG (清华知识工程组)",
            "eecs.pku.edu.cn": "Peking University EECS (北大信科)",
            "iai.buaa.edu.cn": "Beihang IAI (北航人工智能研究院)",
            "nlp.csai.tsinghua.edu.cn": "Tsinghua NLP (清华自然语言处理组)",
            "mllab.sist.edu.cn": "ShanghaiTech MLLab (上海科技大学机器视觉实验室)",
            # Chinese research institutes
            "baai.ac.cn": "Beijing Academy of Artificial Intelligence (北京智源人工智能研究院)",
            "microsoft.com": "Microsoft Research",
            "alibaba-inc.com": "Alibaba",
            "bytedance.com": "ByteDance",
            "tencent.com": "Tencent",
            "baidu.com": "Baidu",
            "huawei.com": "Huawei",
        }
        for domain_key, inst_name in domain_institution_map.items():
            if domain_key in domain:
                return inst_name
        return None

    def _extract_research_areas(self, text: str) -> list[str]:
        """Infer research areas from keyword matches in text."""
        keyword_to_area = {
            # English keywords
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
            "multimodal": "multimodal_learning",
            "autonomous driving": "autonomous_driving",
            "chip design": "chip_design",
            "neural architecture": "neural_architecture_search",
            "federated learning": "federated_learning",
            "diffusion model": "diffusion_models",
            "transformer": "transformers",
            "vision transformer": "vision_transformers",
            # Chinese keywords
            "机器学习": "machine_learning",
            "深度学习": "deep_learning",
            "自然语言处理": "natural_language_processing",
            "计算机视觉": "computer_vision",
            "强化学习": "reinforcement_learning",
            "大语言模型": "large_language_models",
            "生成模型": "generative_models",
            "图神经网络": "graph_neural_networks",
            "机器人": "robotics",
            "人机交互": "human_computer_interaction",
            "安全": "security_privacy",
            "系统": "systems",
            "编程语言": "programming_languages",
            "数据库": "databases",
            "计算机图形学": "computer_graphics",
            "生物信息学": "bioinformatics",
            "量子计算": "quantum_computing",
            "数据挖掘": "data_mining",
            "信息检索": "information_retrieval",
            "语音": "speech_processing",
            "多模态": "multimodal_learning",
            "自动驾驶": "autonomous_driving",
            "芯片设计": "chip_design",
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
