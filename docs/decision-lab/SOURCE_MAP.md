# Implementation evidence map

Generated from Python AST symbols and exact non-Python source anchors by `python3 tools/build_evidence_docs.py`. Last reviewed 27 October 2026.
Links resolve to the current checkout. They locate implementation/tests, not an independent audit or proof that a model predicts reality.
The reviewed implementation baseline is `68585234303887013036fb8026e43c6ab6f59486`; publication should pin its own release commit.

| Layer | Symbol | Source |
| --- | --- | --- |
| Strategic product | `validate_strategic_world` | [strategic_worlds.py:85](../../engine/src/decision_lab/strategic_worlds.py#L85)<!-- code:world_validate --> |
| Strategic product | `StrategicWorld.observations` | [strategic_worlds.py:255](../../engine/src/decision_lab/strategic_worlds.py#L255)<!-- code:world_observe --> |
| Strategic product | `StrategicWorld.advance` | [strategic_worlds.py:287](../../engine/src/decision_lab/strategic_worlds.py#L287)<!-- code:world_advance --> |
| Strategic product | `StrategicWorld._utility` | [strategic_worlds.py:251](../../engine/src/decision_lab/strategic_worlds.py#L251)<!-- code:world_utility --> |
| Strategic product | `replay_strategic_world` | [strategic_worlds.py:339](../../engine/src/decision_lab/strategic_worlds.py#L339)<!-- code:world_replay --> |
| Strategic product | `strategic_game` | [strategic_worlds.py:360](../../engine/src/decision_lab/strategic_worlds.py#L360)<!-- code:world_game --> |
| Strategic product | `game_construction_audit` | [game_construction.py:182](../../engine/src/decision_lab/game_construction.py#L182)<!-- code:construction_audit --> |
| Strategic product | `game_construction_summary` | [game_construction.py:277](../../engine/src/decision_lab/game_construction.py#L277)<!-- code:construction_summary --> |
| Strategic product | `actor_game_support` | [game_construction.py:110](../../engine/src/decision_lab/game_construction.py#L110)<!-- code:actor_support --> |
| Strategic product | `decision_request` | [strategic_models.py:75](../../engine/src/decision_lab/strategic_models.py#L75)<!-- code:decision_request --> |
| Strategic product | `decide` | [strategic_models.py:105](../../engine/src/decision_lab/strategic_models.py#L105)<!-- code:decide --> |
| Strategic product | `authoring_messages` | [strategic_models.py:206](../../engine/src/decision_lab/strategic_models.py#L206)<!-- code:author_prompt --> |
| Strategic product | `adapt_personas` | [persona_controls.py:15](../../engine/src/decision_lab/persona_controls.py#L15)<!-- code:persona --> |
| Strategic product | `merge_proposal` | [batch_authoring.py:208](../../engine/src/decision_lab/batch_authoring.py#L208)<!-- code:batch --> |
| Strategic product | `required_calls` | [batch_authoring.py:92](../../engine/src/decision_lab/batch_authoring.py#L92)<!-- code:author_calls --> |
| Orchestration | `ProductManager.create` | [product_api.py:411](../../engine/src/decision_lab/product_api.py#L411)<!-- code:create --> |
| Orchestration | `ProductManager.review` | [product_api.py:585](../../engine/src/decision_lab/product_api.py#L585)<!-- code:review --> |
| Orchestration | `ProductManager.run` | [product_api.py:621](../../engine/src/decision_lab/product_api.py#L621)<!-- code:run --> |
| Orchestration | `ProductManager._execute` | [product_api.py:658](../../engine/src/decision_lab/product_api.py#L658)<!-- code:execute --> |
| Orchestration | `ProductManager._summarize` | [product_api.py:646](../../engine/src/decision_lab/product_api.py#L646)<!-- code:summary --> |
| Orchestration | `estimate_typesafe_usage` | [product_api.py:77](../../engine/src/decision_lab/product_api.py#L77)<!-- code:credit_estimate --> |
| Orchestration | `ProductManager.configure_access` | [product_api.py:157](../../engine/src/decision_lab/product_api.py#L157)<!-- code:keys --> |
| Orchestration | `ProductManager.configure_author` | [product_api.py:195](../../engine/src/decision_lab/product_api.py#L195)<!-- code:author_keys --> |
| Providers | `TypeSafeClient.evaluate` | [jev.py:209](../../engine/src/decision_lab/jev.py#L209)<!-- code:jev --> |
| Providers | `TypeSafeClient.get_models` | [jev.py:190](../../engine/src/decision_lab/jev.py#L190)<!-- code:jev_get --> |
| Providers | `_urllib_transport` | [jev.py:136](../../engine/src/decision_lab/jev.py#L136)<!-- code:jev_wire --> |
| Providers | `NearAITextModel` | [near_ai.py:168](../../engine/src/decision_lab/near_ai.py#L168)<!-- code:cloud --> |
| Providers | `OfflineDecisions.evaluate` | [offline_decisions.py:11](../../engine/src/decision_lab/offline_decisions.py#L11)<!-- code:offline --> |
| Analytical kernels | `analyze_game` | [strategic_games.py:126](../../engine/src/decision_lab/strategic_games.py#L126)<!-- code:game --> |
| Analytical kernels | `update_beliefs` | [probability_updates.py:103](../../engine/src/decision_lab/probability_updates.py#L103)<!-- code:bayes --> |
| Analytical kernels | `evaluate_forecasts` | [evaluation.py:146](../../engine/src/decision_lab/evaluation.py#L146)<!-- code:evaluation --> |
| Analytical kernels | `_scores` | [evaluation.py:123](../../engine/src/decision_lab/evaluation.py#L123)<!-- code:score --> |
| Financial / separate modules | `sensitivity` | [experiments.py:107](../../engine/src/decision_lab/experiments.py#L107)<!-- code:sensitivity --> |
| Financial / separate modules | `_paired` | [experiments.py:73](../../engine/src/decision_lab/experiments.py#L73)<!-- code:matched --> |
| Financial / separate modules | `keyed_rng` | [randomness.py:7](../../engine/src/decision_lab/randomness.py#L7)<!-- code:rng --> |
| Financial / separate modules | `run_event_chain` | [event_chains.py:240](../../engine/src/decision_lab/event_chains.py#L240)<!-- code:event --> |
| Financial / separate modules | `Ledger._commit` | [finance.py:93](../../engine/src/decision_lab/finance.py#L93)<!-- code:ledger --> |
| Financial / separate modules | `ConstantProductMarket._trade` | [finance.py:182](../../engine/src/decision_lab/finance.py#L182)<!-- code:amm --> |
| Financial / separate modules | `run_live` | [agent_orchestration.py:125](../../engine/src/decision_lab/agent_orchestration.py#L125)<!-- code:finance_live --> |
| Financial / separate modules | `prepare_social_experiment` | [social_experiments.py:31](../../engine/src/decision_lab/social_experiments.py#L31)<!-- code:social --> |
| Financial / separate modules | `run_social_experiment` | [social_experiments.py:176](../../engine/src/decision_lab/social_experiments.py#L176)<!-- code:social_run --> |
| Evidence | `analyze_wallets` | [wallet_evidence.py:119](../../engine/src/decision_lab/wallet_evidence.py#L119)<!-- code:wallet_data --> |
| Evidence | `PublicArchive.record_snapshot` | [public_archive.py:167](../../engine/src/decision_lab/public_archive.py#L167)<!-- code:archive --> |
| Evidence | `build_near_demo` | [near_demo.py:58](../../engine/src/decision_lab/near_demo.py#L58)<!-- code:near_case --> |
| Delivery / integrity | `build_presentation` | [scenario_presentation.py:191](../../engine/src/decision_lab/scenario_presentation.py#L191)<!-- code:presentation --> |
| Delivery / integrity | `render_report` | [product_reports.py:182](../../engine/src/decision_lab/product_reports.py#L182)<!-- code:reports --> |
| Delivery / integrity | `create_commitment` | [integrity.py:44](../../engine/src/decision_lab/integrity.py#L44)<!-- code:commitment --> |
| Delivery / integrity | `NearRegistryClient.verify_transaction` | [near_registry.py:147](../../engine/src/decision_lab/near_registry.py#L147)<!-- code:verify --> |
| Delivery / integrity | `ProductNear.wallet_prepare` | [product_near.py:69](../../engine/src/decision_lab/product_near.py#L69)<!-- code:wallet --> |
| Delivery / integrity | `PreviewServer` | [mvp_preview.py:107](../../engine/src/decision_lab/mvp_preview.py#L107)<!-- code:preview --> |
| Delivery / integrity | `PreviewJevClient.evaluate` | [preview_budget.py:81](../../engine/src/decision_lab/preview_budget.py#L81)<!-- code:allowance --> |
| Delivery / integrity | `journey` | [journey_commands.py:61](../../engine/src/decision_lab/journey_commands.py#L61)<!-- code:journey --> |
| Delivery / integrity | `pub fn register_commitment` | [lib.rs:42](../../contracts/commitment-registry/src/lib.rs#L42)<!-- code:contract --> |
| Tests | `test_own_private_information_and_future_event_boundary` | [test_strategic_worlds.py:35](../../engine/tests/test_strategic_worlds.py#L35)<!-- code:test_private --> |
| Tests | `test_atomic_invalid_or_stale_decision_never_changes_state` | [test_strategic_worlds.py:60](../../engine/tests/test_strategic_worlds.py#L60)<!-- code:test_atomic --> |
| Tests | `test_exact_replay_tamper_rejected_and_deep_detachment` | [test_strategic_worlds.py:79](../../engine/tests/test_strategic_worlds.py#L79)<!-- code:test_replay --> |
| Tests | `test_exact_expected_utility_best_response_and_deviation_regret` | [test_strategic_games.py:26](../../engine/tests/test_strategic_games.py#L26)<!-- code:test_game --> |
| Tests | `test_coin_posterior_and_sequential_normalizers_are_exact` | [test_probability_updates.py:25](../../engine/tests/test_probability_updates.py#L25)<!-- code:test_bayes --> |
| Tests | `test_hand_calculated_holdout_scores_training_only_baseline_and_fixed_bins` | [test_evaluation.py:39](../../engine/tests/test_evaluation.py#L39)<!-- code:test_eval --> |
| Tests | `test_prepare_changes_only_declared_peer_edges_and_no_input_mutation` | [test_social_experiments.py:34](../../engine/tests/test_social_experiments.py#L34)<!-- code:test_social --> |
| Tests | `test_typesafe_typed_decisions_settle_rounds_with_private_information_and_replay` | [test_product_api.py:279](../../engine/tests/test_product_api.py#L279)<!-- code:test_jev --> |
| Tests | `test_buy_uses_gross_reserve_input_and_retains_floor_fee` | [test_finance.py:91](../../engine/tests/test_finance.py#L91)<!-- code:test_money --> |
| Tests | `test_profile_controls_change_real_observations_without_changing_finances_or_rules` | [test_persona_controls.py:6](../../engine/tests/test_persona_controls.py#L6)<!-- code:test_persona --> |
| Tests | `test_approved_run_rechecks_allowance_before_creating_run_artifacts` | [test_preview_budget.py:154](../../engine/tests/test_preview_budget.py#L154)<!-- code:test_budget --> |

## Maintenance

After code moves, run the builder and review the changed claims. `--check` rejects stale marked links and missing relative targets.
A successful link check cannot validate a paper, empirical provenance, predictive accuracy or the meaning of prose.
See [research](RESEARCH_FOUNDATIONS.md), [system design](SYSTEM_DESIGN.md), [provenance](UPSTREAM_REUSE.md).
