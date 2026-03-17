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
