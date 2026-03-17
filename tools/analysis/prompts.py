"""Prompts for process analysis tools.

All LLM prompts are defined here as string constants.
Never inline prompts in tool functions.
"""

ACTIVITY_ANALYSIS_SYSTEM = """
You are an expert RPA (Robotic Process Automation) business
analyst specialising in process complexity assessment.

You apply a specific definition of "activity" when counting:
An activity is a piece of work that forms one logical step
within a process. It could be subdivided into several
keystrokes (up to 10 on average). The activity is done
in a single application.

Examples of ONE activity:
- "Log in to SAP" (single application, single logical step)
- "Open the Excel input file" (single application)
- "Navigate to transaction SE16" (single application)
- "Copy data from SAP to clipboard" (single step)

Examples of MULTIPLE activities:
- "Log in to SAP, navigate to SE16, and extract data" = 3 activities
- "Open Excel, find the row, update the value, save" = 4 activities

You must respond with valid JSON only. No markdown, no
explanation outside the JSON.
"""

ACTIVITY_ANALYSIS_PROMPT = """
Analyse the following PDD sections and count the number of
distinct activities in the process to be automated.

Apply this definition strictly:
- Activity = one logical step done in a single application
- Do NOT count sub-keystrokes as separate activities
- Do NOT count decision points or business rules as activities
  (they are counted separately)
- DO count each application switch as a new activity context
- DO count each distinct data operation as a separate activity

Return a JSON object with exactly these fields:
{{
  "raw_activity_count": <integer>,
  "activity_list": [
    "brief description of each activity"
  ],
  "count_confidence": <float 0.0-1.0>,
  "counting_rationale": "explanation of how you counted",
  "ambiguous_items": [
    "items that were unclear to classify"
  ]
}}

Rules:
- raw_activity_count must equal len(activity_list)
- count_confidence reflects how clearly the PDD describes
  the activities (1.0 = crystal clear, 0.3 = very vague)
- If process steps are not described: return count=0,
  confidence=0.1, explain in counting_rationale
- Maximum countable activities: 60 (XL ceiling from scoring)
  If you count more than 60, return 60 and note this in
  counting_rationale

PDD Sections:
{sections_text}

Few-shot examples to calibrate your counting:

Example 1 — Simple process (expected ~8 activities):
"The bot logs into SAP using stored credentials. It navigates
to transaction SE16. It searches for records matching today's
date. It downloads the results to a CSV file. It opens the
target Excel workbook. It pastes the data into the correct
sheet. It formats the data. It saves and closes Excel."
Correct count: 8 activities

Example 2 — Complex process (expected ~15 activities):
"The bot reads the input Excel file row by row. For each row
it opens the customer portal. It searches for the customer ID.
It downloads the account statement PDF. It opens the PDF. It
extracts the balance figure. It compares with the Excel value.
If different: it flags the row in Excel. It logs the
discrepancy to a log file. It moves to the next row."
Correct count: ~10 per iteration (but count unique activities,
not loop iterations): 9 activities
"""

ACTIVITY_ANALYSIS_RETRY_PROMPT = """
Your previous response could not be parsed. Return ONLY this
JSON structure with no other text:
{{
  "raw_activity_count": 0,
  "activity_list": [],
  "count_confidence": 0.1,
  "counting_rationale": "Unable to parse previous response",
  "ambiguous_items": []
}}

Or if you can analyse the document, fill in the actual values.

Document text (first 1500 chars):
{sections_text_truncated}
"""
