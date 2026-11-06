"""Build funded synthetic actor instances from descriptions, not template defaults."""
from dataclasses import dataclass

from .randomness import keyed_rng


CATEGORIES = (
    "retail", "event_traders", "large_holders", "liquidity", "arbitrage",
    "creators_marketing", "launch_teams", "analysts_community",
)
TRADING_CATEGORIES = frozenset({"retail", "event_traders", "large_holders"})


def _integer(value, name, minimum=0, maximum=None):
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{name} must be an integer in the permitted range")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


@dataclass(frozen=True)
class Actor:
    id: str
    template_id: str
    category: str
    owner_id: str
    initial_cash_cents: int
    allowed_actions: frozenset[str]
    subscriptions: tuple[str, ...]
    position_limit_cents: int
    entry_fraction_bps: int
    attention_capacity: int
    strategy: str
    provenance: dict

    def __post_init__(self):
        for name in ("id", "template_id", "category", "owner_id", "strategy"):
            _text(getattr(self, name), name)
        for name in ("initial_cash_cents", "position_limit_cents", "attention_capacity"):
            _integer(getattr(self, name), name)
        _integer(self.entry_fraction_bps, "entry_fraction_bps", maximum=10000)
        if not isinstance(self.allowed_actions, frozenset) or not self.allowed_actions <= {
            "buy", "sell", "abstain", "observe", "add_liquidity", "remove_liquidity",
        }:
            raise ValueError("invalid allowed_actions")
        if not isinstance(self.subscriptions, tuple):
            raise ValueError("subscriptions must be a tuple of unique source names")
        for source in self.subscriptions:
            _text(source, "subscription")
        if len(set(self.subscriptions)) != len(self.subscriptions):
            raise ValueError("subscriptions cannot repeat source names")
        if not isinstance(self.provenance, dict):
            raise ValueError("provenance must be a mapping")


@dataclass(frozen=True)
class Cast:
    actors: list[Actor]
    excluded: list[dict]


def default_recipe() -> dict:
    """Return fresh, editable *assumed* fixture settings; none are estimates.

    Group counts include the founder and delegated project LP, but exclude the
    two arbitrage roles when only one executable market exists. Outside LPs,
    launch teams, creators, and analysts are passive in this first rule model.
    Explicit role-template IDs bind project roles to their reviewed descriptions
    and reserve those descriptions from the outside actor sampling pool.
    """
    counts = (48, 12, 4, 3, 2, 4, 3, 4)
    cash_ranges = {
        "retail": [5000, 150000], "event_traders": [20000, 500000],
        "large_holders": [500000, 10000000],
    }
    caps = {"retail": 50000, "event_traders": 200000, "large_holders": 2000000}
    return {
        "founder_count": 1,
        "founder_initial_cash_cents": 1000000,
        "two_executable_markets": False,
        "role_templates": {
            "project-founder": "launch_teams-01",
            "project-lp": "liquidity-01",
        },
        "groups": {
            category: {
                "count": count,
                "cash_range_cents": cash_ranges.get(category, [0, 0]),
                "position_limit_cents": caps.get(category, 0),
                "entry_fraction_bps": 1000 if category in TRADING_CATEGORIES else 0,
                "attention_capacity": 2,
                "strategy_choices": ["cautious", "momentum"] if category in TRADING_CATEGORIES else ["observe"],
                "subscription_choices": [["news"], ["news", "creator"], ["news", "creator", "competitor"]],
            }
            for category, count in zip(CATEGORIES, counts)
        },
    }


def build_cast(pool: dict, recipe: dict, seed: int) -> Cast:
    """Instantiate weight-one actors using only reviewed descriptive fields.

    Per-actor named random streams isolate cash, template, strategy and source
    draws. Changing a template's numeric or network defaults has no effect.
    """
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if not isinstance(pool, dict) or not isinstance(pool.get("profiles"), list) or not pool["profiles"]:
        raise ValueError("pool must contain reviewed profiles")
    templates = {category: [] for category in CATEGORIES}
    ids = set()
    for raw in pool["profiles"]:
        if not isinstance(raw, dict):
            raise ValueError("profile must be a mapping")
        profile = {field: raw.get(field) for field in ("id", "name", "description", "category")}
        for field, value in profile.items():
            _text(value, f"profile {field}")
        if profile["category"] not in templates or profile["id"] in ids:
            raise ValueError("profile category must be known and IDs unique")
        ids.add(profile["id"])
        templates[profile["category"]].append(profile)
    for category in CATEGORIES:
        templates[category].sort(key=lambda profile: profile["id"])

    top_keys = {"groups", "founder_count", "founder_initial_cash_cents", "two_executable_markets", "role_templates"}
    if not isinstance(recipe, dict) or set(recipe) != top_keys:
        raise ValueError("recipe has missing or unknown settings")
    _integer(recipe["founder_count"], "founder_count", 1, 1)
    _integer(recipe["founder_initial_cash_cents"], "founder_initial_cash_cents")
    if type(recipe["two_executable_markets"]) is not bool:
        raise ValueError("two_executable_markets must be a boolean")
    role_categories = {"project-founder": "launch_teams", "project-lp": "liquidity"}
    role_templates = recipe["role_templates"]
    if not isinstance(role_templates, dict) or set(role_templates) != set(role_categories):
        raise ValueError("role_templates must explicitly map founder and project LP")
    profiles_by_id = {profile["id"]: profile for profiles in templates.values() for profile in profiles}
    for role, category in role_categories.items():
        template_id = role_templates[role]
        _text(template_id, f"role_templates.{role}")
        if template_id not in profiles_by_id or profiles_by_id[template_id]["category"] != category:
            raise ValueError(f"role template for {role} must exist in category {category}")
    reserved_ids = set(role_templates.values())
    outside_templates = {
        category: [profile for profile in profiles if profile["id"] not in reserved_ids]
        for category, profiles in templates.items()
    }
    groups = recipe["groups"]
    if not isinstance(groups, dict) or set(groups) != set(CATEGORIES):
        raise ValueError("groups must contain exactly the known categories")
    group_keys = {
        "count", "cash_range_cents", "position_limit_cents", "entry_fraction_bps",
        "attention_capacity", "strategy_choices", "subscription_choices",
    }
    for category, group in groups.items():
        if not isinstance(group, dict) or set(group) != group_keys:
            raise ValueError(f"{category} has missing or unknown settings")
        for name in ("count", "position_limit_cents", "attention_capacity"):
            _integer(group[name], f"{category}.{name}")
        _integer(group["entry_fraction_bps"], f"{category}.entry_fraction_bps", maximum=10000)
        cash_range = group["cash_range_cents"]
        if not isinstance(cash_range, (tuple, list)) or len(cash_range) != 2:
            raise ValueError("cash_range_cents must contain lower and upper bounds")
        for value in cash_range:
            _integer(value, "cash_range_cents")
        if cash_range[0] > cash_range[1]:
            raise ValueError("cash range lower bound exceeds upper bound")
        strategies = group["strategy_choices"]
        allowed = {"cautious", "momentum"} if category in TRADING_CATEGORIES else {"observe"}
        if (not isinstance(strategies, (list, tuple)) or not strategies
                or any(not isinstance(s, str) or s not in allowed for s in strategies)):
            raise ValueError(f"invalid strategy_choices for {category}")
        choices = group["subscription_choices"]
        if not isinstance(choices, (list, tuple)) or not choices:
            raise ValueError("subscription_choices must contain source lists")
        for subscriptions in choices:
            if not isinstance(subscriptions, (list, tuple)):
                raise ValueError("each subscription choice must be a source list")
            for source in subscriptions:
                _text(source, "subscription")
            if len(subscriptions) != len(set(subscriptions)):
                raise ValueError("subscription choices cannot repeat sources")
        if group["count"] and not templates[category]:
            raise ValueError(f"pool has no templates for {category}")
    if groups["launch_teams"]["count"] < 1 or groups["liquidity"]["count"] < 1:
        raise ValueError("founder and project LP must each have a cast slot")
    for category, group in groups.items():
        reserved_slots = sum(role_category == category for role_category in role_categories.values())
        if group["count"] > reserved_slots and not outside_templates[category]:
            raise ValueError(f"pool has no outside actor templates for {category}")

    actors, excluded = [], []
    for category in CATEGORIES:
        group = groups[category]
        for index in range(group["count"]):
            actor_id = f"{category}-{index + 1:03d}"
            if category == "launch_teams" and index == 0:
                actor_id = "project-founder"
            elif category == "liquidity" and index == 0:
                actor_id = "project-lp"
            if category == "arbitrage" and not recipe["two_executable_markets"]:
                excluded.append({"id": actor_id, "category": category, "reason": "requires_two_executable_markets"})
                continue
            if actor_id in role_templates:
                profile = profiles_by_id[role_templates[actor_id]]
            else:
                profile = keyed_rng(seed, "cast", actor_id, "template").choice(outside_templates[category])
            cash = keyed_rng(seed, "cast", actor_id, "cash").randint(*group["cash_range_cents"])
            owner = actor_id
            strategy = keyed_rng(seed, "cast", actor_id, "strategy").choice(group["strategy_choices"])
            actions = frozenset({"buy", "sell", "abstain"}) if category in TRADING_CATEGORIES else frozenset({"observe", "abstain"})
            if actor_id == "project-founder":
                owner, cash, strategy = "project", recipe["founder_initial_cash_cents"], "scheduled_exit"
                actions = frozenset({"sell", "abstain"})
            elif actor_id == "project-lp":
                owner, cash = "project", 0
                actions = frozenset({"add_liquidity", "remove_liquidity", "abstain"})
            subscriptions = tuple(keyed_rng(seed, "cast", actor_id, "subscriptions").choice(group["subscription_choices"]))
            rationale = "Synthetic recipe assumptions; named seeded draws, no empirical calibration."
            if actor_id == "project-lp":
                rationale += " Delegated LP aliases project cash and adds no endowment."
            if category == "arbitrage":
                rationale += " Route existence alone does not implement arbitrage; observation only."
            fields = {
                name: {"status": "assumed", "rationale": rationale}
                for name in ("id", "category", "owner_id", "initial_cash_cents", "allowed_actions", "subscriptions",
                             "position_limit_cents", "entry_fraction_bps", "attention_capacity", "strategy", "weight")
            }
            fields["template_id"] = {
                "status": "assumed",
                "rationale": ("Explicit project-role mapping in declared recipe to reviewed descriptive library."
                              if actor_id in role_templates else
                              "Seeded selection from reviewed descriptive library, excluding reserved project-role templates."),
            }
            actors.append(Actor(
                id=actor_id, template_id=profile["id"], category=category, owner_id=owner,
                initial_cash_cents=cash, allowed_actions=actions, subscriptions=subscriptions,
                position_limit_cents=group["position_limit_cents"], entry_fraction_bps=group["entry_fraction_bps"],
                attention_capacity=group["attention_capacity"], strategy=strategy,
                provenance={"status": "assumed", "rationale": rationale, "fields": fields,
                            "template": profile, "weight": 1},
            ))
    return Cast(actors=actors, excluded=excluded)
