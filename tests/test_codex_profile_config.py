"""Independent profile generation does not copy credentials or change defaults."""
import subprocess
import sys
import unittest

from tmh import agentcfg


class CodexProfileConfigTest(unittest.TestCase):
    def test_inherited_profile_is_separate_and_contains_no_provider_or_secret_table(self):
        result = agentcfg.inherited_codex_profile('webuddy-cloudwave', 'aiseat', 'gpt-6-luna')
        self.assertIn('$CODEX_HOME/webuddy-cloudwave.config.toml', result)
        self.assertIn('model_provider = "aiseat"', result)
        self.assertIn('model = "gpt-6-luna"', result)
        self.assertNotIn('[model_providers', result)
        self.assertNotIn('bearer_token', result)
        self.assertNotIn('base_url', result)

    def test_invalid_names_cannot_inject_toml_or_paths(self):
        for values in (('../x', 'aiseat', 'gpt-6-luna'), ('ok', 'x\nmodel="evil"', 'gpt-6-luna'),
                       ('ok', 'aiseat', 'x"\n'), ('--bad', 'aiseat', 'gpt-6-luna')):
            with self.subTest(values=values), self.assertRaises(ValueError):
                agentcfg.inherited_codex_profile(*values)

    def test_existing_api_presets_unchanged(self):
        self.assertIn('ANTHROPIC_BASE_URL', agentcfg.claude_config('custom', 'example'))
        self.assertIn('env_key = "LLM_GATEWAY_KEY"', agentcfg.codex_config('custom', 'example'))

    def test_cli_emits_only_separate_profile(self):
        result = subprocess.run([sys.executable, '-m', 'tmh', 'agent-config', 'codex', '--model', 'gpt-6-luna',
                                 '--profile', 'webuddy-cloudwave', '--inherit-provider', 'aiseat'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), agentcfg.inherited_codex_profile('webuddy-cloudwave', 'aiseat', 'gpt-6-luna').strip())

    def test_cli_rejects_partial_profile_without_changing_any_file(self):
        result = subprocess.run([sys.executable, '-m', 'tmh', 'agent-config', 'codex', '--model', 'example',
                                 '--profile', 'webuddy-cloudwave'], capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
