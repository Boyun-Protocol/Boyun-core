"""Technical Report and User and Agent Decision Record for the NEAR lending casebook."""
from build_financial_casebook import chart, paragraph, section, table

JEV_TARIFF = '$0.042 per million input tokens, $0 output (docs.typesafe.ai/models, checked 2026-10-28)'
COMMANDS = [
    ['Fetch prices (free)', 'curl Binance /api/v3/klines NEARUSDT and USDCUSDT 1h → evidence/; hashes in evidence/manifest.json'],
    ['Run a world (Laya, free)', 'engine/.venv/bin/python tools/run_near_lending_case.py --settings S --cast C --calendar K --path P --out engine/output/DIR'],
    ['Run a world (Jev, paid)', 'same, plus --actor-model jev --env-file .env --max-cost-usd 0.15 (spends money; key read from the named file only)'],
    ['Resume', 'rerun the same command with the same --out; cached decisions are reused, new calls only for uncached states'],
    ['Summarize', 'engine/.venv/bin/python tools/summarize_near_lending_case.py engine/output/DIR'],
    ['Build this casebook (free)', 'engine/.venv/bin/python tools/build_lending_casebook.py --output NEW_DIR'],
    ['Validate structure', 'python tools/validate_financial_report_package.py NEW_DIR'],
    ['Tests', 'engine/.venv/bin/python -m pytest engine/tests/test_lending.py engine/tests/test_lending_choices.py engine/tests/test_lending_case.py engine/tests/test_laya_choices.py engine/tests/test_finance.py']]


def label(w):
    return f'{w["name"]} ({w["code"]})'


def technical(ctx, base):
    ws = list(ctx['worlds'].values())
    doc = base('TECHNICAL-REPORT', 'Technical Report', 'How the six worlds were produced, verified and paid for', ctx)
    jev = [w for w in ws if w['model'] == 'Jev']
    spend = sum(w['manifest'].get('estimated_new_spend_usd') or 0 for w in jev)
    doc['highlights'] = [
        f'Six native runs, each complete to 2,160 hours: {sum(w["manifest"]["model_calls"]["new"] for w in ws):,} new model calls and '
        f'{sum(w["manifest"]["model_calls"]["cached"] for w in ws):,} cached decisions reused.',
        f'Jev spend: about ${spend + 0.00045:.3f} by list-price estimate (two runs plus a 16-call smoke test). Laya runs locally with no fee.',
        'Every world\'s ledger replayed exactly from its event journal. One run was interrupted by an engine bug and resumed after a tested fix.']
    rows = []
    for w in ws:
        m = w['manifest']
        rows.append([label(w), m['model'], f'{m["model_calls"]["new"]:,}', f'{m["model_calls"]["cached"]:,}', f'{m["elapsed_seconds"]:.0f}',
                     m['engine_sha256'][:12], f'engine/output/{w["dir"]}'])
    o = ctx['original']
    rows.append(['Original baseline (superseded engine)', o['model'], f'{o["model_calls"]["new"]:,}', '0', f'{o["elapsed_seconds"]:.0f}',
                 o['engine_sha256'][:12], 'engine/output/near-lending-case-2026-11-05'])
    doc['sections'].append(section('Run identity and coverage',
        table(['World', 'Model', 'New calls', 'Cached', 'Seconds', 'Ledger engine', 'Output'], rows,
              'manifest.json in each output folder records input SHA-256 hashes, engine hash, calls and elapsed time. All runs: 5 November 2026, macOS, local CPU for Laya.'),
        paragraph('Coverage: every world ran all 2,160 hours with no missing interval. First Light reuses the original baseline\'s 1,604 decisions from '
                  'cache on the current engine; all its figures match the original exactly. The original output is preserved because it replays only '
                  'on the earlier engine.'),
        chart('bar', 'New versus cached model calls', [label(w) for w in ws],
              [{'name': 'New calls', 'values': [w['manifest']['model_calls']['new'] for w in ws]},
               {'name': 'Cached', 'values': [w['manifest']['model_calls']['cached'] for w in ws]}],
              'Open Gate resumed from 1,685 cached decisions after an interrupted first attempt; First Light is fully cached.',
              'Counts per world from manifest.json. A cached decision returns the stored model answer for an identical request; no new inference.',
              'Cached and new decisions are interchangeable only because requests are identical; any state change produces a new call.',
              'manifest.json per world.', unit='calls')))
    doc['sections'].append(section('Cost',
        table(['Item', 'Calls', 'Estimated cost', 'Basis'], [
            ['Jev smoke test (1 day)', '16', '$0.00045', JEV_TARIFF],
            *[[label(w), f'{w["manifest"]["model_calls"]["new"]:,}', f'${w["manifest"]["estimated_new_spend_usd"]:.4f}', JEV_TARIFF] for w in jev],
            ['Laya runs (4 worlds + rerun)', f'{sum(w["manifest"]["model_calls"]["new"] for w in ws if w["model"] == "Laya"):,}', '$0', 'Local inference, no API fee']],
            'Jev amounts are list-price estimates from reported input tokens, not provider invoices. Each Jev run had a hard stop ($0.25 then $0.15) that was never reached. '
            'The user reported about $1 of Jev credit before these runs.')))
    doc['sections'].append(section('Stops, failures and fixes',
        paragraph('One stop occurred. The first Open Gate attempt halted at hour 1,524 with Python\'s "Exceeds the limit (4300 digits) for integer string '
                  'conversion". Cause: per-supplier interest receivables were exact fractions accrued hourly, and their denominators grew without bound. '
                  'It was an engine defect, not a provider stop. Fix: accrual, points and partial interest splits round down to 1e-12 USDC. The dust favors '
                  'borrowers and no cash is created. A 90-day regression test reproduces the failure. The run resumed from cache: 1,685 decisions reused, 762 new.'),
        paragraph('No provider errors, rate limits or unknown dispatches were recorded in any run log. Laya printed a checkpoint warning that some '
                  'temperatures fall outside [0.5, 5] and were clamped; treat its confidence scores as uncalibrated.')))
    doc['sections'].append(section('Choice generation and settlement',
        paragraph('Each decision is a menu built from the actor\'s own state. Suppliers: supply or withdraw a step of 25% of their resources (min $1K, '
                  'max $100K), or wait. Borrowers: post 25% of their NEAR, borrow $12,500, repay, remove collateral, or wait. The team: status update, '
                  'private partner message, one extra paid KOL post, or no action. Partners: accept, delay three days once, or decline. Options the ledger '
                  'would reject are not offered. The model returns a score per option; the highest-scoring option is settled. Scores are not probabilities '
                  'of real behavior.'),
        chart('bar', 'Jev is more decisive than Laya, but neither is calibrated', [label(w) for w in ws],
              [{'name': 'Mean top-option score', 'values': [round(w['decisive']['mean_top'], 3) for w in ws]},
               {'name': 'Uniform baseline', 'values': [round(w['decisive']['mean_uniform'], 3) for w in ws]}],
              f'Laya\'s top option averaged {min(w["decisive"]["mean_top"] for w in ws if w["model"] == "Laya"):.3f}–{max(w["decisive"]["mean_top"] for w in ws if w["model"] == "Laya"):.3f}; '
              f'Jev {min(w["decisive"]["mean_top"] for w in jev):.3f}–{max(w["decisive"]["mean_top"] for w in jev):.3f}.',
              'Mean score of the chosen option across scored decisions, against the mean score a uniform pick would give on the same menus.',
              'A high score shows the model is confident, not that it is correct; both models ignored the rate change.',
              'decisions.json probabilities per world.', unit='score')))
    doc['sections'].append(section('Validation and reproduction',
        paragraph('95 tests pass: ledger accounting (conservation, interest, queue, liquidation, write-off, reserve, points, stale oracle, 90-day '
                  'hourly replay and fixed-grid accrual), decision menus (isolation, feasibility, private profile), and the runner (opening deposit, '
                  'awareness gating, partner decline, paid-on-delivery spend, crash triggers and liquidation, resume without calls, team menu limits). '
                  'Each world\'s report replays exactly from its event journal. Replay shows the run is reproducible, not that it is realistic.'),
        table(['Step', 'Command'], COMMANDS, 'Paths are relative to the repository root. Only the Jev run step spends money.'),
        paragraph('Not modeled: operations spending, Rhea rate changes, competitor reactions, oracle lag beyond the hourly step, token decimal rounding '
                  'other than the 1e-12 accrual grid, cap or rate changes during the run, and use of the optional $100K.')))
    return doc


def decision_record(ctx, base):
    answers = ctx['intake']['answers']
    doc = base('DECISION-RECORD', 'User and Agent Decision Record', 'Every recorded user choice and the agent choices made on the user\'s behalf', ctx)
    doc['highlights'] = [f'{len(answers)} user answers recorded on 5 November 2026 through the question box; exact per-answer timestamps were not stored.',
                         'Agent-chosen values are listed separately; the user did not choose them individually.']
    rows = [[a['question_id'], a.get('question', '—')[:140], a['answer_as_received'] if isinstance(a['answer_as_received'], str)
             else '; '.join(a['answer_as_received']), a.get('meaning', '')[:220]] for a in answers]
    doc['sections'].append(section('User answers',
        table(['ID', 'Question', 'Answer as received', 'Recorded effect'], rows,
              'Source: engine/examples/near-lending/intake.json. Answers are quoted as received; "Recorded effect" is the agent\'s summary at the time.')))
    doc['sections'].append(section('Agent choices not individually approved',
        table(['Choice', 'Value', 'Context'], [
            ['Cast balances, motives and channel follows', 'funded-cast-proposal.json', 'Proposed by the agent; the user approved the cast as a whole'],
            ['Liquidator cash, depth, impact, cost', '$150K/$50K; $250K/$80K per hour; 0.5%/1%; $25', 'Part of the approved cast; not separately discussed'],
            ['Decision menu step sizes', '25% of resources; $12,500 borrow step', 'Runner design'],
            ['Borrower group split', '8 accounts of 7,500 NEAR', 'User chose "split into separate accounts"; the count of 8 was the agent\'s'],
            ['Steep rate curve values', '8% base, 15% at 50%, 60% at full', 'User chose "steeper rate curve"; values were the agent\'s'],
            ['Price path scaling', 'Opening price set to $4.0375', 'Agent method, disclosed when paths were offered'],
            ['Jev spend caps', '$0.25 first run, $0.15 second', 'Second cap set after the user reported about $1 of credit']],
            'These choices shape results. Changing any of them requires a new run.')))
    doc['sections'].append(section('Open questions',
        table(['Question', 'Status'], [
            ['Do real borrowers want NEAR-backed USDC at these rates?', 'Unresolved; Laya and Jev disagree and neither responds to price'],
            ['Bull regime', 'Offered, not selected; not run'],
            ['Jev on the bear path', 'Not run'],
            ['Reserve claim eligibility beyond pro rata', 'Pro rata only, as in the selected baseline'],
            ['Use of the optional $100K', 'Held for later by the user; not modeled']], 'Unrun cases are open questions, not simulated events.')))
    return doc
