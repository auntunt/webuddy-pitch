"""Windows process trees owned by a non-inheritable kill-on-close Job Object."""
import base64
import codecs
import ctypes
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

K = ctypes.WinDLL('kernel32', use_last_error=True)

class BasicLimits(ctypes.Structure):
    _fields_ = [('user', ctypes.c_longlong), ('job', ctypes.c_longlong), ('flags', W.DWORD),
                ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t), ('active', W.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]

class IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ('read', 'write', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

class Limits(ctypes.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IO), ('process_memory', ctypes.c_size_t),
                ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, W.DWORD) for name in ('faults', 'total', 'active', 'terminated')]

for name, args, result in [
    ('CreateJobObjectW', [W.LPVOID, W.LPCWSTR], W.HANDLE),
    ('SetInformationJobObject', [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD], W.BOOL),
    ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
    ('QueryInformationJobObject', [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, W.LPVOID], W.BOOL),
    ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
    ('CloseHandle', [W.HANDLE], W.BOOL),
]:
    fn = getattr(K, name); fn.argtypes = args; fn.restype = result


def checked(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def run(cmd, *, cwd=None, env=None, timeout=None, cancel_event=None, stdin=None,
        on_output=None, on_spawn=None, terminate_grace=1., on_bytes=None):
    if __package__:
        from .process_control import ProcessResult
    else:
        from process_control import ProcessResult
    start = time.monotonic()
    cleanup = dict(trigger=None, term_sent=False, kill_sent=False, signals=[], errors=[],
                   remaining_group=False, output_complete=False, reaped=False, complete=False)
    job = checked(K.CreateJobObjectW(None, None))
    proc = None
    raw = bytearray()
    reason = 'exited'
    failure = None
    events = queue.Queue()
    eof = False
    decoder = codecs.getincrementaldecoder('utf-8')('replace')
    try:
        limits = Limits(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        checked(K.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        # Bootstrap cannot execute the target until it receives the request. Assign
        # it to the job first; descendants inherit membership, with no breakaway.
        proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--target'],
                                cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, bufsize=0, close_fds=True)
        checked(K.AssignProcessToJobObject(job, W.HANDLE(int(proc._handle))))
        def read():
            try:
                while True:
                    chunk = proc.stdout.read(65536)
                    if not chunk:break
                    events.put(chunk)
            except OSError as exc:events.put(exc)
            finally:events.put(None)
        reader = threading.Thread(target=read, daemon=True);reader.start()
        data = stdin.encode('utf-8') if isinstance(stdin, str) else stdin
        payload = json.dumps({'command':cmd,'stdin':base64.b64encode(data).decode() if data is not None else None}).encode()
        def write():
            try:
                pending = memoryview(payload)
                while pending:
                    written = proc.stdin.write(pending)
                    if not written:raise OSError('target input pipe accepted no bytes')
                    pending = pending[written:]
                proc.stdin.flush()
            except BrokenPipeError:pass
            except OSError as exc:events.put(exc)
            finally:proc.stdin.close()
        if on_spawn is not None:on_spawn(proc.pid,proc.pid)
        writer=threading.Thread(target=write,daemon=True);writer.start()
        stop_at = None
        while True:
            now=time.monotonic()
            try:
                chunk=events.get(timeout=.02)
                if chunk is None:eof=True
                elif isinstance(chunk,BaseException):raise chunk
                else:
                    raw.extend(chunk)
                    if on_bytes:on_bytes(chunk)
                    text=decoder.decode(chunk)
                    if text and on_output:on_output(text)
            except queue.Empty:pass
            except BaseException as exc:
                failure=exc;on_output=on_bytes=None;reason='exception'
            info=Accounting();checked(K.QueryInformationJobObject(job,1,ctypes.byref(info),ctypes.sizeof(info),None))
            rc=proc.poll()
            if stop_at is None:
                if failure:reason='exception'
                elif cancel_event is not None and cancel_event.is_set():reason='cancelled'
                elif timeout is not None and now-start>=timeout:reason='timeout'
                elif rc is not None and info.active:reason='orphaned'
                if reason!='exited':
                    cleanup.update(trigger=reason,kill_sent=True)
                    checked(K.TerminateJobObject(job,125));stop_at=now
            if rc is not None and info.active==0 and eof:break
            if stop_at is not None and now-stop_at>max(2.,terminate_grace):break
        proc.wait(timeout=2)
        info=Accounting();checked(K.QueryInformationJobObject(job,1,ctypes.byref(info),ctypes.sizeof(info),None))
        cleanup.update(remaining_group=bool(info.active),output_complete=eof,reaped=proc.returncode is not None)
        cleanup['complete']=not info.active and eof and cleanup['reaped'] and not cleanup['errors']
        tail=decoder.decode(b'',final=True)
        if tail and on_output:on_output(tail)
        code={'timeout':124,'cancelled':130,'orphaned':125,'exception':125}.get(reason,proc.returncode)
        if not cleanup['complete']:code=125;reason='cleanup_failed'
        result=ProcessResult(code,reason,time.monotonic()-start,proc.pid,proc.pid,
                             bytes(raw).decode('utf-8','replace'),bytes(raw),cleanup,proc.returncode)
        if failure:failure.process_result=result;raise failure
        return result
    finally:
        K.CloseHandle(job)  # Also terminates the job if supervision itself fails.
        if proc is not None:
            if proc.poll() is None:proc.kill()
            proc.wait(timeout=5)
            if proc.stdin and not proc.stdin.closed:proc.stdin.close()
            if proc.stdout:proc.stdout.close()


if __name__=='__main__':
    request=json.load(sys.stdin)
    data=base64.b64decode(request['stdin']) if request['stdin'] is not None else None
    child=subprocess.Popen(request['command'],stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL)
    child.communicate(data)
    raise SystemExit(child.returncode)
