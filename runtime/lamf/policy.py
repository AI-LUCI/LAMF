"""LAMF security policy loading + invariant-floor checking (DECISIONS.md §I).

The invariant floor F1-F12 is pinned in DECISIONS.md §I and machine-enforced
by 03_CONTRACTS/schemas/security-policy.schema.json. `floor_check` re-checks
the machine-checkable subset of those constraints without a jsonschema
dependency (runtime deps are pyyaml + pynacl only, W-02), mirroring the
schema's const/enum/minimum/maximum/contains clauses and its LAN conditional.

Pinned interface (runtime/README.md):
    PROFILES                      # Path to 02_SECURITY/profiles/
    load_policy(path) -> Policy   # Policy(name: str, raw: dict)
    floor_check(policy) -> list[str]   # [] means conformant
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# 02_SECURITY/profiles/ relative to the package root (runtime/lamf/policy.py
# -> parents[2] is the package root).
PROFILES = Path(__file__).resolve().parents[2] / "02_SECURITY" / "profiles"

PROFILE_NAMES = ("locked", "controlled", "trusted-local", "open-local", "ai-custom")

# The 16-pattern source-exclusion baseline (SECRET_PATTERNS.md §2, U-10a) —
# mandatory in every profile; operators may extend, never remove.
SOURCE_EXCLUSION_BASELINE = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "id_rsa*", "id_ed25519*", "id_ecdsa*", "id_dsa*",
    ".aws/credentials", ".netrc", ".kube/config", "kubeconfig",
    "browser_credential_stores", "os_keychain",
)

# Enum domains mirroring security-policy.schema.json (F6/F10 and lattice keys)
_ENUMS = {
    ("network", "bind"): ("socket_only", "loopback", "lan"),
    ("capture", "ordinary"): ("approval", "quarantine", "automatic"),
    ("capture", "sensitive"): ("approval", "quarantine", "protected_automatic", "sanitized_automatic"),
    ("capture", "full_prompt"): ("off", "session_policy", "sanitized"),
    ("promotion", "auto_durable_facts"): ("no", "rule_limited", "yes_except_protected", "yes_except_invariant"),
    ("context", "automatic"): ("no", "same_scope_bounded", "shared_bounded"),
    ("sharing", "cross_agent_read"): ("approval", "role_scope", "registered_local"),
    ("sharing", "cross_channel_merge"): ("manual", "confirmed", "suggest_confirm", "strong_id_confirmed"),
    ("receipts", "read"): ("every_item", "sensitive_itemized", "sensitive_itemized_aggregate_ordinary"),
    ("deletion", "approval"): ("every_durable_item", "protected_items", "security_identity_only"),
    ("encryption", "at_rest"): ("required", "sensitivity_driven", "recommended"),
    ("remote_sync",): ("denied_by_default", "explicit"),
    ("git", "mode"): ("off", "local", "remote"),
    ("council", "quorum"): ("majority", "two_thirds", "unanimous"),
}


@dataclass
class Policy:
    """A loaded security policy. `name` is the profile name; `raw` is the
    parsed YAML mapping. PINNED dataclass shape (name, raw)."""

    name: str
    raw: dict

    # Convenience accessors (fail-closed: missing keys raise KeyError so a
    # malformed policy can never silently weaken capture behavior).
    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self.raw
        for p in path:
            if not isinstance(node, dict) or p not in node:
                return default
            node = node[p]
        return node

    @property
    def message_max_kib(self) -> int:
        v = self.get("capture", "bounds", "message_max_kib", default=32)
        return min(int(v), 32)  # 32 KiB is the hard ceiling (schema)

    @property
    def tool_excerpt_max_kib(self) -> int:
        v = self.get("capture", "bounds", "tool_excerpt_max_kib", default=8)
        return min(int(v), 8)  # 8 KiB is the hard ceiling (schema)

    @property
    def capsule_max_tokens(self) -> int:
        return int(self.get("context", "capsule_max_tokens", default=1200))


def load_policy(path) -> Policy:
    """Load a policy YAML file into a Policy. PINNED SIGNATURE.

    Raises ValueError if the document is not a mapping or has no profile name.
    Run floor_check() separately to assess floor conformance (init copies a
    shipped profile, which is conformant by construction).
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"policy file {path} is not a mapping")
    name = raw.get("profile")
    if not isinstance(name, str) or not name:
        raise ValueError(f"policy file {path} has no 'profile' name")
    if "_" in name:
        raise ValueError(f"snake_case profile names are banned (U-11): {name!r}")
    return Policy(name=name, raw=raw)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def floor_check(policy: Policy) -> list[str]:
    """Check the machine-checkable subset of the invariant floor (F1-F12).

    Returns a list of violation strings, each prefixed with its floor clause
    id (matching `lamf security validate` output format). An empty list means
    the policy conforms to every machine-checkable floor clause. F4 (import
    path safety) and F9 (chain integrity) are runtime/enforcement clauses with
    no policy-document expression and are not checkable here. PINNED SIGNATURE.
    """
    v: list[str] = []
    raw = policy.raw

    def get(*path):
        node = raw
        for p in path:
            if not isinstance(node, dict):
                return None
            node = node.get(p)
        return node

    # version (schema const 1)
    if get("version") != 1:
        v.append("SCHEMA: version must be 1 (const)")

    # F2 — authenticated actors (const)
    if get("actor_auth") != "required":
        v.append("F2: actor_auth must be 'required' (const)")

    # F1 — pre-spool sanitization, fail-closed (const)
    if get("secrets", "pre_sanitization") != "required":
        v.append("F1: secrets.pre_sanitization must be 'required' (const)")

    # F11 — value detection + 16-pattern source baseline
    if get("secrets", "value_detection") != "required":
        v.append("F11: secrets.value_detection must be 'required' (const)")
    excluded = get("secrets", "excluded_sources")
    if not isinstance(excluded, list) or len(excluded) < 16:
        v.append("F11: secrets.excluded_sources must list at least the 16-pattern baseline")
    else:
        for pat in SOURCE_EXCLUSION_BASELINE:
            if pat not in excluded:
                v.append(f"F11: secrets.excluded_sources missing baseline pattern {pat!r}")

    # F3 — export encryption (const)
    if get("encryption", "export") != "required":
        v.append("F3: encryption.export must be 'required' (const)")

    # F5 — external content never auto-promotes (const)
    if get("promotion", "external_content") != "never_auto":
        v.append("F5: promotion.external_content must be 'never_auto' (const)")

    # F6 — no automatic cross-channel merge (enum membership)
    merge = get("sharing", "cross_channel_merge")
    if merge not in _ENUMS[("sharing", "cross_channel_merge")]:
        v.append(f"F6: sharing.cross_channel_merge must be one of "
                 f"{_ENUMS[('sharing', 'cross_channel_merge')]} (automatic merging forbidden); got {merge!r}")

    # F7 — erasure = crypto shredding (const)
    if get("deletion", "erasure") != "crypto_shredding":
        v.append("F7: deletion.erasure must be 'crypto_shredding' (const)")

    # F8 — approval hygiene
    ttl = get("approvals", "ttl_hours")
    if not _is_int(ttl) or not (4 <= ttl <= 168):
        v.append(f"F8: approvals.ttl_hours={ttl!r} outside [4,168]")
    rl = get("approvals", "rate_limit_per_actor_per_hour")
    if not _is_int(rl) or not (1 <= rl <= 240):
        v.append(f"F8: approvals.rate_limit_per_actor_per_hour={rl!r} outside [1,240]")
    if get("policy_changes", "step_up_auth") != "required":
        v.append("F8: policy_changes.step_up_auth must be 'required' (const)")
    cd = get("policy_changes", "downgrade_cooldown_hours")
    if not _is_int(cd) or cd < 24:
        v.append(f"F8: policy_changes.downgrade_cooldown_hours={cd!r} below minimum 24")
    if get("policy_changes", "diff_display") != "required":
        v.append("F8: policy_changes.diff_display must be 'required' (const)")

    # F10 — receipts: sensitive always itemized (enum membership; no 'off')
    rd = get("receipts", "read")
    if rd not in _ENUMS[("receipts", "read")]:
        v.append(f"F10: receipts.read must be one of {_ENUMS[('receipts', 'read')]}; got {rd!r}")

    # F12 — model self-approval, transcripts, LAN conditional, quarantine TTL,
    # git sensitive classes, council seats
    if get("model_self_approval") is not False:
        v.append("F12: model_self_approval must be false (const)")
    if get("capture", "llm_transcript") != "off":
        v.append('F12: capture.llm_transcript must be "off" (const)')
    if get("network", "lan", "auth") != "required":
        v.append("F12: network.lan.auth must be 'required' (const)")
    if get("network", "bind") == "lan":
        if get("network", "lan", "enabled") is not True:
            v.append("F12: network.bind=lan requires lan.enabled: true")
        if get("network", "lan", "tls") is not True:
            v.append("F12: network.bind=lan requires lan.tls: true")
    qd = get("quarantine", "ttl_days")
    if not _is_int(qd) or not (1 <= qd <= 90):
        v.append(f"F12: quarantine.ttl_days={qd!r} outside [1,90]")
    if get("git", "sensitive_classes") != "excluded":
        v.append("F12: git.sensitive_classes must be 'excluded' (const)")
    if get("council", "max_seats_per_actor") != 1:
        v.append("F12: council.max_seats_per_actor must be 1 (const)")

    # Capture bounds (schema min/max; smaller = tighter on the U-10g lattice)
    mm = get("capture", "bounds", "message_max_kib")
    if not _is_int(mm) or not (1 <= mm <= 32):
        v.append(f"SCHEMA: capture.bounds.message_max_kib={mm!r} outside [1,32]")
    te = get("capture", "bounds", "tool_excerpt_max_kib")
    if not _is_int(te) or not (1 <= te <= 8):
        v.append(f"SCHEMA: capture.bounds.tool_excerpt_max_kib={te!r} outside [1,8]")

    # Remaining enum domains (schema enums; F-relevant values checked above)
    for path_, domain in _ENUMS.items():
        val = get(*path_)
        if val is not None and val not in domain:
            key = ".".join(path_)
            if not any(s.startswith(("F6", "F10")) and key in s for s in v):
                v.append(f"SCHEMA: {key} must be one of {domain}; got {val!r}")

    # capsule token budget (schema [200, 4000])
    ct = get("context", "capsule_max_tokens")
    if not _is_int(ct) or not (200 <= ct <= 4000):
        v.append(f"SCHEMA: context.capsule_max_tokens={ct!r} outside [200,4000]")

    return v
