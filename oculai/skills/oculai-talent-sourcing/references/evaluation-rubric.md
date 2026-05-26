# Evaluation Rubric

## Dimensions

Each candidate is scored across up to 10 dimensions on a 0-10 scale:

| Dimension | Weight | What It Measures |
|---|---|---|
| Academic | High | Research output, venue quality, citation impact, h-index trajectory |
| Engineering | High | Code quality, project complexity, system design, open source contributions |
| Leadership | Medium | Team lead, mentorship, project ownership, community leadership |
| Communication | Medium | Writing clarity (papers/blogs/docs), talks, teaching, outreach |
| Culture Fit | Medium | Work style, values alignment, collaboration patterns |
| Skill Match | Critical | Specific skills required by JD (must-pass gate) |
| Location | Low | Geographic preference, relocation willingness |
| Career Stage | Medium | Seniority match, growth trajectory, readiness for role |
| Mobility | Low | Likelihood to move (new job signals, career transitions) |
| Overall | - | Weighted composite, adjusted for evidence quality |

## Scoring Guidelines

### 9-10: Exceptional
- World-leading expert in the specific area
- Multiple top-tier publications (Nature/Science/NeurIPS/ICML/ACL/etc.)
- h-index > 50 or rapidly growing h-index trajectory
- Major open source project creator or core maintainer
- Multiple independent evidence sources agree

### 7-8: Strong
- Established researcher/engineer with clear expertise in the area
- Regular publications at top venues
- h-index 20-50 or strong upward trend
- Significant open source contributions
- Evidence from 2+ independent sources

### 5-6: Adequate
- Competent in the area with demonstrable experience
- Some publications or equivalent industry experience
- h-index 10-20
- Some open source activity
- Single source evidence (needs verification)

### 3-4: Marginal
- Adjacent expertise, would need significant ramp-up
- Few publications or peripheral involvement
- Low h-index (< 10)
- Limited public evidence

### 1-2: Poor Match
- Different domain entirely
- No relevant publications or experience
- No evidence of required skills

### 0: No Evidence
- Cannot evaluate — no data available

## Must-Pass Gates

Some dimensions are "must-pass" — if below threshold, candidate is filtered regardless of other scores:

- **Skill Match** < 4: Auto-filter (lacks core required skills)
- **Evidence Quality**: If >50% of scored dimensions have confidence < 0.5, flag as "low confidence — needs more evidence"

## Weight Adjustments by Role Type

### Research Scientist
- Academic: 35%, Engineering: 20%, Leadership: 10%, Communication: 15%, Culture: 10%, Skill: 10%

### ML Engineer
- Academic: 15%, Engineering: 40%, Leadership: 10%, Communication: 10%, Culture: 10%, Skill: 15%

### Tech Lead / Manager
- Academic: 10%, Engineering: 25%, Leadership: 30%, Communication: 15%, Culture: 10%, Skill: 10%

### PhD-level Researcher (Chinese Academy)
- Academic: 40%, Engineering: 10%, Leadership: 10%, Communication: 15%, Culture: 15%, Skill: 10%

## Evidence Quality Factors

When scoring confidence, consider:

1. **Source reliability**: Official API > curated database > web scraping > inference
2. **Recency**: Evidence < 2 years old is preferred
3. **Corroboration**: Multiple independent sources > single source
4. **Directness**: Direct evidence (paper authorship) > indirect (institutional affiliation)
5. **Verifiability**: Public URL > paywalled content > unverifiable claim

## Red Flags

Flag these for the Quality Auditor:
- h-index or citation count differs by >30% across sources
- Institution mismatch across sources (possible wrong identity merge)
- Career gap > 3 years with no explanation
- No recent activity (>2 years since last publication/commit)
- All evidence from a single source
- Candidate appears to be a different person with the same name (identity collision)
