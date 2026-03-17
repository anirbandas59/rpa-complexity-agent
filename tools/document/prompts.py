"""Prompts for document intelligence tools.

All LLM prompts are defined here as string constants.
Never inline prompts in tool functions.
"""

SECTION_IDENTIFICATION_SYSTEM = """
You are an expert RPA (Robotic Process Automation) business
analyst. You specialise in analysing Process Design Documents
(PDDs) to extract structured information for complexity
assessment.

Your task is to identify the key sections in a PDD document.
You must respond with valid JSON only. Do not include markdown
code blocks, explanations, or any text outside the JSON object.
"""

SECTION_IDENTIFICATION_PROMPT = """
Analyse the following document text and identify its sections.

For each section found, provide:
- title: the section heading or best descriptive title
- section_type: one of these exact values:
    "process_overview"  - describes what the process does
    "process_steps"     - lists the automation steps
    "business_rules"    - decision points and conditions
    "applications"      - target systems and interfaces
    "exceptions"        - error handling and edge cases
    "inputs_outputs"    - layouts, templates, files used
    "general"           - anything that doesn't fit above
- content: the full text content of that section
- confidence_score: float 0.0-1.0 indicating how confident
  you are this is a real section boundary
- page_number: null (DOCX has no pages) or integer if
  "--- Page N ---" markers are present in the text

Return a JSON object with a single key "sections" containing
an array of section objects.

Document text:
{document_text}
"""

SECTION_IDENTIFICATION_RETRY_PROMPT = """
Your previous response could not be parsed as valid JSON.
Please try again.

Analyse this document and return ONLY a JSON object with this
exact structure:
{{
  "sections": [
    {{
      "title": "section title",
      "section_type": "process_overview",
      "content": "section content text",
      "confidence_score": 0.9,
      "page_number": null
    }}
  ]
}}

Document text (first 2000 characters):
{document_text_truncated}
"""

ENTITY_EXTRACTION_SYSTEM = """
You are an expert RPA (Robotic Process Automation) business
analyst and solution architect. You specialise in extracting
structured information from Process Design Documents (PDDs)
to support complexity assessment.

You understand the following RPA platforms deeply:
Blue Prism, UiPath, Power Automate, Automation Anywhere (AA360).

Your task is to extract specific named entities from PDD
sections. You must respond with valid JSON only. Do not include
markdown code blocks or any text outside the JSON object.
"""

ENTITY_EXTRACTION_PROMPT = """
Extract named entities from the following PDD sections that
are relevant to RPA complexity assessment.

Return a JSON object with these exact keys:

{{
  "rpa_tool": "detected RPA platform or null if not mentioned",

  "applications": [
    {{
      "name": "application name",
      "type": "web|desktop|api|database|file_system|email",
      "notes": "any relevant notes about this application"
    }}
  ],

  "technologies": [
    {{
      "name": "technology name",
      "category": "surface_automation|api|scripting|connector|other",
      "notes": "how it is used in the process"
    }}
  ],

  "file_types": [
    "list of file extensions mentioned e.g. xlsx, pdf, csv"
  ],

  "sap_tcodes": [
    "list of SAP transaction codes if any e.g. SE16, VA01"
  ],

  "process_triggers": [
    {{
      "type": "scheduled|manual|event|api_call|email",
      "description": "how the process is triggered"
    }}
  ],

  "roles": [
    "list of business roles or personas mentioned"
  ],

  "confidence": {{
    "applications": 0.9,
    "technologies": 0.8,
    "overall": 0.85
  }}
}}

Rules:
- applications: list EVERY distinct system the bot interacts with
  (SAP and SAP ECC are the same — deduplicate)
- technologies: only include if it requires ADDITIONAL development
  effort (e.g. API integration, Citrix, VBA macros, Python scripts)
  Do NOT include the RPA tool itself as an additional technology
- file_types: only extensions, lowercase, no dots (xlsx not .xlsx)
- If a field has no relevant entities: return empty array []
- rpa_tool: return exactly one of: "Blue Prism", "UiPath",
  "Power Automate", "AA360", or null

PDD Sections:
{sections_text}
"""

ENTITY_EXTRACTION_RETRY_PROMPT = """
Your previous response could not be parsed. Please return
ONLY valid JSON with no other text.

Extract entities from this PDD text and return this structure:
{{
  "rpa_tool": null,
  "applications": [],
  "technologies": [],
  "file_types": [],
  "sap_tcodes": [],
  "process_triggers": [],
  "roles": [],
  "confidence": {{"applications": 0.5, "technologies": 0.5,
  "overall": 0.5}}
}}

PDD text (truncated):
{sections_text_truncated}
"""
