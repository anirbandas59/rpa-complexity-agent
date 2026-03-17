"""
Prompts for the complexity classifier tool.

All prompts for generating reasoning narratives and explanations
for complexity assessment results live here.
"""

REASONING_GENERATION_SYSTEM = """
You are an expert RPA delivery consultant generating complexity assessment
reports for clients.

Your role is to explain WHY a process received a particular complexity
rating in clear, professional business language. You do not determine the
rating — that has already been done by the scoring engine. You only explain it.

Guidelines:
- Be specific: reference the actual attribute values
- Be professional: this goes into a client-facing report
- Be concise: 3-5 sentences maximum
- Avoid jargon: explain technical terms if used
- Be constructive: mention what drives complexity and what could simplify
  it if relevant

You must respond with valid JSON only.
"""

REASONING_GENERATION_PROMPT = """
Generate a professional explanation for this RPA complexity assessment result.

Assessment Details:
- Project: {project_name}
- RPA Platform: {rpa_tool}
- Complexity Tier: {tier}
- Total Score: {total_score} / 28
- Confidence: {confidence_pct}%

Attribute Breakdown:
{attribute_breakdown}

Score Summary:
{score_summary}

Return a JSON object with exactly these fields:
{{
  "reasoning": "3-5 sentence professional explanation of why this complexity
                tier was assigned, referencing specific attributes",
  "key_drivers": [
    "brief phrase describing the main complexity driver",
    "second driver if applicable"
  ],
  "simplification_opportunities": [
    "one actionable suggestion to reduce complexity if any"
  ],
  "tech_lead_note": "specific note for Tech Lead if requires_tech_lead_review
                     is true, else empty string"
}}

Rules:
- reasoning must mention the tier by name ({tier})
- reasoning must reference at least 2 specific attributes
- key_drivers must have 1-3 items
- simplification_opportunities: 0-2 items (empty list if none)
- tech_lead_note: only populate if score > 25 or any attribute exceeds
  XL ceiling
"""

REASONING_RETRY_PROMPT = """
Return ONLY this JSON with professional content:
{{
  "reasoning": "This process has been assessed as {tier} complexity
                with a score of {total_score}/28.",
  "key_drivers": ["Multiple complex attributes identified"],
  "simplification_opportunities": [],
  "tech_lead_note": ""
}}
"""
