"""
OSHA regulation database for construction-site PPE and zone violations.

Each OshaCode entry covers:
  - The CFR citation (code)
  - Short title and full description
  - Fine range (per-violation serious violation amounts; 2024 inflation-adjusted)
  - Practical corrective actions
  - Reference URL for the full regulation text

Fine amounts are the 2024 OSHA adjusted penalty schedule:
  Serious / Other-than-serious: $1,116 – $15,625 per violation
  Willful or Repeat:            $11,162 – $156,259 per violation
  Failure to Abate:             $15,625 per day
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class OshaCode:
    code: str                         # e.g. "29 CFR 1926.100(a)"
    title: str                        # Short title
    description: str                  # One-sentence regulatory summary
    fine_min_usd: int                 # Per-violation minimum (serious)
    fine_max_usd: int                 # Per-violation maximum (serious)
    willful_max_usd: int              # Willful/repeat ceiling
    corrective_actions: tuple[str, ...]  # Practical steps to remedy
    plain_english: str                # Human-readable explanation
    reference_url: str = ""          # CFR reference link


# ---------------------------------------------------------------------------
# The database — keyed by a short identifier for easy lookup
# ---------------------------------------------------------------------------

OSHA_DB: dict[str, OshaCode] = {

    # ── Head Protection ──────────────────────────────────────────────────────

    "1926.100(a)": OshaCode(
        code="29 CFR 1926.100(a)",
        title="Head Protection",
        description=(
            "Employees working in areas where there is a possible danger of head "
            "injury from impact, or from falling or flying objects, or from electrical "
            "shock and burns, shall be protected by protective helmets."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Issue ANSI/ISEA Z89.1-compliant hard hats to all workers on site immediately.",
            "Post visible signage at every site entrance: 'Hard hat required beyond this point.'",
            "Conduct a toolbox talk covering head injury statistics and proper hard hat fit.",
            "Assign a safety officer to perform daily PPE spot-checks at shift start.",
            "Implement a 'no hard hat, no entry' policy enforced by site supervisors.",
        ),
        plain_english=(
            "A worker was detected without a hard hat in an active construction area. "
            "Head injuries are among the leading causes of fatalities on construction sites — "
            "OSHA requires hard hats wherever falling objects, low clearances, or electrical "
            "hazards are present. This is classified as a Serious violation."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.100",
    ),

    # ── General PPE / High-Visibility ────────────────────────────────────────

    "1926.95(a)": OshaCode(
        code="29 CFR 1926.95(a)",
        title="Personal Protective Equipment — Criteria",
        description=(
            "Protective equipment, including personal protective equipment for eyes, face, head, "
            "and extremities, protective clothing, respiratory devices, and protective shields "
            "and barriers, shall be provided, used, and maintained wherever it is necessary "
            "due to hazards of processes or environment."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Conduct a site-specific PPE hazard assessment and document required equipment per OSHA 1926.95(b).",
            "Ensure all required PPE (hard hat, high-visibility vest, gloves, safety footwear) is available in all sizes.",
            "Train workers on correct donning, doffing, inspection, and replacement of all PPE.",
            "Establish a PPE tracking log: issue date, size, condition, and worker acknowledgement.",
            "Schedule monthly PPE audits and replace worn or damaged equipment immediately.",
        ),
        plain_english=(
            "One or more pieces of required personal protective equipment were missing. "
            "OSHA mandates that employers identify site hazards, select appropriate PPE, "
            "provide it at no cost, and ensure workers wear it correctly at all times."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.95",
    ),

    "1926.28(a)": OshaCode(
        code="29 CFR 1926.28(a)",
        title="Personal Protective Equipment — Employer Responsibility",
        description=(
            "The employer is responsible for requiring the wearing of appropriate personal "
            "protective equipment in all operations where there is an exposure to hazardous "
            "conditions or where the possibility of injury or illness exists."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Enforce mandatory high-visibility vest policy for all workers in vehicle or equipment traffic areas.",
            "Brief subcontractors and temporary workers on PPE requirements before site access.",
            "Establish a visitor PPE kit (hard hat + vest) at the site entrance.",
            "Designate a daily PPE compliance check as part of each shift's sign-on procedure.",
            "Document all PPE non-compliance incidents and issue formal warnings per company policy.",
        ),
        plain_english=(
            "A worker was detected without a required high-visibility safety vest. "
            "On active construction sites — especially near vehicles, forklifts, or heavy equipment — "
            "ANSI/ISEA 107-compliant vests are essential to worker visibility and injury prevention. "
            "The employer bears legal responsibility for enforcing PPE use."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.28",
    ),

    # ── Respiratory Protection ───────────────────────────────────────────────

    "1910.134(a)": OshaCode(
        code="29 CFR 1910.134(a)(1)",
        title="Respiratory Protection",
        description=(
            "In the control of those occupational diseases caused by breathing air "
            "contaminated with harmful dusts, fogs, fumes, mists, gases, smokes, sprays, "
            "or vapors, the primary objective shall be to prevent atmospheric contamination."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Identify all respiratory hazards present (dust, fumes, silica, welding smoke) and document them.",
            "Select NIOSH-approved respirators appropriate to the specific hazard level.",
            "Establish a written Respiratory Protection Program per 29 CFR 1910.134(c).",
            "Conduct medical evaluations for workers required to wear respirators.",
            "Train workers on respirator fit testing, seal checks, and maintenance.",
        ),
        plain_english=(
            "A worker was detected without required respiratory protection in an area with "
            "potential airborne hazards such as silica dust, welding fumes, or chemical vapors. "
            "Chronic exposure to these hazards causes serious lung disease. "
            "OSHA requires a documented respiratory protection program when engineering controls "
            "alone cannot reduce exposure to safe levels."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.134",
    ),

    # ── Hand Protection ──────────────────────────────────────────────────────

    "1910.138(a)": OshaCode(
        code="29 CFR 1910.138(a)",
        title="Hand Protection",
        description=(
            "Employers shall select and require employees to use appropriate hand protection "
            "when employees' hands are exposed to hazards such as those from skin absorption "
            "of harmful substances, severe cuts or lacerations, severe abrasions, punctures, "
            "chemical burns, thermal burns, and harmful temperature extremes."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Identify all hand hazards by task (cuts, abrasion, chemical, heat) and specify glove type per task.",
            "Stock appropriate glove grades (cut-resistant, chemical, thermal) at the workstation.",
            "Include glove requirements in the site's PPE hazard assessment.",
            "Conduct a brief demonstration on correct glove selection, fit, and when to replace.",
            "Post hand protection requirements at each work area as a visual reminder.",
        ),
        plain_english=(
            "A worker was detected without gloves in an area where hand protection is required. "
            "Hand injuries — cuts, crush injuries, and chemical burns — are among the most frequent "
            "construction injuries. OSHA requires employers to assess hand hazards by task and "
            "provide suitable gloves at no cost to workers."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.138",
    ),

    # ── Foot Protection ──────────────────────────────────────────────────────

    "1926.96": OshaCode(
        code="29 CFR 1926.96",
        title="Occupational Foot Protection",
        description=(
            "Safety-toe footwear for employees shall meet the requirements and specifications "
            "in American National Standard for Men's Safety-Toe Footwear, Z41.1-1967."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Require ASTM F2413-compliant safety-toe footwear as a condition of site entry.",
            "Provide a list of approved footwear vendors to all workers before their start date.",
            "Post foot protection requirements at site entrance and in pre-job safety orientation.",
            "Conduct a footwear check as part of daily PPE inspections.",
        ),
        plain_english=(
            "A worker was detected without appropriate safety footwear. "
            "On construction sites, foot injuries from falling objects, punctures, and crushing "
            "are common and often severe. OSHA-compliant steel- or composite-toe boots are required "
            "wherever such hazards exist."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.96",
    ),

    # ── Restricted Zone / No-Entry ───────────────────────────────────────────

    "1926.200(a)": OshaCode(
        code="29 CFR 1926.200(a)",
        title="Accident Prevention Signs and Tags — Danger Areas",
        description=(
            "Danger signs shall be used only where an immediate hazard exists. "
            "Danger signs shall be distinctive in color and shall contain the word 'DANGER' "
            "in upper-case letters on the upper panel."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Install ANSI Z535-compliant DANGER signs at all restricted zone boundaries.",
            "Erect physical barriers (cones, rope lines, temporary fencing) to reinforce signage.",
            "Communicate zone boundaries to all workers during daily pre-shift safety briefings.",
            "Limit access to restricted zones using a permit-to-work system.",
            "Review zone boundaries with subcontractor supervisors before each phase of work.",
        ),
        plain_english=(
            "A person was detected entering a marked restricted or no-entry zone. "
            "OSHA requires danger areas to be clearly identified with standardised signage "
            "and physical barriers to prevent unauthorised access to areas with immediate hazards "
            "such as overhead work, energised equipment, excavations, or structural instability."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.200",
    ),

    "1926.502(j)": OshaCode(
        code="29 CFR 1926.502(j)",
        title="Fall Protection — Warning Line Systems",
        description=(
            "Warning line systems shall be erected around all sides of the work area. "
            "No employee shall be allowed in the area between a roof edge and a warning line "
            "unless the employee is performing roofing work in that area."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Install a compliant warning line system (minimum tensile strength: 500 lbs) at all hazardous boundaries.",
            "Position warning lines at least 6 feet from the hazard edge on low-slope roofs.",
            "Assign a safety monitor to observe workers near warning line boundaries.",
            "Conduct fall protection training for all workers before work begins near open edges.",
            "Inspect warning line systems at the start of each shift and after severe weather.",
        ),
        plain_english=(
            "A worker entered a zone bounded by a warning line or fall-protection barrier. "
            "Falls are the leading cause of construction fatalities — OSHA's warning line regulations "
            "establish mandatory boundaries that only trained and equipped workers may cross. "
            "Untrained or unequipped personnel must not enter these zones under any circumstances."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.502",
    ),

    "1926.21(b)(2)": OshaCode(
        code="29 CFR 1926.21(b)(2)",
        title="Safety Training and Education",
        description=(
            "The employer shall instruct each employee in the recognition and avoidance of "
            "unsafe conditions and the regulations applicable to the work environment to "
            "control or eliminate any hazards or other exposure to illness or injury."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Schedule immediate retraining for any worker found in a restricted zone.",
            "Document training completion and have workers sign acknowledgement forms.",
            "Conduct a site safety orientation for ALL workers before they begin work.",
            "Hold daily pre-task safety briefings (toolbox talks) covering hazards for the day's work.",
            "Post zone maps and hazard summaries in common areas (site office, break room, entrance).",
        ),
        plain_english=(
            "This violation indicates a worker may not have received adequate training on "
            "site hazards and restricted area boundaries. OSHA requires employers to train "
            "every worker — including subcontractors and day labourers — on recognising "
            "and avoiding unsafe conditions before they begin work on site."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.21",
    ),

    # ── General Duty Clause ──────────────────────────────────────────────────

    "5(a)(1)": OshaCode(
        code="OSH Act Section 5(a)(1)",
        title="General Duty Clause",
        description=(
            "Each employer shall furnish to each of his employees employment and a place of "
            "employment which are free from recognised hazards that are causing or are likely "
            "to cause death or serious physical harm to his employees."
        ),
        fine_min_usd=5_000,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Immediately address the identified hazard — remove the condition or provide interim protection.",
            "Conduct a Job Hazard Analysis (JHA) for all high-risk tasks.",
            "Establish a written site safety plan and enforce it consistently.",
            "Empower all workers to stop work when they observe an unsafe condition.",
            "Report serious near-misses internally and review root causes within 24 hours.",
        ),
        plain_english=(
            "This violation falls under OSHA's General Duty Clause — a catch-all provision "
            "that holds employers responsible for any recognised workplace hazard, even if "
            "no specific standard explicitly covers it. It is cited when the hazard is well-known "
            "in the industry and feasible means to abate it exist."
        ),
        reference_url="https://www.osha.gov/laws-regs/oshact/section5-duties",
    ),
}
