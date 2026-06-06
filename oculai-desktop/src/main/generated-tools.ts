// AUTO-GENERATED from tools_schema.json. DO NOT EDIT.
// Regenerate: python scripts/generate_pi_tools.py

export const OCULAI_TOOLS: Record<
  string,
  { description: string; parameters: Record<string, unknown> }
> = {

  // Evidence Tools
  oculai_attach_evidence: {
    description: "Attach a piece of evidence to a candidate.",
    parameters: {
      type: "object",
      properties: {
        person_id: { type: "string" },
        evidence_type: { type: "string" },
        title: { type: "string" },
        source_name: { type: "string" },
        source_url: { type: "string" },
        description: { type: "string" },
        content: { type: "string" },
        confidence: { type: "number" },
        run_id: { type: "string" },
        captured_by_agent: { type: "string" },
        metadata: { type: "string" }
      },
      required: ["person_id", "evidence_type", "title", "source_name"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_capture_page_evidence: {
    description: "Capture evidence from a web page (text content and/or screenshot).",
    parameters: {
      type: "object",
      properties: {
        url: { type: "string" },
        person_id: { type: "string" },
        run_id: { type: "string" },
        mode: { type: "string" },
        captured_by_agent: { type: "string" },
        selector: { type: "string" }
      },
      required: ["url"],
    },
  },
  // Web Search, Outreach & Browser
  oculai_check_approval_status: {
    description: "Check the status of a human approval request.",
    parameters: {
      type: "object",
      properties: {
        approval_id: { type: "string" }
      },
      required: ["approval_id"],
    },
  },

  // Run Lifecycle
  oculai_checkpoint_plan: {
    description: "Write a Plan + Task DAG to the database.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        plan_json: { type: "string" },
        strategy_summary: { type: "string" }
      },
      required: ["run_id", "plan_json"],
    },
  },

  // Source Tools
  oculai_crawl_site: {
    description: "Crawl a website starting from a URL to discover deep candidate evidence.",
    parameters: {
      type: "object",
      properties: {
        start_url: { type: "string" },
        max_pages: { type: "integer" },
        max_depth: { type: "integer" },
        same_domain_only: { type: "boolean" },
        run_id: { type: "string" }
      },
      required: ["start_url"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_create_outreach_draft: {
    description: "Create an outreach draft for a candidate. DOES NOT SEND.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_id: { type: "string" },
        strategy: { type: "string" },
        template: { type: "string" },
        channel: { type: "string" },
        draft_content: { type: "string" },
        subject: { type: "string" },
        agent_id: { type: "string" }
      },
      required: ["run_id", "person_id", "strategy"],
    },
  },

  // Run Lifecycle
  oculai_create_run: {
    description: "Create a new talent sourcing run.",
    parameters: {
      type: "object",
      properties: {
        job_title: { type: "string" },
        jd_text: { type: "string" },
        required_skills: { type: "string" },
        target_domains: { type: "string" },
        config: { type: "string" }
      },
      required: ["job_title", "jd_text"],
    },
  },

  // Source Tools
  oculai_deep_search: {
    description: "Execute deep iterative search across hypotheses and sources.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        hypotheses: { type: "string" },
        config: { type: "string" }
      },
      required: ["run_id", "hypotheses"],
    },
  },

  // Review Orchestrator
  oculai_export_report: {
    description: "Export a sourcing run report in HTML (default) or Markdown format.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        format: { type: "string" }
      },
      required: ["run_id"],
    },
  },

  // Source Tools
  oculai_fetch_source_detail: {
    description: "Fetch detailed information for a single candidate from a source.",
    parameters: {
      type: "object",
      properties: {
        source_name: { type: "string" },
        external_id: { type: "string" }
      },
      required: ["source_name", "external_id"],
    },
  },

  // Candidate Tools
  oculai_get_candidate: {
    description: "Get full candidate profile: person, identities, publications, career, evidence, assessments.",
    parameters: {
      type: "object",
      properties: {
        person_id: { type: "string" }
      },
      required: ["person_id"],
    },
  },

  // Evidence Tools
  oculai_get_evidence: {
    description: "Get all evidence for a candidate, optionally filtered by type.",
    parameters: {
      type: "object",
      properties: {
        person_id: { type: "string" },
        evidence_type: { type: "string" },
        limit: { type: "integer" },
        min_tier: { type: "integer" }
      },
      required: ["person_id"],
    },
  },

  // Assessment Tools
  oculai_get_evidence_by_tier: {
    description: "Get evidence up to a given quality tier.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_id: { type: "string" },
        max_tier: { type: "integer" }
      },
      required: ["run_id", "person_id"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_get_outreach_history: {
    description: "Get outreach history for a candidate.",
    parameters: {
      type: "object",
      properties: {
        person_id: { type: "string" },
        limit: { type: "integer" }
      },
      required: ["person_id"],
    },
  },

  // Run Lifecycle
  oculai_get_run_state: {
    description: "Get the current state of a sourcing run.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" }
      },
      required: ["run_id"],
    },
  },

  // Assessment Tools
  oculai_get_score_history: {
    description: "Get score change history for auditing.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_id: { type: "string" },
        dimension: { type: "string" },
        limit: { type: "integer" }
      },
      required: ["run_id"],
    },
  },

  // Source Tools
  oculai_get_search_progress: {
    description: "Get current deep search progress for a run.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" }
      },
      required: ["run_id"],
    },
  },

  // Assessment Tools
  oculai_get_shortlist: {
    description: "Get shortlisted candidates ranked by overall quality score.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        min_score: { type: "number" },
        limit: { type: "integer" }
      },
      required: ["run_id"],
    },
  },

  // Candidate Tools
  oculai_link_identity: {
    description: "Link an external identity (ORCID, Google Scholar, etc.) to a Person.",
    parameters: {
      type: "object",
      properties: {
        person_id: { type: "string" },
        source_type: { type: "string" },
        external_id: { type: "string" },
        external_url: { type: "string" },
        confidence: { type: "number" },
        verified_by_agent: { type: "string" }
      },
      required: ["person_id", "source_type", "external_id"],
    },
  },
  // Candidate Tools
  oculai_list_candidates: {
    description: "List candidates in a sourcing run with basic person info.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        status: { type: "string" },
        limit: { type: "integer" },
        offset: { type: "integer" }
      },
      required: ["run_id"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_list_pending_approvals: {
    description: "List all pending human approval requests.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" }
      },
    },
  },

  // Source Tools
  oculai_list_source_capabilities: {
    description: "List all registered data sources and their capabilities.",
    parameters: {
      type: "object",
      properties: {
      },
    },
  },

  // Assessment Tools
  oculai_record_assessment: {
    description: "Record a single dimension assessment for a candidate.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_id: { type: "string" },
        assessor_agent: { type: "string" },
        dimension: { type: "string" },
        score: { type: "number" },
        confidence: { type: "number" },
        rationale: { type: "string" },
        evidence_ids: { type: "string" },
        role_type: { type: "string" }
      },
      required: ["run_id", "person_id", "assessor_agent", "dimension", "score"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_request_human_approval: {
    description: "Request human approval for an action with external side effects.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        action_type: { type: "string" },
        action_context: { type: "string" },
        draft_content: { type: "string" },
        agent_id: { type: "string" }
      },
      required: ["run_id", "action_type", "action_context"],
    },
  },

  // Assessment Tools
  oculai_score_candidate: {
    description: "Score a candidate across multiple dimensions simultaneously.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_id: { type: "string" },
        dimensions: { type: "string" },
        assessor_agent: { type: "string" },
        evidence_ids: { type: "string" },
        confidence: { type: "number" },
        rationale: { type: "string" },
        role_type: { type: "string" }
      },
      required: ["run_id", "person_id", "dimensions", "assessor_agent"],
    },
  },

  // Source Tools
  oculai_search_source: {
    description: "Search a specific data source and return structured candidates.",
    parameters: {
      type: "object",
      properties: {
        source_name: { type: "string" },
        keywords: { type: "string" },
        run_id: { type: "string" },
        source_specific_query: { type: "string" },
        limit: { type: "integer" },
        offset: { type: "integer" }
      },
      required: ["source_name", "keywords"],
    },
  },

  // Web Search, Outreach & Browser
  oculai_search_web: {
    description: "Search the web for candidate-related content via Exa or Tavily.",
    parameters: {
      type: "object",
      properties: {
        keywords: { type: "string" },
        provider: { type: "string" },
        run_id: { type: "string" },
        limit: { type: "integer" },
        include_domains: { type: "string" },
        exclude_domains: { type: "string" }
      },
      required: ["keywords"],
    },
  },

  // Candidate Tools
  oculai_upsert_candidate: {
    description: "Idempotent candidate upsert with identity resolution.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        person_data: { type: "string" },
        source_name: { type: "string" },
        agent_id: { type: "string" }
      },
      required: ["run_id", "person_data"],
    },
  },
  // Candidate Tools
  oculai_upsert_candidates_batch: {
    description: "Batch upsert multiple candidates in a single DB transaction.",
    parameters: {
      type: "object",
      properties: {
        run_id: { type: "string" },
        candidates_list: { type: "string" },
        source_name: { type: "string" },
        agent_id: { type: "string" }
      },
      required: ["run_id", "candidates_list"],
    },
  }
};

