"""Local-only security additions for an existing numbered toolbox installation."""
from pathlib import Path
import os
import shutil
import subprocess
from pocket_security import verify_archive
from engine import Finance
from secure_backup import backup_bundle,restore_bundle

def roots(ui):
    return {'records':ui.root.parent,'scripts':Path(__file__).resolve().parent.parent,
            'menu':Path(os.environ['PREFIX'])/'bin/menu','widgets':Path.home()/'.shortcuts',
            'feeds':Path.home()/'.newsboat'}

def backup_folder():
    return Path.home()/'storage/downloads/Termux-Backups'

def choose_backup(ui):
    files=sorted((p for p in backup_folder().glob('toolbox-private-*.tar.gz.age') if p.is_file()),
                 key=lambda p:p.stat().st_mtime,reverse=True)
    if not files:
        print('No encrypted toolbox backups found.');return None
    return ui.choose(files,lambda p:p.name)

def verify(ui,path=None):
    path=path or choose_backup(ui)
    if not path:return False
    print('Checking:',path.name)
    print('Enter the backup passphrase. No records will be restored.')
    result=verify_archive(path)
    print('Backup verified.' if result else 'Verification failed. Check the passphrase and backup file.')
    return result

def share(ui,path=None):
    path=path or choose_backup(ui)
    if not path or not verify(ui,path):return False
    if not shutil.which('termux-open'):
        print('Share this encrypted file using your file manager:',path);return False
    result=subprocess.run(['termux-open','--send','--chooser','--content-type',
                           'application/octet-stream',str(path)],check=False)
    if result.returncode:
        print('Could not open the share chooser. File:',path);return False
    print('Share chooser requested. Select your destination and finish there.')
    print('The toolbox cannot confirm the upload. Keep the passphrase separately.')
    return True

def location(ui):
    folder=backup_folder()
    print('Backup folder:',folder)
    for path in sorted(folder.glob('toolbox-private-*.tar.gz.age')):
        if path.is_file():print(' ',path.name)
    print('In Android Files, browse Downloads > Termux-Backups. Category filters may hide .age files.')
    print('Use Share encrypted backup to select a destination directly.')

def create(ui):
    print('Encrypted backup of records, toolbox scripts, menu, widgets and RSS files. Books/media outside these roots are excluded.')
    print('Choose a strong passphrase at the age prompt. Leave empty for age to print a generated passphrase.')
    print('Save it separately before continuing. The toolbox does not store it; there is no password recovery.')
    path=backup_bundle(roots(ui),ui.root,backup_folder())
    print('Saved:',path)
    choice=input('v: verify now | s: verify and share | Enter: return after saving the passphrase: ').strip().lower()
    if choice=='v':verify(ui,path)
    elif choice=='s':share(ui,path)

def backup(ui):
    actions=[('Create encrypted backup',create),('Verify backup passphrase (no restore)',verify),
             ('Share encrypted backup (verify first)',share),('Show backup folder and filenames',location),
             ('Restore encrypted backup',restore)]
    while True:
        print('\nENCRYPTED BACKUPS')
        for number,(label,_) in enumerate(actions,1):print(f' {number}  {label}')
        print(' 0  Return')
        choice=input('Choose: ').strip()
        if choice in ('','0'):return
        if not choice.isdigit() or not 1<=int(choice)<=len(actions):
            print('Choose a listed number.');continue
        actions[int(choice)-1][1](ui)
        ui.pause()

def restore(ui):
    destination=Path.home()/'storage/downloads/Termux-Backups'
    path=ui.choose(sorted(destination.glob('toolbox-private-*.tar.gz.age'),reverse=True),lambda p:p.name)
    if not path:return
    print('Close other toolbox sessions. A new encrypted backup is required before replacing matching files.')
    ui.f.close()
    try:
        before=restore_bundle(path,roots(ui),ui.root,destination)
        if before:print('Restored. Previous state:',before)
    finally:ui.f=Finance(ui.root/'finance.sqlite')
    ui.pause()

def export(ui):
    print('Private CSV export:',ui.f.export(ui.root/'Exports'));ui.pause()

def enhance_ui(cls):
    cls.secure_backup=backup;cls.secure_restore=restore;cls.export=export

if __name__=='__main__':
    import sys
    from main import UI
    ui=UI()
    try:
        if sys.argv[1:]==['backup']:backup(ui)
        elif sys.argv[1:]==['restore']:restore(ui)
        else:raise ValueError('Choose backup or restore.')
    except (KeyboardInterrupt,EOFError):print('Cancelled.')
    except Exception as error:print('Could not finish:',error)
    finally:ui.f.close()
