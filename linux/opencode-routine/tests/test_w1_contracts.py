"""W1 local validation only; disposable planning files, no runtime launches."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

LIBRARY = Path(__file__).resolve().parents[1] / ".local/lib/opencode-routine"
sys.path.insert(0, str(LIBRARY))

from routine.contracts import RoutineError, canonical, digest
from routine.local_contracts import load_package, validate_fixture_evidence, validate_profile


def profile():
    return {
        "version": 4, "execution": "trusted-local",
        "commands": {"setup": [], "checks": {
            "test": {"argv": ["python3", "-m", "unittest"], "timeout_seconds": 30},
            "lint": {"argv": ["lint", "literal;not-a-shell-fragment"], "timeout_seconds": 15},
        }},
        "command_limits": {"command_seconds": 60, "input_bytes": 1048576, "output_bytes": 65536},
        "budgets": {"slice_seconds": 3600, "inactivity_seconds": 600,
                    "integration_seconds": 1800, "repairs": 2},
        "concurrency": {"workers_per_feature": 3},
        "credential_refs": ["dev-model"],
        "runtime": {"opencode_version": "2.0.22", "api_sha256": "a" * 64,
                    "configuration_sha256": "c" * 64, "connection_ref": "existing-service"},
        "services": [], "qa": {"kind": "none", "start": None},
    }


class LocalProfileTests(unittest.TestCase):
    def reject(self, value):
        with self.assertRaises(RoutineError):
            validate_profile(value)

    def test_valid_local_profile_and_zero_repairs(self):
        value = profile()
        validate_profile(value)
        value["budgets"]["repairs"] = 0
        validate_profile(value)

    def test_exact_fields_at_every_object(self):
        paths = [(), ("commands",), ("commands", "checks", "test"), ("command_limits",),
                 ("budgets",), ("concurrency",), ("runtime",), ("qa",)]
        for path in paths:
            for mutation in ("extra", "missing"):
                with self.subTest(path=path, mutation=mutation):
                    value = profile()
                    target = value
                    for key in path:
                        target = target[key]
                    if mutation == "extra":
                        target["unknown"] = None
                    else:
                        del target[next(iter(target))]
                    self.reject(value)

    def test_historical_versions_and_wrong_execution_are_not_local(self):
        for version in (1, 2, 3, 5, True, 4.0, "4"):
            value = profile()
            value["version"] = version
            self.reject(value)
        for execution in ("sandbox", "", None, True, []):
            value = profile()
            value["execution"] = execution
            self.reject(value)

    def test_positive_integer_fields_reject_coercion(self):
        fields = [("command_limits", key) for key in profile()["command_limits"]]
        fields += [("budgets", key) for key in ("slice_seconds", "inactivity_seconds", "integration_seconds")]
        fields += [("concurrency", "workers_per_feature")]
        for section, key in fields:
            for invalid in (0, -1, True, 1.0, "1", None):
                with self.subTest(section=section, key=key, invalid=invalid):
                    value = profile()
                    value[section][key] = invalid
                    self.reject(value)

    def test_repairs_are_integer_zero_through_two(self):
        for invalid in (-1, 3, True, 2.0, "2", None):
            value = profile()
            value["budgets"]["repairs"] = invalid
            self.reject(value)

    def test_commands_require_argv_strings_and_positive_deadlines(self):
        for argv in ([], "python3 -m unittest", [1], [True], [None], [""], ["a\x00b"], {}):
            value = profile()
            value["commands"]["checks"]["test"]["argv"] = argv
            self.reject(value)
        for timeout in (0, -1, True, 30.0, "30", None, 61):
            value = profile()
            value["commands"]["checks"]["test"]["timeout_seconds"] = timeout
            self.reject(value)

    def test_setup_and_checks_both_obey_command_and_slice_limits(self):
        for section in ("setup", "checks"):
            value = profile()
            value["budgets"]["slice_seconds"] = 30
            command = {"argv": ["fixture"], "timeout_seconds": 31}
            if section == "setup":
                value["commands"]["setup"] = [command]
            else:
                value["commands"]["checks"] = {"test": command}
            self.reject(value)
            command["timeout_seconds"] = 30
            validate_profile(value)

    def test_check_names_and_containers_are_strict(self):
        for checks in ({}, [], {"not a name": {"argv": ["test"], "timeout_seconds": 1}},
                       {1: {"argv": ["test"], "timeout_seconds": 1}}):
            value = profile()
            value["commands"]["checks"] = checks
            self.reject(value)
        value = profile()
        value["commands"]["setup"] = {}
        self.reject(value)

    def test_runtime_requires_hashes_and_nonsecret_reference_identifiers(self):
        for key, invalid in (("api_sha256", "A" * 64), ("configuration_sha256", "short"),
                             ("opencode_version", ""), ("opencode_version", 2),
                             ("connection_ref", "https://user:secret@example.com")):
            value = profile()
            value["runtime"][key] = invalid
            self.reject(value)
        for refs in (["dev", "dev"], ["secret=value"], [{"id": "dev"}], "dev", [True]):
            value = profile()
            value["credential_refs"] = refs
            self.reject(value)

    def test_services_and_qa_are_disabled_for_fixtures(self):
        for services in ({}, None, [{"id": "db"}]):
            value = profile()
            value["services"] = services
            self.reject(value)
        for qa in ({"kind": "command", "start": None}, {"kind": "none", "start": []}):
            value = profile()
            value["qa"] = qa
            self.reject(value)


class LocalPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="routine-w1-contracts-", dir="/tmp/opencode")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest_path = ".opencode/routine/features/feature/approval.json"
        spec = b"# Fixture\n<!-- criterion: AC-1 -->\n<!-- criterion: AC-2 -->\n"
        self.write("planning/spec.md", spec)
        tickets = []
        for slice_id, criteria, dependencies in (("owner", ["AC-1"], []), ("consumer", ["AC-2"], ["owner"])):
            path = f"planning/{slice_id}.md"
            data = f"# Slice {slice_id}\n".encode()
            self.write(path, data)
            tickets.append({"slice_id": slice_id, "path": path, "sha256": digest(data),
                            "criteria": criteria, "dependencies": dependencies})
        self.profile = profile()
        self.manifest = {"version": 2, "execution": "trusted-local", "feature_id": "feature",
                         "spec": {"path": "planning/spec.md", "sha256": digest(spec), "criteria": ["AC-1", "AC-2"]},
                         "tickets": tickets, "profile_sha256": digest(canonical(self.profile)),
                         "bundle_sha256": "b" * 64,
                         "baseline": {"commit": "d" * 40, "branch": "refs/heads/features/feature"}}
        self.save()

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def save(self):
        data = canonical(self.profile)
        self.write(".opencode/routine/project.json", data)
        self.manifest["profile_sha256"] = digest(data)
        self.write(self.manifest_path, canonical(self.manifest))

    def load(self):
        return load_package(self.root, "feature")

    def reject(self, code=None):
        with self.assertRaises(RoutineError) as caught:
            self.load()
        if code:
            self.assertEqual(caught.exception.code, code)

    def evidence(self):
        return {"version": 1, "execution": "trusted-local", "baseline": deepcopy(self.manifest["baseline"]),
                "profile_sha256": self.manifest["profile_sha256"], "mutations_approved": True,
                "checks": {name: {"outcome": "passed", "evidence_ref": f"baseline-{name}"}
                           for name in self.profile["commands"]["checks"]}}

    def reject_evidence(self, value):
        with self.assertRaises(RoutineError):
            validate_fixture_evidence(value, self.load())

    def test_load_returns_exact_bytes_without_mutation(self):
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        package = self.load()
        self.assertEqual(set(package), {"manifest", "profile", "snapshots"})
        self.assertEqual(package["manifest"], self.manifest)
        self.assertEqual(package["profile"], self.profile)
        self.assertEqual(package["snapshots"], {path: data.decode() for path, data in before.items()})
        self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_approval_exact_fields_nested_and_top_level(self):
        original = deepcopy(self.manifest)
        for path in ((), ("baseline",), ("spec",), ("tickets", 0)):
            for mutation in ("extra", "missing"):
                with self.subTest(path=path, mutation=mutation):
                    self.manifest = deepcopy(original)
                    target = self.manifest
                    for key in path:
                        target = target[key]
                    if mutation == "extra":
                        target["unknown"] = None
                    else:
                        del target[next(iter(target))]
                    self.write(self.manifest_path, canonical(self.manifest))
                    self.reject()

    def test_mixed_historical_packages_rejected(self):
        for version in (1, True, 2.0, "2", 3):
            self.manifest["version"] = version
            self.save()
            self.reject()
        self.manifest["version"] = 2
        self.profile["version"] = 3
        self.save()
        self.reject()
        self.profile = profile()
        self.manifest["execution"] = "sandbox"
        self.save()
        self.reject()

    def test_feature_identity_and_baseline_syntax(self):
        original = deepcopy(self.manifest)
        mutations = [("feature_id", "other"), ("bundle_sha256", "bad")]
        for key, value in mutations:
            self.manifest = deepcopy(original)
            self.manifest[key] = value
            self.save()
            self.reject()
        for key, value in (("commit", "HEAD"), ("commit", True), ("branch", "refs/heads/main"), ("branch", [])):
            self.manifest = deepcopy(original)
            self.manifest["baseline"][key] = value
            self.save()
            self.reject()
        self.manifest = deepcopy(original)
        self.manifest["baseline"]["commit"] = "d" * 64
        self.save()
        self.load()

    def test_exact_hash_drift_rejected(self):
        for path in ("planning/spec.md", "planning/owner.md", ".opencode/routine/project.json"):
            with self.subTest(path=path):
                data = (self.root / path).read_bytes()
                self.write(path, data + b"\n")
                self.reject("changed_input")
                self.write(path, data)

    def test_strict_json_and_utf8(self):
        original = (self.root / self.manifest_path).read_bytes()
        for data in (b'{"version":2,"version":2}', b'{"version":NaN}', b"\xff", b"[]"):
            self.write(self.manifest_path, data)
            self.reject()
        self.write(self.manifest_path, original)
        self.write("planning/owner.md", b"\xff")
        self.reject()

    def test_missing_symlinked_and_unnormalized_inputs(self):
        target = self.root / "planning/owner.md"
        data = target.read_bytes()
        target.unlink()
        self.reject("missing_input")
        self.write("planning/replacement.md", data)
        target.symlink_to(self.root / "planning/replacement.md")
        self.reject("invalid_path")
        target.unlink()
        self.write("planning/owner.md", data)
        for path in ("../outside.md", "/absolute.md", "planning/./owner.md", ".git/config", "planning\\owner.md"):
            self.manifest["tickets"][0]["path"] = path
            self.save()
            self.reject("invalid_path")

    def test_document_paths_must_be_distinct(self):
        for path in ("planning/spec.md", ".opencode/routine/project.json", self.manifest_path):
            self.manifest["tickets"][0]["path"] = path
            self.save()
            self.reject()

    def test_graph_unknown_self_cycle_and_duplicate_ids(self):
        original = deepcopy(self.manifest)
        for dependencies in (["missing"], ["owner"], ["consumer"]):
            self.manifest = deepcopy(original)
            self.manifest["tickets"][0]["dependencies"] = dependencies
            self.save()
            self.reject("invalid_graph")
        self.manifest = deepcopy(original)
        self.manifest["tickets"][1]["slice_id"] = "owner"
        self.save()
        self.reject()

    def test_required_criteria_match_spec_and_ticket_mappings(self):
        original = deepcopy(self.manifest)
        for criteria in (["missing"], [], ["AC-1", "AC-1"]):
            self.manifest = deepcopy(original)
            self.manifest["tickets"][0]["criteria"] = criteria
            self.save()
            self.reject()
        self.manifest = deepcopy(original)
        for spec in (b"<!-- criterion: AC-1 -->", b"<!-- criterion: AC-1 -->\n<!-- criterion: AC-1 -->\n<!-- criterion: AC-2 -->"):
            self.write("planning/spec.md", spec)
            self.manifest["spec"]["sha256"] = digest(spec)
            self.save()
            self.reject("unresolved_criteria")

    def test_passed_and_exception_fixture_evidence(self):
        value = self.evidence()
        validate_fixture_evidence(value, self.load())
        value["checks"]["lint"] = {"outcome": "exception", "evidence_ref": "lint-evidence",
                                   "failure_ref": "preexisting-lint", "scope_ref": "unrelated-lint",
                                   "approval_ref": "approved-exception"}
        validate_fixture_evidence(value, self.load())

    def test_fixture_evidence_requires_exact_approved_identity(self):
        for key, invalid in (("version", True), ("version", 1.0), ("execution", "sandbox"),
                             ("mutations_approved", 1), ("mutations_approved", False),
                             ("profile_sha256", "e" * 64)):
            value = self.evidence()
            value[key] = invalid
            self.reject_evidence(value)
        for key, invalid in (("commit", "e" * 40), ("branch", "refs/heads/features/other")):
            value = self.evidence()
            value["baseline"][key] = invalid
            self.reject_evidence(value)
        for path in ((), ("baseline",), ("checks", "test")):
            value = self.evidence()
            target = value
            for key in path:
                target = target[key]
            target["unknown"] = None
            self.reject_evidence(value)

    def test_fixture_checks_exactly_cover_named_profile_checks(self):
        for checks in ({}, [], {"test": {"outcome": "passed", "evidence_ref": "test"}},
                       {**self.evidence()["checks"], "extra": {"outcome": "passed", "evidence_ref": "extra"}}):
            value = self.evidence()
            value["checks"] = checks
            self.reject_evidence(value)

    def test_fixture_outcomes_and_reference_fields_are_strict(self):
        for entry in ({"outcome": "failed", "evidence_ref": "test"},
                      {"outcome": "passed", "evidence_ref": "secret=value"},
                      {"outcome": "passed", "evidence_ref": True},
                      {"outcome": "passed", "evidence_ref": "test", "approval_ref": "approval"},
                      {"outcome": "exception", "evidence_ref": "test"},
                      {"outcome": [], "evidence_ref": "test"}):
            value = self.evidence()
            value["checks"]["test"] = entry
            self.reject_evidence(value)
        exception = {"outcome": "exception", "evidence_ref": "test", "failure_ref": "failure",
                     "scope_ref": "scope", "approval_ref": "approval"}
        for key in exception:
            value = self.evidence()
            entry = deepcopy(exception)
            del entry[key]
            value["checks"]["test"] = entry
            self.reject_evidence(value)
        for key in ("evidence_ref", "failure_ref", "scope_ref", "approval_ref"):
            value = self.evidence()
            value["checks"]["test"] = {**exception, key: "not an identifier"}
            self.reject_evidence(value)


if __name__ == "__main__":
    unittest.main()
