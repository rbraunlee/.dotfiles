"""Preparation only: no claim of an executable OpenCode provider config."""
from copy import deepcopy
import unittest

from test_m2_environment import environment_profile
from routine.contracts import RoutineError, canonical
from routine.policy import environment_policy
from routine.provider_config import provider_preparation, executable_opencode_configuration


class ProviderPreparationTests(unittest.TestCase):
    def setUp(self):
        self.plan = environment_policy(environment_profile(), "a" * 64)

    def test_manifest_is_deterministic_scoped_non_executable_and_secret_free(self):
        manifest = provider_preparation(self.plan)
        self.assertEqual(manifest, provider_preparation(deepcopy(self.plan)))
        self.assertFalse(manifest["executable"])
        self.assertFalse(manifest["qualified"])
        self.assertEqual(manifest["kind"], "routine-provider-preparation")
        self.assertEqual(manifest["providers"], [{"id": "openai", "domains": ["api.example.com"],
            "credential_ref": "model-access", "credential_file": "/run/credentials/provider/openai/model-access"}])
        self.assertNotIn("database-access", canonical(manifest).decode())
        self.assertIn("trusted_qualified_provider_mapping", manifest["blockers"])

    def test_missing_extra_or_wrong_provider_binding_fails_closed(self):
        for mutate in (lambda p: p["credentials"].pop(),
                       lambda p: p["credentials"][-1].update(purpose="development"),
                       lambda p: p["credentials"][-1].update(target="/other/key"),
                       lambda p: p["credentials"][-1].update(delivery="environment"),
                       lambda p: p["credentials"].append(deepcopy(p["credentials"][-1]))):
            plan = deepcopy(self.plan)
            mutate(plan)
            with self.assertRaises(RoutineError):
                provider_preparation(plan)

    def test_unsupported_shapes_domains_and_inline_values_are_rejected(self):
        for change in ({"domains": ["unapproved.example"]}, {"domains": ["https://api.example.com"]},
                       {"domains": []}, {"apiKey": "FAKE-NOT-A-REAL-KEY"}, {"models": ["guessed"]}):
            plan = deepcopy(self.plan)
            plan["providers"][0].update(change)
            with self.assertRaises(RoutineError):
                provider_preparation(plan)

    def test_manifest_pins_plan_and_runtime_without_reading_credentials(self):
        manifest = provider_preparation(self.plan)
        self.assertEqual(manifest["runtime"], self.plan["runtime"])
        changed = deepcopy(self.plan)
        changed["artifact_id"] = "b" * 64
        self.assertNotEqual(manifest["plan_sha256"], provider_preparation(changed)["plan_sha256"])

    def test_no_provider_is_a_valid_preparation_but_never_executable(self):
        self.plan["providers"] = []
        self.plan["credentials"] = self.plan["credentials"][:1]
        self.assertEqual(provider_preparation(self.plan)["providers"], [])
        with self.assertRaises(RoutineError) as error:
            executable_opencode_configuration(self.plan)
        self.assertEqual(error.exception.code, "policy_unavailable")

    def test_no_mapping_flag_or_fabricated_mapping_can_enable_configuration(self):
        for mapping in (None, {}, {"qualified": True}, {"providers": {"openai": {"apiKey": "{file:key}"}}}):
            with self.assertRaises(RoutineError) as error:
                executable_opencode_configuration(self.plan, mapping)
            self.assertEqual(error.exception.code, "policy_unavailable")

    def test_preparation_rejects_unpinned_runtime_and_non_dns_domain_even_in_allowed_list(self):
        for runtime in ({"image": "worker:latest"}, {"opencode_version": "unknown"}):
            plan = deepcopy(self.plan)
            plan["runtime"].update(runtime)
            with self.assertRaises(RoutineError):
                provider_preparation(plan)
        for domain in ("https://api.example.com", "127.0.0.1", "host.local", "*.example.com"):
            plan = deepcopy(self.plan)
            plan["proxy_policy"]["allowed_domains"] = [domain]
            plan["providers"][0]["domains"] = [domain]
            with self.assertRaises(RoutineError):
                provider_preparation(plan)
