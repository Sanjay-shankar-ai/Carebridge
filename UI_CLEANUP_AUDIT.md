# CareBridge: UI Cleanup Audit (Step 0)

> Generated: 2026-11-20 | Branch: ui-cleanup-production-polish | Scope: frontend only

---

## 1. AI Entry Points — KEEP / REMOVE

### PATIENT dashboard (`app/patient/page.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L204–208 — Welcome banner | `<Button>Ask CareBridge AI</Button>` → `/chat` | **KEEP** (primary chat entry point) |
| L489–494 — Appointment card footer | `<Link href="/chat">Request Reschedule</Link>` with Clock icon | **REMOVE** — not AI, but label is confusing; replace footer text with "Questions? Contact your coordinator." |
| L548–554 — Care Coordinator card footer | `<Button>Consult Care Companion</Button>` → `/chat` | **REMOVE** — duplicate chat link |
| L559–581 — Full-width banner card | `<Sparkles>` icon + "CareBridge AI Clinical Companion" heading + `<Button>Open AI Chat</Button>` | **REMOVE** — entire card is redundant; already one chat button in welcome banner |

**Net result for Patient:** 1 chat entry (Welcome banner) remains.

---

### DOCTOR dashboard (`app/doctor/page.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L788–818 — Right column "AI Clinical Co-Pilot" card | `<Sparkles>` icon + "Clinical Co-Pilot" heading + summary stats + `<Button>Consult Doctor Subgraph</Button>` | **KEEP stats text**; **REMOVE** Sparkles icon, rename card to "Clinical Summary", remove button — replace with plain link "Chat with AI Assistant →" |
| L791 | `<Sparkles className="w-4 h-4 text-[#0F766E]" />` decorative sparkle | **REMOVE** |
| L814–816 | `<Button>Consult Doctor Subgraph</Button>` → `/chat` | **REMOVE button**; convert to plain link |

**Net result for Doctor:** 1 chat entry (sidebar "Clinical AI Chat") remains.

---

### COORDINATOR dashboard (`app/coordinator/page.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L521 — Recovery card "Trigger Play" button | `leftIcon={<Sparkles>}` decorative sparkle on action button | **REMOVE** sparkle icon; replace with `RotateCcw` |
| L456 — Stalled Care Radar subtitle | `"Cognitive Recovery Agent detects patient barriers..."` | **REWRITE** — see §2 |
| L773 — Upload modal title | `"Upload Diagnostic Test Report & AI Doctor Staging"` | **REWRITE** — see §2 |
| L778–780 — Upload modal body | `"CareBridge AI will parse the disease condition..."` | **REWRITE** — see §2 |

**Net result for Coordinator:** 1 chat entry (sidebar "Patient AI Chat") remains.

---

### SIDEBAR (`components/Sidebar.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L46 — Doctor nav | `"AI Clinical Assistant"` | **RENAME** → `"Clinical AI Chat"` |
| L53 — Patient nav | `"CareBridge AI Chat"` | **KEEP** |
| L65 — Coordinator nav | `"AI Patient Chat"` | **RENAME** → `"Patient AI Chat"` |
| L66 — Coordinator nav | `"AI Activity Monitor"` | **KEEP** (functional label) |
| L147–149 — Demo switcher | `<Sparkles> Switch Persona (Demo)` | **KEEP** (dev tool, clearly labeled) |

---

### HEADER (`components/Header.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L84–92 — Patient CTA | `<Button>Ask CareBridge AI</Button>` → `/chat` | **REMOVE** — duplicates the Welcome banner button on patient dashboard |
| L75–78 — Protocol pill | `"Screening-to-Care Protocol"` | **KEEP** |

---

### NOTIFICATION CENTER (`components/NotificationCenter.tsx`)

| Location | Element | Verdict |
|---|---|---|
| L199 — Fallback icon | `<Sparkles>` as default notification icon | **REPLACE** with `<Bell>` |

---

## 2. AI / LLM Strings to Rewrite

| File | Current | Rewrite |
|---|---|---|
| `patient/page.tsx` L567–568 | `"CareBridge AI Clinical Companion"` | (Remove entire card) |
| `patient/page.tsx` L571 | `"The AI Companion has full context..."` | (Remove entire card) |
| `coordinator/page.tsx` L456 | `"Cognitive Recovery Agent detects patient barriers..."` | `"Identifies stalled journeys and proposes coordinator interventions"` |
| `coordinator/page.tsx` L773 | `"Upload Diagnostic Test Report & AI Doctor Staging"` | `"Upload Diagnostic Test Report"` |
| `coordinator/page.tsx` L778` | `"CareBridge AI will parse... dispatch an instant patient notification."` | `"Upload patient findings. The system will parse urgency, match a specialist, and notify the patient."` |
| `coordinator/page.tsx` L736 title | `"Upload Test Report & AI Doctor Staging"` | `"Upload Test Report"` |
| `doctor/page.tsx` L792 | `"Clinical Co-Pilot"` heading | `"Clinical Summary"` |
| `doctor/page.tsx` L814 | `"Consult Doctor Subgraph"` button | Replaced by plain `"Chat with AI Assistant →"` link |
| `admin/page.tsx` L209 subtitle | `"Latest LangGraph node executions and tool invocations"` | (page will be deleted) |
| `Sidebar.tsx` L46 | `"AI Clinical Assistant"` | `"Clinical AI Chat"` |
| `Sidebar.tsx` L65 | `"AI Patient Chat"` | `"Patient AI Chat"` |
| `NotificationCenter.tsx` L199 | `<Sparkles>` icon | `<Bell>` |

---

## 3. Long Vertical Scroll Pages

### PATIENT (`/patient`)
Sections stacked top-to-bottom:
1. Welcome banner (tall card)
2. Screening result notification banner
3. Screening result educational card (3 info blocks + reassurance box)
4. **14-stage grid** (7-col grid of 14 cards — biggest scroll contributor on mobile)
5. 2-column: Next appointment + Care coordinator cards
6. AI companion banner *(to be removed)*

**Problem:** Items 3–5 produce 1,500+ px vertical scroll on mobile. The 14-stage grid has no progressive disclosure.

**Fix (Step 2):** Tabs — **Overview** (banner + appointment + notification) | **My Journey** (compact stepper) | **Appointments** | **Messages**

---

### DOCTOR (`/doctor`)
Sections stacked:
1. Page header + 4 KPI cards
2. Conditional escalation alert banner
3. 12-column grid: patient table (8 cols) + appointments + "Clinical Co-Pilot" (4 cols)
4. **Evidence-based closure checklist** (5 static "Verified" items — always rendered)
5. Inbound referrals card (top 3)
6. 6 modals mounted in DOM

**Problem:** Left column stacks table → checklist → referrals with no tabs. Closure checklist always visible even when not closing a case.

**Fix (Step 2):** Tabs — **Overview** (KPIs + escalation) | **My Patients** (table) | **Reviews** (clinical review) | **Appointments** | **Closure** (checklist + closure modal trigger)

---

### COORDINATOR (`/coordinator`)
Sections stacked:
1. Page header + 4 action buttons
2. Conditional escalation banner
3. 4 KPI cards
4. Stalled Care Radar (3-col grid, shows 3 cards)
5. **Cross-facility referrals** (all referrals — no limit shown)
6. **All Active Cases table** (all cases, no pagination)

**Problem:** Referrals and cases table have no pagination. At scale this is an infinite scroll page.

**Fix (Step 2):** Tabs — **Overview** (KPIs + radar) | **Referrals** | **Recovery & SLA** | **All Cases**. Pagination: 15 rows per page.

---

## 4. Layout Problems

### PATIENT

| Issue | Severity |
|---|---|
| 3 duplicate chat CTAs | 🔴 High |
| Redundant "AI Clinical Companion" banner card | 🔴 High |
| 14-stage grid has no horizontal connector / stepper UX on mobile | 🟡 Medium |
| `alert()` used for download errors | 🟡 Medium |
| Hardcoded fallback strings ("Meenakshi Ramanathan", etc.) | 🟢 Low |
| No per-page `<title>` tag | 🟢 Low |

### DOCTOR

| Issue | Severity |
|---|---|
| `<Sparkles>` misleading in "Clinical Co-Pilot" card | 🟡 Medium |
| "Consult Doctor Subgraph" is internal jargon | 🟡 Medium |
| `alert()` used for errors in 6+ handlers | 🟡 Medium |
| Closure checklist always rendered (5 static items all "Verified") | 🟡 Medium |
| No pagination on patient table | 🟢 Low |
| `icon` prop name bug in admin page Button (should be `leftIcon`) | 🟢 Low |

### COORDINATOR

| Issue | Severity |
|---|---|
| `<Sparkles>` on "Trigger Play" action button | 🟡 Medium |
| `alert()` / `confirm()` / `prompt()` in 6 handlers | 🟡 Medium |
| No pagination on cases table | 🟡 Medium |
| AI-branded modal title/body | 🟢 Low |

### SHARED / GLOBAL

| Issue | Severity |
|---|---|
| **`app/admin/page.tsx` exists** — violates no-Admin-role rule; route `/admin` is reachable | 🔴 **Critical** |
| Header duplicate patient chat button vs. dashboard | 🔴 High |
| NotificationCenter missing "View all notifications" link | 🟡 Medium |
| `<Sparkles>` as default notification icon | 🟡 Medium |
| Sidebar has no mobile hamburger / collapse | 🟡 Medium |
| No 404 or 403 pages | 🟡 Medium |

---

## 5. `npm run lint` Result (Step 0)

**Status:** ESLint was not configured. `next lint` prompted interactively (no `.eslintrc.json` existed).
**Action taken:** Created `c:\CareBridge\frontend\.eslintrc.json` with `{ "extends": "next/core-web-vitals" }`.
**Rerun lint** will be reported with exact output at end of Step 1.

---

## Git Status (Step 0)

- Repository initialized in `c:\CareBridge\frontend`
- Branch `ui-cleanup-production-polish` created from initial commit
- `.eslintrc.json` added

---

## Consolidated Change Plan

### Step 1: Remove AI Clutter
1. **Delete** `app/admin/page.tsx` (no Admin role)
2. **Remove** patient AI companion banner card (patient/page.tsx L559–581)
3. **Remove** header duplicate chat button (Header.tsx L84–92)
4. **Remove** 2 duplicate chat links (patient page L489–494, L548–554)
5. **Remove** `<Sparkles>` from coordinator "Trigger Play" button
6. **Remove** `<Sparkles>` from doctor "Clinical Co-Pilot"; rename card to "Clinical Summary"
7. **Remove** "Consult Doctor Subgraph" button; add plain chat link
8. **Replace** `<Sparkles>` default notification icon with `<Bell>`
9. **Rewrite** all AI-branded labels per §2 table
10. Run `npm run lint`, `npm run build`, report exact output
11. Commit: `"Step 1: Remove AI clutter, rename labels, delete admin page"`

### Step 2: Fix Long Scroll
- Tabbed layouts per role (see §3)
- Compact 14-stage stepper (horizontal desktop, vertical mobile)
- Pagination on cases table (15/page)
- Collapsible/move closure checklist to Closure tab

### Step 3: Design System
- Extend Tailwind with status color tokens (grey/amber/blue/green/red/purple)
- Add `KPICard`, `PageHeader`, tab wrapper components
- RTL via logical CSS properties
- Verify contrast and focus states

### Step 4: Production Readiness
- Replace `alert()`/`confirm()`/`prompt()` with toast + modal patterns
- Add "View all notifications" link in NotificationCenter
- Skeleton loaders, error states with Retry button
- 404 and 403 pages
- `<title>` tags per page
