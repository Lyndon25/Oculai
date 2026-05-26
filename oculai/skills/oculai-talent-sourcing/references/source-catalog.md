# Source Catalog

## Academic Sources

### arXiv
- **Type**: API (OAI-PMH)
- **Coverage**: Preprints — CS, math, physics, statistics
- **Strengths**: Latest research, all CS subfields, open access
- **Limitations**: Not peer-reviewed, no citation data
- **Rate Limit**: 1 req/s (polite crawling)
- **Tools**: `oculai_search_source(source="arxiv", ...)`, `oculai_fetch_source_detail(source="arxiv", external_id=...)`

### Semantic Scholar
- **Type**: REST API (requires API key)
- **Coverage**: 200M+ papers across all disciplines
- **Strengths**: Author h-index, citation counts, ORCID linking, venue filtering
- **Limitations**: API key required, 100 req/5min
- **Tools**: `oculai_search_source(source="semantic_scholar", ...)`, `oculai_fetch_source_detail(source="semantic_scholar", external_id=...)`

### OpenAlex
- **Type**: REST API (free, polite email required)
- **Coverage**: 270M+ publications — papers, authors, institutions, topics
- **Strengths**: Complete entity graph, proceedings-article type for conference papers, institution normalization
- **Limitations**: Large result sets need pagination
- **Tools**: `oculai_search_source(source="openalex", ...)`, `oculai_fetch_source_detail(source="openalex", external_id=...)`

### DBLP
- **Type**: REST API (free, no key)
- **Coverage**: CS bibliography — authors, publications, venues, conferences
- **Strengths**: Most precise CS author-publication mapping, homepage URLs, ORCID links
- **Limitations**: No abstracts, no citation data
- **Tools**: `oculai_search_source(source="dblp", ...)`, `oculai_fetch_source_detail(source="dblp", external_id=...)`

## Technical Sources

### GitHub
- **Type**: REST API (token recommended)
- **Coverage**: Repositories, users, contributions, organizations
- **Strengths**: Code as direct evidence of engineering skill, contribution history, tech stack identification
- **Limitations**: 5000 req/h (authenticated), 60 req/h (unauthenticated)
- **Tools**: `oculai_search_source(source="github", ...)`, `oculai_fetch_source_detail(source="github", external_id=...)`

## Chinese Sources

### Baidu Search (百度搜索)
- **Type**: Official Baidu AI Search API (BDSE)
- **Coverage**: Chinese web — personal homepages, blogs, news, social media
- **Strengths**: Chinese language coverage unmatched by Exa/Tavily, freshness filtering
- **Limitations**: Requires Baidu Qianfan API key
- **Tools**: `oculai_search_source("baidu", keywords, ...)`

### Baidu Scholar (百度学术)
- **Type**: Official Baidu Scholar API
- **Coverage**: Chinese and English academic papers, journals, conference proceedings
- **Strengths**: Chinese academic papers not indexed by Semantic Scholar/OpenAlex
- **Limitations**: Less metadata than Western academic APIs
- **Tools**: `oculai_search_source("baidu_scholar", keywords, ...)`

## Conference Paper Sources (P1)

### ACM Digital Library
- **Status**: Fully Open Access since Jan 2026
- **Coverage**: 600K+ CS papers, all conference proceedings
- **Strengths**: Highest-quality CS conference papers, DOI access
- **Tools**: Source connector (planned M5)

### OpenReview
- **Coverage**: ICLR, NeurIPS, ICML, etc. — submissions and reviews
- **Strengths**: Active submitters = active researchers; review content = peer evaluation
- **Tools**: Source connector (planned M5)

## Web / Homepage Sources

### Personal Homepage Pipeline
- **Discovery**: DBLP, Semantic Scholar, GitHub API → extract homepage URL
- **Fetch**: Crawl4AI → Markdown → structured extraction
- **Content**: Papers, projects, collaborators, teaching, awards, latest research
- **Tools**: `oculai_capture_page_evidence(url, mode="text")` — P1

## Choosing Sources

Source selection is a strategic decision by the main Agent based on JD domain:

| JD Domain | Primary Sources | Secondary Sources |
|---|---|---|
| AI/ML Research | arXiv, Semantic Scholar, OpenAlex | DBLP, Baidu Scholar, GitHub |
| Systems/Engineering | GitHub, DBLP | Semantic Scholar, Baidu Search |
| Computer Vision | arXiv, Semantic Scholar, OpenAlex | GitHub, Baidu Scholar |
| NLP/LLM | arXiv, Semantic Scholar | GitHub, Baidu Scholar, OpenAlex |
| Chinese Tech | Baidu Scholar, Baidu Search | GitHub, DBLP |
| Cross-discipline | OpenAlex, Semantic Scholar | Baidu Scholar, Baidu Search |
