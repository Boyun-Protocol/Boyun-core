# Research foundations: language models and NEAR

Reviewed 29 October 2026. These references support specific architectural
concepts. Shared authorship does not establish Boyun's forecasting accuracy,
endorsement, or implementation of the cited protocols.

| Primary work | Brief introduction | Relevance to Boyun | Boundary |
| --- | --- | --- | --- |
| [Attention Is All You Need](https://arxiv.org/abs/1706.03762v7), Vaswani et al., 2017, including Illia Polosukhin | Transformer attention combines token representations using query/key compatibility weights. Sections 3.2–3.2.3, pp. 3–5. | Background for context-sensitive model interfaces; distinguish internal neural attention from the messages supplied to an actor. | Not NEAR protocol research or evidence of social simulation accuracy. No undocumented Jev architecture is assumed. |
| [Nightshade: NEAR Protocol Sharding Design 2.0](https://discovery-domain.org/papers/nightshade.pdf), Skidanov, Polosukhin, Wang; July 2019, updated February 2024 | Shards partition blockchain state/work; chunks belong to one logical chain. Sections 1.3, 3.1. Data availability and long-term retention are discussed separately in section 2.6. | Explain the blockchain platform and why a commitment registry does not store or validate the complete off-chain experiment. | Boyun's world branches and replay are not Nightshade sharding or consensus. An on-chain hash does not ensure artifact availability. |
| [Decentralized Confidential Machine Learning](https://github.com/nearai/papers/blob/main/DecentralizedConfidentialMachineLearning.pdf), Polosukhin, Skidanov, Le Guen; undated manuscript | TEE-hosted model inference uses trusted connections to known code and model-hash checks. Sections 1–3, pp. 2–4. | Specify requirements for a future confidential author/inference route. | Current API compatibility and model names do not prove attestation, model identity, or end-to-end privacy. The paper's payment design is not implemented by Boyun. |
| [Proof of Response](https://arxiv.org/abs/2502.10637v1), Polosukhin and Skidanov, 2025 | Under its network assumptions, obtain a response, evidence of a broken edge, or delay compensation. Sections 2–4, pp. 2–5. | Explain reliability requirements if model or agent services are later distributed. | Current timeouts/cooldowns are local error handling, not this protocol, compensation, or proof of correct content. |
| [MCP architecture, version 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/architecture) | A host/client/server protocol exposes tools, resources, and reusable prompts to agent applications. | Standardize external-agent access to reviewed world execution and reports. | Discovery does not establish scientific validity. Retrieved data may be sent to the connected host's remote model. Newer protocol revisions require separate compatibility testing. |

## How the references are applied

The paper's language-model background introduces the Transformer briefly. Its
decentralized-systems related work distinguishes execution, availability,
confidentiality, model identity, and responsiveness. The architecture discussion
then applies these distinctions to actual Boyun boundaries rather than claiming
that every cited technology is installed.

The active work remains research-oriented: explicit hypotheses, reviewed
incentives, conditional trajectories, sensitivity tests, replay, and prospective
evaluation against resolved outcomes. User interfaces and prices are supporting
delivery choices, not the scientific contribution.

## Source verification

The [official NEAR papers index](https://near.org/papers) links Nightshade, DCML,
and Proof of Response. Primary PDFs and arXiv metadata were inspected through
gstack browse. Nightshade's title page identifies its three authors and 2024
revision. Attention's original conference year is 2017; the cited arXiv copy is
revision 7 from 2023. DCML has no printed publication date; its PDF creation
timestamp is not treated as one. Proof of Response's arXiv submission is
15 February 2025. The sources' claims remain distinct from a Boyun result.

Downloaded reading copies stay under ignored local research output. The paper
contains external citations and pseudocode, without mutable Boyun code-line
citations. MiroFish remains explicit direct software provenance.
