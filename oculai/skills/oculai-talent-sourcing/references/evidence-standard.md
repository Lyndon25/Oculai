# Evidence Standard

## Evidence Hierarchy

Evidence is ranked by reliability and directness:

### Tier 1: Direct, Verifiable, Multi-Source
- Peer-reviewed publication with DOI and author list matching candidate identity
- GitHub commit history under verified account
- Patent with inventor name matching candidate
- Official institutional profile page confirming position
- ORCID profile linking to publications

### Tier 2: Direct, Single-Verified Source
- Single academic database entry (Semantic Scholar, DBLP, etc.)
- Conference talk video/slides with candidate as speaker
- Technical blog post on verified personal domain
- Award/certification listing on official institution site

### Tier 3: Indirect or Inferred
- Co-author network suggesting collaboration (not direct evidence of expertise)
- Institutional affiliation implying expertise area
- Location data suggesting availability
- Self-reported skills on professional profile

### Tier 4: Unverified
- Social media content without identity verification
- Third-party mentions or news articles
- Inferred from name similarity (possible identity collision)
- LLM-extracted claims without URL verification

## Required Evidence by Claim Type

### Technical Expertise
- **Required**: Paper(s) on the topic, OR code repository demonstrating the skill, OR patent
- **Supporting**: Conference talks, blog posts, course teaching
- **Minimum**: 1 Tier 1 or 2 evidence items

### Academic Impact
- **Required**: Citation count from Semantic Scholar or OpenAlex, h-index
- **Supporting**: Venue rankings, award listings
- **Minimum**: h-index from 2 sources OR 1 source + DOI list

### Career History
- **Required**: Career timeline with institution + dates from at least 2 sources
- **Supporting**: LinkedIn, personal webpage, institutional pages
- **Minimum**: Current position verified

### Engineering Skill
- **Required**: GitHub repositories with substantive commits, OR technical blog with code
- **Supporting**: Stack Overflow, open source contributions, technical talks
- **Minimum**: 1 repository with >10 commits in relevant technology

### Communication Ability
- **Required**: Published paper (writing sample), OR talk recording, OR technical blog
- **Supporting**: Teaching evaluations, community engagement
- **Minimum**: 1 writing sample (paper or blog)

## Evidence Attachment Format

When using `oculai_attach_evidence`:

```json
{
  "person_id": "uuid",
  "evidence_type": "paper",
  "title": "Descriptive title",
  "description": "What this evidence demonstrates",
  "source_url": "https://doi.org/...",
  "source_name": "semantic_scholar",
  "confidence": 0.95,
  "content": {
    "venue": "NeurIPS 2025",
    "year": 2025,
    "citations": 120,
    "relevance": "Directly demonstrates expertise in LLM inference optimization"
  }
}
```

## Evidence Gaps

When evidence is missing for a claim, explicitly note:
- What claim is unverified
- What evidence would verify it
- Whether the gap is acceptable (non-critical) or blocking (critical skill unverified)
