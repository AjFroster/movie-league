# Mockup Notes — "Movie League" Reskin

Source: two screenshots supplied by user from Claude UI Builder (claude.ai/design), no downloadable file — transcribed by visual inspection during this session. Treat as the ground-truth design reference for Phase 1 (UI Redesign). If more precision is needed (exact hex values, exact px), ask the user to export/attach the actual mockup file(s).

## Screen 1: "My Team" — roster/team view

URL shown in mock browser chrome: `movieleague.app/l/critics-circle/my-team`

**Top nav bar:**
- Dark bar, app wordmark "MOVIE LEAGUE" (small gold/amber square icon + bold caps text) left-aligned
- Nav links to the right of wordmark: League, My Team (active/underlined), Titles, Trades, Calendar — all caps, small, muted gray except active item in white with underline
- Far right: small muted meta text "LINEUP LOCKS SUN 5:00 PM PT"

**Page header block:**
- Small caps meta line: "2ND OF 10 · 46 NOMS · 9 WINS" (muted gray)
- Large serif team name "The Long Take" (white, big, serif display font — this is the standout typographic choice, contrasts with the mono/condensed caps used everywhere else)
- Right-aligned stat cluster: three stacked stat blocks (label above, big number below) — POINTS (389.0, white), PROJECTED (473, white), SLOTS FILLED (8/8, white)
- Gold/amber filled button "SAVE LINEUP" (dark text on amber bg, rounded corners) far right

**Roster table** (left ~70% width):
- Column headers, small caps muted gray: SLOT | TITLE | STATUS | PTS | PROJ | OWNED
- Each row: slot label (caps, e.g. "BEST PICTURE 1", "LEAD PERF 1", "BENCH", "VAULT"), poster thumbnail (small dark placeholder rect), title in white + small muted subtitle line (director/context), status as colored dot + label, PTS (bold white number), PROJ (muted number), OWNED (muted percentage)
- Status dot colors + labels seen: amber dot "IN CONTENTION", amber dot "PEAKING", amber dot "FRONTRUNNER", red/orange dot "AT RISK", blue dot "STEADY", blue dot "SPECULATIVE", gray dot "BENCHED", gray dot "INELIGIBLE"
- One row (LEAD PERF 1 / Ines Karr) has a highlighted/active row background (subtle dark-gold tint) — appears to be the "currently selected/at-risk-of-locking" row
- Rows for BENCH/VAULT slots show 0.0 pts, grayed out styling — visually deprioritized vs active roster

**Sidebar** (right ~30% width): "THIS WEEK" panel
- List of upcoming event cards, each with: day abbreviation (TUE/THU/FRI/SUN) + tag on the right ("AFFECTS 3 SLOTS", "INDIE FLEX", "ALL SLOTS", "LINEUP LOCK"), bold white headline, muted gray description line below
- Cards separated by thin horizontal dividers, no heavy borders/shadows — flat dark panel

**Below fold (partially visible):** "OPEN ROSTER MOVES" section with two pill buttons "WAIVERS (2)" and "TRADE BLOCK"

## Screen 2: "Nightfall Country" — movie/title detail view

URL: `movieleague.app/titles/nightfall-country`

**Hero header:**
- Full-width dark banner area, faint placeholder text "KEY ART — 1360×236" centered (i.e. intended for a wide key-art image, currently empty/placeholder in mock)
- Below banner, left-aligned: small caps muted meta line "BEST PICTURE POOL · TIER A · MERIDIAN PICTURES" (amber-tinted first segment or all muted — treat as category/pool tag)
- Large serif movie title "Nightfall Country" (same serif display font as team name on screen 1)
- Meta line below title: "DIR. AMARA OKONKWO · 138 MIN · TELLURIDE PREMIERE · WIDE AUG 21" (muted gray, small caps/mono)
- Right-aligned: two buttons — filled amber "CLAIM · WAIVER $14" and outlined "WATCHLIST"

**Stat strip** (5 stat blocks in a row, divided by vertical hairlines):
- SEASON POINTS: 96.5 (large amber number) + "3RD HIGHEST IN LEAGUE" caption
- PROJECTION: 128 (large white number) + "MODEL RANGE 104-151" caption
- NOMS / WINS: 11/2 (large white) + "ACROSS 6 BODIES" caption
- ROSTERED: 84% (large white) + "UP 22 PTS THIS WEEK" caption
- BOX OFFICE: 2.8x (large white) + "MULTIPLIER BONUS +7" caption

**Three-column body:**
1. **POINTS LEDGER** (left, widest column) — itemized list of scoring categories, each row: label + small muted sub-label right-aligned (e.g. "11 NOMS"), a thin horizontal progress/fill bar (amber or blue fill depending on category — amber for point-earning categories, blue for the two lowest bars in the mock: "critics top-ten mentions" and "box-office multiplier"... actually re-checking: fill bar colors alternate amber/blue per row, not obviously rule-bound — flag this as a question for the researcher/user rather than asserting a rule), bold point value right-aligned. Rows: Nominations (11×6)=66, Wins (2×20)=40, Precursor/guild wins=8, Critics top-ten mentions=9, Box-office multiplier=7, Festival premiere=4
2. **CAMPAIGN TRACKER** (middle) — vertical timeline of dated events, each with: status dot (amber=recent/major, blue=minor, gray=older), bold white headline, muted gray date/detail line, right-aligned point delta in amber (e.g. "+24", "+6", "+20"). Reverse-chronological (newest at top).
3. **LEAGUE OWNERSHIP** (right sidebar, narrower) — "ROSTERED BY" callout card with amber-tinted border/bg, shows which fantasy team owns it + which slot; below that "SIMILAR AVAILABLE" list of other titles with pool tag + owned% + point value, in a plain list (no cards/borders, just rows with a small poster thumbnail)

**Bottom (partially visible):** an export/share control bar — "Cancel" / resolution dropdown ("2× (2720 × 1760 px)") / "Download PNG" button. This is a Claude-UI-Builder export affordance, NOT part of the actual app design — exclude from implementation.

## Cross-screen design system (inferred)

- **Background:** near-black (#0a0a0a to #121212 range)
- **Accent:** gold/amber (#e0a339-ish — exact hex TBD, get real value if possible) used for: primary CTA buttons, "in contention/frontrunner/peaking" status dots, positive point deltas, season-points hero number, active nav underline
- **Status colors:** amber = active/good/in-contention, red/orange = at-risk, blue = steady/speculative/informational, gray = inactive/benched/ineligible
- **Typography:** two-font system — serif display face for entity names (team name, movie title) only; everything else (nav, labels, stats, body, meta) uses a monospace or condensed-caps sans, small size, often all-caps with letter-spacing
- **Component patterns repeated across both screens:** status-dot + label pill, stat block (label-above-number), progress/fill bar row, card-free flat list rows separated by hairline dividers (no heavy shadows/borders anywhere), amber-bordered "highlight" callout card (ownership card, active roster row)
- **Spacing:** generous vertical rhythm, comfortable row height in tables, consistent column gutters

## Open questions for UI researcher / user

1. Exact hex values for background, amber accent, status colors (red/blue/gray) — need real swatches or a color-pick pass if the user can export the mockup HTML
2. Serif display font choice (looks like a classic serif — Playfair Display / Georgia-ish — needs confirmation) and the mono/condensed sans for labels
3. Progress-bar color rule in Points Ledger (amber vs blue per row) — inconsistent in the two visible rows, confirm with user or treat as decorative variation
4. Whether "THIS WEEK" sidebar (screen 1) and "CAMPAIGN TRACKER" (screen 2) map to any real backend data source, or are purely illustrative additions beyond current API — flag as scope question, since REQUIREMENTS.md says UI-only/no backend changes
