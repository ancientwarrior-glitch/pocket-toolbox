from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch
import io
import json
import runpy
import tempfile
import unittest
import urllib.request
import urllib.error

from home_board import home_data, render_home
from charts import serve
from install_original import install


class HomeBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def test_reads_original_formats_without_changing_records(self):
        self.write('Everyday/Jabones-Yayo/reading-log.json', {'/Books/John.epub': {'status': 'Reading'}, '/Books/Other.pdf': {'status': 'Finished'}})
        self.write('Everyday/Organizer/shopping.json', [{'text': 'Bottles', 'done': False}, {'text': 'Gloves', 'done': True}])
        self.write('Everyday/Organizer/uploads.json', [{'title': 'Soap video', 'status': 'To upload'}, {'title': 'Study', 'status': 'Published'}, {'title': 'Test', 'status': 'Download checked'}])
        self.write('Everyday/Organizer/batch-dates.json', {'2026-01-02-030000-Test.txt': '2026-01-02'})
        batch = self.home / 'Everyday/Jabones-Yayo/Batches/2026-01-02-030000-Test.txt'
        batch.parent.mkdir(parents=True)
        batch.write_text('Private batch notes')
        journal = self.home / 'Everyday/Journal/2026-01-31.txt'
        journal.parent.mkdir(parents=True)
        journal.write_text('Private journal')
        before = {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        data = home_data(self.home, date(2026, 1, 31))
        self.assertEqual(data['reading'], ['John'])
        self.assertEqual(data['shopping'], ['Bottles'])
        self.assertEqual(data['waiting'], ['Soap video'])
        self.assertEqual(data['published'], 1)
        self.assertEqual(data['checked'], 1)
        self.assertEqual(data['batches'][0]['age'], 29)
        html = render_home(data)
        self.assertNotIn('Private journal', html)
        self.assertNotIn('Private batch notes', html)
        self.assertTrue(data['journal'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_empty_and_corrupt_records_are_distinct(self):
        data = home_data(self.home)
        self.assertEqual(data['issues'], [])
        self.assertIn('No books marked Reading', render_home(data))
        self.write('Everyday/Organizer/shopping.json', {})
        data = home_data(self.home)
        self.assertIn('Could not read shopping.json', data['issues'][0])

    def test_markup_is_escaped_and_placeholders_in_names_preserved(self):
        self.write('Everyday/Organizer/shopping.json', [{'text': '<script>__ISSUES__</script>', 'done': False}])
        html = render_home(home_data(self.home))
        self.assertIn('&lt;script&gt;__ISSUES__&lt;/script&gt;', html)
        self.assertNotIn('<script>__ISSUES__', html)

    def test_latest_backup_uses_modified_time(self):
        import os
        folder = self.home / 'storage/downloads/Termux-Backups'
        folder.mkdir(parents=True)
        for name, stamp in [('z-old.tar.gz', 1), ('a-new.tar.gz', 2), ('ignored.txt', 3)]:
            path = folder / name
            path.write_text('fixture')
            os.utime(path, (stamp, stamp))
        self.assertEqual(home_data(self.home)['backup']['name'], 'a-new.tar.gz')

    def test_page_links_stay_inside_random_route(self):
        def opener(url):
            for suffix, expected in [('', b'HOME'), ('/finance', b'FINANCE'), ('/business', b'BUSINESS')]:
                with urllib.request.urlopen(url + suffix) as response:
                    self.assertEqual(response.read(), expected)
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(url + '/../../config.json')
        serve('HOME', opener=opener, pause=lambda _: None, pages={'finance': 'FINANCE', 'business': 'BUSINESS'})

    def test_installer_keeps_terminal_help_and_is_idempotent(self):
        prefix = self.home / 'prefix'
        (prefix / 'bin').mkdir(parents=True)
        menu = prefix / 'bin/menu'
        menu.write_text('case "$choice" in\n        0) exit ;;\nesac\nread -p "Choose: " choice\n')
        script = self.home / 'bin/toolbox-home.py'
        script.parent.mkdir()
        script.write_text('import sys\nprint("Original help" if sys.argv[1:] == ["help"] else "Old board")\n')
        with redirect_stdout(io.StringIO()):
            install(Path(__file__).parent, self.home, prefix)
            install(Path(__file__).parent, self.home, prefix)
        self.assertEqual(script.read_text().count('# Pocket visual dashboard add-on'), 1)
        with patch('sys.argv', [str(script), 'help']), patch('subprocess.run') as run, redirect_stdout(io.StringIO()) as out:
            runpy.run_path(str(script))
            run.assert_not_called()
            self.assertIn('Original help', out.getvalue())
        with patch('sys.argv', [str(script)]), patch('pathlib.Path.home', return_value=self.home), patch('subprocess.run') as run:
            with self.assertRaises(SystemExit):
                runpy.run_path(str(script))
            self.assertEqual(run.call_args.args[0][-1], '--board')


if __name__ == '__main__':
    unittest.main()
