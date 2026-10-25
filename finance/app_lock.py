"""Password-gated terminal sessions. This is an interface lock, not file encryption.

A controller owns a private flock and PTY; descendants in that terminal session
may enter the toolbox without re-prompting. Closing/idle terminates its process
 group, including local board servers. No password/session secret is put in argv.
"""
from pathlib import Path
import base64
import errno
import fcntl
import getpass
import hashlib
import hmac
import json
import os
import pty
import secrets
import select
import signal
import sys
import termios
import time
import tty
from pocket_security import private_dir, private_file, no_links

IDLE_SECONDS=300
N=32768
MARKER='# Pocket password launcher'

def folder():return private_dir(Path.home()/'.config/pocket-toolbox-lock')
def config_path():return folder()/'password.json'
def read_json(path):
    no_links(path)
    if path.stat().st_size>4096:raise ValueError('Invalid lock settings; refusing to open.')
    return json.loads(path.read_text())
def atomic(path,value):
    path=no_links(path);pending=no_links(path.with_name('.'+path.name+'-'+secrets.token_hex(8)))
    try:
        with pending.open('x') as stream:
            json.dump(value,stream);stream.flush();os.fsync(stream.fileno())
        pending.chmod(0o600);os.replace(pending,path)
        fd=os.open(str(path.parent),os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:pending.unlink(missing_ok=True)

def derive(password,salt):
    return hashlib.scrypt(password.encode('utf-8'),salt=salt,n=N,r=8,p=1,maxmem=64*1024*1024,dklen=32)
def password_record(password):
    if len(password)<12 or len(password.encode('utf-8'))>1024:raise ValueError('Use a password/passphrase of 12–1024 characters (at most 1024 UTF-8 bytes).')
    salt=secrets.token_bytes(32)
    return {'version':1,'salt':base64.b64encode(salt).decode(),'hash':base64.b64encode(derive(password,salt)).decode()}
def matches(password,record):
    if not isinstance(record,dict) or record.get('version')!=1:raise ValueError('Unsupported lock settings.')
    try:salt=base64.b64decode(record['salt'],validate=True);wanted=base64.b64decode(record['hash'],validate=True)
    except (KeyError,ValueError,TypeError) as e:raise ValueError('Invalid lock settings.') from e
    if len(salt)!=32 or len(wanted)!=32:raise ValueError('Invalid lock settings.')
    if len(password.encode('utf-8'))>1024:return False
    return hmac.compare_digest(derive(password,salt),wanted)

def ask_new():
    first=getpass.getpass('New toolbox password (12+ characters): ')
    if first!=getpass.getpass('Repeat toolbox password: '):raise ValueError('Passwords differ. Nothing changed.')
    return password_record(first)

def authenticate():
    path=config_path()
    if not path.exists():
        print('\nSET UP TOOLBOX PASSWORD\nThis password will be required each time you open a new toolbox session.')
        print('This locks the interface. Working files remain readable from the Termux shell.')
        print('It is separate from your encrypted-backup passwords. Save it safely.')
        record=ask_new();atomic(path,record);print('Toolbox password created.');return
    private_file(path);record=read_json(path)
    throttle=folder()/'attempts.json'
    state=read_json(throttle) if throttle.exists() else {'failures':0,'retry':0}
    if not isinstance(state,dict) or type(state.get('failures')) is not int or not isinstance(state.get('retry'),(float,int)):raise ValueError('Invalid retry state.')
    delay=min(60,max(0,state['retry']-time.time()))
    if delay:raise ValueError(f'Too many attempts. Try again in {int(delay)+1} seconds.')
    if not matches(getpass.getpass('Toolbox password: '),record):
        failures=min(20,state['failures']+1);wait=min(60,2**min(failures,6))
        atomic(throttle,{'failures':failures,'retry':time.time()+wait})
        raise ValueError('Wrong password. Toolbox remains closed.')
    atomic(throttle,{'failures':0,'retry':0})

def active():
    path=folder()/'active.json'
    if not path.exists():return None
    try:
        record=read_json(path)
        if type(record.get('sid')) is not int or type(record.get('controller')) is not int:return None
        if record['controller']<=1 or record['sid']<=1:return None
        os.kill(record['controller'],0)
        # A stale state file must not authorize access after a crash.
        with no_links(folder()/'session.lock').open('a+') as stream:
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return record
            finally:
                try:fcntl.flock(stream,fcntl.LOCK_UN)
                except OSError:pass
    except (OSError,ValueError,TypeError):return None
    return None

def authorized():
    record=active()
    return bool(record and os.getsid(0)==record['sid'])

def touch():
    if authorized():
        path=folder()/'activity';no_links(path);path.touch(mode=0o600,exist_ok=True)

def request_lock():
    record=active()
    if record:os.kill(record['controller'],signal.SIGUSR1);return True
    return False

def guard(argv=None):
    """Call before a protected script opens data. Re-enter via a PTY on success."""
    if authorized():return
    command=argv or [sys.executable,*sys.argv]
    try:raise SystemExit(run(command))
    except (KeyboardInterrupt,EOFError):raise SystemExit('Cancelled. Toolbox remains closed.')
    except (ValueError,OSError) as error:raise SystemExit(str(error))

def sync_size(fd):
    if sys.stdin.isatty():
        size=fcntl.ioctl(sys.stdin.fileno(),termios.TIOCGWINSZ,b'\0'*8)
        fcntl.ioctl(fd,termios.TIOCSWINSZ,size)

def stop_group(pid):
    try:os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError:return
    until=time.monotonic()+1
    while time.monotonic()<until:
        try:
            if os.waitpid(pid,os.WNOHANG)[0]:break
        except ChildProcessError:break
        time.sleep(.02)
    try:os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    try:os.waitpid(pid,0)
    except ChildProcessError:pass

def run(command,idle=IDLE_SECONDS):
    if not command:raise ValueError('Missing toolbox command.')
    if not sys.stdin.isatty():raise ValueError('Open this command in an interactive Termux terminal.')
    lease=no_links(folder()/'session.lock').open('a+')
    try:
        verified=False
        try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            authenticate();verified=True
            if not request_lock():raise ValueError('Another session is starting. Close it and try again.')
            end=time.monotonic()+4
            while True:
                try:fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=end:raise ValueError('Previous session is still closing. Try again shortly.')
                    time.sleep(.05)
        if not verified:authenticate()
        print('Unlocked. Exit to lock, or use Ctrl+] to lock now. Auto-lock: 5 minutes without terminal input or board loading/saving.',flush=True)
        state=folder()/'active.json';activity=folder()/'activity';no_links(activity);activity.touch(mode=0o600)
        oldtty=termios.tcgetattr(sys.stdin.fileno());pid=fd=None;handlers={};closing=[False]
        def close(*args):closing[0]=True
        def resize(*args):
            if fd is not None:sync_size(fd)
        try:
            # Child waits for a pipe handshake until its SID has been registered.
            read,write=os.pipe()
            controller=os.getpid()
            pid,fd=pty.fork()
            if pid==0:
                try:
                    os.close(write);os.read(read,1);os.close(read);lease.close()
                    group=os.getpgrp()
                    if os.fork()==0:
                        os.closerange(0,256)
                        while True:
                            try:os.kill(controller,0)
                            except ProcessLookupError:
                                try:os.killpg(group,signal.SIGKILL)
                                except ProcessLookupError:pass
                                os._exit(0)
                            time.sleep(.2)
                    os.execvp(command[0],command)
                except BaseException:os._exit(127)
            os.close(read);sync_size(fd)
            atomic(state,{'sid':pid,'controller':os.getpid()})
            os.write(write,b'1');os.close(write)
            for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGUSR1,signal.SIGINT):handlers[sig]=signal.signal(sig,close)
            handlers[signal.SIGWINCH]=signal.signal(signal.SIGWINCH,resize)
            tty.setraw(sys.stdin.fileno());last=time.monotonic();seen=activity.stat().st_mtime_ns
            while not closing[0]:
                stamp=activity.stat().st_mtime_ns
                if stamp!=seen:last=time.monotonic();seen=stamp
                if time.monotonic()-last>=idle:break
                ready,_,_=select.select([sys.stdin.fileno(),fd],[],[],.2)
                if sys.stdin.fileno() in ready:
                    value=os.read(sys.stdin.fileno(),4096)
                    if not value or b'\x1d' in value:break
                    last=time.monotonic();os.write(fd,value)
                if fd in ready:
                    try:value=os.read(fd,65536)
                    except OSError as e:
                        if e.errno==errno.EIO:break
                        raise
                    if not value:break
                    sys.stdout.buffer.write(value);sys.stdout.buffer.flush()
        finally:
            if pid:stop_group(pid)
            if fd is not None:os.close(fd)
            termios.tcsetattr(sys.stdin.fileno(),termios.TCSADRAIN,oldtty)
            for sig,old in handlers.items():signal.signal(sig,old)
            state.unlink(missing_ok=True);activity.unlink(missing_ok=True)
            print('\033[2J\033[3J\033[HToolbox locked.',flush=True)
        return 0
    finally:lease.close()

def settings():
    if not authorized():guard([sys.executable,__file__,'--settings'])
    print('CHANGE TOOLBOX PASSWORD\nExisting encrypted-backup passwords will not change.')
    authenticate()
    record=ask_new();atomic(config_path(),record);print('Password changed. It applies on your next unlock.')

def main():
    try:
        if sys.argv[1:]==['--check']:raise SystemExit(0 if authorized() else 1)
        if sys.argv[1:]==['--lock']:
            print('Lock requested.' if request_lock() else 'Toolbox is already locked.');return
        if sys.argv[1:]==['--settings']:settings();return
        args=sys.argv[1:]
        if args and args[0]=='--':args=args[1:]
        raise SystemExit(run(args))
    except (KeyboardInterrupt,EOFError):raise SystemExit('Cancelled. Toolbox remains closed.')
    except (ValueError,OSError) as error:raise SystemExit(str(error))

if __name__=='__main__':main()
