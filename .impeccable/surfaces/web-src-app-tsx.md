---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

Scope: the PAM web console (all routes under web/src). Mode: Operate.
Audience and job: household customer first (where did my money go this month, what is over budget, what bill is due or missed, fix a wrong category, enter my own records); analyst, reviewer and admin work dense queues behind the same login.
Constraints: PRODUCT.md; money in integer paise formatted en-IN; month in the URL; every list keyset-paged with load more; loading, empty, read-only sample, queued and error states explicit; WCAG 2.2 AA; light and dark.

## Direction contract

THESIS: The month is a ruled hisaab register page, not a dashboard of cards. It refuses the stat-card row plus donut plus sidebar arrangement: figures sit in rupee and paise columns, transfers are written as Contra and struck out of spend, and the naive ledger total is struck through beside the true one.

OWN-WORLD: Cool register white (#F7F9FC) ground with pale blue horizontal rules (#C9D6EA) and one red margin rule (#C8102E); ballpoint blue ink (#1E3A8A) for figures and actions, near-black (#14171F) for text, red ink only for over-budget, missed and struck marks. Ruled tables, not cards; 0 to 2px radius; every rule 1px. Rubber-stamp labels (outlined caps, slight tilt only on the one stamp per page) for states: CONTRA, REFUND, REVERSED, SAMPLE, MISSED. Dark: blue-black page (#0E1420), rules #22304A, ink #8FB0FF, margin red #FF5A6E. Typeface: a workhorse grotesk for UI with tabular figures; amounts always in a right-aligned Rs. | P. column pair.

STORY: The customer opens their month, sees the true spend written at the head with the inflated naive figure struck out and why, scans category lines ruled against their budget limit, then reads entries down the margin by date and fixes anything stamped uncategorized. Staff see the same register grammar as dense queues.

FIRST VIEWPORT: Left: a narrow binding strip with role navigation as tabbed register sections. Top of page: month as the folio heading with previous/next page turn, the true-spend figure large in ink, struck naive figure and income beside it. Below, two columns on desktop: left 60% category lines (name, spend columns, a ruled budget limit line with spend bar of exact length, status stamp), right 40% "needs attention" margin notes (over budget, missed bill, uncategorized count) each a link. Primary action (Add entry, real households) sits in the folio header right.

FORM: Hisaab Register, grounded candidate 3 of 7, seed key bf262100. Signature interaction: on month change the folio turns (rules stay, figures re-ink) and the naive total is struck through with a drawn line; contra and reversed rows render struck with a stamp, never removed.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
