"""Original toolbox's known JSON formats, read without importing its scripts."""
from datetime import date, datetime
from pathlib import Path
import html
import json
import re


def home_data(home=None, today=None):
    home = Path(home or Path.home())
    today = today or date.today()
    data = home / 'Everyday'
    organizer = data / 'Organizer'
    issues = []

    def read(path, expected, default):
        if not path.exists():
            return default
        try:
            result = json.loads(path.read_text())
            if not isinstance(result, expected):
                raise ValueError('Unexpected format')
            return result
        except (OSError, ValueError):
            issues.append('Could not read ' + path.name + '; its records were left unchanged.')
            return default

    log = read(data / 'Jabones-Yayo/reading-log.json', dict, {})
    reading = sorted(Path(name).stem for name, record in log.items()
                     if isinstance(record, dict) and record.get('status') == 'Reading')
    shopping = read(organizer / 'shopping.json', list, [])
    pending = [str(item['text']) for item in shopping
               if isinstance(item, dict) and 'text' in item and not item.get('done')]
    uploads = read(organizer / 'uploads.json', list, [])
    uploads = [r for r in uploads if isinstance(r, dict)]
    waiting = [str(r.get('title', 'Untitled')) for r in uploads if r.get('status') == 'To upload']
    dates = read(organizer / 'batch-dates.json', dict, {})
    batches = []
    for path in sorted((data / 'Jabones-Yayo/Batches').glob('*.txt'), reverse=True):
        label = path.stem
        parts = label.split('-', 4)
        if len(parts) == 5 and parts[0].isdigit():
            label = parts[4]
        made = dates.get(path.name)
        age = None
        state = 'Production date not set'
        if made:
            try:
                age = (today - date.fromisoformat(made)).days
                state = f'{age} days old' if age >= 0 else 'Production date is in the future'
            except (ValueError, TypeError):
                state = 'Check production date'
        batches.append(dict(name=label, state=state, age=age))
    backups = []
    folder = home / 'storage/downloads/Termux-Backups'
    for path in folder.glob('*'):
        if path.is_file() and (path.name.endswith('.tar.gz') or path.suffix in ('.tgz', '.zip')):
            try:
                info = path.stat()
                backups.append(dict(name=path.name, modified=info.st_mtime, size=info.st_size))
            except OSError:
                issues.append('Could not inspect a backup file.')
    latest = max(backups, key=lambda r: r['modified']) if backups else None
    if latest:
        latest['date'] = datetime.fromtimestamp(latest['modified']).strftime('%Y-%m-%d %H:%M')
    return dict(today=str(today), reading=reading, shopping=pending, batches=batches,
                waiting=waiting, published=sum(r.get('status') == 'Published' for r in uploads),
                checked=sum(r.get('status') == 'Download checked' for r in uploads),
                journal=(data / 'Journal' / f'{today:%Y-%m-%d}.txt').is_file(),
                backup=latest, issues=issues)


def render_home(data, editor=None):
    escape = lambda value: html.escape(str(value), quote=True)
    def listing(items, empty):
        if not items:
            return '<p class="empty">' + escape(empty) + '</p>'
        return '<ul>' + ''.join('<li>' + escape(item) + '</li>' for item in items) + '</ul>'
    batch_items = [b['name'] + ' · ' + b['state'] for b in data['batches']]
    backup = data['backup']
    backup_html = ('<strong>' + escape(backup['name']) + '</strong><p>' + escape(backup['date']) +
                   ' · ' + f"{backup['size']/1024/1024:.1f} MB" + '</p><small>File found in Termux-Backups. Contents and restore have not been verified.</small>') if backup else '<p class="empty">No backup archive found in Downloads/Termux-Backups.</p>'
    sections = (
        '<section><h2>Currently reading</h2>' + listing(data['reading'], 'No books marked Reading yet.') + '<small>Open Books in your terminal menu to read or change status.</small></section>' +
        '<section><h2>Shopping · still needed</h2>' + listing(data['shopping'], 'Nothing pending on your shopping list.') + '<small>Manage your checklist through Lists and trackers.</small></section>' +
        '<section><h2>Batch notebook</h2>' + listing(batch_items, 'No batch notes yet.') + '<small>From your original Jabones notes. Age does not establish product readiness. Production and stock costs are on the business board.</small></section>' +
        '<section><h2>Videos to upload</h2>' + listing(data['waiting'], 'No videos marked To upload.') + '<p>' + str(data['published']) + ' published · ' + str(data['checked']) + ' download checked</p><small>Statuses are your saved labels, not a live check of Blurt.media.</small></section>' +
        '<section><h2>Today’s journal</h2><p>' + ('Entry saved.' if data['journal'] else 'No entry saved today.') + '</p><small>Open Everyday → Today’s journal to write. Journal text stays out of this board.</small></section>' +
        '<section><h2>Latest toolbox backup</h2>' + backup_html + '</section>')
    replacements = dict(date=escape(data['today']), books=len(data['reading']), shopping=len(data['shopping']),
                        uploads=len(data['waiting']), batches=len(data['batches']), sections=sections,
                        issues=listing(data['issues'], ''),mode='Saved records and editing controls.' if editor is not None else 'Read-only snapshot.')
    page=re.sub(r'__([A-Z]+)__', lambda match: str(replacements[match[1].lower()]), PAGE)
    if editor is not None:
        from board_actions import render_editor
        page=page.replace('<!--EDITOR-->',render_editor(editor))
    return page


def open_home(finance, home=None, opener=None, pause=input):
    from charts import dashboard_data, render, serve
    from business_board import board_data, render_board
    from board_actions import BoardActions
    from contextlib import closing
    from engine import Finance
    actions=BoardActions(home or Path.home(),finance.path)
    def money_page():
        with closing(Finance(finance.path)) as current:return render(dashboard_data(current))
    def business_page():
        with closing(Finance(finance.path)) as current:return render_board(board_data(current))
    serve(lambda:render_home(home_data(home),actions.state()), opener=opener, pause=pause,
          pages={'finance': money_page, 'business': business_page},api=actions)


PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Yayo’s dashboard</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101521;color:#f4f3fc;font:16px/1.55 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px 16px 48px}header{margin-bottom:22px}.tag{font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#bea9ff}h1{font-size:clamp(30px,6vw,46px);letter-spacing:-1px;margin:4px 0}h2{font-size:20px;margin:0 0 14px}p{color:#bdc4d7;margin:8px 0}small{color:#a8b3ca;font-size:13px}nav{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}a{color:#f1ecff;text-decoration:none;background:#30264c;border:1px solid #645284;border-radius:12px;padding:14px 20px;min-height:48px}a:hover,a:focus{background:#483663;outline:2px solid #bea9ff}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}.card,section{background:#1a2233;border:1px solid #34405a;border-radius:16px;padding:20px}.card strong{display:block;font-size:32px;color:#c8b8ff}.card span{color:#bdc4d7;font-size:13px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}li{padding:10px 0;border-bottom:1px solid #303d55;overflow-wrap:anywhere}ul{padding-left:20px;margin:0 0 15px}.empty{padding:15px 0}section strong{overflow-wrap:anywhere}footer{color:#a8b3ca;font-size:13px;margin-top:24px}@media(max-width:650px){.grid{grid-template-columns:1fr}.cards{grid-template-columns:1fr 1fr}.card,section{padding:16px}main{padding:20px 12px}}
</style></head><body><main><header><div class="tag">Pocket Toolbox · on your phone</div><h1>Yayo’s dashboard</h1><p>__DATE__ · Your saved records, together.</p></header><nav><a id="finance" href="#">Finance graphs →</a><a id="business" href="#">Jabones Yayo board →</a></nav>
<div class="cards"><div class="card"><strong>__BOOKS__</strong><span>Currently reading</span></div><div class="card"><strong>__SHOPPING__</strong><span>Shopping items needed</span></div><div class="card"><strong>__UPLOADS__</strong><span>Videos to upload</span></div><div class="card"><strong>__BATCHES__</strong><span>Batch notes</span></div></div><div class="grid">__SECTIONS__</div>__ISSUES__
<!--EDITOR--><footer>__MODE__ Keep Termux’s board screen open while using the links. Return there and press Enter when finished. Reopen Dashboard to refresh. Books and journals are managed from the terminal menus. Records stay on your phone; no external scripts or uploads.</footer></main><script>
const root=location.pathname.replace(/\\/$/,'');for(const name of ['finance','business'])document.getElementById(name).href=root+'/'+name;
</script></body></html>'''
