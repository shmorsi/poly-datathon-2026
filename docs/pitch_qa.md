# EPICENTRE: the pitch and the hard questions (finals, Fri 20 Nov)

Most AI investing demos recommend a trade. An order-execution-only broker such as National Bank Direct Brokerage may not; EPICENTRE shows what the move already did, against the investor's own limits.

> **How to use it.** Answer in one breath, then show it on the page: every answer ends with **Show**, the section and the click.
> If a question is not here, answer with what the page shows and nothing more.
> No number is typed: `scripts/fill_docs.py` fills each figure
> from the final saved runs into this file, from its template `docs/templates/pitch_qa.md` (the grammar: `docs/templates/video_script.md`,
> "How the numbers get in").
> Friday runs without AWS: the saved real runs on the static demo, each labelled "recorded on Bedrock on <date>".

## The pitch lines

- **The headline.** "Crash-test your move before you make it." « Passez votre placement au crash-test avant d'agir. »
- **10 seconds.** "It never tells Robert what to buy. It shows where his own line broke, and proves every number."
- **The thesis.** "It made money and still broke his floor. Ending higher does not mean your limits held."
- **30 seconds.** "Robert, 59, wants 40 % of his $600,000
  in NVIDIA. His broker is order-execution-only: it cannot tell him what to do. EPICENTRE shows him what that move already did. In
  this 2021–26 replay it ended higher, $1,847,077 against
  $911,676, and on the way it broke both limits assumed for him: from
  $623,398 it fell to $408,174, 34.5 % from its high, past his 15 % rule and below the
  $510,000 his $90,000 capacity allows. Ending higher does not mean your limits held. We never tell
  him what to buy: we show where his own line broke, and we prove every number."

## Never say (on stage, in the Q&A, in the hallway)

"safe", "fits", "allowed", "you can", "holds up to", "recommend", buy / sell / hold as advice, "you should", "if the tariff war flares
up" (say "in the tariff episodes on record"), "he said he could absorb" (say "the loss he could afford, assumed for this fictional
profile"), "NVIDIA's history since the 1970s", "x % of stretches", "the chance" or "the odds", "the numbers are the same with the AI
off", "if Bedrock goes down nothing changes", "a team of agents", "live" for a saved run.

## 1. Is it advice?

### 1.1 "Isn't this advice?"
**Answer.** No. It never says what to do; it says what already happened to this exact move, against the investor's limits.
Every sentence is in the past tense, and the verdict always carries "in this 2021–26 replay"; the size ruler under the race names where the
floor first broke, never a size that is acceptable; no account is ever read. For the four fictional investors, the limits are assumed from the profile's risk band (data/personas.json over config.py, read by governance.load_limits; the floor from the loss the profile is assumed to absorb, when that is tighter); only the limits a user types in the live app's editor are typed by the user. It is decision support,
not a suitability assessment: order-execution-only brokers may not give advice (CIRO rules); EPICENTRE is designed to make no
recommendation, subject to the broker's compliance review.
**Show.** The lamp and the line under it (`#replay`); the note under the command bar on whose limits they are; the record's *Client-run simulation, not a recommendation or a suitability assessment.* (`#record`).

### 1.2 "So your tool told my client 8 % NVIDIA is fine?"
**Answer.** No. It shows where the past broke the limit assumed for him. In this replay his floor first broke at
9 % NVIDIA, and depending on the start month the first break moves
between 9 % and 35 %. It never marks a size acceptable, never reads his
profile, and records what he saw.
**Show.** The size ruler under the race in `#replay`: the notch (*Your floor first broke at …*), the start-month line under it,
and at any other size *What-if at … instead of the … you asked. A replay, not a recommendation.*
**Never say.** The size below the notch, as a number to pick.

### 1.3 "Why don't you propose an allocation?"
**Answer.** Because an order-execution-only broker cannot, and because the case names the trap: "the best historical return is the
best investment". A proposed mix would be advice, and it would be fitted on hindsight: NVIDIA is in the universe because it won. The
investor brings the move; we replay it against his limits. What we do show instead: where the floor first broke, and the same
40 % in three places, against his 15 % floor: in the broad US market it fell
14.2 %, in the Nasdaq-100 fund 18.4 %,
in NVIDIA 34.5 %. That separates more stocks from one industry from one company.
**Show.** The size ruler in `#replay`; the ladder in `#money`; every fictional mix labelled *Fictional illustration, not a recommendation.*

### 1.4 "Robert never said he could absorb $90,000."
**Answer.** Right: he is fictional, and the page says so. He has two limits, both assumed for this fictional profile, as the
finance workshop separates them: his tolerance, no fall of more than 15 % from any high (the floor check, the
ruler and the band use it), and his capacity, the $90,000 he could afford to lose (stay above $510,000). Each fall is told
in the money's own dollars, at its high and at its low. A real investor sets his own in the live editor; the page never
reads one from an account. The other starting limits (one company 10 %, one sector
35 %, crypto 0 % for an investor who wants none) are EPICENTRE's illustrative
starting values; in use, the client sets them: a broker would never set them for a client.
**Show.** The line under the command bar; *Your limits* at the top of `#checklist` and, in the live app, *Edit your limits*, then
*Check again* (the same run judged on the new limits); the limits and who set them, on the record (`#record`).

### 1.5 "What if he just asks: should I buy NVIDIA?"
**Answer.** Bedrock Guardrails stop the plain request at the door, then a code check (`advice_guard.py`) stops a request for advice,
a size, permission or a forecast before any model reads it, and the page points back to the replay. The two checks are layers, not
the promise, and both miss some rephrasings. On a blind set written before anyone read the check, they stopped
41 / 60 of its must-block questions (95 % Wilson
55.8 %–78.7 %) and passed
59 / 60 benign questions. The check was then tuned on
those misses, so that set is in-sample now: a regression pin, never a rate. On a second blind set, written after the tuning, they
stopped 39 / 50 (95 % Wilson
64.8 %–87.2 %) and passed
50 / 50 benign questions · no model ·
15 Nov 2026 · Measured · limit: one of our agents wrote and labelled both sides of each set. The
promise is structural: no part of the system writes a recommendation. Code decides the verdict; the explanation is checked by the
receipt, which treats advice and forecast words as defects and has the explanation re-asked.
**Show.** Live: type the question in the command bar. Friday: the eval card in `#how`; the measured rates are in
`docs/eval_results.md` (section 6a, k / N with Wilson intervals).
**Never say.** "It blocks every advice question." The in-sample result, as if it were a rate.

## 2. Data and history

### 2.1 "Is five years enough?"
**Answer.** No single window is, so we do not lean on one. Five years of real daily prices decide the verdict because that is where
every fund has real data in CAD, and it holds 2022, when stocks and bonds fell together. Three checks around it never change it: leave
2022 out and the move still broke his floor in 2025, 16.9 % from its
high; move the start month and the first break moves between 9 % and
35 % (two falls decide it: 2022 for the early starts, early 2025 alone for the later ones); and 11 named crises since
1973, by stand-in, probably milder than the real thing.
**Show.** The second red hatch on the race; the start-month line under the size ruler in `#replay`; `#deep`, *Not just 2022*.

### 2.2 "How can you replay NVIDIA before it existed?"
**Answer.** We don't, and the page says so. For the older crises a stand-in replaces each line: the Canadian market for the index
fund, a government bond ladder, gold, T-bills, and for NVIDIA the US chip and electronics industry. An industry
falls less than its most volatile company, so the stand-in is the gentle case: it can show the floor broke, never that it held. We
checked the stand-ins first, against the real funds in the replay's own years: today's mix by stand-in fell at worst
8.7 %, against 10.6 % with the real funds; NVIDIA itself
fell 60.2 % while its industry fell 27.0 %.
**Show.** `#deep`: the stand-in row, the validation line, the gentle-case note, *probably milder than the real thing, never NVIDIA's own history*.
**Never say.** "NVIDIA in 1973."

### 2.3 "What if the past does not repeat?"
**Answer.** It won't, exactly. This is a crash test, not a forecast: it shows what this exact move already did to money like his,
against limits set before looking. The page never says what will happen; every history panel says "This already happened; it is
not a forecast." The value is the comparison under the same history: today's mix against the move, the same shocks, the same floor.
**Show.** The two lines of the race; the footer's limits.

### 2.4 "You picked the shocks, and NVIDIA, with hindsight."
**Answer.** Yes, and we say it first. The 37 shocks were chosen in 2026 as questions to test, not as a sample,
each with its public source; NVIDIA is in the universe because it won. That makes the twist stronger, not weaker: even the winner
broke his floor on the way. What hindsight cannot touch is the arithmetic: every number is recomputed from dated prices, and nothing
dated after the decision reaches a tool.
**Show.** The footer's limits; a shock's source link on the globe caption or in `#thread`.

### 2.5 "Your rolling windows overlap; a share of them is not a probability."
**Answer.** Agreed, which is why the page shows no "% of stretches". Overlapping windows are far fewer independent cases than they
look, and a share of them reads as odds. We show episodes instead: named crises, each marked broke, touched (within a point) or held,
including the ones where the move did no worse, and only the claims that survive the sensitivity runs. With the move, his floor
broke by 5 to
35 points in
4 crises; today's mix came within reach in
3, too close to call. The stripes exist behind a flag and stay off.
**Show.** `#deep`: the broke / touched / held marks and the no-worse rows.

### 2.6 "Monthly data hides the lows."
**Answer.** It does, and that is one more reason the deep card is probably milder than the real thing and never the verdict. Month-end closes, an
industry instead of one company, and a bond ladder without credit risk all make a break rarer, so the card can support "it broke",
never "it held". The verdict itself runs on daily prices.
**Show.** `#deep`'s honesty block; the daily race above it.

### 2.7 "Recompute proves it is reproducible, not that it is right."
**Answer.** Correct, so we also check against the outside world: our returns against the issuers' published returns for the same
funds and periods, each with its source. For XIU.TO (Year to date to 2026-11-12 (NAV)):
ours 17.99 %, published 17.93 %. And tests pin the finance rules (the rounding, the look-ahead cut, the currency conversion).
An independent re-implementation, sharing no code with the engine, reproduced all 32 headline figures and 33 deep-history values.
**Show.** The reconciliation rows in `#how` (ours · published · source); `docs/finance_methods.md`, section 7; `docs/audit_independent.md`.

### 2.8 "Is the floor a percentage or dollars? And what is the shock limit?"
**Answer.** Both, as two limits. The floor is his tolerance, a 15 % fall from any high, so it follows every new
high; his capacity is the $90,000 he could afford to lose. Each fall keeps its own dollars: the
2025 break went from $1,473,670 to $1,224,257, 16.9 % from its high. The shock
limit, 7.5 %, is a rule of thumb, half the 15 % rule: a softer check that shows Caution. On its own it can add caveats to the verdict, never turn it to Outside: only a hard limit, like the
floor, does that.
**Show.** The gold ribbon and the breach labels on the race; the checklist's tier tags (`#checklist`).

### 2.9 "Why the first break and not the last size that held?"
**Answer.** Because in Robert's run the size below the first break reached the floor within a rounding step, and naming it would
read as permission. The honest statement is the first size that broke, with the band across start months beside it.
**Show.** The size ruler in `#replay`: the notch, the start-month line, and the readouts at the two sizes either side of it.

## 3. The AI

### 3.1 "What if the AI is wrong?"
**Answer.** Then you see it, and code catches what matters. The navigator only reads: a move, a shock family and its precedents,
shown as chips beside what it set aside; code checks its picks against the catalogue and computes every number. The explanation is
checked number by number: in Robert's run the receipt traced 15 of 15 numbers to
tool output; a wrong number turns it red, names the line and has the explanation re-asked, and if it still fails the page shows the
code-written explanation and says why.
**Show.** The READ chips (`#replay`); the receipt line, then a number's `#thread` drawer (`#why`).

### 3.2 "Isn't the agent just a parser?"
**Answer.** On a clean sentence, keyword rules often find the family too. Robert's words ("Washington slaps new levies on Canadian goods") name no
tariff, so they find no shock at all; the navigator read the tariff war and chose its precedents, and switching it off shows that
difference. Switching it off changes no verdict in the four saved runs; it changes the question answered: without it, Robert's
shock check replays every family's earlier episodes (worst 13.6 %) instead of the 6 tariff war episodes he asked about
(worst 9.0 %). The navigator earns its place where words are messy: on 48 blind questions it read the shock family right 44 times,
keyword rules 31; the gap is widest in French and in paraphrases, where no keyword matches. It also asks
when a limit is missing and abstains when no precedent is close. Switch it off, and the page shows what it changed in this run.
**Show.** `#why`: *Switch the navigator off*, the card *What the navigator changed in this run*, the labelled French case.

### 3.3 "37 / 40 on your own questions is tuning. What is the held-out score?"
**Answer.** Agreed: a score on the questions you tuned on proves little. So a separate Claude agent of ours (not an independent person) wrote and
labelled a blind set before it saw the development set: 48 questions in French, slang, typos, headlines, advice bait, no-precedent
cases and paraphrases, pinned by hash before the run, never tuned on, measured in two passes. The first pass scored the shock
families only: navigator 43 / 48, keyword rules
31 / 48. The second, on a later navigator, kept every reading whole: navigator
44 / 48 (95 % Wilson
80.4 %–96.7 %), keyword rules 31 /
48 (50.4 %–76.6 %), us.anthropic.claude-sonnet-5-5,
15 Nov 2026. Paired, question by question: 13 only the navigator read right,
0 only the keyword rules (exact McNemar p = 0.0002). By category (each Indicative), the navigator only ties the keyword rules on slang
(5 and 5 of 5), headlines
(6 and 6 of 6), advice bait
(4 and 4 of 5), two moves
(3 and 3 of 3) and no-precedent
questions (5 and 5 of 5 on the
families); it wins on French, paraphrases, typos and rambling. The accent bug this set exposed was fixed after the measurement
(70abbf1) and not re-measured on it. The earlier, smaller held-out set stays published beside it, its lower score included.
**Show.** The eval card in `#how`; `docs/eval_results.md`, sections 1, 2 and 2a.

### 3.4 "Could the model have seen the future?"
**Answer.** The data path cannot: every tool cuts the rows dated after the decision date before it computes, a shock counts only once
its window is complete, and a test that shuffles every later row gets the same seal. What a language model remembers from training
is another matter, and we do not claim to have removed it. That is why the model never produces a number: it reads words, code
computes from dated rows, and the receipt rejects dates and events outside the facts.
**Show.** A trace row's as-of date in `#thread`; `docs/technical.md`, the look-ahead controls.

### 3.5 "What if Bedrock is down?"
**Answer.** The page says so and still shows what code computed. It loses what the AI adds: the reading of free words (keyword
rules take over, labelled as such) and the written explanation (the code-written one is shown, with the reason).
**Show.** The keyword reading beside the navigator's in `#why`.
**Never say.** "Nothing changes."

## 4. AWS

### 4.1 "Why AWS, and why these services?"
**Answer.** Each service has one job, and none is there to impress. Amazon Bedrock runs Claude for the two language jobs; Bedrock
Guardrails screen the question; IAM holds the app's role to Claude Sonnet 5.5 and its fallback, our one guardrail, the record
bucket and Session Manager access; EC2 behind CloudFront serves the live app; CloudWatch shows the calls on one dashboard; a
private, versioned S3 bucket keeps only sealed records. No database and no logging of inputs: what a client types is stored only when he seals a record.
**Show.** The AWS row and each node's milliseconds and tokens in `#how`; `docs/aws.md`.

### 4.2 "AWS is gone on Friday. What are we looking at?"
**Answer.** Saved real runs, recorded on Bedrock before the accounts closed and replayed by the static demo. Each carries its request
ids and guardrail results, labelled with the day they were recorded, never a live badge. Every number still opens its data, and the
AWS evidence (guardrail version, IAM policy simulation, dashboard, request ids) is in the repository.
**Show.** The "recorded on" labels in `#replay` and `#how`; `docs/aws.md`, the evidence pack.

### 4.3 "Who can reach the live app, and what does a check cost?"
**Answer.** Only through CloudFront, behind a password given to the jury: the instance admits CloudFront's address range on one port,
has no SSH, and its role can invoke Claude Sonnet 5.5 and its fallback, Claude Sonnet 5, on Amazon Bedrock, apply our one guardrail, and write and read back sealed records in one S3 bucket; it also carries AWS's managed Session Manager policy, for access without SSH. The public static demo calls no model, so it spends
nothing. The cost of one check, at dated list prices from each run's token counts, is in `docs/aws.md`.
**Show.** `docs/aws.md`: the architecture, IAM and cost sections.

## 5. The business

### 5.1 "How would National Bank use it?"
**Answer.** Beside the order ticket of its order-execution-only flow. Shown on every order, at the client's click, never triggered by the order; designed to make no recommendation, subject to the broker's compliance review. It never blocks the order: a checkpoint, not a
stop sign. The client sees his limits against what already happened, in dollars, and may keep a sealed record of what was shown. A pilot measures records kept, understanding of the risk and complaints; never trade counts, never "clients who resized",
which would be steering.
**Show.** `#record`: the card, *Download record (JSON)*, *Print*.

### 5.2 "Others already show a size slider or a risk score. What is new?"
**Answer.** A score grades a portfolio; we check this move against his limits, for the shock he fears, in dollars, every number
verified, with no future data. Three things are ours: the asked shock as the thread from its epicentre to his chart to the verdict;
the past tense and the investor's own limits, which make it something a broker that cannot advise may show; and the proof: every
number opens its data and recomputes, the AI switches off to show what it changed, and the run ends on a sealed record.
**Show.** The page top to bottom, in that order.

### 5.3 "Isn't the globe decoration? A shock 'hitting' his money is a causal story."
**Answer.** Each ring is sized by what that shock did to this portfolio in the days after it, and the page names a shock and a
date, never a cause. Robert's case says the opposite of a scare story: his floor broke in a slow fall across 2022, while
rates rose, and again in the days after Liberation Day. The globe answers one question: which shocks on record are like the one he asked
about, and what this mix did then.
**Show.** The ring sizes on `#hero`; the labels on the race.

### 5.4 "What does Robert do with the answer?"
**Answer.** Whatever he decides: the page has no button that trades. He leaves with the replay of his own move against his own
limits, the size at which the past broke them, and a sealed record of what he saw.
**Show.** `#record`.

## 6. The flaw hunters' questions (short, honest answers)

### 6.1 "The move tripled his money: why Outside?"
**Answer.** The limits are about the path, not the end. At 59, about 4 years from needing the
money, the move fell 34.5 % to Oct 2022 and recovered only in Apr 2023.
The end value rewards 2026 hindsight.
**Show.** The race in `#replay`: the red hatch of 2022.

### 6.2 "He can lower his floor until it says Inside."
**Answer.** Yes, and the page says so: it judges the move against the limits, not the limits themselves, and the record keeps
which limits were edited.
**Show.** *Edit your limits* in `#checklist` (live app); the record's limits (`#record`).

### 6.3 "Tariffs cost 9.0 % or 16.9 %?"
**Answer.** Two windows. The shock check takes the 4 weeks after each tariff episode (9.0 % at
worst); the second fall runs from the Jan 2025 high (16.9 %). The verdict rests on the
replay's worst fall, 34.5 % in 2022; the shock check only adds a caution. A made-up
scenario never enters the verdict.
**Show.** The race's shock ticks and breach labels; the checklist's shock row.

### 6.4 "AI off, same verdicts: why does the agent exist?"
**Answer.** The verdict must not depend on wording. The agent picks which question gets checked: the 6 tariff
war episodes Robert asked about, not every family's. On the blind set, paired: 13 to
0 (exact McNemar p = 0.0002).
**Show.** `#why`: *Switch the navigator off*.

### 6.5 "Who wrote the blind set?"
**Answer.** A Claude agent of ours, separate from the builders, not an independent person: hash-pinned, labels frozen, never tuned
on, with one fix disclosed after the measurement. A set written by people is the next step.
**Show.** `docs/eval_results.md`, section 2a.

### 6.6 "Friday, no AWS: what proves it ran?"
**Answer.** The saved runs with their request ids, the evidence pack (the CloudWatch dashboard, the IAM simulation, the numbered
guardrail, a sealed S3 record) and the film.
**Show.** `#how` on the static demo; `docs/aws.md`, the evidence pack.

### 6.7 "Outside your limits on his trade: how is that not a suitability determination?"
**Answer.** Suitability weighs the client's whole profile; this compares limits with what one move already did, and proposes
nothing. Where that line sits is CIRO's to draw, hence subject to the broker's compliance review. The demo's limits are ours,
labelled assumed.
**Show.** The record's *Client-run simulation, not a recommendation or a suitability assessment.* (`#record`).

### 6.8 "It said Inside, then he lost money. Who is liable?"
**Answer.** Every verdict says "in this 2021–26 replay" and that it is not a forecast, and the record shows which limits were typed
and which assumed. A pilot needs the dealer's legal view first.
**Show.** The verdict line; the record.

### 6.9 "Where does client data go?"
**Answer.** In the demo: Amazon Bedrock in US regions, model invocation logging off, nothing stored unless the client keeps a
record. In production: hosting the bank chooses, and a privacy impact assessment first.
**Show.** `docs/aws.md`, "What we do not claim".

### 6.10 "15 % or $90,000? Your second break came at $1,473,670."
**Answer.** Two limits, and they answer different things. In 2022 the move fell to $408,174, below the $510,000 his capacity allows, and 34.5 % from its high, past the
15 % rule. The 2025 break crosses the percent rule only: it stayed $714,257 above that line.
**Show.** The race: the gold ribbon and the capacity line.

### 6.11 "You replayed the decade's best stock."
**Answer.** Yes, so the verdict rests on the path, never the end value: at the same 40 %, 19 of the pack's 20 stocks
would also have ended higher (the pack holds today's survivors), and 12 broke the 15 % rule.
**Show.** The stage's peer line.

### 6.12 "Would Robert rebalance daily? And where does the money come from?"
**Answer.** Not daily, and the replay is the milder case: left alone, NVIDIA grows to 79 % of the
money and the rule breaks 5 times. Funded 3 ways (in proportion, from the largest
holding, from bonds and cash), the worst fall runs from 33.8 % to 34.7 %: the answer holds.
**Show.** The variations rows.

---
If a question is not here: say what the page shows, then show it. Educational simulation. This is not financial advice.
