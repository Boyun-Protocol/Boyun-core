# Campaigns, persistent state and actor coordination

Updated 2 November 2026. The separate [campaign runtime](CAMPAIGN_RUNTIME.md) now
implements a first bounded version of campaign spending/delivery, private signals
and long-horizon checkpoints. This document also specifies remaining modeling
work. It is not an instruction to buy a promotion or trade.

## Assessment of the current model

The first native pilot is too weak to represent a memecoin launch. Its three
actors started without trader inventory, could only buy/sell/hold, did not publish
or subscribe to one another, and had no campaign purchase, external demand cohort,
bonding curve, migration or full founder sale rights. The price remaining flat
when all three choose hold follows those constraints. That is not evidence that
Jev cannot reason, and increasing the number of identically constrained calls
would not repair the model.

The primary fixes are executable market/campaign mechanics, state history,
distinct incentives and a restricted communication structure. Test those before
concluding that a larger language model or an unrestricted agent swarm is needed.

## Every node is a saved state transition

Record the snapshot before choices and after settlement: timestamp and sequence,
price, declared market cap and FDV, reserves, rolling volume with exact windows,
trade counts, all actor cash/inventory/cost basis, own/visible decisions, event
receipts, pending orders/commitments, current campaigns and expiry, actor knowledge,
observation hashes, model outputs and source versions. Unimplemented or unavailable
fields remain explicitly unsupported/unknown rather than invented zeros.

Full checkpoints are private simulation records. Each next actor prompt receives
only permitted current observations, its own actions/positions and the relevant
history of public market state. Preserve the full history on disk; use an explicit
bounded context view and deterministic summaries as horizons grow. A summary must
retain cash commitments, risk/exit conditions, unresolved questions, information
availability and references to exact older checkpoints. Do not silently truncate
an important exit instruction or let a summary introduce future information.

The v2 runtime now implements pre/post checkpoints, exact supply-derived market
cap/FDV, executed rolling turnover and actor-specific market/balance history.
V2 itself still labels campaign state and private decision messages unsupported.
The newer, separate `campaign-world.v1` implements campaign commitments, delivery,
expiry and authorized next-step signal templates without altering v2 replay.

## Verified DEX Screener product distinction

Read-only official sources inspected 2 November 2026:

| Product | What the evidence says | Model consequence |
| --- | --- | --- |
| Token listing | Tokens are automatically listed after addition to a pool and at least one transaction | Do not charge an invented listing fee or assume paid information is required for discovery |
| Enhanced Token Info | Marketplace displayed $299, with $499 struck through; includes token details/socials; processing may take up to 12h | Store the checked offer and timestamp as a quoted product input, not a permanent fee or instant delivery guarantee |
| Boosts | Paid temporary Trending Score multiplier, active for 12–24h depending on pack; not a guarantee of trending | Model exposure opportunity, expiry and uncertain audience response; pack-specific price is still unverified |

Sources: [Token Listing](https://docs.dexscreener.com/token-listing),
[Enhanced Token Info](https://marketplace.dexscreener.com/product/token-info),
[Boosting](https://docs.dexscreener.com/boosting).

These statements do not establish the offer available at a historical launch
timestamp. An as-of simulation needs a capture available at or before its cutoff,
or a clearly labeled later-sourced product assumption. Source marketing claims
about engagement are not empirical conversion estimates.

## Model a paid campaign as a causal chain of uncertain responses

1. **Choose:** authorized founder/partner compares no campaign, Enhanced Token Info,
   an explicitly priced Boost pack, or a KOL campaign using remaining budget.
2. **Commit:** reserve/deduct the declared cost once; record payer, terms, duration,
   delivery uncertainty, non-refundability where verified, and cancellation rights.
3. **Deliver:** after the appropriate delay, record actual modeled exposure or
   visible publication. Order placed, order accepted and campaign live differ.
4. **Inform:** deliver the public/targeted signal to eligible actors, with measured
   or assumed audience reach, attention limits, overlap and disclosure.
5. **React:** distinct retail personas inspect liquidity, recent price/volume,
   prior promotions, concentration, source credibility and their own positions.
   They may ignore it, buy, sell or wait. Paid promotion can also increase skepticism.
6. **Execute:** settle orders against the venue. Derive price and turnover from
   fills, not directly from the campaign label. Retain fees and failed execution.
7. **Learn:** update actor-visible history, evaluate expiration/retention and compare
   campaign cash cost with subsequent outcomes under matched assumptions.

Buying exposure does not itself buy tokens. A direct price uplift plus separate
modeled campaign-induced buys would double-count the effect. "Low chance of organic
volume" is a hypothesis to estimate or sweep, not an accepted numeric input. Reach,
conversion, buyer size, duration and correlation require evidence separately.

## Coordination without omniscience

Use a declared communication graph rather than one all-knowing group chat:

| Actor/channel | Allowed context | Candidate work |
| --- | --- | --- |
| Founder ↔ authorized MM | Private inventory limits, budget commitments, requested quote/liquidity policy | Propose, acknowledge, reject or revise permitted inventory/liquidity actions |
| Founder ↔ Marketing Partner | Campaign budget, timing, evidence and delivery obligations | Compare paid products, schedule the chosen campaign and report delivery |
| Marketing Partner ↔ KOL | Agreed publication/delivery terms and disclosure | Model a publication, delay, refusal or expiry |
| Meme / Foundation Ecosystem | Its own resources and declared permissions | Choose independent community activity; do not assume unlimited treasury support |
| Retail/public feed | Visible posts, trade-derived market data, observable campaign markers | Different reactions by goals, holdings, trust and attention |

A proposal is not a commitment; a commitment is not an executed trade. Messages
carry sender, audience, sent/available time, typed intent and references. Fresh
same-barrier proposals remain unseen until the next allowed observation phase.
Private coordination cannot leak through retail explanations or hidden event IDs.
Public price changes do not reveal the identity or intention of their cause.

Model authorized liquidity and inventory management, and allow no intervention.
Do not make arbitrary price targets, guaranteed support, fictitious organic volume
or unlimited funds consequences of an MM label. MM rights must match the venue.

## Recommended agent structure

- A **research/authoring coordinator** constructs evidence, schedules, roles and
  candidate mechanics before the run. It does not rewrite facts after outcomes.
- A **deterministic world engine** owns time, budgets, venue state and settlement.
- **Separate typed decision agents** control founder, MM, marketing/community
  choices and heterogeneous retail positions using restricted information.
- A **critic/evaluator outside the world** checks conservation, privacy, stale
  information, implausible activity, and matched policy comparisons. It cannot
  retroactively steer an actor using hidden state.

This structure needs purposeful communication, not a swarm for its own sake.
If actor quality remains poor after the missing mechanics and evidence are fixed,
run controlled Jev-versus-alternative decision tests on the same observations,
affordable menus and goals. Compare action feasibility, response to changed state,
consistency with own goals, calibration where measurable, diversity and cost.
Do not equate more trading or higher founder profit with better model reasoning.

## Next acceptance experiment

First implement typed private messages and campaign cash/delivery state, then
compare no promotion, information-only, priced Boost, and KOL arms under matched
external draws. Include campaign failure, ignored promotion, skeptical selling,
organic inflow, expiry and coordination refusal. Every arm conserves resources.
Re-evaluate actors on each arm's resulting state; reusing unchanged launch scores
would erase the feedback being tested. Size the call/token budget before live use.

The full requested horizon still needs more than the bounded four-step pilot:
minute resolution around launch and material events, regular hourly decisions,
background population/arrival modeling, venue transitions and explicit long-context
budgeting. Do not claim a full launch simulation until those gates are exercised.
