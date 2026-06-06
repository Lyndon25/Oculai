-- 008_seed.sql
-- Test seed data for Oculai multi-Agent development.

-- ============================================================
-- Seed Persons
-- ============================================================
INSERT INTO Person (person_id, canonical_name, aliases, orcid, google_scholar_id, latest_institution,
    latest_position, total_papers, h_index, total_citations, last_active_date,
    pool_tags, watch_level, freshness_score, confidence_score, created_by_agent, updated_by_agent)
VALUES
(
    'a0000000-0000-0000-0000-000000000001', 'Yann LeCun',
    ARRAY['Y. LeCun','Yann Andre LeCun'], NULL, 'scholar:lecun123',
    'New York University', 'Professor', 250, 85, 250000, '2026-05-01',
    ARRAY['rising_star_core'], 'high', 0.95, 0.98,
    'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000002', 'Jane Smith',
    ARRAY['J. Smith'], '0000-0002-0000-0002', NULL,
    'Stanford University', 'Postdoc', 45, 22, 3500, '2026-04-15',
    ARRAY['rising_star'], 'high', 0.85, 0.90,
    'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000003', 'John Doe',
    ARRAY['J. Doe','Johnathan Doe'], '0000-0003-0000-0003', 'scholar:jdoe456',
    'Google Research', 'Senior Researcher', 80, 40, 12000, '2026-05-10',
    ARRAY['core','active'], 'medium', 0.90, 0.95,
    'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000004', 'Li Wei',
    ARRAY['W. Li'], '0000-0004-0000-0004', 'scholar:liwei789',
    'Tsinghua University', 'Associate Professor', 120, 35, 8000, '2026-03-20',
    ARRAY['active'], 'medium', 0.70, 0.85,
    'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000005', 'Emily Chen',
    ARRAY['E. Chen','Em Chen'], '0000-0005-0000-0005', NULL,
    'MIT', 'PhD Student', 10, 8, 450, '2026-05-20',
    ARRAY['rising_star'], 'high', 0.99, 0.70,
    'seed_script', 'seed_script'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed Person Profiles
-- ============================================================
INSERT INTO PersonProfile (person_id, version, source_agent, raw_data_hash, institution, career_stage, mobility_score, created_by_agent, updated_by_agent)
VALUES
(
    'a0000000-0000-0000-0000-000000000001', 1, 'sourcing-agent-1', 'sha256:abc123def',
    '{"name": "New York University", "department": "Computer Science", "location": "New York, NY"}'::jsonb,
    'senior', 0.1, 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000002', 1, 'sourcing-agent-1', 'sha256:def456ghi',
    '{"name": "Stanford University", "department": "Computer Science", "location": "Stanford, CA"}'::jsonb,
    'postdoc', 0.7, 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000003', 1, 'sourcing-agent-2', 'sha256:ghi789jkl',
    '{"name": "Google Research", "department": "NLP Group", "location": "Mountain View, CA"}'::jsonb,
    'senior', 0.3, 'seed_script', 'seed_script'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed Academic Works
-- ============================================================
INSERT INTO AcademicWork (person_id, type, title, venue, year, citations, doi, source_db, created_by_agent, updated_by_agent)
VALUES
(
    'a0000000-0000-0000-0000-000000000001', 'paper',
    'Deep Learning', 'Nature', 2015, 50000,
    '10.1038/nature14539', 'google_scholar', 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000001', 'paper',
    'Gradient-Based Learning Applied to Document Recognition', 'Proceedings of the IEEE', 1998, 35000,
    '10.1109/5.726791', 'dblp', 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000002', 'paper',
    'Advances in LLM Inference Optimization', 'ACL', 2025, 120,
    '10.18653/v1/2025.acl.123', 'acl_anthology', 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000003', 'paper',
    'Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks', 'NeurIPS', 2024, 850,
    '10.5555/neurips2024.rag', 'neurips_proceedings', 'seed_script', 'seed_script'
),
(
    'a0000000-0000-0000-0000-000000000005', 'preprint',
    'Efficient Transformer Architectures for Long-Context Inference', 'arXiv', 2026, 5,
    '10.48550/arxiv.2601.01234', 'arxiv', 'seed_script', 'seed_script'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed SourcingRun
-- ============================================================
INSERT INTO SourcingRun (run_id, title, status, created_by, target_profile, target_keywords, target_domains, config)
VALUES
(
    'b0000000-0000-0000-0000-000000000001',
    'NLP推理优化研究员招聘 - AI芯片公司',
    'running',
    'hr-admin-1',
    '{"title": "Senior Researcher - NLP Inference Optimization", "min_h_index": 15, "required_skills": ["LLM", "inference optimization", "PyTorch"], "location": "Shanghai"}'::jsonb,
    ARRAY['NLP', 'inference optimization', 'transformer', 'LLM'],
    ARRAY['cs.AI', 'cs.CL', 'cs.LG'],
    '{"data_sources": ["semantic_scholar", "arxiv", "dblp", "github"], "max_concurrency": 10, "reviewers": ["hr-admin-1", "hiring-manager-2"]}'::jsonb
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed Plan
-- ============================================================
INSERT INTO Plan (plan_id, run_id, planner_state_json, status, strategy_summary, created_by_agent, updated_by_agent)
VALUES
(
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    '{"strategy": "multi_source_parallel", "sources": ["arxiv", "semantic_scholar", "dblp", "github"]}'::jsonb,
    'active',
    'Search for NLP inference optimization researchers across academic and code sources, then evaluate and shortlist.',
    'claude-code::main-agent', 'claude-code::main-agent'
)
ON CONFLICT DO NOTHING;

-- Set active plan on the run
UPDATE SourcingRun SET active_plan_id = 'c0000000-0000-0000-0000-000000000001'
WHERE run_id = 'b0000000-0000-0000-0000-000000000001';

-- ============================================================
-- Seed CandidateRecords
-- ============================================================
INSERT INTO CandidateRecord (run_id, person_id, status, quality_score, created_by_agent, updated_by_agent)
VALUES
(
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000002',
    'pending', 85,
    'seed_script', 'seed_script'
),
(
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000003',
    'pending', 92,
    'seed_script', 'seed_script'
),
(
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000005',
    'pending', 78,
    'seed_script', 'seed_script'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed Tasks (DAG)
-- ============================================================
INSERT INTO Task (task_id, plan_id, run_id, task_type, task_name, step_key, status, priority, input_data, created_by_agent, updated_by_agent)
VALUES
(
    'd0000000-0000-0000-0000-000000000001',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'search_strategy',
    'Generate search strategy from JD',
    'strategy',
    'pending', 10,
    '{"job_title": "NLP推理优化研究员", "required_skills": ["LLM", "inference optimization", "PyTorch"]}'::jsonb,
    'seed_script', 'seed_script'
),
(
    'd0000000-0000-0000-0000-000000000002',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'search',
    'Search arXiv for candidates',
    'search_arxiv',
    'pending', 9,
    '{"source": "arxiv", "query": "$strategy.source_queries.arxiv"}'::jsonb,
    'seed_script', 'seed_script'
),
(
    'd0000000-0000-0000-0000-000000000003',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'search',
    'Search Semantic Scholar for candidates',
    'search_s2',
    'pending', 9,
    '{"source": "semantic_scholar", "query": "$strategy.source_queries.semantic_scholar"}'::jsonb,
    'seed_script', 'seed_script'
),
(
    'd0000000-0000-0000-0000-000000000004',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'search',
    'Search GitHub for candidates',
    'search_github',
    'pending', 8,
    '{"source": "github", "query": "$strategy.source_queries.github"}'::jsonb,
    'seed_script', 'seed_script'
),
(
    'd0000000-0000-0000-0000-000000000005',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'identity_resolution',
    'Resolve identities and merge duplicates',
    'identity',
    'pending', 7,
    '{"candidate_ids": "$search_arxiv.candidates", "merge_with": ["$search_s2", "$search_github"]}'::jsonb,
    'seed_script', 'seed_script'
),
(
    'd0000000-0000-0000-0000-000000000006',
    'c0000000-0000-0000-0000-000000000001',
    'b0000000-0000-0000-0000-000000000001',
    'evaluate',
    'Evaluate and score shortlisted candidates',
    'evaluate',
    'pending', 5,
    '{"candidate_ids": "$identity.resolved_candidates"}'::jsonb,
    'seed_script', 'seed_script'
)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed Task Dependencies
-- ============================================================
INSERT INTO TaskDependency (plan_id, task_id, depends_on_task_id, input_mapping)
VALUES
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000002', 'd0000000-0000-0000-0000-000000000001',
    '{"query": "$strategy.source_queries.arxiv"}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000003', 'd0000000-0000-0000-0000-000000000001',
    '{"query": "$strategy.source_queries.semantic_scholar"}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000004', 'd0000000-0000-0000-0000-000000000001',
    '{"query": "$strategy.source_queries.github"}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000002', '{}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000003', '{}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000005', 'd0000000-0000-0000-0000-000000000004', '{}'::jsonb),
('c0000000-0000-0000-0000-000000000001', 'd0000000-0000-0000-0000-000000000006', 'd0000000-0000-0000-0000-000000000005', '{}'::jsonb)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Seed DataSourceQuota
-- ============================================================
INSERT INTO DataSourceQuota (source_name, daily_limit, used_today)
VALUES
    ('semantic_scholar', 5000, 0),
    ('arxiv', 10000, 0),
    ('dblp', 10000, 0),
    ('github', 3000, 0),
    ('openalex', 10000, 0)
ON CONFLICT DO NOTHING;
