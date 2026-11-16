# EPICENTRE

**Crash-test your move before you make it.**

« Passez votre placement au crash-test avant d'agir. »

An investor states a move in their own words; EPICENTRE replays it on real 2021–26 daily prices and sourced shocks, against the investor's own limits, and answers in dollars. It never says buy, sell or hold.

![Robert's replay at its end frame: his question as the AI read it, the shock on the globe, his money against his floor, the verdict](img/replay-end-frame.png)

Robert's replay at its end frame. This already happened; it is not a forecast. Fictional illustration, not a recommendation.

## The problem

Most AI investing demos recommend a trade. An order-execution-only broker such as National Bank Direct Brokerage may not; EPICENTRE shows what the move already did, against the investor's own limits. Robert, close to retirement, hears everyone is talking about NVIDIA and is about to put ⟨run:robert:scenario.change.weight|pct0⟩ of his portfolio in it. Nothing at the order shows him what such a move already did.

## The agentic approach

Five visible steps: Observe, Understand, Compare, Explain, Verify. Claude Sonnet 5.5 on Amazon Bedrock does the two language jobs: the **navigator** reads free words or a headline into a move, a shock family and sourced precedents (it asks for a missing limit and abstains without a precedent), and the **debrief** explains. Code computes every number and every check and writes the verdict; a **receipt** checks each number of the explanation before it is shown. Bedrock Guardrails screen the question.

## What is original

Ending higher does not mean your limits held: with the move, Robert ended higher, yet his floor broke on the way. Each investor gets a different answer: Robert's hyped request is challenged (**⟨run:robert:verdict|verdict⟩**: his floor); Mateo's values decide (**⟨run:mateo:verdict|verdict⟩**: he owns CNQ.TO, which it excludes, directly); for Amira, high risk is not anything goes (**⟨run:amira:verdict|verdict⟩**: crypto over its cap). AI off: no verdict changes; the question checked does.

## Data sources

The organizers' starter set: Yahoo Finance daily prices, Bank of Canada exchange and policy rates, FRED. Sourced shocks, each with its link and date; the screened fund's published exclusions; issuer ETF holdings (local, never redistributed); public index series for the crises before 2021. Nothing dated after the decision reaches a tool. Limits: one regime in five years; shocks chosen with hindsight; nominal CAD, no taxes or fees.

## Explainability

Every number on the page is a button: its facts row, the trace step that computed it, the data rows behind it, and Recompute, which re-runs its own tool with no model. Each sentence carries ● fact, ◐ assumption or ○ fiction. Robert's receipt traced ⟨run:robert:receipt.verified⟩ of ⟨run:robert:receipt.total⟩ numbers to tool output.

## What the user gains

Robert sees the move against his own limits, in dollars, before acting: its worst fall took his money down to ⟨run:robert:breaches.0.trough_value|usd⟩, past the ⟨run:robert:profile.capacity_dollars|usd⟩ he could afford to lose (assumed). He may keep a sealed record: edit one number and the seal breaks. National Bank Direct Brokerage could offer it beside the order ticket, a checkpoint, not a stop sign. At the client's click, never triggered by the order, and subject to the broker's compliance review.

---

**Static demo**, public, no AWS call: [shmorsi.github.io/poly-datathon-2026](https://shmorsi.github.io/poly-datathon-2026/) · **Live app on AWS**, with the password from the submission form, until the AWS account closes: [dqetfenyawfe9.cloudfront.net](https://dqetfenyawfe9.cloudfront.net) · **Code**: [github.com/shmorsi/poly-datathon-2026](https://github.com/shmorsi/poly-datathon-2026)

*Educational simulation. This is not financial advice.*
