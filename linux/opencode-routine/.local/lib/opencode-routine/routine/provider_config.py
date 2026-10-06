"""Secret-free routine preparation manifest, NOT executable OpenCode configuration."""
from copy import deepcopy
import ipaddress
import re

from .contracts import canonical, digest, fields, hash_value, identifier, require
from .credential_sources import normalized_binding
from .policy import credential_target
from .contracts import RoutineError


def provider_preparation(plan):
    """Consumes an approved environment plan; never resolves credentials or models."""
    hash_value(plan["artifact_id"])
    fields(plan["runtime"], ("image", "opencode_version"), "provider runtime")
    require(plan["runtime"]["opencode_version"] == "2.0.22" and isinstance(plan["runtime"]["image"], str) and
            re.fullmatch(r"sha256:[0-9a-f]{64}", plan["runtime"]["image"]),
            "invalid_runtime", "Unsupported provider preparation runtime")
    allowed = (plan.get("proxy_policy") or {}).get("allowed_domains", [])
    bindings = {}
    for binding in plan["credentials"]:
        normalized_binding(binding)
        if binding["consumer"].startswith("provider:"):
            pair = (binding["consumer"], binding["ref"])
            require(pair not in bindings, "invalid_credential", "Duplicate provider binding")
            bindings[pair] = binding
    providers, ids, expected = [], set(), set()
    for provider in plan["providers"]:
        fields(provider, ("id", "credential_ref", "domains"), "provider preparation")
        name, ref = identifier(provider["id"]), identifier(provider["credential_ref"])
        require(name not in ids, "invalid_profile", "Duplicate prepared provider")
        ids.add(name)
        domains = provider["domains"]
        require(isinstance(domains, list) and domains and all(isinstance(domain, str) and domain in allowed for domain in domains)
                and len(domains) == len(set(domains)), "invalid_profile", "Provider requires distinct approved domains")
        for domain in domains:
            require(re.fullmatch(r"(?=.{1,253}$)[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+", domain)
                    and not domain.endswith((".localhost", ".local", ".internal")),
                    "invalid_profile", "Provider requires exact public DNS names")
            try:
                ipaddress.ip_address(domain)
            except ValueError:
                pass
            else:
                raise RoutineError("invalid_profile", "Numeric provider domains are unsupported")
        pair = ("provider:" + name, ref)
        require(pair in bindings, "invalid_credential", "Provider credential binding is missing")
        expected.add(pair)
        providers.append({"id": name, "credential_ref": ref, "domains": list(domains),
                          "credential_file": credential_target(ref, pair[0])})
    require(set(bindings) == expected, "invalid_credential", "Unclaimed provider credential binding")
    return {"version": 1, "kind": "routine-provider-preparation", "artifact_id": plan["artifact_id"],
            "plan_sha256": digest(canonical(plan)), "runtime": deepcopy(plan["runtime"]), "providers": providers,
            "executable": False, "qualified": False,
            "blockers": ["trusted_qualified_provider_mapping", "opencode_configuration_isolation", "approved_endpoint_qualification"]}


def executable_opencode_configuration(plan, trusted_mapping=None):
    # No mapping format or qualification authority has been agreed. In particular
    # a caller-provided qualified=True flag must never enable provider execution.
    raise RoutineError("policy_unavailable", "OpenCode provider configuration requires an approved trusted qualified mapping; preparation is not configuration")
