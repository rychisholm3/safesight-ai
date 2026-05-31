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

    # ── Fall Protection ──────────────────────────────────────────────────────

    "1926.502(b)": OshaCode(
        code="29 CFR 1926.502(b)",
        title="Guardrail Systems",
        description=(
            "Guardrail systems and their use shall comply with the following provisions: "
            "top rail height shall be 42 inches (plus or minus 3 inches) above the walking/working level; "
            "midrails shall be installed at a height midway between the top edge of the guardrail system "
            "and the walking/working level surface."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Install OSHA-compliant guardrail systems (42\" top rail ±3\") on all open-sided surfaces 6+ ft above lower level.",
            "Inspect guardrails at the start of each shift for damage, displacement, or missing components.",
            "Document guardrail installation on a site safety checklist before work begins on elevated surfaces.",
            "Ensure midrails are installed between the top rail and working surface on all guardrail systems.",
            "Train all workers on fall hazards and the importance of never removing or bypassing guardrail systems.",
        ),
        plain_english=(
            "A worker was detected in an area where guardrail protection is required but may not be present. "
            "29 CFR 1926.502(b) is the single most-cited OSHA standard in construction. Falls are the #1 "
            "cause of construction fatalities — guardrails are the primary engineering control and must "
            "be installed on all open-sided surfaces 6 feet or more above a lower level."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.502",
    ),

    "1926.502(d)": OshaCode(
        code="29 CFR 1926.502(d)",
        title="Personal Fall Arrest Systems",
        description=(
            "Personal fall arrest systems and their use shall comply with the following provisions: "
            "when stopping a fall, a personal fall arrest system shall limit maximum arresting force "
            "to 1,800 lbs; bring a worker to a complete stop within 3.5 feet of free fall."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Provide ANSI-rated full-body harnesses and self-retracting lanyards for all workers at heights.",
            "Identify and mark suitable anchor points (capable of supporting 5,000 lbs per attached worker).",
            "Conduct hands-on harness fitting and inspection training for all workers before elevated work.",
            "Inspect all fall arrest equipment before each use; remove any damaged or worn components from service.",
            "Establish a rescue plan for fallen workers — do not leave a suspended worker unattended.",
        ),
        plain_english=(
            "In areas where guardrails are not feasible, personal fall arrest systems (full-body harness, "
            "shock-absorbing lanyard, and anchor point) are mandatory for workers at heights of 6 feet or more. "
            "OSHA requires that the system be rigged to prevent a free fall greater than 6 feet and be inspected "
            "before every use."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.502",
    ),

    "1926.503": OshaCode(
        code="29 CFR 1926.503",
        title="Fall Protection Training Requirements",
        description=(
            "The employer shall provide a training programme for each employee who might be exposed to "
            "fall hazards. The programme shall enable each employee to recognise the hazards of falling "
            "and shall train each employee in the procedures to be followed in order to minimise these hazards."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Schedule mandatory fall protection training for all workers before they access elevated areas.",
            "Cover: fall hazard recognition, correct use of guardrails and personal fall arrest systems, and rescue procedures.",
            "Retain signed training records for each worker; retrain any worker observed using fall protection incorrectly.",
            "Conduct retraining after any fall incident or near-miss involving fall hazards.",
            "Include fall hazard information in the site-specific orientation for every new worker and subcontractor.",
        ),
        plain_english=(
            "Workers detected in elevated or fall-hazard areas must have received documented fall protection training. "
            "OSHA requires training to cover recognition of fall hazards, correct PPE use, and emergency procedures. "
            "Without training, even correctly installed equipment may be misused — increasing, not decreasing, fall risk."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.503",
    ),

    # ── Scaffolding ──────────────────────────────────────────────────────────

    "1926.451(g)": OshaCode(
        code="29 CFR 1926.451(g)",
        title="Scaffold Fall Protection",
        description=(
            "Each employee on a scaffold more than 10 feet above a lower level shall be protected "
            "from falling to that lower level by the use of guardrail systems or personal fall arrest systems."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Install guardrails on all four sides of scaffold platforms above 10 feet.",
            "Ensure scaffold planking is fully decked and secured with no gaps greater than 1 inch.",
            "Check scaffold erection or modification was performed or supervised by a Competent Person.",
            "Inspect scaffolding before each work shift and after any event that could affect structural integrity.",
            "Do not allow scaffold use by more workers or materials than the platform is rated to support.",
        ),
        plain_english=(
            "A worker was detected on or near scaffolding without adequate fall protection. Scaffolding "
            "violations are consistently in OSHA's top 10 most-cited standards. Workers on platforms "
            "above 10 feet require either guardrails or personal fall arrest systems — and the scaffold "
            "must be erected, inspected, and tagged as safe by a Competent Person before use."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.451",
    ),

    # ── Excavation & Trenching ───────────────────────────────────────────────

    "1926.652(a)": OshaCode(
        code="29 CFR 1926.652(a)(1)",
        title="Excavations — Employee Protection",
        description=(
            "Each employee in an excavation shall be protected from cave-ins by an adequate protective "
            "system designed in accordance with 29 CFR 1926.652(b) or (c), except when excavations are "
            "made entirely in stable rock or are less than 5 feet in depth and examination by a Competent "
            "Person provides no indication of a potential cave-in."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Immediately remove all workers from unprotected excavations deeper than 5 feet.",
            "Have a Competent Person classify the soil type and specify the required protective system (sloping, shoring, or trench box).",
            "Install the approved protective system before workers re-enter the excavation.",
            "Inspect the excavation daily and after rain or other events that may increase hazard.",
            "Establish and mark safe access/egress routes (ladders, ramps) within 25 feet of all workers.",
        ),
        plain_english=(
            "A worker was detected near or in an excavation area. Cave-ins kill an average of two workers "
            "per month in the US — they strike without warning and 1 cubic yard of soil weighs over a ton. "
            "OSHA requires a Competent Person to classify soil and specify a protective system before any "
            "worker enters an excavation 5 feet or deeper. No exceptions."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.652",
    ),

    # ── Electrical Safety ────────────────────────────────────────────────────

    "1926.416(a)": OshaCode(
        code="29 CFR 1926.416(a)(1)",
        title="Electrical — General Requirements",
        description=(
            "No employer shall permit an employee to work in such proximity to any part of an electric "
            "power circuit that the employee could contact the electric power circuit in the course of work, "
            "unless the employee is protected against electric shock by de-energising the circuit and "
            "grounding it or by guarding it effectively by insulation or other means."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Establish and enforce an Electrical Safety Program including lockout/tagout (LOTO) procedures.",
            "Mark all energised electrical equipment and overhead power line locations clearly on site maps.",
            "Maintain OSHA-required approach distances from overhead power lines (minimum 10 ft for lines up to 50kV).",
            "Ensure all temporary wiring uses GFCI protection; inspect cords and equipment daily.",
            "Provide arc-flash rated PPE (gloves, face shield, insulated tools) for any work near energised circuits.",
        ),
        plain_english=(
            "A worker was detected near electrical infrastructure or restricted electrical equipment areas. "
            "Electrocution is one of OSHA's 'Fatal Four' construction hazards. Work near energised circuits "
            "requires LOTO procedures, approach distance controls, and arc-rated PPE — all documented in a "
            "written electrical safety program."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.416",
    ),

    # ── Ladders ─────────────────────────────────────────────────────────────

    "1926.1053(b)": OshaCode(
        code="29 CFR 1926.1053(b)",
        title="Ladders — Use Requirements",
        description=(
            "When portable ladders are used for access to an upper landing surface, the ladder side rails "
            "shall extend at least 3 feet above the upper landing surface; the ladder shall be secured. "
            "Employees shall face the ladder when ascending or descending."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Ensure ladder side rails extend at least 3 feet above each upper landing or access point.",
            "Secure ladders at top and bottom to prevent displacement; use a spotter if securing is not possible.",
            "Inspect ladders before each use; remove any ladder with cracks, broken rungs, or bent rails from service.",
            "Train workers: one person per ladder, face the ladder when climbing, three-point contact at all times.",
            "Do not use the top two rungs of a step ladder or the top three rungs of an extension ladder.",
        ),
        plain_english=(
            "A worker was detected using or accessing a ladder. Ladder falls cause thousands of construction "
            "injuries each year. OSHA requires ladders to be properly set up (1:4 angle ratio), secured, "
            "extending 3 feet above access points, and used with three-point contact at all times. "
            "Ladders must be inspected daily by a Competent Person."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.1053",
    ),

    # ── Confined Space ───────────────────────────────────────────────────────

    "1910.146(c)": OshaCode(
        code="29 CFR 1910.146(c)(1)",
        title="Permit-Required Confined Spaces",
        description=(
            "The employer shall evaluate the workplace to determine if any spaces are permit-required "
            "confined spaces. If the workplace contains permit spaces, the employer shall inform exposed "
            "employees by posting danger signs or by any other equally effective means of the existence "
            "and location of and the danger posed by the permit spaces."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Post 'DANGER — Confined Space — Do Not Enter' signs at all permit-required confined space openings.",
            "Implement a written confined space entry programme with a permit system before any entry.",
            "Test atmosphere for oxygen, flammable gases, and toxic contaminants before entry.",
            "Station an attendant outside the confined space during all entries; have a rescue plan ready.",
            "Provide entrants with all required PPE including supplied-air respirators if atmosphere is hazardous.",
        ),
        plain_english=(
            "A worker was detected near or attempting to enter what may be a confined space. "
            "Confined spaces — tanks, vaults, manholes, excavations — can contain oxygen-deficient or "
            "toxic atmospheres that incapacitate a worker in seconds. OSHA requires atmospheric testing, "
            "a written entry permit, an outside attendant, and a rescue plan before any worker enters."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.146",
    ),

    # ── Housekeeping & Walking-Working Surfaces ──────────────────────────────

    "1926.25": OshaCode(
        code="29 CFR 1926.25",
        title="Housekeeping — Construction Sites",
        description=(
            "During the course of construction, alteration, or repairs, form and scrap lumber with protruding "
            "nails, and all other debris, shall be kept cleared from work areas, passageways, and stairs in "
            "and around buildings or other structures."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Assign daily housekeeping responsibilities to each crew; conduct end-of-shift cleanup.",
            "Remove scrap lumber, protruding nails, and debris from all walkways and stairways immediately.",
            "Place waste bins throughout the site; use designated collection areas for scrap material.",
            "Keep access routes, emergency egress paths, and fire extinguisher locations clear at all times.",
            "Include housekeeping in site safety inspections and pre-task safety plans.",
        ),
        plain_english=(
            "Debris, scrap lumber with nails, and cluttered walkways are among the most common causes "
            "of slips, trips, and puncture injuries on construction sites. OSHA requires work areas, "
            "passageways, and stairs to be kept clear throughout the workday — not just during end-of-day cleanup."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.25",
    ),

    # ── Struck-By Hazards ────────────────────────────────────────────────────

    "1926.602(a)": OshaCode(
        code="29 CFR 1926.602(a)(9)(ii)",
        title="Material Handling — Vehicles and Equipment",
        description=(
            "No person shall be permitted to stand or pass under elevated portions of any truck, crane, "
            "shovel, derrick, or similar piece of equipment while any load is suspended."
        ),
        fine_min_usd=1_116,
        fine_max_usd=15_625,
        willful_max_usd=156_259,
        corrective_actions=(
            "Establish and enforce exclusion zones around cranes and lifting operations — use barricades or spotters.",
            "Implement a tag-line policy: all suspended loads must be controlled with tag lines.",
            "Require high-visibility vests for all workers near vehicle operating areas.",
            "Use a designated signal person (rigger/dogman) for all lifting operations.",
            "Conduct daily pre-lift meetings covering lift radius, exclusion zone boundaries, and emergency procedures.",
        ),
        plain_english=(
            "A worker was detected in proximity to heavy equipment or vehicle operating areas. "
            "Struck-by incidents involving cranes, forklifts, and other heavy equipment are among the "
            "leading causes of construction fatalities. OSHA prohibits workers from standing or passing "
            "under suspended loads and requires exclusion zones around operating equipment."
        ),
        reference_url="https://www.osha.gov/laws-regs/regulations/standardnumber/1926/1926.602",
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
