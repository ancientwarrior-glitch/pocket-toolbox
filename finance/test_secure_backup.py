from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from unittest.mock import patch
import io
import json
import shutil
import sqlite3
import tarfile
import unittest
from secure_backup import backup_bundle,restore_bundle

@contextmanager
def plain_fixture(source,root):yield source

def cipher_fixture(source,target):shutil.copyfile(source,target);return target

class BundleTests(unittest.TestCase):
    def test_bundle_round_trip_snapshots_and_preserves_extra_files(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);records=root/'records';records.mkdir();scripts=root/'scripts';scripts.mkdir()
            (records/'note.txt').write_text('before');(scripts/'run').write_text('fixture');(scripts/'run').chmod(0o700)
            with sqlite3.connect(records/'finance.sqlite') as db:db.execute('CREATE TABLE fixture(value)');db.execute('INSERT INTO fixture VALUES(1)')
            mapping={'records':records,'scripts':scripts}
            with patch('secure_backup.encrypt_archive',side_effect=cipher_fixture),patch('secure_backup.decrypted_archive',side_effect=plain_fixture):
                archive=backup_bundle(mapping,records,root/'exports')
                (records/'note.txt').write_text('after');(records/'extra.txt').write_text('keep')
                prior=restore_bundle(archive,mapping,records,root/'exports',confirm=lambda _: 'RESTORE')
            self.assertTrue(prior.is_file());self.assertEqual((records/'note.txt').read_text(),'before')
            self.assertEqual((records/'extra.txt').read_text(),'keep')
            self.assertEqual((scripts/'run').stat().st_mode&0o777,0o700)
            with sqlite3.connect(records/'finance.sqlite') as db:self.assertEqual(db.execute('SELECT value FROM fixture').fetchone()[0],1)
            self.assertEqual(list(records.glob('.bundle-*')),[])

    def test_unsafe_bundle_rejected_before_backup_or_write(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);records=root/'records';records.mkdir();archive=root/'bad.tar.gz.age'
            with tarfile.open(archive,'w:gz') as out:
                body=b'unsafe';member=tarfile.TarInfo('records/../../escape');member.size=len(body);out.addfile(member,io.BytesIO(body))
            with patch('secure_backup.decrypted_archive',side_effect=plain_fixture),patch('secure_backup.backup_bundle') as before:
                with self.assertRaises(ValueError):restore_bundle(archive,{'records':records},records,root/'exports')
                before.assert_not_called()
            self.assertFalse((root/'escape').exists())

    def test_backup_rejects_links(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);records=root/'records';records.mkdir();(records/'link').symlink_to(root/'outside')
            with self.assertRaises(ValueError):backup_bundle({'records':records},records,root/'exports')

if __name__=='__main__':unittest.main()
