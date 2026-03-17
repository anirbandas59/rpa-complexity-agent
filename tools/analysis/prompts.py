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

INTERFACE_DETECTION_SYSTEM = """
You are an expert RPA business analyst specialising in
identifying target applications that an RPA bot must interact
with during process execution.

A "target application" is any system, tool, or interface
that the business uses and that the RPA bot must open,
read from, write to, click in, or otherwise interact with.

Classification rules:
- Count each distinct application separately
- SAP modules (SAP ECC, SAP BW, SAP HR) count as ONE
  application unless the bot uses completely different
  transaction codes in different SAP systems
- Microsoft Office apps count separately (Excel ≠ Outlook
  ≠ Word ≠ Teams)
- Web browsers count as the WEBSITE they access, not
  the browser itself (Chrome is not an application —
  "Customer Portal" is)
- Email counts as ONE interface (Outlook/Gmail/etc.)
- File system / shared drive counts as ONE interface

You must respond with valid JSON only.
"""

INTERFACE_DETECTION_PROMPT = """
Identify all target applications/interfaces that the RPA
bot must interact with in this process.

Return a JSON object with exactly these fields:
{{
  "applications": [
    {{
      "name": "canonical application name",
      "type": "web|desktop|api|database|file_system|email",
      "automation_method": "ui_automation|api_call|file_read_write|email_trigger",
      "evidence": "quote or paraphrase from the document confirming this",
      "confidence": <float 0.0-1.0>
    }}
  ],
  "total_count": <integer — must equal len(applications)>,
  "detection_confidence": <float 0.0-1.0>,
  "notes": "any relevant observations about the interfaces"
}}

Rules:
- Deduplicate: SAP and SAP ECC are the same application
- Do NOT include the RPA tool itself (Blue Prism, UiPath etc.)
- Do NOT include operating system components (Windows
  Explorer, Task Scheduler) unless the bot explicitly
  interacts with them as part of the process
- If no applications are clearly identified: return
  empty applications array and detection_confidence=0.1

PDD Sections:
{sections_text}
"""

INTERFACE_DETECTION_RETRY_PROMPT = """
Return ONLY this JSON with actual values from the document:
{{
  "applications": [],
  "total_count": 0,
  "detection_confidence": 0.1,
  "notes": "retry attempt"
}}

Document text (first 1500 chars):
{sections_text_truncated}
"""

BUSINESS_RULE_EXTRACTION_SYSTEM = """
You are an expert RPA business analyst specialising in
identifying business rules that affect process complexity.

You apply a STRICT definition of what counts as a
complexity-relevant business rule:

A business rule COUNTS if it:
1. Creates an entirely new process flow or sub-process
2. That new flow contains MORE THAN 2 activities
3. The flow is conditional — only triggered in certain cases

A business rule DOES NOT COUNT if it:
- Only validates data (check if field is empty, numeric, etc.)
- Only logs an error and continues or exits
- Only skips a step or moves to the next record
- Creates a flow with 2 or fewer activities

Examples that COUNT:
- "If customer type is VIP, navigate to the premium portal,
  look up the tier, update three fields, and send a
  notification email" (5+ activities in new flow)
- "For month-end processing, run the reconciliation module
  which involves opening a different system, extracting
  data, comparing, and generating a report" (6+ activities)

Examples that DO NOT COUNT:
- "If the file is empty, log an error and stop" (1 activity)
- "Validate that the amount field is not zero" (validation)
- "If already processed, skip to next record" (1 activity)

You must respond with valid JSON only.
"""

BUSINESS_RULE_EXTRACTION_PROMPT = """
Identify business rules in this PDD that create new process
flows with more than 2 activities.

Return a JSON object with exactly these fields:
{{
  "flow_creating_rules": [
    {{
      "description": "clear description of the rule and
                      what new flow it creates",
      "condition": "the IF condition that triggers this rule",
      "branch_name": "short name for this branch/flow",
      "estimated_branch_activities": <integer>,
      "evidence": "direct quote or paraphrase from document",
      "confidence": <float 0.0-1.0>
    }}
  ],
  "non_qualifying_rules": [
    {{
      "description": "rule that was considered but excluded",
      "reason_excluded": "why it does not qualify
                          (e.g. only 1 activity, validation only)"
    }}
  ],
  "total_qualifying_count": <integer>,
  "extraction_confidence": <float 0.0-1.0>,
  "notes": "observations about the business rules in this process"
}}

Rules:
- total_qualifying_count must equal len(flow_creating_rules)
- Only include rules where estimated_branch_activities > 2
- Include non_qualifying_rules to show your reasoning
- If no qualifying rules found: return empty flow_creating_rules
  and total_qualifying_count=0
- Maximum countable rules: 6 (XL ceiling from scoring matrix)
  If you find more than 6, include only the 6 most significant

PDD Sections:
{sections_text}
"""

BUSINESS_RULE_RETRY_PROMPT = """
Return ONLY this JSON structure:
{{
  "flow_creating_rules": [],
  "non_qualifying_rules": [],
  "total_qualifying_count": 0,
  "extraction_confidence": 0.1,
  "notes": "retry attempt"
}}

Or fill in actual values if you can analyse this text:
{sections_text_truncated}
"""

LAYOUT_IDENTIFICATION_SYSTEM = """
You are an expert RPA business analyst specialising in
identifying digital layouts and templates used in automated
processes.

You apply this PRECISE definition:
A "digital layout" is any distinct input or output file
template that the RPA bot reads from or writes to.

Counting rules:
- Count by TEMPLATE, not by file type
- Two Excel files with different structures = 2 layouts
- The same template used in multiple steps = 1 layout
- Each uniquely named report or form = 1 layout
- Input files and output files are both counted
- Email templates count as layouts
- Database tables do NOT count as layouts (they are
  interfaces, not templates)
- Configuration files (.ini, .config, .yaml) do NOT count
  unless the bot reads them as data inputs

Examples:
✅ COUNTS as separate layouts:
- "Month End Report.xlsx" and "Daily Summary.xlsx" = 2 layouts
  (same extension, different templates)
- Input CSV file and Output PDF report = 2 layouts
- Login credentials Excel and Processing Excel = 2 layouts

❌ COUNTS as ONE layout:
- Same input template used for 5 different customers = 1 layout
- Same Excel processed on Monday and Friday = 1 layout

You must respond with valid JSON only.
"""

LAYOUT_IDENTIFICATION_PROMPT = """
Identify all distinct digital layouts (templates/files) that
the RPA bot reads from or writes to in this process.

Return a JSON object with exactly these fields:
{{
  "layouts": [
    {{
      "name": "descriptive name of the layout/template",
      "file_extension": "xlsx|pdf|csv|xml|docx|txt|json|other",
      "is_input": <true if bot reads this>,
      "is_output": <true if bot writes/creates this>,
      "template_type": "input_template|output_report|schema_file|config_file|email_template|other",
      "evidence": "quote or paraphrase confirming this layout",
      "confidence": <float 0.0-1.0>
    }}
  ],
  "total_count": <integer — must equal len(layouts)>,
  "detection_confidence": <float 0.0-1.0>,
  "exceeds_ceiling": <true if count > 10>,
  "notes": "observations about the layouts in this process"
}}

Rules:
- Each entry must have at least is_input=true OR is_output=true
- Deduplicate: same template referenced multiple times = 1 entry
- Do NOT count database tables
- Do NOT count configuration files
- Maximum: 10 layouts (XL ceiling). If more found, include
  the 10 most significant and set exceeds_ceiling=true

PDD Sections:
{sections_text}
"""

LAYOUT_IDENTIFICATION_RETRY_PROMPT = """
Return ONLY this JSON with actual values if possible:
{{
  "layouts": [],
  "total_count": 0,
  "detection_confidence": 0.1,
  "exceeds_ceiling": false,
  "notes": "retry attempt"
}}

Document text (first 1500 chars):
{sections_text_truncated}
"""
