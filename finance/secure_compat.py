"""Local-only security additions for an existing numbered toolbox installation."""
from pathlib import Path
import os
from engine import Finance
from secure_backup import backup_bundle,restore_bundle

def roots(ui):
    return {'records':ui.root.parent,'scripts':Path(__file__).resolve().parent.parent,
            'menu':Path(os.environ['PREFIX'])/'bin/menu','widgets':Path.home()/'.shortcuts',
            'feeds':Path.home()/'.newsboat'}

def backup(ui):
    print('Encrypted backup of records, toolbox scripts, menu, widgets and RSS files. Books/media outside these roots are excluded.')
    print('Enter a strong passphrase locally at the age prompt. Keep it safely; there is no password recovery.')
    destination=Path.home()/'storage/downloads/Termux-Backups'
    print('Saved:',backup_bundle(roots(ui),ui.root,destination));ui.pause()

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
