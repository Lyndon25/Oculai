# Source Catalog

> **China-First Mandate**: Chinese sources are always primary. Western sources must target Chinese institutions/names.

## Chinese Sources (Tier 1 — Primary)

### Baidu Qianfan (百度千帆搜索)
- **Type**: Official Baidu AI Search API
- **Coverage**: Chinese web — personal homepages, blogs, news, company pages, tech forums
- **Chinese Talent Value**: Best coverage of Chinese web; indexes content from zhihu, juejin, csdn, company sites
- **Limitations**: Requires BAIDU_API_KEY (100 calls/day free)
- **Rate Limit**: Conservative (~2 req/s)
- **Query Strategy**: Chinese keywords + role titles + institution names; use site: operator for platform-specific searches
- **Tools**: `oculai_search_source(source="baidu_qianfan", ...)`

### Baidu Scholar (百度学术)
- **Type**: Official Baidu Scholar API
- **Coverage**: Chinese and English academic papers, journals, conference proceedings
- **Chinese Talent Value**: Covers Chinese academic papers not indexed by Semantic Scholar/OpenAlex
- **Limitations**: Less metadata than Western APIs; beta endpoint (may 404)
- **Rate Limit**: ~1 req/3s
- **Query Strategy**: Chinese academic keywords + researcher names; particularly valuable for Chinese university researchers
- **Tools**: `oculai_search_source(source="baidu_scholar", ...)`

### Zhihu (知乎)
- **Type**: Public API (zhihu.com/api/v4)
- **Coverage**: Chinese Q&A platform — professional profiles, education, employment, topic expertise
- **Chinese Talent Value**: High-quality professional profiles with verified employment history; Q&A activity demonstrates expertise depth
- **Limitations**: Rate-limited; may require browser User-Agent header; no API key needed
- **Query Strategy**: Chinese role title + skill keywords ("大模型 算法工程师", "计算机视觉 研究员"), cross-reference names from other sources
- **Tools**: `oculai_search_source(source="zhihu", ...)`, `oculai_fetch_source_detail(source="zhihu", external_id=...)`

### Juejin (掘金)
- **Type**: Public API (api.juejin.cn)
- **Coverage**: Chinese developer community — user profiles, job titles, companies, tech tags
- **Chinese Talent Value**: Direct access to Chinese developers with tech stack tags, company info, article activity
- **Limitations**: Limited search pagination; text content only
- **Query Strategy**: Tech stack + job title Chinese keywords ("大模型工程师", "前端架构师 字节跳动")
- **Tools**: `oculai_search_source(source="juejin", ...)`, `oculai_fetch_source_detail(source="juejin", external_id=...)`

### CSDN (中国开发者网络)
- **Type**: Search API + HTML scraping
- **Coverage**: Largest Chinese technical blog platform — active Chinese developers
- **Chinese Talent Value**: Technical bloggers demonstrating hands-on skills; long-form content reveals depth
- **Limitations**: Unofficial scraping; ~1 req/2s to avoid blocks
- **Query Strategy**: Technical implementation keywords ("大模型 实战", "架构设计 微服务"), extract usernames from blog results
- **Tools**: `oculai_search_source(source="csdn", ...)`, `oculai_fetch_source_detail(source="csdn", external_id=...)`

### Baidu Search (百度搜索 — unofficial)
- **Type**: baidusearch PyPI package (pip install baidusearch)
- **Coverage**: General Chinese web
- **Chinese Talent Value**: Supplementary discovery for content not captured by Qianfan API
- **Limitations**: Unofficial scraper, IP ban risk if used aggressively
- **Tools**: `oculai_search_source(source="baidu", ...)`

## Academic Sources (Tier 3 — With China Filters)

### arXiv
- **Type**: API (OAI-PMH)
- **Coverage**: Preprints — CS, math, physics, statistics
- **Chinese Talent Value**: Must target Chinese institutions (Tsinghua, PKU, SJTU, CAS, etc.) or Chinese co-author names
- **Limitations**: Not peer-reviewed, no citation data
- **Rate Limit**: 1 req/s
- **Query Strategy**: Technical terms paired with Chinese institution names; use author affiliation filter where available
- **Tools**: `oculai_search_source(source="arxiv", ...)`, `oculai_fetch_source_detail(source="arxiv", external_id=...)`

### Semantic Scholar
- **Type**: REST API (recommend API key)
- **Coverage**: 200M+ papers across all disciplines
- **Chinese Talent Value**: Author h-index, citation counts, ORCID linking; must filter by Chinese author affiliation or name
- **Limitations**: API key recommended, 100 req/5min
- **Query Strategy**: Author name patterns (Chinese surnames + given names) filtered by institution country
- **Tools**: `oculai_search_source(source="semantic_scholar", ...)`, `oculai_fetch_source_detail(source="semantic_scholar", external_id=...)`

### OpenAlex
- **Type**: REST API (free, polite email required)
- **Coverage**: 270M+ publications — papers, authors, institutions, topics
- **Chinese Talent Value**: Best institution normalization; can filter by Chinese institution ROR ID
- **Limitations**: Large result sets need pagination
- **Tools**: `oculai_search_source(source="openalex", ...)`, `oculai_fetch_source_detail(source="openalex", external_id=...)`

### DBLP
- **Type**: REST API (free, no key)
- **Coverage**: CS bibliography — authors, publications, venues, conferences
- **Chinese Talent Value**: Precise CS author-publication mapping; homepage URLs for Chinese researchers
- **Tools**: `oculai_search_source(source="dblp", ...)`, `oculai_fetch_source_detail(source="dblp", external_id=...)`

### Conference Source
- **Type**: API
- **Coverage**: Conference proceedings, author lists
- **Tools**: `oculai_search_source(source="conference", ...)`

## Technical Sources (Tier 2-3)

### GitHub
- **Type**: REST API (token recommended)
- **Coverage**: Repositories, users, contributions, organizations
- **Chinese Talent Value**: Filter by Chinese institutions, Chinese tech companies (Alibaba, Tencent, ByteDance, Meituan, etc.), or Chinese location in profile
- **Limitations**: 5000 req/h (authenticated), 60 req/h (unauthenticated)
- **Query Strategy**: Tech stack + Chinese company names; use location:China in user search; look for .edu.cn emails in commit history
- **Tools**: `oculai_search_source(source="github", ...)`, `oculai_fetch_source_detail(source="github", external_id=...)`

### Personal Homepage
- **Type**: HTML scraping
- **Coverage**: Personal homepages, limited to university-domain pages
- **Chinese Talent Value**: Important for Chinese academic candidates; .edu.cn and .edu.hk domains
- **Tools**: `oculai_capture_page_evidence(url, mode="text")`

### Industry Source
- **Type**: GitHub-based industry search
- **Coverage**: Company-affiliated developers on GitHub
- **Chinese Talent Value**: Filter to Chinese tech companies (Alibaba, Tencent, ByteDance, Baidu, Huawei, Meituan, Xiaomi, etc.)
- **Tools**: `oculai_search_source(source="industry", ...)`

## Choosing Sources — China-First Selection

Source selection for Chinese talent discovery:

| Role Category | Primary Sources (Tier 1) | Secondary Sources (Tier 2-3) |
|---|---|---|
| AI/ML Researcher (China) | baidu_scholar, baidu_qianfan, zhihu | arXiv (China-filtered), Semantic Scholar (China-filtered), OpenAlex |
| Engineer/Developer (China) | juejin, csdn, zhihu, baidu_qianfan | GitHub (China-filtered), personal_homepage |
| Academic Researcher (China) | baidu_scholar, zhihu, baidu_qianfan | Semantic Scholar, dblp, OpenAlex, arXiv |
| Tech Lead/Manager (China) | zhihu, baidu_qianfan, juejin | GitHub, industry (China companies) |
| Cross-Domain Talent | baidu_qianfan, zhihu, baidu_scholar | OpenAlex, Semantic Scholar |
| **Discovery from JD keywords** | baidu_qianfan, baidu_scholar, zhihu, juejin | All other sources with China filters |

### Source Priority Order

For a typical tech role search (China-first):

```
1st batch: baidu_qianfan + baidu_scholar + zhihu     (broad Chinese discovery)
2nd batch: juejin + csdn + baidu_search               (developer community discovery)
3rd batch: github + personal_homepage                 (code + academic homepage, China-filtered)
4th batch: semantic_scholar + openalex + dblp + arxiv  (academic, China-filtered)
```

Adjust batches based on role type. AI/ML academic roles move academic sources earlier. Engineering roles move juejin/csdn earlier.
