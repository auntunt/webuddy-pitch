"""Isolated execution configuration; no official CLI, model or real credential."""
import json
import importlib.util
import os
from pathlib import Path
import tempfile
import traceback
import unittest
from unittest import mock

from tmh.platform.codex_frozen_config import MAX_CONFIG_BYTES, FrozenConfig, worker_command, worker_environment


@unittest.skipUnless(os.name == "posix" and importlib.util.find_spec("tomllib"), "isolated Linux carrier requires POSIX and Python 3.11+")
class CodexFrozenConfigTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="tmh-isolated-config-")
        self.addCleanup(temp.cleanup)
        self.home = Path(temp.name)
        self.home.chmod(0o700)
        self.base = self.home / "config.toml"
        self.overlay = self.home / "team.config.toml"
        self.write(self.base, '''model = "base-model"
model_provider = "gateway"
developer_instructions = "PUBLIC_UNWANTED_PARENT_INSTRUCTION"
[mcp_servers.unwanted]
command = "/do-not-execute"
[model_providers.gateway]
name = "synthetic"
base_url = "https://gateway.example/v1"
wire_api = "responses"
experimental_bearer_token = "SYNTHETIC_HOST_CREDENTIAL_ONLY"
''')
        self.write(self.overlay, 'model = "team-model"\nmodel_provider = "gateway"\napproval_policy = "never"\n')

    def write(self, path, content):
        path.write_text(content)
        path.chmod(0o600)

    def freeze(self, **kw):
        return FrozenConfig(self.home, "team", environment={}, **kw)

    def test_generated_worker_gets_selected_model_and_only_public_gateway(self):
        frozen = self.freeze()
        self.assertEqual(frozen.model, "team-model")
        self.assertEqual(frozen.upstream({}), {"endpoint": "https://gateway.example/v1/responses", "key": "SYNTHETIC_HOST_CREDENTIAL_ONLY"})
        config = frozen.worker_config().decode()
        binding = json.dumps(frozen.binding())
        for unwanted in ("SYNTHETIC_HOST_CREDENTIAL_ONLY", "PUBLIC_UNWANTED_PARENT_INSTRUCTION", "/do-not-execute", "https://gateway.example"):
            self.assertNotIn(unwanted, config)
            self.assertNotIn(unwanted, binding)
        self.assertIn('model = "team-model"', config)
        self.assertIn('base_url = "http://127.0.0.1:48671/v1"', config)
        self.assertIn('default_permissions = "webuddy_frozen_v1"', config)
        self.assertIn('enabled = false', config)
        self.assertEqual([x["name"] for x in frozen.binding()["sources"]], ["config.toml", "team.config.toml"])

    def test_explicit_source_owner_is_bound_and_cannot_be_chosen_by_unprivileged_caller(self):
        frozen = FrozenConfig(self.home, "team", environment={}, source_owner_uid=os.geteuid())
        self.assertEqual(frozen.binding()["source_owner_uid"], os.geteuid())
        frozen.assert_current({})
        for value in (True, -1, "0"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "owner"):
                FrozenConfig(self.home, "team", environment={}, source_owner_uid=value)
        if os.geteuid() != 0:
            with self.assertRaisesRegex(ValueError, "owner"):
                FrozenConfig(self.home, "team", environment={}, source_owner_uid=os.geteuid() + 1)

    def test_generated_config_explicitly_disables_remote_tool_plane(self):
        import tomllib
        frozen = self.freeze()
        generated = tomllib.loads(frozen.worker_config().decode())
        self.assertEqual(generated["web_search"], "disabled")
        self.assertEqual(generated["mcp_servers"], {})
        self.assertEqual(generated["plugins"], {})
        for name in ("apps", "enable_mcp_apps", "plugins", "remote_plugin", "image_generation",
                     "browser_use", "browser_use_external", "computer_use", "skill_mcp_dependency_install",
                     "tool_suggest", "recommended_plugins"):
            self.assertIs(generated["features"][name], False, name)
        self.assertEqual(generated["permissions"]["webuddy_frozen_v1"]["network"], {"enabled": False})
        self.assertNotIn("[features]", self.base.read_text())
        self.assertIn("--strict-config", worker_command())

    def test_model_override_and_exact_source_change_stale_without_fallback(self):
        frozen = self.freeze(requested_model="explicit-model")
        self.assertEqual(frozen.model, "explicit-model")
        # Even a nonselected setting is part of the original complete source.
        self.write(self.base, self.base.read_text() + '\n# changed complete source\n')
        with self.assertRaisesRegex(ValueError, "changed"):
            frozen.assert_current({})
        with self.assertRaisesRegex(ValueError, "changed"):
            frozen.upstream({})

    def test_environment_credential_rotation_cannot_silently_change_upstream(self):
        self.write(self.base, self.base.read_text().replace('experimental_bearer_token = "SYNTHETIC_HOST_CREDENTIAL_ONLY"', 'env_key = "SYNTHETIC_KEY"'))
        frozen = FrozenConfig(self.home, "team", environment={"SYNTHETIC_KEY": "SYNTHETIC_A"})
        self.assertEqual(frozen.upstream({"SYNTHETIC_KEY": "SYNTHETIC_A"})["key"], "SYNTHETIC_A")
        with self.assertRaisesRegex(ValueError, "changed"):
            frozen.upstream({"SYNTHETIC_KEY": "SYNTHETIC_B"})
        with self.assertRaisesRegex(ValueError, "unavailable"):
            frozen.upstream({})
        self.assertNotIn("SYNTHETIC_A", json.dumps(frozen.binding()))

    def test_unsupported_overlay_does_not_copy_hooks_or_provider_override(self):
        original = self.overlay.read_text()
        for suffix in ('\n[hooks]\ncommand = "bad"\n', '\n[model_providers.gateway]\nbase_url = "https://other.example/v1"\n'):
            with self.subTest(suffix=suffix):
                self.write(self.overlay, original + suffix)
                with self.assertRaisesRegex(ValueError, "unsupported"):
                    self.freeze()

    def test_complete_file_limit_rejects_instead_of_binding_a_prefix(self):
        self.write(self.base, "#" + "x" * MAX_CONFIG_BYTES)
        with self.assertRaisesRegex(ValueError, "complete-file limit"):
            self.freeze()

    def test_source_replaced_during_read_cannot_bind_old_fd_to_new_path(self):
        replacement = self.home / "replacement"
        self.write(replacement, self.base.read_text() + "\n# replacement\n")
        original_stat = os.stat
        replaced = []

        def swap_at_identity_check(name, *args, **kw):
            if name == "config.toml" and kw.get("dir_fd") is not None and not replaced:
                os.replace(replacement, self.base)
                replaced.append(True)
            return original_stat(name, *args, **kw)

        with mock.patch("tmh.platform.codex_frozen_config.os.stat", side_effect=swap_at_identity_check):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.freeze()
        self.assertEqual(replaced, [True])

    def test_invalid_endpoint_or_ambiguous_auth_is_rejected(self):
        original = self.base.read_text()
        for endpoint in ('http://gateway.example/v1', 'https://user:pass@gateway.example/v1',
                         'https://gateway.example/v1?secret=query', 'https://gateway.example:444/v1',
                         'https://gateway.example/v1/other', 'https://gateway.example:bad/v1'):
            with self.subTest(endpoint=endpoint):
                self.write(self.base, original.replace('https://gateway.example/v1', endpoint))
                with self.assertRaisesRegex(ValueError, "endpoint"):
                    self.freeze()
        self.write(self.base, original + 'env_key = "ALSO_PRESENT"\n')
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.freeze()

    def test_private_files_links_fifo_and_permissions_fail_before_use(self):
        if os.name != "posix":
            self.skipTest("POSIX carrier only")
        original = self.base.read_text()
        self.base.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.freeze()
        self.base.unlink()
        self.base.symlink_to(self.overlay)
        with self.assertRaises(OSError):
            self.freeze()
        self.base.unlink()
        os.mkfifo(self.base, 0o600)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.freeze()
        self.base.unlink()
        self.write(self.base, original)
        os.link(self.base, self.home / "alias")
        with self.assertRaisesRegex(ValueError, "owner-only"):
            self.freeze()

    def test_parser_error_does_not_export_private_line_or_parent_environment(self):
        self.write(self.base, 'private = "SYNTHETIC_PARSE_SECRET" invalid\n')
        try:
            self.freeze()
        except ValueError:
            diagnostic = traceback.format_exc()
        else:
            self.fail("malformed source accepted")
        self.assertNotIn("SYNTHETIC_PARSE_SECRET", diagnostic)
        os.environ["SYNTHETIC_PARENT_ENV"] = "PUBLIC_CONTAMINATION_CANARY"
        self.addCleanup(os.environ.pop, "SYNTHETIC_PARENT_ENV", None)
        environment = worker_environment()
        self.assertNotIn("SYNTHETIC_PARENT_ENV", environment)
        self.assertEqual(environment["CODEX_HOME"], "/work/home/.codex")
        self.assertEqual(set(environment), {"PATH", "LANG", "HOME", "CODEX_HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE", "WEBUDDY_ISOLATED_PUBLIC_KEY"})
        command = worker_command()
        self.assertEqual(command[:3], ["/usr/bin/node", "/opt/official/bin/codex.js", "exec"])
        self.assertNotIn("--sandbox", command)
        self.assertEqual(command[-1], "-")
        self.assertNotIn("--profile", command)


if __name__ == "__main__":
    unittest.main()
