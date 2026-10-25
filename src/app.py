#!/usr/bin/env python3
"""Pocket Toolbox 0.2.0. Standard-library application; Android helpers are optional."""
from pathlib import Path, PurePosixPath
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from contextlib import closing
from collections import defaultdict
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from urllib.parse import urlsplit, quote

_security_folder=Path(__file__).resolve().parent/'finance'
if not _security_folder.is_dir():_security_folder=Path(__file__).resolve().parents[1]/'finance'
sys.path.insert(0,str(_security_folder))
from pocket_security import private_dir,private_file,harden_tree,encrypt_archive,decrypted_archive,verify_archive,MAX_ARCHIVE_BYTES,MAX_MEMBER_BYTES,MAX_ARCHIVE_MEMBERS
sys.path.pop(0)

VERSION = '0.2.4-beta'
BOOKS = {'.pdf', '.epub', '.mobi', '.azw', '.azw3', '.txt'}
MEDIA = {'.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mkv', '.mov', '.3gp'}
KINDS = ('Income', 'Sale', 'Expense', 'Purchase', 'Debt payment', 'Debt collected')
INCOMING = {'Income', 'Sale', 'Debt collected'}
DEFAULTS = dict(title='Pocket Toolbox', project_name='My Project', currency='MXN',
                books_folder='~/storage/shared/Books', downloads_folder='~/storage/downloads',
                media_folder='~/storage/shared/Pocket-Toolbox-Media', color=True,
                feeds=[], shortcuts={}, peertube_hosts=[], video_height=360)

def validate_settings(settings):
    if not isinstance(settings, dict): raise ValueError('Settings must be a JSON object.')
    result = dict(DEFAULTS, **settings)
    for name in ['title','project_name','currency','books_folder','downloads_folder','media_folder']:
        if not isinstance(result[name],str) or not result[name].strip(): raise ValueError(f'{name} must be non-empty text.')
    if type(result['color']) is not bool: raise ValueError('color must be true or false.')
    if type(result['video_height']) is not int or not 1 <= result['video_height'] <= 4320: raise ValueError('video_height must be an integer from 1 to 4320.')
    for name in ['feeds','peertube_hosts']:
        if not isinstance(result[name],list) or any(not isinstance(s,str) for s in result[name]): raise ValueError(f'{name} must be a list of strings.')
    for url in result['feeds']:
        if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).netloc or any(c.isspace() for c in url): raise ValueError('Feed URLs must be single HTTP(S) URLs without spaces.')
    if not isinstance(result['shortcuts'],dict) or any(not isinstance(v,str) for v in result['shortcuts'].values()): raise ValueError('shortcuts must map names to paths.')
    return result

def stamp():
    return datetime.now().strftime('%Y%m%d-%H%M%S-%f')

def amount(text):
    value = Decimal(text.strip())
    if not value.is_finite() or value <= 0 or value * 100 != (value * 100).to_integral_value():
        raise ValueError('Use a positive amount with at most two decimals, without commas.')
    return int(value * 100)

def safe(text):
    return re.sub(r'[^\w .-]', '_', text).strip(' .')[:80] or 'Untitled'

def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.saving-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)

class App:
    def __init__(self, root=None):
        self.root = private_dir(Path(root or Path.home() / '.local/share/pocket-toolbox').expanduser().absolute())
        self.config_path = self.root / 'config.json'
        private_file(self.config_path)
        if not self.config_path.exists():
            atomic(self.config_path, json.dumps(DEFAULTS, indent=2))
        self.config = validate_settings(json.loads(self.config_path.read_text()))
        self.data = self.root / 'data'
        harden_tree(self.data)
        self.dbpath = self.data / 'budget.sqlite'
        with closing(sqlite3.connect(self.dbpath)) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY,date TEXT,scope TEXT,kind TEXT,description TEXT,cents INTEGER,debt INTEGER);
                CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY,scope TEXT,person TEXT,direction TEXT,cents INTEGER);''')
            db.commit()

    def path(self, name):
        return Path(self.config[name]).expanduser().resolve()

    def read(self, name, default):
        path = self.data / name
        return json.loads(path.read_text()) if path.exists() else default

    def write(self, name, value):
        atomic(self.data / name, json.dumps(value, indent=2, ensure_ascii=False))

    def sql(self, query, values=()):
        with closing(sqlite3.connect(self.dbpath)) as db:
            cursor = db.execute(query, values)
            rows = cursor.fetchall()
            db.commit()
            return rows

    def money(self, cents):
        return f'{Decimal(cents)/100:,.2f} {self.config["currency"]}'

    def heading(self, title):
        if sys.stdout.isatty():
            print('\033[2J\033[H', end='')
        color = '\033[1;36m' if self.config['color'] else ''
        reset = '\033[0m' if self.config['color'] else ''
        print(f'\n{color}{title}{reset}\n')

    def pause(self):
        input('\nEnter: back ')

    def choose(self, items, label=str):
        for n, item in enumerate(items, 1):
            print(f'{n:>3}  {label(item)}')
        if not items:
            print('Nothing here yet.')
            self.pause()
            return None
        value = input('\nNumber | Enter: back: ').strip()
        if value.isdigit() and 1 <= int(value) <= len(items):
            return items[int(value)-1]
        return None

    def run(self, command):
        if not shutil.which(command[0]):
            print(f'Missing command: {command[0]}. See Help for dependencies.')
            return
        subprocess.run(command, check=False)

    def open(self, target):
        self.run(['termux-open', '--chooser', str(target)])

    def note(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            self.heading(path.stem)
            print('1 Read\n2 Add\n3 Edit with nano\n0 Back')
            choice = input('\nChoose: ').strip()
            if choice == '0':
                return
            if choice == '1':
                print(path.read_text() if path.exists() else 'No notes yet.')
                self.pause()
            elif choice == '2':
                print('Write your note. A single . on a new line saves it.')
                lines = []
                while True:
                    line = input()
                    if line == '.':
                        break
                    lines.append(line)
                if any(line.strip() for line in lines):
                    with path.open('a') as out:
                        out.write(f'\n[{datetime.now():%Y-%m-%d %H:%M}]\n' + '\n'.join(lines) + '\n')
            elif choice == '3':
                if path.exists():
                    backup = self.data / 'edit-history' / (stamp() + '-' + path.name)
                    backup.parent.mkdir(exist_ok=True)
                    shutil.copy2(path, backup)
                print('CTRL+O then Enter: save. CTRL+X: exit.')
                self.pause()
                self.run(['nano', str(path)])

    def book_note(self, book):
        relative = str(book.relative_to(self.path('books_folder')))
        key = hashlib.sha256(relative.encode()).hexdigest()[:12]
        return self.data / 'reading-notes' / (safe(book.stem) + '-' + key + '.txt')

    def library(self):
        root = self.path('books_folder')
        if not root.is_dir():
            print(f'Books folder missing: {root}\nSet the path in Settings.')
            self.pause()
            return
        folder, results = root, None
        while True:
            self.heading('Library: ' + str(folder.relative_to(root)))
            favorites = set(self.read('favorites.json', []))
            items = results if results is not None else sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for n, item in enumerate(items, 1):
                if item.is_dir():
                    total = sum(p.is_file() and p.suffix.lower() in BOOKS for p in item.rglob('*'))
                    label = f'{item.name}/ ({total} books)'
                else:
                    star = '* ' if str(item.relative_to(root)) in favorites else ''
                    label = star + item.stem
                print(f'{n:>3}  {label}')
            print('\nNumber: open | a NUMBER: favorite | n NUMBER: notes\ns: search | f: favorites | r NUMBER: reading status | 0: up | q: quit')
            choice = input('\nChoose: ').strip().lower()
            if choice == 'q':
                return
            if choice == '0':
                if results is not None:
                    results = None
                elif folder != root:
                    folder = folder.parent
            elif choice == 's':
                query = input('Title, author, or category: ').casefold().strip()
                if query:
                    results = sorted(p for p in root.rglob('*') if p.is_file() and query in str(p.relative_to(root)).casefold())
            elif choice == 'f':
                results = sorted(root / name for name in favorites if (root / name).is_file() and (root / name).resolve().is_relative_to(root))
            else:
                parts = choice.split()
                if not parts: continue
                command, number = ('open', parts[0]) if len(parts) == 1 else (parts[0], parts[-1])
                if not number.isdigit() or not 1 <= int(number) <= len(items):
                    continue
                item = items[int(number)-1]
                if not item.resolve().is_relative_to(root):
                    print('This shortcut points outside the library.'); self.pause(); continue
                if command == 'open':
                    if item.is_dir():
                        folder, results = item, None
                    else:
                        self.open(item)
                elif item.is_file():
                    key = str(item.relative_to(root))
                    if command == 'a':
                        favorites.symmetric_difference_update({key})
                        self.write('favorites.json', sorted(favorites))
                    elif command == 'n':
                        self.note(self.book_note(item))
                    elif command == 'r':
                        status = self.choose(['Reading', 'Finished', 'Set aside', 'Remove from log'])
                        if status:
                            log = self.read('reading-log.json', {})
                            if status == 'Remove from log': log.pop(key, None)
                            else: log[key] = status
                            self.write('reading-log.json', log)

    def shopping(self):
        items = self.read('shopping.json', [])
        while True:
            self.heading('Shopping list')
            for n, item in enumerate(items, 1):
                print(f'{n:>3} [{"x" if item["done"] else " "}] {item["text"]}')
            choice = input('\na: add | number: check | d NUMBER: delete | 0: back: ').strip().lower()
            if choice == '0': return
            if choice == 'a':
                text = input('Item and quantity: ').strip()
                if text: items.append(dict(text=text, done=False))
            else:
                number = choice[2:].strip() if choice.startswith('d ') else choice
                if number.isdigit() and 1 <= int(number) <= len(items):
                    if choice.startswith('d '): items.pop(int(number)-1)
                    else: items[int(number)-1]['done'] = not items[int(number)-1]['done']
            self.write('shopping.json', items)

    def record(self, kind=None):
        scope = self.choose(['Personal', 'Business'])
        if not scope: return
        kind = kind or self.choose(['Income', 'Sale', 'Expense', 'Purchase'])
        if not kind: return
        description = input('Description (include quantity where useful): ').strip()
        if not description: return
        value = amount(input(f'Total {self.config["currency"]} (125.50, no commas): '))
        day = input('Date YYYY-MM-DD (Enter: today): ').strip() or str(date.today())
        day = datetime.strptime(day, '%Y-%m-%d').strftime('%Y-%m-%d')
        if input(f'{scope} | {kind} | {description} | {self.money(value)}. Save? [y/N]: ').lower() == 'y':
            self.sql('INSERT INTO entries VALUES(NULL,?,?,?,?,?,NULL)', (day, scope, kind, description, value))

    def totals(self):
        month = input('Month YYYY-MM (Enter: this month): ').strip() or str(date.today())[:7]
        month = datetime.strptime(month, '%Y-%m').strftime('%Y-%m')
        rows = self.sql('SELECT date,scope,kind,description,cents FROM entries WHERE substr(date,1,7)=? ORDER BY date,id', (month,))
        for scope in ['Personal', 'Business']:
            incoming = sum(r[4] for r in rows if r[1] == scope and r[2] in INCOMING)
            outgoing = sum(r[4] for r in rows if r[1] == scope and r[2] not in INCOMING)
            print(f'\n{scope}: in {self.money(incoming)} | out {self.money(outgoing)} | difference {self.money(incoming-outgoing)}')
        for row in rows: print(row[:4], self.money(row[4]))
        print('\nRecorded cash flow, not profit or available cash balance.')
        if input('Export this month to CSV? [y/N]: ').lower() == 'y':
            folder = self.path('downloads_folder') / 'Pocket-Toolbox-Exports'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'budget-{month}-{stamp()}.csv'
            with path.open('w', newline='', encoding='utf-8-sig') as out:
                writer = csv.writer(out)
                writer.writerow(['Date', 'Area', 'Type', 'Description', 'Money in', 'Money out', 'Currency'])
                for day, scope, kind, description, value in rows:
                    decimal = f'{Decimal(value)/100:.2f}'
                    writer.writerow([day, scope, kind, description, decimal if kind in INCOMING else '', '' if kind in INCOMING else decimal, self.config['currency']])
            print(path)
        self.pause()

    def debt_balance(self, number, original):
        return original - self.sql('SELECT COALESCE(SUM(cents),0) FROM entries WHERE debt=?', (number,))[0][0]

    def debts(self):
        print('1 Add an existing debt\n2 Record a payment/collection\n3 View debts')
        choice = input('Choose: ')
        if choice == '1':
            scope = self.choose(['Personal', 'Business'])
            person = input('Person/business: ').strip() if scope else ''
            if not person: return
            direction = self.choose(['I owe', 'Owed to me'])
            if not direction: return
            value = amount(input('Amount still outstanding (no commas): '))
            if input(f'{person}: {self.money(value)}. Save? [y/N]: ').lower() == 'y':
                self.sql('INSERT INTO debts VALUES(NULL,?,?,?,?)', (scope, person, direction, value))
                print('Existing debt recorded; no cash movement added.')
        elif choice in ('2', '3'):
            rows = self.sql('SELECT * FROM debts ORDER BY id')
            row = self.choose(rows, lambda r: f'{r[2]} | {r[1]} | {r[3]} | {self.money(self.debt_balance(r[0],r[4]))}')
            if row and choice == '2':
                number, scope, person, direction, original = row
                value = amount(input('Payment amount: '))
                if value > self.debt_balance(number, original): raise ValueError('Payment exceeds outstanding debt.')
                kind = 'Debt payment' if direction == 'I owe' else 'Debt collected'
                if input(f'{kind}: {self.money(value)}. Save? [y/N]: ').lower() == 'y':
                    self.sql('INSERT INTO entries VALUES(NULL,?,?,?,?,?,?)', (str(date.today()), scope, kind, person, value, number))
                    print('Cash movement included. Do not enter it again.')

    def correct(self):
        rows = self.sql('SELECT * FROM entries ORDER BY id DESC LIMIT 50')
        row = self.choose(rows, lambda r: f'{r[1]} | {r[2]} | {r[3]} | {r[4]} | {self.money(r[5])}')
        if not row: return
        number, day, scope, kind, description, value, debt = row
        action = input('e: edit | d: delete | Enter: cancel: ').lower()
        if action == 'd':
            if input('Type DELETE to confirm: ') != 'DELETE': return
            self.backup()
            self.sql('DELETE FROM entries WHERE id=?', (number,))
        elif action == 'e':
            newday = input(f'Date [{day}]: ').strip() or day
            newday = datetime.strptime(newday, '%Y-%m-%d').strftime('%Y-%m-%d')
            description = input(f'Description [{description}]: ').strip() or description
            text = input(f'Total [{Decimal(value)/100:.2f}]: ').strip()
            value = amount(text) if text else value
            if debt:
                original = self.sql('SELECT cents FROM debts WHERE id=?', (debt,))[0][0]
                others = self.sql('SELECT COALESCE(SUM(cents),0) FROM entries WHERE debt=? AND id<>?', (debt, number))[0][0]
                if others + value > original: raise ValueError('Amount exceeds recorded debt.')
            if input(f'{newday} | {description} | {self.money(value)}. Save? [y/N]: ').lower() != 'y': return
            self.backup()
            self.sql('UPDATE entries SET date=?,description=?,cents=? WHERE id=?', (newday, description, value, number))

    def budget(self):
        self.finance()

    def finance(self, action='main'):
        import importlib.util
        folder=self.root/'finance'
        if not (folder/'main.py').exists():folder=Path(__file__).resolve().parents[1]/'finance'
        sys.path.insert(0,str(folder))
        try:
            spec=importlib.util.spec_from_file_location('pocket_finance_ui',folder/'main.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            ui=module.UI(self.data/'Finance',public_root=self.root,config=self.config)
            try:getattr(ui,action)()
            finally:ui.f.close()
        finally:sys.path.pop(0)

    def earlier_records(self):
        print('Earlier 0.1 ledger: read-only. Use Finance option 12 to import a snapshot once.')
        for row in self.sql('SELECT * FROM entries ORDER BY date,id'):print(row)
        print('DEBTS')
        for row in self.sql('SELECT * FROM debts ORDER BY id'):print(row)
        self.pause()

    def project_note(self):
        folder = self.data / 'batches'
        folder.mkdir(exist_ok=True)
        action = input('n: new batch | Enter: existing batch: ')
        if action == 'n':
            name = input('Batch name: ').strip()
            if not name: return
            path = folder / (safe(name) + '-' + stamp() + '.txt')
        else: path = self.choose(sorted(folder.glob('*.txt')), lambda p: p.stem)
        if path: self.note(path)

    def timeline(self):
        dates = self.read('batch-dates.json', {})
        files = sorted((self.data / 'batches').glob('*.txt'))
        def label(path):
            made = dates.get(path.name)
            return path.stem + (f' | {(date.today()-date.fromisoformat(made)).days} days old' if made else ' | production date not set')
        path = self.choose(files, label)
        if path:
            text = input('Actual production date YYYY-MM-DD (Enter: cancel): ').strip()
            if text:
                made = date.fromisoformat(text)
                if made > date.today(): raise ValueError('Production date is in the future.')
                dates[path.name] = str(made)
                self.write('batch-dates.json', dates)
        print('Batch age alone does not establish curing readiness.')

    def media(self):
        source = input('Full source photo/video path (Enter: browse saved media): ').strip()
        folder = self.path('media_folder')
        if not source:
            path = self.choose(sorted(p for p in folder.glob('*') if p.is_file()), lambda p: p.name)
            if path: self.open(path)
            return
        path = Path(source).expanduser()
        if not path.is_file() or path.suffix.lower() not in MEDIA: raise ValueError('Choose a supported image or video file.')
        label = input('Label: ').strip() or path.stem
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / (stamp() + '-' + safe(label) + path.suffix)
        try: shutil.copy2(path, target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        print(f'Copied to {target}. Original kept.')
        self.pause()

    def uploads(self):
        records = self.read('uploads.json', [])
        for n, r in enumerate(records, 1): print(f'{n} [{r["status"]}] {r["title"]}')
        choice = input('a: add | number: update | Enter: back: ').strip()
        if choice == 'a':
            title = input('Title: ').strip()
            if title: records.append(dict(title=title, url='', status='To upload'))
        elif choice.isdigit() and 1 <= int(choice) <= len(records):
            record = records[int(choice)-1]
            print(record)
            link = input('Video link (Enter: keep): ').strip()
            if link and (urlsplit(link).scheme not in ('http', 'https') or not urlsplit(link).netloc): raise ValueError('Use an HTTP(S) video link.')
            status = self.choose(['To upload', 'Published', 'Download checked'])
            if not status: return
            if status != 'To upload' and not (link or record['url']): raise ValueError('Add the video link first.')
            if status == 'Download checked' and input('Have you downloaded and opened the copy yourself? [y/N]: ').lower() != 'y': return
            record.update(url=link or record['url'], status=status)
        self.write('uploads.json', records)

    def browse(self, folder=None):
        folder = folder or Path.home()
        while True:
            self.heading(str(folder))
            items = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for n, item in enumerate(items, 1): print(n, item.name + ('/' if item.is_dir() else ''))
            choice = input('number: open | a: shortcut | 0: parent | q: quit: ').strip()
            if choice == 'q': return
            if choice == '0': folder = folder.parent
            elif choice == 'a':
                name = input('Shortcut name: ').strip()
                if name:
                    shortcuts = self.read('shortcuts.json', {})
                    shortcuts[name] = str(folder)
                    self.write('shortcuts.json', shortcuts)
            elif choice.isdigit() and 1 <= int(choice) <= len(items):
                item = items[int(choice)-1]
                if item.is_dir(): folder = item
                else: self.open(item)

    def shortcuts(self):
        shortcuts = {'Home': str(Path.home()), 'Downloads': str(self.path('downloads_folder')), 'Books': str(self.path('books_folder'))}
        shortcuts.update(self.config['shortcuts'])
        shortcuts.update(self.read('shortcuts.json', {}))
        chosen = self.choose(list(shortcuts.items()), lambda pair: pair[0])
        if chosen: self.browse(Path(chosen[1]).expanduser())

    def downloads(self):
        files = sorted((p for p in self.path('downloads_folder').iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:40]
        path = self.choose(files, lambda p: p.name)
        if path: self.open(path)

    def pdf_search(self):
        if not shutil.which('pdftotext'): raise ValueError('Install PDF search: pkg install poppler')
        query = input('Word or phrase: ').strip().casefold()
        if not query: return
        matches, skipped = [], 0
        for path in self.path('books_folder').rglob('*'):
            if path.suffix.lower() != '.pdf' or not path.is_file(): continue
            print('Checking:', path.name, flush=True)
            try:
                result = subprocess.run(['pdftotext', '-layout', str(path), '-'], capture_output=True, text=True, errors='replace', timeout=30)
                if result.returncode: skipped += 1; continue
                # Normalize whitespace so phrases can span line breaks.
                if ' '.join(query.split()) in ' '.join(result.stdout.casefold().split()): matches.append(path)
            except subprocess.TimeoutExpired: skipped += 1
        print(f'{skipped} files could not be read. Image-only scans need OCR.')
        path = self.choose(matches, lambda p: p.name)
        if path: self.open(path)

    def duplicates(self):
        root = self.choose([self.path('books_folder'), self.path('downloads_folder')])
        if not root: return
        sizes, hashes = defaultdict(list), defaultdict(list)
        skipped = 0
        for p in root.rglob('*'):
            try:
                if p.is_file() and not p.is_symlink() and p.stat().st_size: sizes[p.stat().st_size].append(p)
            except OSError: skipped += 1
        for paths in sizes.values():
            if len(paths) < 2: continue
            for p in paths:
                print('Checking:', p.name, flush=True)
                try:
                    digest = hashlib.sha256()
                    with p.open('rb') as source:
                        for chunk in iter(lambda: source.read(1024*1024), b''): digest.update(chunk)
                    hashes[digest.hexdigest()].append(p)
                except OSError: skipped += 1
        groups = [paths for paths in hashes.values() if len(paths) > 1]
        report = '\n\n'.join('\n'.join(map(str, paths)) for paths in groups)
        print(report or 'No identical non-empty files found.')
        print(f'\nSkipped unreadable files: {skipped}. Nothing deleted.')
        atomic(self.data / 'duplicate-report.txt', report)
        self.pause()

    def search(self):
        query = input('Search: ').strip().casefold()
        if not query: return
        results = []
        for path in self.path('books_folder').rglob('*'):
            if path.is_file() and query in str(path.relative_to(self.path('books_folder'))).casefold(): results.append(('Book', path.name, str(path), path))
        for path in self.data.rglob('*.txt'):
            if 'edit-history' in path.parts or path.name == 'duplicate-report.txt': continue
            text = path.read_text()
            if query in (path.name + text).casefold(): results.append(('Note', path.stem, text, path))
        for name in ['shopping.json', 'uploads.json', 'reading-log.json', 'batch-dates.json']:
            records = self.read(name, {})
            iterable = list(records.items()) if isinstance(records, dict) else records
            for record in iterable:
                text = json.dumps(record, ensure_ascii=False)
                if query in text.casefold(): results.append(('Record', name, text, None))
        for row in self.sql('SELECT date,scope,kind,description,cents FROM entries'):
            text = ' | '.join(map(str, row[:4])) + ' | ' + self.money(row[4])
            if query in text.casefold(): results.append(('Earlier 0.1 budget', row[3], text, None))
        for row in self.sql('SELECT * FROM debts'):
            text = f'{row[1]} | {row[2]} | {row[3]} | Outstanding: {self.money(self.debt_balance(row[0],row[4]))}'
            if query in text.casefold(): results.append(('Earlier 0.1 debt', row[2], text, None))
        finance_path=self.data/'Finance/finance.sqlite'
        if finance_path.exists():
            with closing(sqlite3.connect(finance_path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                db.row_factory=sqlite3.Row
                for table in ['cash','invoices','batches','items','investment_events','trade_plans','journal']:
                    for row in db.execute('SELECT * FROM '+table+' ORDER BY id DESC'):
                        text=json.dumps(dict(row),ensure_ascii=False)
                        if query in text.casefold():results.append(('Finance',table+' #'+str(row['id']),text,None))
        record = self.choose(results, lambda r: f'[{r[0]}] {r[1]}')
        if record:
            print(record[2])
            if record[3] and input('o: open | Enter: back: ').lower() == 'o': self.open(record[3])
            else: self.pause()

    def export_notes(self):
        files = sorted((self.data / 'reading-notes').glob('*.txt'))
        action = input('1 One book\n2 All reading notes\nChoose: ')
        if action == '1':
            path = self.choose(files, lambda p: p.stem)
            if not path: return
            files = [path]
        elif action != '2': return
        if not files: print('No reading notes yet.'); self.pause(); return
        folder = self.path('downloads_folder') / 'Pocket-Toolbox-Exports'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('reading-notes-' + stamp() + '.txt')
        atomic(path, '\n\n'.join(p.stem + '\n' + '='*40 + '\n' + p.read_text() for p in files))
        print('Saved:', path)
        self.pause()

    def backup(self):
        folder = self.path('downloads_folder') / 'Pocket-Toolbox-Backups'
        if folder.is_relative_to(self.root): raise ValueError('Backup folder must be outside the app folder.')
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / ('pocket-' + stamp() + '.tar.gz.age')
        print('Choose a passphrase you will keep safely. If you leave it empty, age prints a generated passphrase above Saved.')
        print('Save that passphrase separately before leaving this screen. It is not stored by the toolbox.')
        with tempfile.TemporaryDirectory(prefix='.backup-',dir=self.root) as temporary:
            plain=Path(temporary)/'archive.tar.gz'
            self._write_archive(plain,temporary)
            encrypt_archive(plain,path)
        print('Encrypted backup saved:', path)
        return path

    def encrypted_backups(self):
        folder=self.path('downloads_folder')/'Pocket-Toolbox-Backups'
        return sorted((p for p in folder.glob('pocket-*.tar.gz.age') if p.is_file()),key=lambda p:p.stat().st_mtime,reverse=True)

    def verify_backup(self,path=None):
        path=path or self.choose(self.encrypted_backups(),lambda p:p.name)
        if not path:return False
        print('Checking:',path.name)
        print('Enter this backup\'s passphrase locally. Records will not be restored or changed.')
        success=verify_archive(path)
        print('Backup decryption verified. No records were restored.' if success else 'Verification failed. Check the passphrase; the existing records remain unchanged.')
        return success

    def share_backup(self,path=None):
        path=path or self.choose(self.encrypted_backups(),lambda p:p.name)
        if not path:return
        if not self.verify_backup(path):return
        if not shutil.which('termux-open'):
            print('Android sharing is unavailable here. File:',path)
            return
        print('Opening the Android share chooser for the encrypted file only. Choose an app and confirm the upload there.')
        result=subprocess.run(['termux-open','--send','--chooser','--content-type','application/octet-stream',str(path)],check=False)
        if result.returncode:print('Could not open sharing. Find this file in your configured Downloads folder:',path)
        print('No upload is confirmed by the toolbox. Keep the passphrase separate from the shared file.')

    def backup_location(self):
        folder=self.path('downloads_folder')/'Pocket-Toolbox-Backups'
        print('Backup folder:',folder)
        print('Use folder browsing in Android Files; category filters may hide .age files.')
        for path in self.encrypted_backups():print(' ',path.name)
        print('Or use Share encrypted backup to send the chosen file directly to another app.')
        self.pause()

    def create_backup(self):
        path=self.backup()
        print('Keep the passphrase shown above. Each generated passphrase belongs to its own backup.')
        choice=input('v: verify now | s: verify and share | Enter: return after saving the passphrase: ').strip().lower()
        if choice=='v':self.verify_backup(path);self.pause()
        elif choice=='s':self.share_backup(path);self.pause()

    def backups(self):
        self.menu('Encrypted backups',[
            ('Create encrypted backup',self.create_backup),
            ('Verify backup passphrase (no restore)',lambda:(self.verify_backup(),self.pause())),
            ('Share encrypted backup (verify first)',lambda:(self.share_backup(),self.pause())),
            ('Show backup folder and filenames',self.backup_location),
            ('Restore a backup',self.restore)])

    def _write_archive(self,path,temporary):
        count=0;expanded=0
        def check_member(info):
            nonlocal count,expanded
            count+=1;expanded+=info.size
            if count>MAX_ARCHIVE_MEMBERS or info.size>MAX_MEMBER_BYTES or expanded>MAX_ARCHIVE_BYTES:raise ValueError('Records exceed safe backup/restore limits.')
            info.mode=0o600
            return info
        with tarfile.open(path, 'w:gz') as out:
            with closing(sqlite3.connect(self.dbpath)) as source, closing(sqlite3.connect(str(Path(temporary)/'budget.sqlite'))) as target:
                source.backup(target)
            out.add(Path(temporary)/'budget.sqlite', arcname='data/budget.sqlite',filter=check_member)
            out.add(self.config_path, arcname='config.json',filter=check_member)
            for p in self.data.rglob('*'):
                if p.is_file() and not p.is_symlink() and p != self.dbpath and not any(p.name.endswith(s) for s in ('.sqlite-wal','.sqlite-shm','.sqlite-journal')):
                    if p.suffix=='.sqlite':
                        snapshot=Path(temporary)/('snapshot-'+hashlib.sha256(str(p).encode()).hexdigest()+'.sqlite')
                        with closing(sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)) as source,closing(sqlite3.connect(snapshot)) as target:source.backup(target)
                        out.add(snapshot,arcname='data/'+str(p.relative_to(self.data)),filter=check_member)
                    else:out.add(p, arcname='data/' + str(p.relative_to(self.data)), recursive=False,filter=check_member)

    def restore(self):
        folder = self.path('downloads_folder') / 'Pocket-Toolbox-Backups'
        path = self.choose(sorted([*folder.glob('pocket-*.tar.gz.age'),*folder.glob('pocket-*.tar.gz')], reverse=True), lambda p: p.name)
        if not path: return
        with decrypted_archive(path,self.root) as plain,tarfile.open(plain, 'r:gz') as source,tempfile.TemporaryDirectory(prefix='.stage-',dir=self.root) as temporary:
            staged, seen = [], set()
            total=0
            for index,member in enumerate(source):
                total+=member.size
                if index>=MAX_ARCHIVE_MEMBERS or member.size<0 or member.size>MAX_MEMBER_BYTES or total>MAX_ARCHIVE_BYTES:raise ValueError('Backup exceeds safe restore limits.')
                name = PurePosixPath(member.name)
                if (name.is_absolute() or '..' in name.parts or not member.isfile() or
                    not (str(name) == 'config.json' or (len(name.parts)>1 and name.parts[0]=='data'))):
                    raise ValueError('Unsupported or unsafe backup member.')
                if str(name) in seen: raise ValueError('Repeated backup member.')
                seen.add(str(name))
                dest = self.root / str(name)
                if any(p.is_symlink() for p in [dest, *dest.parents]): raise ValueError('Destination contains a symbolic link.')
                if dest.exists() and not dest.is_file(): raise ValueError('Destination is not a file.')
                temp = Path(temporary) / str(len(staged))
                with source.extractfile(member) as stream, temp.open('wb') as out: shutil.copyfileobj(stream, out)
                if temp.stat().st_size != member.size: raise ValueError('Truncated backup.')
                if str(name) == 'config.json':
                    settings = json.loads(temp.read_text())
                    validate_settings(settings)
                if str(name) == 'data/budget.sqlite':
                    with closing(sqlite3.connect(temp.as_uri()+'?mode=ro',uri=True)) as db:
                        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Invalid budget database.')
                        for table in ['entries','debts']: db.execute('SELECT * FROM '+table+' LIMIT 0')
                if str(name)=='data/Finance/finance.sqlite':
                    with closing(sqlite3.connect(temp.as_uri()+'?mode=ro',uri=True)) as db:
                        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Invalid Finance database.')
                        for table in ['accounts','cash','invoices','items','batches','imports','audit']:db.execute('SELECT * FROM '+table+' LIMIT 0')
                staged.append((temp,dest))
            if not {'config.json','data/budget.sqlite'}.issubset(seen): raise ValueError('Incomplete backup.')
            if (self.data/'Finance/finance.sqlite').exists() and 'data/Finance/finance.sqlite' not in seen:
                raise ValueError('This older backup has no Finance database. Restore it in a separate install to avoid mixing it with current Finance records.')
            print(f'{len(staged)} files. Matching records/settings will be replaced; additional files remain.')
            if input('Type RESTORE to continue: ') != 'RESTORE': return
            self.backup()
            for temp, dest in staged:
                dest.parent.mkdir(parents=True, exist_ok=True)
                fd, pending = tempfile.mkstemp(dir=dest.parent)
                try:
                    with os.fdopen(fd,'wb') as out, temp.open('rb') as stream: shutil.copyfileobj(stream,out)
                    os.replace(pending,dest)
                finally: Path(pending).unlink(missing_ok=True)
            self.config = validate_settings(json.loads(self.config_path.read_text()))
            print('Restored. Book and media files are not included in these backups.')
            self.pause()

    def rss(self):
        action = input('1 Open feeds\n2 Add a feed\n3 Remove a feed\nChoose: ')
        feeds = self.read('feeds.json', self.config['feeds'])
        if action == '2':
            url = input('HTTP(S) feed URL: ').strip()
            if urlsplit(url).scheme not in ('http','https') or not urlsplit(url).netloc or any(c.isspace() for c in url): raise ValueError('Use a single HTTP(S) URL without spaces.')
            if url not in feeds: feeds.append(url)
            self.write('feeds.json', feeds)
        elif action == '3':
            chosen = self.choose(feeds)
            if chosen: feeds.remove(chosen); self.write('feeds.json', feeds)
        elif action == '1':
            if not feeds: print('Add a feed first.'); self.pause(); return
            folder = self.data / 'rss'
            folder.mkdir(exist_ok=True)
            urls = folder / 'urls'
            atomic(urls, '\n'.join(feeds)+'\n')
            config = folder / 'config'
            command = shlex.join([sys.executable, str(Path(__file__).resolve()), '--open-url']) + ' %u'
            atomic(config, 'browser ' + json.dumps(command) + '\n')
            self.run(['newsboat','-r','-u',str(urls),'-C',str(config),'-c',str(folder/'cache.db')])

    def open_url(self, url):
        parts = urlsplit(url)
        if parts.scheme not in ('http','https') or not parts.netloc: raise ValueError('Use an HTTP(S) URL.')
        if parts.hostname in self.config['peertube_hosts']:
            video_id = parts.path.rstrip('/').split('/')[-1]
            api = f'{parts.scheme}://{parts.netloc}/api/v1/videos/{quote(video_id,safe="")}'
            try:
                with urllib.request.urlopen(api,timeout=20) as response: data = json.load(response)
                options = []
                for playlist in data.get('streamingPlaylists',[]):
                    for media in playlist.get('files',[]):
                        height = media.get('resolution',{}).get('id',0)
                        link = media.get('fileUrl','')
                        if height > 0 and link.endswith('-fragmented.mp4'):
                            options.append((height,link.removesuffix('-fragmented.mp4')+'.m3u8'))
                if not options:
                    for media in data.get('files',[]):
                        height, link = media.get('resolution',{}).get('id',0), media.get('fileUrl','')
                        if height > 0 and link: options.append((height,link))
                if options:
                    lower = [o for o in options if o[0] <= self.config['video_height']]
                    height, link = max(lower) if lower else min(options)
                    print('Selected:',height,'p')
                    self.run(['termux-open','--chooser','--content-type','video/*',link])
                    return
            except (OSError,ValueError,KeyError,TypeError) as error: print('Video lookup failed:',error)
        self.open(url)

    def dashboard(self):
        self.finance('home_board')

    def terminal_dashboard(self):
        self.heading(self.config['title'] + ' — ' + str(date.today()))
        log = self.read('reading-log.json',{})
        print('CURRENT READS')
        for name,status in log.items():
            if status == 'Reading': print(' ',Path(name).stem)
        print('\nSHOPPING')
        for item in self.read('shopping.json',[]):
            if not item['done']: print(' ',item['text'])
        print('\nBATCHES')
        dates = self.read('batch-dates.json',{})
        for path in sorted((self.data/'batches').glob('*.txt')):
            made = dates.get(path.name)
            print(' ',path.stem, f'— {(date.today()-date.fromisoformat(made)).days} days old' if made else '— production date not set')
        print('\nVIDEOS TO UPLOAD')
        for item in self.read('uploads.json',[]):
            if item['status'] == 'To upload': print(' ',item['title'])
        backups = sorted((self.path('downloads_folder')/'Pocket-Toolbox-Backups').glob('pocket-*.tar.gz'))
        print('\nLATEST BACKUP:',backups[-1].name if backups else 'None yet')
        self.pause()

    def settings(self):
        print('Settings:',self.config_path)
        print('Edit title, project name, folders, currency, feeds, video quality, colors, shortcuts.')
        if input('e: edit JSON with nano | Enter: back: ').lower() == 'e':
            original = self.config_path.read_text()
            self.run(['nano',str(self.config_path)])
            try:
                updated = json.loads(self.config_path.read_text())
                self.config = validate_settings(updated)
            except (ValueError,TypeError):
                atomic(self.config_path,original)
                print('Invalid JSON. Previous settings restored.')
                self.pause()

    def help(self):
        print("0.2: Dashboard opens the visual board; Budget opens full Finance. Create accounts/categories first.")
        print("Finance: 18 graphs, 19 business board, 20 main board. Finance 12 imports the earlier 0.1 ledger once.")
        print("Stock purchases/sales and payments are linked. Enter each once. Records stay in this toolbox’s app folder.")
        print('''Type pocket to start. 0 returns from menus. CTRL+C cancels an action.
Books: number opens; a NUMBER favorites; n NUMBER notes; r NUMBER reading status.
Notes: single . saves an entry. Nano: CTRL+O, Enter saves; CTRL+X exits.
RSS: Enter opens feed/article; o opens externally; R refreshes; q goes back.
Shopping: a adds; number checks; d NUMBER deletes.
Project stock purchases and Finance share ONE ledger. Enter each payment once.
Cash flow differs from profit. Finance also tracks opening balances and business costs.
Backups include settings and private records; books/media are excluded.
Restore makes a fresh backup first. It replaces matching files and keeps extras.
Shared files need termux-setup-storage and Android access permission.
If another app cannot open a Termux file, see README's Android file-sharing section.
Optional commands: nano, newsboat, pdftotext (pkg install nano newsboat poppler).
PDF image scans need OCR; duplicate finder never deletes files.
The customization form contains preferences, not your private records.
No telemetry; network access is used by RSS/video links you choose.
This release is a starter kit. Android app handoffs require a phone test.''')
        print('\nRecords:',self.data,'\nSettings:',self.config_path)
        self.pause()

    def menu(self, title, actions):
        while True:
            try:
                self.heading(title)
                for n,(label,_) in enumerate(actions,1): print(f'{n:>2}  {label}')
                print(' 0  Back / exit')
                choice = input('\nChoose: ').strip()
                if choice == '0': return
                if choice.isdigit() and 1 <= int(choice) <= len(actions): actions[int(choice)-1][1]()
            except KeyboardInterrupt: print('\nCancelled.')
            except (OSError,ValueError,TypeError,KeyError,InvalidOperation,sqlite3.Error,tarfile.TarError) as error:
                print('Could not finish:',error)
                self.pause()

    def main(self):
        project = lambda: self.menu(self.config['project_name'], [
            ('Batch/project notes',self.project_note),('Stock, batches, purchases and sales',lambda:self.finance('inventory')),
            ('Batch timeline',self.timeline),('Copy/open media',self.media),('Upload tracker',self.uploads)])
        self.menu(self.config['title'], [
            ('Dashboard',self.dashboard),('Books, favorites, reading log and notes',self.library),
            ('Quick notes',lambda:self.note(self.data/'notes.txt')),
            ("Today's journal",lambda:self.note(self.data/'journal'/(str(date.today())+'.txt'))),
            ('Shopping list',self.shopping),('Budget and debts',self.budget),
            (self.config['project_name'],project),('RSS and videos',self.rss),
            ('Recent downloads',self.downloads),('Folder shortcuts',self.shortcuts),
            ('Search everything',self.search),('Search PDF text',self.pdf_search),
            ('Find duplicate files',self.duplicates),('Export reading notes',self.export_notes),
            ('Backups: create, verify and share',self.backups),('Restore records',self.restore),
            ('Settings',self.settings),('Help',self.help),
            ('Finance graphs',lambda:self.finance('graphs')),
            ('Business board',lambda:self.finance('business_board')),
            ('Earlier 0.1 ledger (read-only)',self.earlier_records)])

if __name__ == '__main__':
    if '--version' in sys.argv:
        print(VERSION)
    else:
        sys.path.insert(0,str(_security_folder))
        from app_lock import guard
        guard()
        try:
            app = App()
            if len(sys.argv)>2 and sys.argv[1]=='--open-url': app.open_url(sys.argv[2])
            else: app.main()
        except (KeyboardInterrupt,EOFError): print('\nClosed.')
