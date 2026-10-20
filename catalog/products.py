"""The product catalog.

Each entry carries marketing copy (used by the Marketing AI to generate social
posts), targeting language (used by the Sales AI to generate outreach) and
commercial terms (used by the storefront and lead scoring).

``demo_url`` points at a live public preview; ``repo_url`` points at the source
repository when there is no hosted demo. Both are optional.

All prices are in Philippine peso (PHP). See ``currency.py`` for conversion.
"""

from __future__ import annotations

from typing import Any

PRODUCTS: list[dict[str, Any]] = [
    {
        "slug": "hardware-inventory-system",
        "name": "Hardware Management System",
        "tagline": "Know exactly what hardware you own, where it is, and who has it.",
        "description": (
            "A hardware management system that tracks every laptop, server, monitor "
            "and peripheral your company owns across its whole lifecycle. Barcode "
            "scanning records assets coming in and going out, each item is assigned to "
            "a team member, and the system tracks warranty expiry, depreciation and "
            "end-of-life dates so nothing fails unexpectedly and no asset is lost or "
            "stolen."
        ),
        "audience": "IT asset managers and operations teams",
        "category": "IT Asset Management",
        "icon": "🖥️",
        "price_month": 1490,
        "price_setup": 9000,
        "lead_value": 135000,
        "features": [
            "Barcode and QR scanning for check-in / check-out",
            "Assignment history per asset and per employee",
            "Warranty and depreciation tracking",
            "Low-stock and end-of-life alerts",
            "Audit-ready export for auditors",
            "Bulk import from spreadsheets or existing systems",
        ],
        "highlights": [
            "Cut asset audits from days to an afternoon",
            "Never buy a replacement for a machine you still own",
            "Every handoff recorded with a timestamp",
        ],
    },
    {
        "slug": "clinic-inventory-system",
        "name": "Clinic Inventory System",
        "tagline": "Track stock, expiry and controlled drugs across every clinic room.",
        "description": (
            "A clinic inventory system built for medical supply rooms. It tracks "
            "consumables, controlled drugs and equipment by clinic location, enforces "
            "batch and expiry tracking, flags recalls, and produces the dispensing and "
            "stock reports that healthcare regulators ask for during an inspection."
        ),
        "audience": "clinic managers and pharmacy coordinators",
        "category": "Healthcare Inventory",
        "icon": "🩺",
        "price_month": 2490,
        "price_setup": 16000,
        "lead_value": 235000,
        "repo_url": "https://github.com/mjkulit03/Clinic_Inventory",
        "features": [
            "Multi-site stock with per-room bin locations",
            "Batch number and expiry tracking with recall alerts",
            "Controlled-drug register with dual sign-off",
            "Reorder points and supplier lead-time tracking",
            "Inspection-ready dispensing reports",
            "Role-based access for clinical and admin staff",
        ],
        "highlights": [
            "Find any recall-affected batch in seconds",
            "Inspection-ready reports, generated on demand",
            "Expiry write-offs fall because stock rotates properly",
        ],
    },
    {
        "slug": "office-supplies-inventory-system",
        "name": "Office Supplies Inventory System",
        "tagline": "Stop re-buying printer paper you already have in the cupboard.",
        "description": (
            "An office supplies inventory system for consumables: paper, toner, pens, "
            "cleaning and kitchen stock. Staff request supplies from a shared "
            "catalogue, approvers see the cost before ordering, and the system tracks "
            "supplier contracts so you always reorder at the best price."
        ),
        "audience": "office managers and procurement teams",
        "category": "Inventory & Procurement",
        "icon": "📦",
        "price_month": 1190,
        "price_setup": 6000,
        "lead_value": 78000,
        "repo_url": "https://github.com/mjkulit03/Office_supplies_Inventory",
        "features": [
            "Self-service supply request and approval workflow",
            "Consumable stock levels per office and per shelf",
            "Supplier contract and price-list management",
            "Consumption reports by cost centre",
            "Automatic reorder suggestions at threshold",
            "Kitting for onboarding new starters",
        ],
        "highlights": [
            "Every request has an owner and an approval trail",
            "See spend by cost centre, not just by order",
            "Onboarding kits go out in one click",
        ],
    },
    {
        "slug": "it-asset-management-system",
        "name": "IT Asset Management System",
        "tagline": "One source of truth for software licences, contracts and devices.",
        "description": (
            "An IT asset management system covering both hardware and software. It "
            "tracks device lifecycle, software licence allocation and renewal dates, "
            "vendor contracts, and cost-per-user, so IT can answer what you own, what "
            "it costs and what renews next quarter without opening six spreadsheets."
        ),
        "audience": "IT directors and systems administrators",
        "category": "IT Asset Management",
        "icon": "🗂️",
        "price_month": 2890,
        "price_setup": 18000,
        "lead_value": 290000,
        "features": [
            "Hardware and software licence in one register",
            "Renewal calendar with 60/30/7-day reminders",
            "Cost-per-user and total-cost-of-ownership reporting",
            "Vendor and contract records with renewal terms",
            "Access review and offboarding checklist",
            "API and CSV import for existing inventories",
        ],
        "highlights": [
            "No surprise licence renewals for unused seats",
            "Offboarding removes access and flags the hardware",
            "Renewal costs forecast a quarter in advance",
        ],
    },
    {
        "slug": "service-management-request-system",
        "name": "Service Management Request System",
        "tagline": "Every request logged, owned, prioritised and closed on time.",
        "description": (
            "A service management request system for internal IT and facilities "
            "support. Staff raise requests against a service catalogue, the system "
            "applies priority and SLA rules automatically, assigns work to the right "
            "engineer, and keeps the requester updated until the request is closed."
        ),
        "audience": "IT service desks and facilities teams",
        "category": "Service Management",
        "icon": "🎫",
        "price_month": 1990,
        "price_setup": 12000,
        "lead_value": 175000,
        "features": [
            "Service catalogue with request forms per service",
            "Automatic priority, routing and SLA clocks",
            "Engineer workload and queue views",
            "Requester updates without chasing anyone",
            "Knowledge-base articles attached to requests",
            "Monthly SLA attainment and backlog reporting",
        ],
        "highlights": [
            "SLA breaches are predicted, not discovered",
            "Staff stop emailing the helpdesk address",
            "Recurring requests become automated workflows",
        ],
    },
    {
        "slug": "offsite-login-timekeeping-system",
        "name": "Offsite Log-In Management System (Time Keeping)",
        "tagline": "Accurate attendance for staff working offsite, with no spreadsheets.",
        "description": (
            "An offsite log-in management system for time keeping that lets remote and "
            "field staff clock in from a phone or browser. It records location, device "
            "and shift start and end, handles leave and overtime approvals, and exports "
            "payroll-ready timesheets for staff who never touch an office network."
        ),
        "audience": "HR managers and operations leads",
        "category": "Time & Attendance",
        "icon": "⏱️",
        "price_month": 1490,
        "price_setup": 8000,
        "lead_value": 145000,
        "demo_url": "https://mjkulit03.github.io/offsite-employee-login/",
        "repo_url": "https://github.com/mjkulit03/offsite-employee-login",
        "features": [
            "Clock-in and clock-out from mobile or browser",
            "Location and device capture with privacy thresholds",
            "Shift rosters, breaks and overtime rules",
            "Leave requests and manager approval",
            "Payroll-ready timesheet export",
            "Anomaly flags for missed or duplicate punches",
        ],
        "highlights": [
            "Timesheets that add up without a manual pass",
            "Approved leave stops counting as worked hours",
            "Anomalies surfaced before payroll runs",
        ],
    },
    {
        "slug": "grocery-sales-inventory-system",
        "name": "Grocery Sales and Inventory Management System",
        "tagline": "Retail stock and sales that reconcile at close, every close.",
        "description": (
            "A grocery sales and inventory management system for retail stores. "
            "Point-of-sale integrates with stock levels so shelf counts stay accurate, "
            "expiry and discount rules reduce waste, supplier purchase orders are driven "
            "by real demand, and daily reconciliation shows margin by product and by "
            "promotion."
        ),
        "audience": "independent grocers and retail managers",
        "category": "Retail & Sales",
        "icon": "🛒",
        "price_month": 1790,
        "price_setup": 12000,
        "lead_value": 200000,
        "features": [
            "Point-of-sale linked to live stock levels",
            "Expiry, markdown and clearance rules",
            "Purchase orders driven by demand and lead time",
            "Margin reporting by product and promotion",
            "Multi-store stock transfers",
            "Daily reconciliation with variance alerts",
        ],
        "highlights": [
            "Fewer markdowns because stock rotates properly",
            "Daily close reconciles in minutes, not hours",
            "Reorder what actually sells, not what looks nice",
        ],
    },
    {
        "slug": "student-record-facial-recognition-system",
        "name": "Student Record with Facial Recognition System",
        "tagline": "Attendance and student records in one secure, auditable place.",
        "description": (
            "A student record system with facial recognition attendance. Enrolment, "
            "guardian details, academic history and attendance live in one record; a "
            "camera at the door matches faces to enrolments to mark attendance "
            "automatically, with consent capture, retention controls and an auditable "
            "access log."
        ),
        "audience": "school administrators and registrars",
        "category": "Education & Attendance",
        "icon": "🎓",
        "price_month": 3290,
        "price_setup": 24000,
        "lead_value": 360000,
        "features": [
            "Student record with guardian and academic history",
            "Face enrolment with explicit consent capture",
            "Automatic attendance marking at the door",
            "Manual attendance override with a reason",
            "Retention and deletion controls for biometric data",
            "Full access audit log",
        ],
        "highlights": [
            "Registers complete before the bell rings",
            "Biometric data stored with consent and retention limits",
            "Every record access is auditable",
        ],
    },
    {
        "slug": "hris",
        "name": "HRIS — Human Resource Information System",
        "tagline": "One employee record from hire to exit, with payroll-ready data.",
        "description": (
            "A human resource information system and HR platform that holds one employee "
            "record from hire to exit: personal details, contracts, positions, leave "
            "balances and payroll inputs. It tracks onboarding and offboarding "
            "checklists, document and licence expiries, and statutory contributions for "
            "SSS, PhilHealth and Pag-IBIG, so payroll and compliance never depend on one "
            "person's spreadsheet."
        ),
        "audience": "HR managers and people operations teams",
        "category": "HR & Payroll",
        "icon": "🧑‍💼",
        "price_month": 2690,
        "price_setup": 18000,
        "lead_value": 280000,
        "features": [
            "Single employee master record from hire to exit",
            "Org chart, positions and reporting lines",
            "Leave credits, filings and approval routing",
            "Payroll inputs with SSS, PhilHealth and Pag-IBIG rules",
            "Onboarding and offboarding checklists with owners",
            "Document, licence and contract expiry alerts",
            "Employee self-service for requests and payslips",
            "Role-based access with a full audit trail",
        ],
        "highlights": [
            "Payroll inputs exported without a manual pass",
            "Expiring documents flag themselves before the audit",
            "Every change to an employee record is attributable",
        ],
    },
    {
        "slug": "project-management-system",
        "name": "Project Management System",
        "tagline": "Scope, schedule and budget on one board your client can trust.",
        "description": (
            "A project management platform that keeps scope, schedule and budget on one "
            "board. Teams plan work as tasks with dependencies, move between kanban and "
            "Gantt views, log time against deliverables, and see budget versus actual "
            "cost before the overrun. Clients get a read-only portal, and every status "
            "update is captured for the weekly report."
        ),
        "audience": "project managers and delivery teams",
        "category": "Project & Work Management",
        "icon": "📋",
        "price_month": 1990,
        "price_setup": 12000,
        "lead_value": 190000,
        "features": [
            "Projects, tasks, subtasks and dependencies",
            "Kanban and Gantt views over the same work",
            "Time logging and timesheet approvals",
            "Budget versus actual cost per project",
            "Client portal with read-only progress",
            "File attachments and comment history",
            "Milestone and deadline notifications",
            "Workload view by person and by team",
        ],
        "highlights": [
            "One board answers where the project actually stands",
            "Budget overruns surface before month-end",
            "Clients stop asking for status updates",
        ],
    },
    {
        "slug": "offline-pos-system",
        "name": "Offline POS System",
        "tagline": "Keep selling when the internet drops, reconcile when it returns.",
        "description": (
            "A point-of-sale system that keeps selling when the internet drops. Each "
            "terminal records sales locally, prints receipts and deducts stock from the "
            "local catalogue, then syncs every transaction to the server when a "
            "connection returns. It handles barcode scanning, returns, voids with manager "
            "approval, cash drawer counts and a Z-read at close, so a retail store can run "
            "a full day without a live connection."
        ),
        "audience": "retail store owners and counter staff",
        "category": "Retail & Sales",
        "icon": "🧾",
        "price_month": 1590,
        "price_setup": 10000,
        "lead_value": 170000,
        "features": [
            "Full offline selling with local persistence",
            "Automatic sync and conflict resolution on reconnect",
            "Barcode scanning and receipt printing",
            "Returns, voids and manager approval",
            "Cash drawer count and end-of-day Z-read",
            "Live stock deduction per terminal",
            "Multi-terminal sync over the store LAN",
            "Sales, margin and item reports by shift",
        ],
        "highlights": [
            "A dropped connection never stops the queue",
            "Every offline sale reconciles when the link returns",
            "Close the day with a Z-read, not a handwritten count",
        ],
    },
    {
        "slug": "cybersecurity-games",
        "name": "Cybersecurity Games",
        "tagline": "Security awareness staff actually finish, with proof they did.",
        "description": (
            "A security awareness training platform delivered as cyber security games. "
            "Short missions cover phishing, password hygiene, social engineering, data "
            "handling and incident reporting; staff earn points on a team leaderboard "
            "while the platform records who completed which module. Administrators run "
            "simulated phishing campaigns and see risk by team, with no classroom time "
            "required."
        ),
        "audience": "security officers and IT training leads",
        "category": "Security Awareness",
        "icon": "🛡️",
        "price_month": 1290,
        "price_setup": 6000,
        "lead_value": 95000,
        "repo_url": "https://github.com/mjkulit03/cybersec_game",
        "features": [
            "Scenario games for phishing, passwords and social engineering",
            "Simulated phishing campaigns with safe landing pages",
            "Team leaderboards and completion tracking",
            "Role-based training paths for staff and managers",
            "Risk scoring by team and by department",
            "Offline mode for air-gapped networks",
            "Certificates and completion evidence for audits",
            "Content updates without re-deployment",
        ],
        "highlights": [
            "Staff practise the attack instead of reading about it",
            "Phishing click rates become a number you can manage",
            "Audit evidence for awareness training in one report",
        ],
    },
    {
        "slug": "file-tracking-system",
        "name": "Online File Tracking System",
        "tagline": "Every physical file accounted for, from registration to archive.",
        "description": (
            "An online file tracking system for physical and digital records. Every file "
            "gets a barcode or QR label, and each movement is recorded as a chain of "
            "custody: who checked it out, which office holds it, when it is due back and "
            "who received it. Overdue files trigger reminders, retention rules flag "
            "records for disposition, and the audit log shows the complete history of a "
            "document from registration to archive."
        ),
        "audience": "records officers and document controllers",
        "category": "Records & Document Management",
        "icon": "🗃️",
        "price_month": 1490,
        "price_setup": 8000,
        "lead_value": 120000,
        "demo_url": "https://mjkulit03.github.io/file-tracking/",
        "repo_url": "https://github.com/mjkulit03/file-tracking",
        "features": [
            "Barcode and QR registration for every file",
            "Chain-of-custody check-out and check-in",
            "Current location by office, room and custodian",
            "Overdue and missing-file alerts",
            "Retention schedules and disposition workflow",
            "Bulk import from existing registers",
            "Search by reference, subject, date or custodian",
            "Complete access and movement audit log",
        ],
        "highlights": [
            "Find who holds a file in seconds, not a phone tree",
            "Overdue records chase their own custodian",
            "Disposition decisions are documented, not remembered",
        ],
    },
]

CATEGORIES: list[str] = sorted({p["category"] for p in PRODUCTS})


def list_products() -> list[dict[str, Any]]:
    """All products, as stored."""
    return list(PRODUCTS)


def list_categories() -> list[str]:
    return list(CATEGORIES)


def products_in_category(category: str) -> list[dict[str, Any]]:
    wanted = (category or "").strip().lower()
    return [p for p in PRODUCTS if p["category"].lower() == wanted]


def find_product(slug: str) -> dict[str, Any] | None:
    """Look up a product by slug, or None if it does not exist."""
    wanted = (slug or "").strip().lower()
    for product in PRODUCTS:
        if product["slug"].lower() == wanted:
            return product
    return None
