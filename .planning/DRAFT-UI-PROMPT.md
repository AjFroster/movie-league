# Design prompt — Movie League draft board

Paste everything below the line into Claude's design tool. It is self-contained.

---

Design three screens for **Movie League**, a fantasy movie league app. Players draft
upcoming films and score points from ratings and box office. The app already exists and has
an established visual system — these new screens must look like they were always part of it,
not like a different product bolted on.

## The existing design system — match this exactly

Dark, editorial, data-dense. Think a well-set sports almanac rather than a SaaS dashboard.
Flat surfaces, hairline dividers, **no drop shadows anywhere**, no rounded-corner cards
floating on backgrounds.

**Colour**

| Token | Hex | Used for |
|---|---|---|
| Background | `#0a0a0f` | page |
| Surface | `#121218` | panels sitting on the page |
| Raised surface | `#17171f` | hover, expanded, selected rows |
| Accent (amber) | `#e0a339` | primary actions, positive points, the one thing on screen that matters most |
| Destructive (red) | `#f2545b` | negative points, at-risk states, errors |
| Info (blue) | `#5b9bd5` | neutral/informational status only |
| Text | `#e4e7f5` | primary |
| Text dim | `#8890ab` | secondary, labels |
| Text faint | `#4d5372` | tertiary, disabled, "no data" |
| Border | `#1c1c26` | hairline dividers |
| Border bright | `#2a2a38` | section boundaries |

Amber is reserved and rationed. It marks the single most important element in a view —
never used decoratively, never for more than a few elements at once.

**Type** — three families, strictly by role:

- **Playfair Display** (serif) — *only* for proper names: a film title, a player's name in a
  heading, the league name. Nothing else. 36px desktop / 28px mobile.
- **JetBrains Mono** — all labels, numbers, table headers, status text, metadata. Uppercase
  with ~0.06–0.08em letter-spacing for labels. 11px labels, 20px headings.
- **Inter** — body prose and helper text only. 14px.

**Spacing** — 4 / 8 / 16 / 24 / 32 / 48 / 64 px only.

**Existing patterns to reuse:** label-above-number stat blocks; hairline-divided flat rows
(not cards); coloured status dot + uppercase mono label; tables with right-aligned numeric
columns; dimming rows that carry no data rather than hiding them.

## Screen 1 — League list (home)

Entry point. Shows every league the user has, and a way to make a new one.

Each league needs: name, year, status (**setup** / **drafting** / **complete**), player
count, and draft progress (e.g. "12 of 24 picks"). A league mid-draft is the most urgent
thing on this screen and should read that way — the user's likely intent is "resume".

Include the empty state: no leagues yet.

## Screen 2 — Create league

A form: league name, year (2026 or 2027), number of rounds (default 6, range 1–30), and a
list of player names (**2–20 players**, added one at a time, removable, no duplicates).

Show the derived consequence of the inputs as they change — *N players × R rounds = T total
picks* — because that number determines how long the draft takes and people get it wrong.

The primary action is "Create league". Starting the draft is a **separate, deliberate step**
on the next screen, because it randomizes the draft order and cannot be undone.

## Screen 3 — Draft board (the important one)

This is where a group sits together and drafts. One shared screen, passed around the room —
**no login, no per-user view**. Whoever is on the clock picks, then hands the laptop on. The
person holding it must be able to tell whose turn it is from across a table.

It must show, simultaneously:

1. **Who is on the clock** — the single most prominent element on the screen. Include the
   pick number and round (e.g. "Round 2 · Pick 7 of 24").
2. **Draft order, with the snake made visible.** Order reverses every round: round 1 runs
   1→2→3→4, round 2 runs 4→3→2→1, round 3 forward again. People misunderstand snake drafts
   constantly — the design should make "you pick next, then not again for a while" obvious
   without explanation.
3. **The available film pool** — up to 300 films for the league's year, ranked by
   anticipation. Each film has a title, release date, and poster. Already-drafted films must
   be visibly unavailable (**shown but struck through / dimmed — not removed**, so people can
   see what's gone). Needs a search box, since a wanted film may be far down the list.
4. **Picks made so far**, ideally grouped by player so everyone can see the rosters forming.

**States to design:**

- **Setup** — league created, draft not started. Prominent "Start draft" action, with the
  order not yet decided. Make clear that starting randomizes the order irreversibly.
- **Drafting** — the main state, described above.
- **Draft complete** — all picks in, rosters final, a route onward to the league standings.
- **Error** — a pick was rejected because someone else took that film or it isn't that
  player's turn. Should be recoverable and non-alarming, not a modal dead end.

**Real data to design against** (do not invent different field names):

```json
{
  "name": "Movie League 2027", "year": 2027, "rounds": 6, "status": "drafting",
  "order": ["Dee", "Cal", "Ann", "Bob"],
  "picks_made": 1, "total_picks": 24,
  "on_the_clock": { "pick": 2, "round": 1, "slot": 2, "player": "Cal" },
  "picks": [
    { "pick": 1, "round": 1, "player": "Dee",
      "tmdb_id": 1003598, "title": "Avengers: Secret Wars" }
  ]
}
```

Real 2027 films for realistic mockups: *Avengers: Secret Wars*, *Spider-Man: Beyond the
Spider-Verse*, *Frozen III*, *Ice Age: Boiling Point*, *Sonic the Hedgehog 4*, *Shrek 5*,
*The Bluey Movie*, *The Beekeeper 2*, *The Lord of the Rings: The Hunt for Gollum*,
*Gremlins 3*.

Real player names to use: Liam, Mark, Andrew, Jaq, Evan.

## Constraints

- **Desktop-first** (a group around one laptop), but the draft board must stay usable at
  768px. It will never be a phone-primary experience.
- **No authentication, no per-user state.** Any person can act for whoever is on the clock.
- Assume **no poster images available** for some films — design a placeholder that does not
  look broken. Many 2027 films have no artwork yet.
- Film titles run long ("The Lord of the Rings: The Hunt for Gollum"). Do not design a layout
  that only works with short titles.
- Draft order is **fixed once the draft starts** and cannot be edited mid-draft.

## What matters most

Someone glancing at the screen from across a room should instantly know **whose turn it is**.
Everything else — pool, rosters, order — is reference material that supports that one
question. Rank the visual hierarchy accordingly.
