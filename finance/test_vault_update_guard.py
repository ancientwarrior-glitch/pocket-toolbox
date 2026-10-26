from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
import json
from pocket_security import require_plain_storage
from install_passwords import install as password_install
from install_security import install as security_install

class VaultUpdateGuardTests(TestCase):
    def test_plain_password_gate_is_allowed(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'.config/pocket-toolbox-lock/password.json';path.parent.mkdir(parents=True);path.write_text('{"version":1}')
            require_plain_storage(root)
    def test_vault_marker_blocks_both_original_updaters_before_writes(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'.config/pocket-toolbox-lock/password.json';path.parent.mkdir(parents=True);path.write_text('{"version":1,"vault":{"phase":"migrating"}}')
            before=path.read_bytes()
            with self.assertRaises(ValueError):password_install(root/'nonexistent',root,root/'prefix')
            with self.assertRaises(ValueError):security_install(root/'nonexistent',root,root/'prefix')
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse((root/'bin').exists())
    def test_corrupt_privacy_configuration_is_not_ignored(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'.config/pocket-toolbox-lock/password.json';path.parent.mkdir(parents=True);path.write_text('bad json')
            with self.assertRaises(ValueError):require_plain_storage(root)

    def test_record_marker_alone_blocks_password_reset_style_update(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);marker=root/'Everyday/.pocket-vault-required';marker.parent.mkdir();marker.write_bytes(b'fixture marker')
            with self.assertRaises(ValueError):require_plain_storage(root)
