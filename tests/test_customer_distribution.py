"""Customer resources are explicit and nested archives cannot bypass the audit."""
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from tmh import resources

spec = importlib.util.spec_from_file_location('customer_audit', Path(__file__).resolve().parents[1] / 'scripts/deploy/customer_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CustomerDistributionTest(unittest.TestCase):
    def test_only_approved_resources_and_code_are_copied(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in resources.FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('approved')
            for name in ('docs/self-improvement/private.md', 'agents/unreviewed.md', 'tmh/_resources/private.md', 'tmh/cache/data.py', 'tmh/user.db'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('must not ship')
            (root / 'tmh/product.py').write_text('pass')
            self.assertEqual({n for _, n in resources.files(root)}, set(resources.FILES))
            self.assertEqual([n for _, n in resources.code_files(root / 'tmh')], ['product.py'])
            self.assertIn('docs/agent-commands.md', resources.FILES)
            self.assertNotIn('README.md', resources.FILES)

    def test_nested_private_material_is_reported_without_contents(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, 'w') as z:
            z.writestr('auth.json', '{"token":"synthetic"}')
            z.writestr('private.pem', '-----BEGIN PRIVATE KEY-----\nsynthetic\n')
            z.writestr('ca.pem', '-----BEGIN CERTIFICATE-----\npublic\n')
        outer = io.BytesIO()
        with zipfile.ZipFile(outer, 'w') as z:
            z.writestr('nested.zip', inner.getvalue())
            z.writestr('tmh/_resources/skills/acceptance-l2/SKILL.md', 'JeecgBoot JB-6 internal case')
            z.writestr('Webuddy/tools/node/node-v24/node_modules/undici/lib/web/cache/cache.js', 'export function cache() {}')
            z.writestr('Webuddy/cache/generated.json', '{}')
            z.writestr('tmh/_resources/docs/self-improvement/verification-runtime-2026-10-18.md', 'internal')
        with zipfile.ZipFile(outer) as z:
            result = audit.inspect_zip(z, resource_files=resources.FILES)
        self.assertFalse(result['ok'])
        self.assertIn({'path': 'tmh/_resources/skills/acceptance-l2/SKILL.md', 'category': 'internal_resource_content'}, result['findings'])
        self.assertIn({'path': 'nested.zip!/private.pem', 'category': 'private_key_material'}, result['findings'])
        self.assertTrue(any(f['path'].endswith('generated.json') for f in result['findings']))
        self.assertFalse(any(f['path'].endswith('cache.js') for f in result['findings']))
        self.assertFalse(any(f['path'].endswith('ca.pem') for f in result['findings']))
        self.assertTrue(all(set(f) == {'path', 'category'} for f in result['findings']))
        self.assertNotIn('synthetic', str(result))

    def test_missing_runtime_guidance_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'incomplete.whl'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('tmh/__init__.py', '')
            with self.assertRaisesRegex(ValueError, 'required_resource_missing'):
                audit.require_clean(path, ['docs/agent-commands.md'])

    def test_product_privacy_rules_use_generic_patterns_and_keep_container_contract(self):
        package = io.BytesIO()
        with zipfile.ZipFile(package, 'w') as z:
            z.writestr('tmh/private.py', 'home="/Users/synthetic-developer/project"\nhost="100.64.0.9"\nhead="synthetic-login:fix-order"')
            z.writestr('tmh/container.py', 'home="/home/worker"\nhost="127.0.0.1"\nhead="owner:fix-order"')
        with zipfile.ZipFile(package) as z:
            result = audit.inspect_zip(z)
        self.assertEqual({f['category'] for f in result['findings']}, {'personal_account_example', 'personal_or_server_home_path', 'non_example_network_address'})
        self.assertTrue(all(f['path'] == 'tmh/private.py' for f in result['findings']))
