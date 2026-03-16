"""
Prompts for RPA output generation tools.

Contains all LLM prompts for step decomposition and timeline generation.
Never inline prompts in tool code — use this centralized module.
"""

# ===========================================================================
# STEP DECOMPOSITION PROMPTS
# ===========================================================================

STEP_DECOMPOSITION_SYSTEM = """
You are an expert RPA developer and solution architect
generating a detailed process step decomposition for an
automation project.

You assign development effort weights to each step using
this EXACT scale from the RPA delivery methodology:

Weight 0.0 — FULL reusability:
  Step is identical to one in another automation and can be
  reused with zero modification. Examples: "Upload CSV file",
  "Activate object", "Update processing status"

Weight 0.5 — PARTIAL reusability:
  Step exists elsewhere but needs minor modification.
  Examples: "Go to t-code ZDIASMDIA, find object" (same
  navigation, different object), "Read upload status"

Weight 1.0 — Standard NEW step:
  New step requiring typical development effort.
  Examples: "Search for modification request in template",
  "Verify approver hierarchical layer"

Weight 2.0 — COMPLEX step:
  High-effort step with multi-path logic, complex parameters,
  or significant conditional handling.
  Examples: "Enter mass change t-code with various parameters",
  "Update signatories CSV file" (4 different action types)

You must respond with valid JSON only. No markdown, no
text outside the JSON.
"""

STEP_DECOMPOSITION_PROMPT = """
Generate a detailed step decomposition for this RPA process.

Process Information:
- Project: {project_name}
- RPA Platform: {rpa_tool}
- Complexity Tier: {tier}
- Activity Count: {activity_count}
- Business Rule Branches: {rule_count}

Process Sections:
{sections_text}

Business Rules Identified:
{rules_text}

Generate steps organised by branch. Each branch corresponds
to one business rule or the main process flow.

Return a JSON object with exactly this structure:
{{
  "branches": [
    {{
      "branch_name": "Main Flow",
      "description": "Steps common to all scenarios",
      "steps": [
        {{
          "step_number": 1,
          "description": "Clear description of what the bot does",
          "weight": 1.0,
          "reusability_tag": "NONE",
          "reusability_comment": "New step — no reusability"
        }}
      ]
    }},
    {{
      "branch_name": "Branch name matching business rule",
      "description": "When this branch executes",
      "steps": [...]
    }}
  ],
  "total_weighted_steps": <sum of all step weights>,
  "generation_notes": "any observations about the decomposition"
}}

Weight assignment rules:
- Use 0.0 only for steps truly identical to standard patterns
  (file upload, status update, activate)
- Use 0.5 for navigational steps reused across branches
- Use 1.0 for the majority of new business logic steps
- Use 2.0 only for genuinely complex multi-path operations
- total_weighted_steps must equal sum of all step weights

Reusability tags: "FULL" | "PARTIAL" | "NONE"
- FULL → weight must be 0.0
- PARTIAL → weight must be 0.5
- NONE → weight must be 1.0 or 2.0
"""

STEP_DECOMPOSITION_RETRY_PROMPT = """
Return ONLY this minimal JSON:
{{
  "branches": [
    {{
      "branch_name": "Main Process Flow",
      "description": "Primary automation steps",
      "steps": [
        {{
          "step_number": 1,
          "description": "Process execution step",
          "weight": 1.0,
          "reusability_tag": "NONE",
          "reusability_comment": "Standard step"
        }}
      ]
    }}
  ],
  "total_weighted_steps": 1.0,
  "generation_notes": "Minimal fallback decomposition"
}}
"""
