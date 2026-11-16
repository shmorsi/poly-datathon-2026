# EPICENTRE: the film (4:45; hard cap 5:00)

> **Shooting script for the Replay page** (lane D2, Sun 15 Nov; replaces the D Task 16 skeleton). It follows the page top to bottom.
> No number is typed:
> `scripts/fill_docs.py` fills every figure from the final saved runs into this file, from its template
> `docs/templates/video_script.md` (see "How the numbers get in"). Read this filled file aloud; edit only the template. No faces: a product film, screen capture plus one voice.

## The film in one paragraph

Lights on a night Earth are shocks that already happened. Robert, a fictional investor, asks about NVIDIA and the
tariff war in his own words; Claude on Amazon Bedrock reads them into a move and a shock, visibly; the worst tariff shock for his mix
flies home from Washington onto his chart; the move races today's mix in dollars, wins money, and still breaks his floor on the way; the
lamp lands on **Outside your limits, in this 2021–26 replay**, and *ending higher does not mean your limits held*. One drag shows where his
floor first broke. Older crises, by stand-in, show it was not just 2022 (probably milder than the real thing, never the verdict). One number is
pulled down to its prices and recomputed; the AI is switched off to show what it changed; Mateo and Amira get different answers for
different reasons; AWS in four sentences; the film ends on the sealed record Robert may keep. Tagline in English, then in French.

## Voice and wording (binding)

- **Past tense, qualified (R1).** "Outside his limits, in this 2021–26 replay." "In the tariff episodes on record, this mix lost up
  to …". Never "if … flares up", "holds up to", "fits", "safe", "allowed", "you can", "recommend", buy / sell / hold, "you should".
- **Where it breaks (R2).** Say where his floor *first broke*; never name a size as acceptable, never "the limit is …".
- **The money twist (R3, R35).** "It ended higher. It broke his ⟨run:robert:limits.floor|pct0⟩ rule in ⟨run:robert:breaches.0.trough_date|year⟩ and again in
  ⟨run:robert:breaches.1.trough_date|year⟩; it fell below the ⟨run:robert:capacity.line|usd⟩ he can afford in ⟨run:robert:capacity.after.low_date|year⟩." Then, once: "Ending higher does not mean your limits held."
- **His two limits are assumptions (R13, R35).** His tolerance, "no fall of more than … from any high" (the floor), and his capacity,
  "the $… he could afford to lose", both assumed for this fictional profile. Dollars are the path's own: the value at the high and
  at the low of each fall, never "the same fall on his $…".
- **History is not a forecast.** The film says "This already happened; it is not a forecast." once, over the deep-history beat.
  After "fell" or "lost", the size is said without a minus sign.
- **Association, not cause.** A shock is named with its date and what this mix did in the days after it, never as the cause.
- **The AI.** Say what it did and what code did. Never "the numbers are the same with the AI off", never "if Bedrock goes down,
  nothing changes". Saved runs are "recorded on Bedrock on <date>", never shown as live (R15).
- **Plain English**, about 150 words a minute, the investor's name, never "the user". Every number with its unit.

## How the numbers get in

Every figure is a slot: the text `run:‹investor›:‹path›` or `eval:‹path›`, optionally followed by `|‹format›`, between the
mathematical angle brackets U+27E8 and U+27E9 (the filled copy has none left). `run` reads the saved runs in `data/demo_runs/` (Robert's `default.json`, the others' `default_‹investor›.json`; a folder of `‹investor›.json` Results also works), `eval` reads `docs/eval_results.json`.

- **Path:** keys joined by dots; a number indexes a list (`tipping_point.curve.40.end_value`: item 40 of the size curve, which has one point per whole percent);
  `field=value` picks the first list item whose field has that value (`checks.rule=crypto.value`,
  `tipping_point.curve.verdict=Incompatible.weight` is the first size whose verdict was Outside: R2's "first broke at").
- **Formats:** `pct` = the size of a fraction as a percent, one decimal (e.g. −0.1234 → "12.3 %"); `pct0` = whole percent; `spct`
  = signed percent; `usd` = the size in dollars, to the dollar (e.g. "$1,234"); `int` = whole number; `x1` = one decimal; `len` =
  how many items; `year`, `month`, `date` = parts of an ISO date (e.g. "2024", "Jan 2024", "9 Jan 2024"). Rounding is ROUND_HALF_UP.
- **A missing key fails the build**, loudly. Never fill a slot by hand; if a key moved, fix the path, not the number.
- **The screen wins.** The voice is filled from the same final runs the page shows. Beats marked LIVE carry no run-specific number in
  the voice, because the live app's data is rebuilt on the instance and can differ slightly (lane B6 measures it).

## Before the take (gates)

1. The final saved runs are on main (`data/demo_runs/*.json`, recorded on Bedrock at 15:00) and `scripts/fill_docs.py` builds
   `docs/video_script.md` with no missing slot. Read every filled line once against the page.
2. The page passes on the saved runs at 1920×1080: every section's end state correct; motion on (`window.EPI_MOTION`) only where it
   is smooth, a crossfade otherwise (R9); risk stripes off (`window.EPI_STRIPES` stays off: the ledger ruling).
3. LIVE beats (3 and 12): the live app on AWS answers, the guardrail is a numbered version (lane B6), and the advice question of
   beat 12 is one the live input guardrail blocked in lane B4's run ("Should I buy NVIDIA?" was blocked; re-check on the day).
4. Hide the password, the account menu, any account id, bookmarks and notifications. A clean browser profile, zoom 100 %.
5. Capture 1920×1080 at 60 fps (or 2560×1440, scaled down). The cursor moves only when the beat clicks or drags.

## The beats

| # | Time | Beat | Page section | Source |
|---|---|---|---|---|
| 1 | 0:00–0:15 | The shocks on record | `#hero` | saved run |
| 2 | 0:15–0:33 | Robert's question | `#hero` command bar | saved run |
| 3 | 0:33–0:51 | The AI reads it | `#replay` READ | LIVE |
| 4 | 0:51–1:03 | The shock flies home | `#replay` EPICENTRE, HANDOFF | saved run |
| 5 | 1:03–1:29 | The race | `#replay` RACE | saved run |
| 6 | 1:29–1:54 | The verdict | `#replay` VERDICT | saved run |
| 7 | 1:54–2:19 | Where it breaks | the size ruler in `#replay`, then `#money` | saved run |
| 8 | 2:19–2:47 | Not just 2022 | `#deep` | saved run |
| 9 | 2:47–3:07 | One number, all the way down | `#why`, `#thread` | saved run (LIVE for Recompute if possible) |
| 10 | 3:07–3:32 | Switch the AI off | `#why`, `#how` eval card | saved run |
| 11 | 3:32–4:00 | Three investors, three answers | `#investors` | saved runs |
| 12 | 4:00–4:25 | How it works, on AWS | `#how`, the live command bar, CloudWatch | saved run + LIVE |
| 13 | 4:25–4:45 | The record, and the close | `#record`, end card | saved run + edit |
| (14) | 4:45–4:50 | Team card (optional) | edit | — |

## Scene by scene

### 1 · The shocks on record · 0:00–0:15 · saved run

- **Screen.** A fresh load of the page on Robert's saved run. The night Earth, turned to North America, fills the right of the frame;
  the shocks ignite once, in date order (about four seconds): a core, a halo and one ring each, the ring sized by what that shock did
  to this portfolio. One calm caption names the asked family and its count (R7); the rest dim. Legend bottom right; the headline
  *Crash-test your move before you make it.* bottom left. No overlay: the page is the title.
- **Voice.** "Every light is a shock that already happened: tariffs, war and oil, chips, rates. ⟨run:robert:events|len⟩ of them since
  ⟨run:robert:events.0.date|month⟩, each where it began. Each ring is sized by what it did to one investor's money."
- **Never.** A caption per shock (a strobe, cut by R7); "shocks are getting more frequent".

### 2 · Robert's question · 0:15–0:33 · saved run

- **Screen.** Stay on the command bar: Robert's question in his own words, the investor chips (Robert · Mateo · Amira · Too
  Canadian?), the line under it (age, amount, the limit "assumed for this fictional profile", *Fictional illustration, not a
  recommendation.*) and the note on whose limits they are (R4). The cursor moves to **Replay**.
- **Voice.** "Robert, ⟨run:robert:profile.age⟩, retires in ⟨run:robert:profile.horizon_years⟩ years. A fictional
  ⟨run:robert:amount|usd⟩. In his own words: *⟨run:robert:question⟩* His limit, ⟨run:robert:profile.capacity_dollars|usd⟩, is
  an assumption for this fictional profile."

### 3 · The AI reads it · 0:33–0:51 · LIVE

- **Screen.** On the live app on AWS (password typed off camera), press **Replay**. The question lifts into a strip; the five steps
  stream with their service and milliseconds (OBSERVE · UNDERSTAND · COMPARE · EXPLAIN · VERIFY); the navigator's chips land left to
  right: the move, the family *Tariff war*, the precedents; the badge *Amazon Bedrock · Claude* with its time; greyed, the families
  it set aside, each with its one reason. On landing, the steps collapse into one receipt line. If the live app fails, take the
  saved run: the same chips replay from its trace and the badge reads "recorded on Bedrock" with its date (R15), never "live".
- **Caption.** *The navigator: Claude on Amazon Bedrock reads the words* → *Code computes every number*
- **Voice.** "Claude on Amazon Bedrock reads his words: a move, NVIDIA to ⟨run:robert:scenario.change.weight|pct0⟩ of his money; a
  shock, the tariff war; and the earlier tariff episodes to replay. It shows what it set aside, and why. From here on, code computes
  every number."
- **Never.** "A team of agents". The navigator reads; it computes nothing.

### 4 · The shock flies home · 0:51–1:03 · saved run

- **Screen.** The globe zooms, not a long flight (R7), to Washington; one ring fires; the caption names the shock and its date. The
  globe shrinks into the left third and a thin cyan leader drops to that date on the chart's time axis (if the leader was cut, the
  cyan tick and its label carry the thread). With motion off: a crossfade to the same end frame.
- **Voice.** "The worst of them for this mix: ⟨run:robert:events.event_id=liberation_day_2025.title⟩,
  ⟨run:robert:events.event_id=liberation_day_2025.date|date⟩, ⟨run:robert:events.event_id=liberation_day_2025.place⟩. A light on
  the map becomes a day on his chart."
- **Check.** The globe lands on the same event the voice names (the asked family's worst trough with the move). If not, the screen
  wins: change the event id in the three slots above.

### 5 · The race · 1:03–1:29 · saved run

- **Screen.** The chart draws left to right with a date readout: Robert's amount in dollars, today's mix in grey, the move in
  magenta, the gold ribbon under it (*your floor follows every new high*). Where the magenta dips under the ribbon, a red hatch with
  its label and dollars: the ⟨run:robert:breaches.0.trough_date|year⟩ trough (labelled with its backdrop, the Bank of Canada
  raising rates) and the ⟨run:robert:breaches.1.trough_date|year⟩ breach
  (labelled with its shock, "… from its high · = … on …", R13). Cyan ticks mark the tariff shocks. End labels: the two end values.
- **Voice.** "Grey is his mix today; magenta, the move. The gold ribbon is his floor: a ⟨run:robert:limits.floor|pct0⟩ fall from
  any high. In ⟨run:robert:breaches.0.trough_date|year⟩ the move fell from ⟨run:robert:breaches.0.peak_value|usd⟩ to
  ⟨run:robert:breaches.0.trough_value|usd⟩, ⟨run:robert:breaches.0.depth|pct⟩ from its high. In ⟨run:robert:breaches.1.trough_date|year⟩, in the days
  after Liberation Day, it broke the floor again: ⟨run:robert:breaches.1.depth|pct⟩ from its high. It ended at
  ⟨run:robert:tipping_point.curve.40.end_value|usd⟩; without the move, ⟨run:robert:tipping_point.curve.0.end_value|usd⟩."
- **Never.** "He lost $…" (nothing was lost: it is a replay); a dollar drop measured from a later, higher value (R13); "Liberation
  Day caused it".

### 6 · The verdict · 1:29–1:54 · saved run

- **Screen.** The lamp lands, unboxed: the status icon and **OUTSIDE YOUR LIMITS** in condensed caps, *in this 2021–26 replay*
  directly under it (R1), and *Without the move: inside your limits.* Sentence 1 (the money), sentence 2 (the asked shock, in the
  past tense), then the money twist (R3). Leave two seconds of silence on the twist before the last line.
- **Voice.** "Outside his limits, in this replay. Without the move: inside. And the shock he asked about: in the
  ⟨run:robert:turbulence.tariffs.n⟩ tariff episodes on record, this mix lost up to ⟨run:robert:turbulence.tariffs.worst_after|pct⟩,
  more than the ⟨run:robert:limits.scenario_stress|pct⟩ shock limit set for him. It ended higher. It broke his ⟨run:robert:limits.floor|pct0⟩ rule in
  ⟨run:robert:breaches.0.trough_date|year⟩ and again in ⟨run:robert:breaches.1.trough_date|year⟩. … Ending higher does not mean your limits held."
- **Never.** "If the tariff war flares up"; a present-tense verdict ("is outside"); a green or red word without its icon.

### 7 · Where it breaks · 1:54–2:19 · saved run

- **Screen.** Stay on the stage (`#replay`): under the race, the size ruler of NVIDIA, the thumb at the asked size. Drag left
  slowly in one continuous move: the magenta path morphs, the trough marker moves, the readouts roll. At every size but the one
  asked, the lamp says only what the fall did to his floor (*Broke your floor*, *Touched your floor*, *Held above your floor*,
  never a verdict, R20) with *What-if at … instead of the … you asked. A replay, not a recommendation.* The gold notch *Your
  floor first broke at …* sits at the first failing size, the run to its right hatched red; the start-month line under the
  ruler gives the band. Stop on the notch and let go. Then one beat on `#money`: *… of the
  money · … of the risk* and the independent bets, before and after.
- **Voice.** "Drag the size: the same history, replayed at each step. In this replay, his floor first broke at
  ⟨run:robert:tipping_point.curve.verdict=Incompatible.weight|pct0⟩ NVIDIA; depending on the start month, between
  ⟨run:robert:tipping_band.lo|pct0⟩ and ⟨run:robert:tipping_band.hi|pct0⟩. It shows where the past broke his limit; it never marks a
  size acceptable. At ⟨run:robert:scenario.change.weight|pct0⟩, NVIDIA was ⟨run:robert:scenario.change.weight|pct0⟩ of his money and
  ⟨run:robert:risk.after.shares.NVDA|pct0⟩ of his risk."
- **If the page shows no band** (no `tipping_band` in the final run), delete "; depending on the start month, between … and …"
  before filling.
- **Never.** "Robert can hold up to …", "the safe size", "the limit is …". The lamp reads *Inside* at small sizes: let the screen say
  it; the voice never does.

### 8 · Not just 2022 · 2:19–2:47 · saved run

- **Screen.** `#deep`, *Not just 2022* (◐): one row per named crisis, replayed with public stand-ins: today's mix, with the move,
  the stand-in alone, each row marked broke, touched (within a point) or held; the rows where the move did no worse stay on screen
  too. The validation line (the stand-ins against the real funds on 2021–26), the gentle-case note, *probably milder than the real thing, never NVIDIA's
  own history*, *This already happened; it is not a forecast.* Risk stripes stay off.
- **Voice.** "Not just 2022: the page replays the move through ⟨run:robert:deep_history.counts.n⟩ named crises since
  ⟨run:robert:deep_history.episodes.0.trigger_date|year⟩, by stand-in. For NVIDIA, ⟨run:robert:deep_history.gentle_case.label⟩: in the replay's own
  years it fell ⟨run:robert:deep_history.gentle_case.stand_in|pct⟩ while NVIDIA fell ⟨run:robert:deep_history.gentle_case.real|pct⟩,
  the gentle case. Even so, the move broke his floor in
  ⟨run:robert:deep_history.robust_claims.claims.id=after_broke.episodes|len⟩ of them, by
  ⟨run:robert:deep_history.robust_claims.claims.id=after_broke.lo_pp⟩ to
  ⟨run:robert:deep_history.robust_claims.claims.id=after_broke.hi_pp⟩ points. Today's mix came within reach in
  ⟨run:robert:deep_history.robust_claims.claims.id=today_touched.n⟩: too close to call. Probably milder than the real thing, never the verdict. This already
  happened; it is not a forecast."
- **Check.** The voice uses only the robust claims (`deep_history.robust_claims`, the directions that survive the sensitivity runs),
  the same sentence the card leads with; never the raw broke counts.
- **Never.** "NVIDIA in 1973"; "x % of stretches", "the chance", "the odds" (R5: episodes, not percentages).

### 9 · One number, all the way down · 2:47–3:07 · saved run (LIVE for Recompute if possible)

- **Screen.** `#why`: the explanation in three to five sentences, each with its ● ◐ ○ marker; every number is a button. Click the
  worst fall in the money sentence: the `#thread` drawer opens with the facts row (label, value, unit, kind), the trace step that
  computed it (tool, inputs, service, milliseconds), the price rows behind it with their dates, and **Recompute** → *Reproduced ✓*.
  Under the text, the receipt line (numbers traced, guardrail, corrections).
- **Voice.** "Bedrock writes the explanation; code checks it. Every number is a button: the fact, the step that computed it, the
  prices behind it. Recompute: the same number again. The receipt traced ⟨run:robert:receipt.verified⟩ of
  ⟨run:robert:receipt.total⟩ numbers to tool output; a wrong one turns it red, and the explanation is re-asked."
- **On a saved run** the drawer labels Recompute as the build-time check: then say "The build-time recompute: the same number."

### 10 · Switch the AI off · 3:07–3:32 · saved run

- **Screen.** In `#why`, flip *Switch the navigator off*: the keyword reading appears beside the navigator's, and the card *What the
  navigator changed in this run* lists the real differences for Robert's run. Then the labelled case from the blind held-out set
  (R8, R10): a question in French, the keyword reading empty, the navigator's reading *Tariff war*. Scroll to the eval card in
  `#how`: both arms on the blind set, with their intervals.
- **Caption.** *Blind held-out set, ⟨eval:holdout_v2.date|date⟩: navigator ⟨eval:holdout_v2.navigator_k⟩ / ⟨eval:holdout_v2.n⟩
  (95 % Wilson ⟨eval:@wilson(holdout_v2.navigator_k,holdout_v2.n).lo|pct⟩–⟨eval:@wilson(holdout_v2.navigator_k,holdout_v2.n).hi|pct⟩) · keyword rules ⟨eval:holdout_v2.keyword_k⟩ /
  ⟨eval:holdout_v2.n⟩ (⟨eval:@wilson(holdout_v2.keyword_k,holdout_v2.n).lo|pct⟩–⟨eval:@wilson(holdout_v2.keyword_k,holdout_v2.n).hi|pct⟩) · ⟨eval:model⟩ · Measured · the second of two passes (the first: navigator ⟨eval:holdout_v2.first_pass.navigator_k⟩ / ⟨eval:holdout_v2.n⟩)*
- **Voice.** "Switch the navigator off, and the page shows what it changed. Robert's words say levies, not tariffs: keyword rules find
  no shock at all; the navigator read the tariff war and chose its precedents, and the verdict stays the same. In the blind test, a question in French: keyword rules found no shock; the
  navigator read the tariff war. On ⟨eval:holdout_v2.n⟩ blind questions it read the family right ⟨eval:holdout_v2.navigator_k⟩
  times; keyword rules, ⟨eval:holdout_v2.keyword_k⟩."
- **Check.** Say only what the card lists: for the final run, the shock family and the precedents (navigator against none) and
  the same verdict; Robert's words are "⟨run:robert:scenario.read_from⟩". If a re-recorded run's card says the two readings agree,
  say so instead. The French case is eval item `hv2_fr01` (keyword reading empty, navigator
  `tariffs`); never claim a verdict change the card does not show.

### 11 · Three investors, three answers · 3:32–4:00 · saved runs

- **Screen.** `#investors`, *Three investors, three answers*: each card shows the question, the lamp word, one sentence and the check
  that decided it (R14). Click **Mateo**: the stage replays for him, the globe goes to his asked family's epicentre, his lamp lands
  with *in this 2021–26 replay*; the deciding check is his values. Click **Amira**: her lamp; the deciding checks are crypto against
  its cap and her diversification. Optional, three silent seconds: the *Too Canadian?* card, the workshop's own question.
- **Voice.** "Mateo's answer turns on his values: ⟨run:mateo:checks.rule=esg_direct.holding⟩ is held directly, though his values
  screen excludes it, and excluded companies make up ⟨run:mateo:checks.rule=esg_indirect.value|pct⟩ of his money inside his funds.
  Amira takes high risk: her mix fell ⟨run:amira:kpis.max_drawdown.value|pct⟩, inside the ⟨run:amira:limits.floor|pct0⟩ floor set
  for her. But crypto was ⟨run:amira:checks.rule=crypto.value|pct0⟩ against a ⟨run:amira:checks.rule=crypto.limit|pct0⟩ cap, and
  her mix behaved like ⟨run:amira:risk.today.bets|x1⟩ independent bets. High risk is not anything goes."
- **Check.** The voice never says a lamp word for Mateo or Amira: the screen does. If a final run decides on another check, rewrite
  that sentence from the card, never the other way round.

### 12 · How it works, on AWS · 4:00–4:25 · saved run + LIVE

- **Screen.** `#how`: the diagram of this run (question → input guardrail → navigator on Bedrock → code computes → checks → the
  explanation on Bedrock → the receipt → output guardrail → Robert), each node with this run's milliseconds and tokens from the
  trace; the AWS row, one job each; the reconciliation rows (ours · published · source, R12). On a saved run the request ids and
  guardrail results read "recorded on Bedrock on <date>" (R15). Then LIVE: type *Should I buy NVIDIA?* in the live app's command
  bar; the input guardrail stops it and the page points back to the replay. Last, three seconds of the CloudWatch dashboard
  *epicentre*, its time range visible (lane B6's capture; skip the shot if it is absent).
- **Voice.** "On AWS: Claude on Amazon Bedrock does the two language jobs. Bedrock Guardrails screen the question.
  IAM lets the app call Claude Sonnet 5.5, with Claude Sonnet 5 as its fallback, apply our one guardrail and keep sealed records in one bucket. EC2 behind CloudFront serves it;
  CloudWatch shows the calls. Our returns are checked against the issuers' published ones. Ask it for advice, and it declines."
- **Check.** "and keep sealed records in one bucket" stays only if lane B6's private, versioned S3 record bucket is live; otherwise cut those
  four words. Never a live-looking badge on a saved run.

### 13 · The record, and the close · 4:25–4:45 · saved run + edit

- **Screen.** `#record`: Robert's sealed decision record: the move as confirmed, the limits and who set them, the verdict in this 2021–26
  replay today and with the move, both end values and the breaches, the deciding checks, every number with its source, the data
  version and run id, the SHA-256 seal, and *Client-run simulation, not a recommendation or a suitability assessment.* Toggle *Edit
  a number* and change one digit: *Seal broken: this record no longer matches the run.* Undo: the seal is whole again. Cut to
  black: *A checkpoint, not a stop sign.* (1.5 s) → *Crash-test your move before you make it.* / *« Passez votre placement au crash-test avant d'agir. »* (3 s)
  → *Educational simulation. This is not financial advice.* (2 s).
- **Voice.** "The run ends on a record Robert may keep: the move, his limits, both outcomes, every number with
  its source, sealed. Change one number, and the seal breaks. A broker that cannot advise can still show what a move already did.
  EPICENTRE. Crash-test your move before you make it."

### 14 · Team card (optional) · 4:45–4:50

- **Screen.** The team's names as registered for the datathon, the repository address, PolyFinances Datathon 2026 · AlphaForge AI.
  No voice.

## What to record (shot list)

| Shot | Beat | Source | How |
|---|---|---|---|
| S1 | 1 | saved | Fresh load at `#hero`, motion on, hands off for 8 s (the ignition plays once). |
| S2 | 2 | saved | Stay on the command bar 6 s; slow cursor to **Replay** (no click). |
| S3 | 3 | LIVE | The live app: click **Replay**; record until the receipt line lands. A second take on the saved run as the fallback. |
| S4–S6 | 4–6 | saved | Click **Replay** on the saved run; record the whole stage unbroken (zoom, handoff, race, lamp, twist). |
| S7 | 7 | saved | `#replay`'s size ruler: one slow drag from the asked size to the notch (about 4 s), let go; then scroll to `#money`. |
| S8 | 8 | saved | `#deep`: scroll in, stay 10 s, no hover. |
| S9 | 9 | LIVE if possible | `#why`: click the worst fall; in `#thread` click **Recompute**; stay on *Reproduced ✓*. |
| S10 | 10 | saved | `#why`: flip the navigator switch; stay on the card and the labelled French case; scroll to the eval card in `#how`. |
| S11 | 11 | saved | `#investors`: click Mateo, wait for his lamp; click Amira, wait for hers. |
| S12 | 12 | saved + LIVE | `#how` (stay 6 s); the live app: type the advice question, Enter, stay on the stop; the CloudWatch capture. |
| S13 | 13 | saved | `#record`: toggle *Edit a number*, change one digit, stay on *Seal broken*, undo. |
| End | 13–14 | edit | Black cards: the line, the tagline (EN, then FR), the disclaimer, the optional team card. |

Overlays (the captions of beats 3 and 10, the end cards) are added in the edit over untouched footage; a HyperFrames composition
works. Keep them to the page's own words, one line each, 3–4 s, bottom left on the 12-column grid.

## French subtitles

- A separate FR track (`.srt`) made from the **filled** English voice, then read once by a fluent French speaker. The page itself
  stays in English on screen (red gate 9); the subtitles translate the voice, not the interface. The French tagline is the only
  French on screen, once, at the end.
- Numbers keep their filled values and change only their typography: `34,5 %` (comma, no-break space before %), `207 146 $`, dates
  `3 avril 2025`. Never retype a number from memory.
- At most two lines of 42 characters, 1 to 6 s each, cut on the voice's own pauses.

| English | French subtitle |
|---|---|
| Crash-test your move before you make it. | Passez votre placement au crash-test avant d'agir. |
| Outside his limits, in this 2021–26 replay | Hors de ses limites, dans ce rejeu 2021–2026 |
| Inside his limits / Inside, with caveats | Dans ses limites / Dans ses limites, avec réserves |
| his floor (a … fall from any high) | son plancher (une baisse de … depuis tout sommet) |
| Where it breaks | Là où ça casse |
| Not just 2022 · probably milder than the real thing · stand-in | Pas seulement 2022 · sans doute plus doux que la réalité · substitut |
| This already happened; it is not a forecast. | C'est déjà arrivé ; ce n'est pas une prévision. |
| Ending higher does not mean your limits held. | Finir plus haut ne veut pas dire que vos limites ont tenu. |
| Fictional illustration, not a recommendation. | Illustration fictive, pas une recommandation. |
| the navigator (the AI that reads the words) | l'agent navigateur (l'IA qui lit les mots) |
| the receipt · the sealed decision record | le reçu de vérification · le dossier de décision scellé |
| an order-execution-only broker | un courtier exécutant (exécution d'ordres, sans conseil) |
| A checkpoint, not a stop sign. | Un point de contrôle, pas un panneau d'arrêt. |
| Educational simulation. This is not financial advice. | Simulation éducative. Ceci n'est pas un conseil financier. |

## If it runs long (cut in this order)

1. The *Too Canadian?* glimpse (beat 11). 2. The `#money` tail of beat 7. 3. The CloudWatch shot (beat 12). 4. "Our returns are
checked against the issuers' published ones." 5. The team card. Never cut: the verdict in dollars, the money twist, *Where it
breaks*, the AI-off beat, the one number pulled to its data, the AWS sentences, the sealed record, the disclaimer.

## Takes and delivery

- **Main take:** Sunday evening, after the 15:00 final runs and the redeploy: beats 3, 9 and 12 on the live app, the rest on the
  saved runs (the static build or the local server on the same final runs). **Backup take:** Monday morning, before the AWS
  accounts close.
- **Voice:** one voice, recorded separately from the filled script, about 150 words a minute, room tone under the cuts; no music, or a
  quiet bed well under the voice. The page's own motion is the show: no extra zooms or effects.
- **Check after the edit:** every number heard and every number seen against `docs/video_script.md`, line by line. A number
  that differs from the screen is re-filled from the run on screen, never argued.
- **Export:** 1920×1080 H.264, at most 5:00, with the EN and FR `.srt` files; the saved runs used are kept next to the video file.
- **Finals (Friday, no AWS):** the same film; the live demo becomes the saved runs on the static demo, and every AWS screen shows the
  recorded evidence, labelled "recorded".

## Numbers sheet

Kinds as in the Result's facts rows: ● fact (computed from data) · ◐ assumption (a limit, a rule, a stand-in) · ○ fiction (the
investor, the amount, the move). Dollars at the worst are ○: a fictional amount times a real fall.

| Slot (run: robert unless named) | What it is | Kind | On the page | Beat |
|---|---|---|---|---|
| `events\|len` · `events.0.date\|month` | shocks on record; the month of the first | ● | `#hero` legend | 1 |
| `profile.age` · `profile.horizon_years` · `amount\|usd` | Robert, his horizon, his amount | ○ | `#hero` line | 2, 5 |
| `profile.capacity_dollars\|usd` | his capacity, the loss he could afford, assumed | ◐ | `#hero` line | 2 |
| `question` | his words, verbatim | ○ | command bar | 2 |
| `scenario.change.weight\|pct0` | the size of the move | ○ | READ chip, the size ruler | 3, 7 |
| `events.event_id=liberation_day_2025.title` · `.date\|date` · `.place` | the shock the globe flies to | ● | EPICENTRE caption | 4 |
| `limits.floor\|pct0` | his floor, a fall from any high | ◐ | the gold ribbon | 5 |
| `breaches.0.trough_date\|year` · `breaches.0.depth\|pct` · `breaches.0.peak_value\|usd` · `breaches.0.trough_value\|usd` | the first floor break and its own dollars, at the high and at the low | ● · ○ | race label | 5 |
| `breaches.1.trough_date\|year` · `breaches.1.depth\|pct` | the second floor break | ● | race label | 5 |
| `tipping_point.curve.40.end_value\|usd` · `tipping_point.curve.0.end_value\|usd` | end values with and without the move | ● | race end labels | 5 |
| `turbulence.tariffs.n` · `turbulence.tariffs.worst_after\|pct` | tariff episodes on record; the worst for this mix | ● | verdict, sentence 2 | 6 |
| `limits.scenario_stress\|pct` | the shock limit (half his floor) | ◐ | verdict, sentence 2 | 6 |
| `tipping_point.curve.verdict=Incompatible.weight\|pct0` | the first size whose verdict was Outside | ● | the ruler's notch | 7 |
| `tipping_band.lo\|pct0` · `tipping_band.hi\|pct0` | that size across start months | ● | the start-month line under the ruler | 7 |
| `risk.after.shares.NVDA\|pct0` | NVIDIA's share of the risk with the move | ● | `#money` | 7 |
| `deep_history.counts.n` · `deep_history.episodes.0.trigger_date\|year` | named crises; the first one's year | ◐ | `#deep` | 8 |
| `deep_history.gentle_case.label` · `.stand_in\|pct` · `.real\|pct` | NVIDIA's stand-in, and how much gentler it fell | ◐ · ● | `#deep` note | 8 |
| `deep_history.robust_claims.claims.id=after_broke.episodes\|len` · `.lo_pp` · `.hi_pp` · `claims.id=today_close.n` | the robust claims: where the move broke the floor, by how many points; where today's mix came close | ◐ | `#deep` headline | 8 |
| `receipt.verified` · `receipt.total` | numbers the receipt traced | ● | `#why` receipt line | 9 |
| eval: `holdout_v2.n` · `.navigator_k` · `.keyword_k` · `.date\|date` · `model` | the blind held-out eval | ● Measured | `#how` eval card | 10 |
| eval: `@wilson(holdout_v2.navigator_k,holdout_v2.n).lo\|pct` · `.hi` · the same for `keyword_k` | their 95 % Wilson intervals, computed by the filler with the formula of `scripts/eval.py` | ● | `#how` eval card | 10 |
| mateo: `checks.rule=esg_direct.holding` · `checks.rule=esg_indirect.value\|pct` | the excluded company held directly; excluded names inside his funds | ● | Mateo's card | 11 |
| amira: `kpis.max_drawdown.value\|pct` · `limits.floor\|pct0` | her worst fall; the floor set for her | ● · ◐ | Amira's card | 11 |
| amira: `checks.rule=crypto.value\|pct0` · `checks.rule=crypto.limit\|pct0` · `risk.today.bets\|x1` | crypto against its cap; independent bets | ● · ◐ | Amira's card | 11 |

Every slot fills from the 09:41 saved runs and today's `docs/eval_results.json`; lane B3's keys (`tipping_band`, `deep_history`,
`deep_validation`, `ladder`, `reconciliation`, `not_2022`, `navigator_effect`) are among them. The Wilson bounds are computed by
the filler (`@wilson(k,n)`), so they need no key.

---
Educational simulation. This is not financial advice.
