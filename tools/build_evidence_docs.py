"""Resolve documentation evidence to actual source symbols; no network/model work.

Run without flags after a code move to refresh marked links and SOURCE_MAP.md.
--check refuses stale/missing symbols, broken relative links and Mermaid fences.
It checks structural references, not whether prose claims or research are true.
"""
import ast
import os
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs/decision-lab'
# id, module, qualified symbol, layer. Symbols are resolved, never guessed line numbers.
ENTRIES=[
('world_validate','strategic_worlds','validate_strategic_world','Strategic product'),
('world_observe','strategic_worlds','StrategicWorld.observations','Strategic product'),
('world_advance','strategic_worlds','StrategicWorld.advance','Strategic product'),
('world_utility','strategic_worlds','StrategicWorld._utility','Strategic product'),
('world_replay','strategic_worlds','replay_strategic_world','Strategic product'),
('world_game','strategic_worlds','strategic_game','Strategic product'),
('construction_audit','game_construction','game_construction_audit','Strategic product'),
('construction_summary','game_construction','game_construction_summary','Strategic product'),
('actor_support','game_construction','actor_game_support','Strategic product'),
('decision_request','strategic_models','decision_request','Strategic product'),
('decide','strategic_models','decide','Strategic product'),
('author_prompt','strategic_models','authoring_messages','Strategic product'),
('persona','persona_controls','adapt_personas','Strategic product'),
('batch','batch_authoring','merge_proposal','Strategic product'),
('author_calls','batch_authoring','required_calls','Strategic product'),
('create','product_api','ProductManager.create','Orchestration'),
('review','product_api','ProductManager.review','Orchestration'),
('run','product_api','ProductManager.run','Orchestration'),
('execute','product_api','ProductManager._execute','Orchestration'),
('summary','product_api','ProductManager._summarize','Orchestration'),
('credit_estimate','product_api','estimate_typesafe_usage','Orchestration'),
('keys','product_api','ProductManager.configure_access','Orchestration'),
('author_keys','product_api','ProductManager.configure_author','Orchestration'),
('jev','jev','TypeSafeClient.evaluate','Providers'),
('jev_get','jev','TypeSafeClient.get_models','Providers'),
('jev_wire','jev','_urllib_transport','Providers'),
('cloud','near_ai','NearAITextModel','Providers'),
('offline','offline_decisions','OfflineDecisions.evaluate','Providers'),
('game','strategic_games','analyze_game','Analytical kernels'),
('bayes','probability_updates','update_beliefs','Analytical kernels'),
('evaluation','evaluation','evaluate_forecasts','Analytical kernels'),
('score','evaluation','_scores','Analytical kernels'),
('sensitivity','experiments','sensitivity','Financial / separate modules'),
('matched','experiments','_paired','Financial / separate modules'),
('rng','randomness','keyed_rng','Financial / separate modules'),
('event','event_chains','run_event_chain','Financial / separate modules'),
('ledger','finance','Ledger._commit','Financial / separate modules'),
('amm','finance','ConstantProductMarket._trade','Financial / separate modules'),
('finance_live','agent_orchestration','run_live','Financial / separate modules'),
('social','social_experiments','prepare_social_experiment','Financial / separate modules'),
('social_run','social_experiments','run_social_experiment','Financial / separate modules'),
('wallet_data','wallet_evidence','analyze_wallets','Evidence'),
('archive','public_archive','PublicArchive.record_snapshot','Evidence'),
('near_case','near_demo','build_near_demo','Evidence'),
('presentation','scenario_presentation','build_presentation','Delivery / integrity'),
('reports','product_reports','render_report','Delivery / integrity'),
('commitment','integrity','create_commitment','Delivery / integrity'),
('verify','near_registry','NearRegistryClient.verify_transaction','Delivery / integrity'),
('wallet','product_near','ProductNear.wallet_prepare','Delivery / integrity'),
('preview','mvp_preview','PreviewServer','Delivery / integrity'),
('allowance','preview_budget','PreviewJevClient.evaluate','Delivery / integrity'),
('journey','journey_commands','journey','Delivery / integrity'),
('contract','contracts/commitment-registry/src/lib.rs','pub fn register_commitment','Delivery / integrity'),
('test_private','test_strategic_worlds','test_own_private_information_and_future_event_boundary','Tests'),
('test_atomic','test_strategic_worlds','test_atomic_invalid_or_stale_decision_never_changes_state','Tests'),
('test_replay','test_strategic_worlds','test_exact_replay_tamper_rejected_and_deep_detachment','Tests'),
('test_game','test_strategic_games','test_exact_expected_utility_best_response_and_deviation_regret','Tests'),
('test_bayes','test_probability_updates','test_coin_posterior_and_sequential_normalizers_are_exact','Tests'),
('test_eval','test_evaluation','test_hand_calculated_holdout_scores_training_only_baseline_and_fixed_bins','Tests'),
('test_social','test_social_experiments','test_prepare_changes_only_declared_peer_edges_and_no_input_mutation','Tests'),
('test_jev','test_product_api','test_typesafe_typed_decisions_settle_rounds_with_private_information_and_replay','Tests'),
('test_money','test_finance','test_buy_uses_gross_reserve_input_and_retains_floor_fee','Tests'),
('test_persona','test_persona_controls','test_profile_controls_change_real_observations_without_changing_finances_or_rules','Tests'),
('test_budget','test_preview_budget','test_approved_run_rechecks_allowance_before_creating_run_artifacts','Tests'),
]


def symbols():
    result={}
    for key,module,qualified,layer in ENTRIES:
        path=ROOT/module if '/'in module else ROOT/('engine/tests'if module.startswith('test_')else'engine/src/decision_lab')/(module+'.py')
        if path.suffix!='.py':
            found=[i for i,line in enumerate(path.read_text().splitlines(),1)if line.strip().startswith(qualified)]
            if len(found)!=1:raise ValueError(f'Missing or ambiguous non-Python source anchor {module}:{qualified}')
            result[key]=(path,found[0],qualified,layer);continue
        tree=ast.parse(path.read_text());node=tree
        for name in qualified.split('.'):
            found=[item for item in node.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))and item.name==name]
            if len(found)!=1:raise ValueError(f'Missing or ambiguous evidence symbol {module}:{qualified}')
            node=found[0]
        result[key]=(path,node.lineno,qualified,layer)
    return result


def link(key,target,index):
    path,line,_,_=index[key]
    relative=os.path.relpath(path,target.parent)
    return f'[{path.name}:{line}]({relative}#L{line})<!-- code:{key} -->'


def render_refs(text,target,index=None):
    index=index or symbols()
    text=re.sub(r'@@([a-z_]+)@@',lambda m:link(m[1],target,index),text)
    return re.sub(r'\[[^\]\n]+\]\([^\)\n]+\)<!-- code:([a-z_]+) -->',lambda m:link(m[1],target,index),text)


def source_map(index):
    rows=['# Implementation evidence map','',
          'Generated from Python AST symbols and exact non-Python source anchors by `python3 tools/build_evidence_docs.py`. Last reviewed 27 October 2026.',
          'Links resolve to the current checkout. They locate implementation/tests, not an independent audit or proof that a model predicts reality.',
          'The reviewed implementation baseline is `68585234303887013036fb8026e43c6ab6f59486`; publication should pin its own release commit.',
          '','| Layer | Symbol | Source |','| --- | --- | --- |']
    for key,(_,_,symbol,layer)in index.items():rows.append(f'| {layer} | `{symbol}` | {link(key,DOCS/"SOURCE_MAP.md",index)} |')
    rows+=['','## Maintenance','',
           'After code moves, run the builder and review the changed claims. `--check` rejects stale marked links and missing relative targets.',
           'A successful link check cannot validate a paper, empirical provenance, predictive accuracy or the meaning of prose.',
           'See [research](RESEARCH_FOUNDATIONS.md), [system design](SYSTEM_DESIGN.md), [provenance](UPSTREAM_REUSE.md).','']
    return '\n'.join(rows)


def check_links(path,text,planned=()):
    for target in re.findall(r'\]\(([^\s)]+)\)',text):
        if '://'in target or target.startswith('#'):continue
        plain,_,fragment=target.partition('#')
        resolved=(path.parent/plain).resolve()
        if not resolved.exists()and resolved not in planned:raise ValueError(f'{path.relative_to(ROOT)}: missing link {target}')
        if fragment.startswith('L')and fragment[1:].isdigit():
            if int(fragment[1:])>len(resolved.read_text().splitlines()):raise ValueError(f'Invalid line: {target}')
    if text.count('```')%2:raise ValueError(f'Unclosed fence: {path}')


def main():
    index=symbols()
    targets=[ROOT/'README.md',DOCS/'RESEARCH_FOUNDATIONS.md',DOCS/'SYSTEM_DESIGN.md',DOCS/'UPSTREAM_REUSE.md']
    changes=[]
    for path in targets:
        original=path.read_text();rendered=render_refs(original,path,index)
        check_links(path,rendered,planned={(DOCS/"SOURCE_MAP.md").resolve()})
        if original!=rendered:changes.append((path,rendered))
    target=DOCS/'SOURCE_MAP.md';rendered=source_map(index)
    check_links(target,rendered)
    if not target.exists()or target.read_text()!=rendered:changes.append((target,rendered))
    if '--check'in sys.argv and changes:raise SystemExit('Stale evidence links: '+', '.join(str(p.relative_to(ROOT))for p,_ in changes))
    for path,text in changes:path.write_text(text)
    print(f'Checked {len(index)} source symbols and {len(targets)+1} documents; '+('current.'if not changes else'refreshed marked references.'))


if __name__=='__main__':main()
