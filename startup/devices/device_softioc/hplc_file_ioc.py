#!/opt/conda/bin/python3
#
# CA for the Agilent HPLC, communicates to the system using he SDK
#

import threading, subprocess, hashlib, sys
import numpy as np
import time,os
from pathlib import PureWindowsPath,Path
import json
import warnings
from epics import caget, caput


from pcaspy import Driver, SimpleServer

ADF_location = PureWindowsPath(r"C:/CDSProjects/HPLC/")
windows_ip = "xf16id@10.66.123.226"
#data_path = "/nsls2/users/jbyrnes/test_uv_scp/" will get this from login and set the PV on windows IOC#
#global proc_path
#caput('XF:16IDC-ES{HPLC}PROC_PATH

prefix = 'XF:16IDC-ES{HPLC}'

pvdb = {
    "busy" : {'type' : 'short', 'scan' : 0.5},
    "COMMAND" : {'type': 'string', 'asyn': True},
    "OUTPUT" : {'type': 'string'},
    "STATUS" : {'type' : 'enum', 'enums' : ['DONE', 'BUSY']},
    "ERROR" : {'type' : 'string'},
    "GET_UV" : {'type' : 'int', 'value' : 0, 'scan' : 1},
    "GET_UV_RBV": {'type' : 'int', 'value' : 0},
    "LAST_REASON" : {'type' : 'string'},
    "PROC_PATH":{'type' : 'char', 'count': 1024, 'value' : ''},
    "UV_dest_path": {'type' : 'char', 'count' : 1024, 'value' : ""}
}


def _run(cmd, timeout=None, capture=True):
    """Run a shell command. Returns (rc, stdout, stderr)."""
    if isinstance(cmd, list):
        popen_args = cmd
        shell=False
    else:
        popen_args = cmd
        shell=True
    proc = subprocess.Popen(popen_args, stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None,
                            shell=shell, text=True)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        return 124, out or "", (err or "") + "\nTIMEOUT"
    return proc.returncode, out or "", err or ""

class myDriver(Driver):
    def __init__(self):
        super().__init__()                     # python3
        self.lock = threading.Lock()
        self.tid = None
        self.busy = 0
        self.sample_name = None
        self.UV_dest_path = None

    def execute(self, action, *arg):
        print("executing %s(%s)" % (action,arg))
        self.busy += 1
        self.lock.acquire()
        action(*arg)
        self.lock.release()
        self.busy -= 1
        
        print("Done.")

    def _windows_dir_for_sample(self, sample):
        # Windows path: C:/CDSProjects/HPLC/<sample>/
        return str(ADF_location / sample)

    def _linux_dir_for_sample(self, sample):
        return str(Path(proc_path) / sample)
    def _make_remote_manifest(self, win_dir):
        """
        Ask Windows (over SSH) for a JSON list of files with sizes under win_dir.
        Uses PowerShell to emit JSON: [{FullName:..., Length:...}, ...]
        """
        ps = (
            "powershell -NoProfile -Command "
            "\"Get-ChildItem -LiteralPath '{}' -Recurse -File | "
            "Select-Object FullName,Length | ConvertTo-Json -Compress\""
        ).format(win_dir.replace("'", "''")) ##escapes single quotes that windows does not like
        rc, out, err = _run(["ssh", windows_ip, ps])
        if rc != 0 or not out.strip():
            return rc, None, err
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            # Normalize to relative paths using Windows separator -> POSIX for comparison
            base = PureWindowsPath(win_dir)
            manifest = {}
            for entry in data:
                full = PureWindowsPath(entry["FullName"])
                rel = str(full.relative_to(base)).replace("\\", "/")
                manifest[rel] = int(entry.get("Length", 0))
            return 0, manifest, ""
        except Exception as e:
            return 1, None, f"manifest_parse_error: {e}"

    def _make_local_manifest(self, lin_dir):
        lin_dir = Path(lin_dir)
        manifest = {}
        for root, _, files in os.walk(lin_dir):
            for f in files:
                p = Path(root) / f
                rel = str(p.relative_to(lin_dir)).replace("\\", "/")
                try:
                    sz = p.stat().st_size
                except FileNotFoundError:
                    sz = -1
                manifest[rel] = sz
        return manifest

    def _verify_dir(self, sample):
        """Compare Windows -> Linux manifests for the sample directory."""
        win_dir = self._windows_dir_for_sample(sample)
        lin_dir = self._linux_dir_for_sample(sample)
        rc, src_manifest, err = self._make_remote_manifest(win_dir)
        if rc != 0 or src_manifest is None:
            return False, f"remote_manifest_failed: {err.strip() or rc}"
        dst_manifest = self._make_local_manifest(lin_dir)

        # Fast checks
        if not src_manifest and not dst_manifest:
            return False, "empty_source_and_dest"
        if len(src_manifest) != len(dst_manifest):
            return False, f"file_count_mismatch src={len(src_manifest)} dst={len(dst_manifest)}"

        # Per-file size compare
        for rel, sz in src_manifest.items():
            if rel not in dst_manifest:
                return False, f"missing:{rel}"
            if int(dst_manifest[rel]) != int(sz):
                return False, f"size_mismatch:{rel} src={sz} dst={dst_manifest[rel]}"
        return True, "ok"    
    def _copy_with_scp(self, sample):
        proc_path = caget('XF:16IDC-ES{HPLC}PROC_PATH')
        win_dir = self._windows_dir_for_sample(sample)
        lin_dir = self._linux_dir_for_sample(sample)
        os.makedirs(lin_dir, exist_ok=True)
        src = f"{windows_ip}:{win_dir}"
        cmd = ["scp", "-r", src, str(proc_path)]
        return _run(cmd)
    def _copy_and_verify(self, sample):
        """Main workflow: copy then verify, flip PVs accordingly."""
        self.setParam('STATUS', 1)  # BUSY
        self.setParam('GET_UV_RBV', 0)
        self.setParam('LAST_REASON', "")
        self.updatePVs()
        try:
            rc, out, err = self._copy_with_scp(sample)
            method = "scp"

            self.setParam('OUTPUT', (out or "").strip())
            self.setParam('ERROR', (err or "").strip())

            if rc != 0:
                self.setParam('GET_UV_RBV', 0)
                self.setParam('LAST_REASON', f"{method}_failed_rc{rc}")
                return

            ok, reason = self._verify_dir(sample)
            self.setParam('GET_UV_RBV', 1 if ok else 0)
            self.setParam('LAST_REASON', reason)
        except Exception as e:
            self.setParam('ERROR', str(e))
            self.setParam('GET_UV_RBV', 0)
            self.setParam('LAST_REASON', f"exception:{e}")
        finally:
            self.setParam('STATUS', 0)  # DONE
            self.updatePVs()                   
                   
    '''              
    def create_uv_aray(self, sample_name):
        sample = sample_name
        ext = f"{sample_name}.dx_DAD1E.CSV"
        full_path = data_path / sample / ext
        print(f"Obtaining UV data from {full_path}")
        try:
            data = np.genfromtext(full_path , delimiter=",")
            flat = data.flatten()
            shape = list(data.shape)
            self.setParam('HPLC:UVDATA', flat.tolist())
            self.updatePVs()
        finally:
            pass
    ''' 
    def move_UVdata(self, sample_name):
        #self.sample_name = caget('XF:16IDC-ES{HPLC}SAMPLE_NAME')
        print(self.sample_name)
        rel_path =PureWindowsPath(f"r/{self.sample_name[0]}/")
        win_path = PureWindowsPath(ADF_location) / self.sample_name[0]
        full_path = f"{windows_ip}:{win_path}"
        #win_path = f"{windows_ip}:{ADF_location}{rel_path}"
        print(f"Moving UV files for {self.sample_name[0]}")
        self.runShell(command = ["scp", "-r", full_path, data_path])
                 

    
    def runShell(self, command):
        print("DEBUG : Run ", command)
        self.setParam('STATUS' , 1)
        self.updatePVs()
        try:
            time.sleep(0.01)
            proc = subprocess.Popen(command,
                                    stdout= subprocess.PIPE,
                                    stderr = subprocess.PIPE)
            proc.wait()
        except OSError:
            self.setParam('ERROR', str(sys.exc_info()[1]))
            self.setParam('OUTPUT', '')
        else:
            self.setParam('ERROR' , proc.stderr.read().rstrip())
            self.setParam('OUTPUT', proc.stdout.read().decode().rstrip())
        self.callbackPV("COMMAND")
        self.setParam('STATUS', 0)
        self.updatePVs()
        self.tid = None
        print("DEBUG: Finish " , command)
    
    def read(self, reason):
        if reason == 'busy':
            print('# of requests being processed: %d' % self.busy)
            return self.busy
        elif reason == "PROC_PATH":
            UV_dest_path = self.getParam(reason)
            self.UV_dest_path=UV_dest_path.encode("ASCII")
            print(f"{self.UV_dest_path}")
            self.setParam("UV_dest_path", self.UV_dest_path)
            return self.UV_dest_path

        print("read request: %s" % reason)
        if self.busy>0:
            print("devices busy.")
            return -1
        else:
            value = self.getParam(reason)
        
        return value

        #self.lock.acquire()
        #self.lock.release()

    def write(self, reason, value):
        status = True
        # take proper actions
        print(reason,value)

        if reason == "COMMAND":
            if not self.tid:
                command = value
                self.tid = threading.Thread(target=self.runShell, args=(command,))
                self.tid.start()
                if status:
                    self.setParam(reason, value)
                return status
            else:
                status = False

        elif reason == "GET_UV":
            if value == 1:
                # SAMPLE_NAME PV is expected to be a scalar string.
                sn = caget(f'{prefix}SAMPLE_NAME')
                # Cope with numpy/string array returns
                if isinstance(sn, (list, tuple)) or (hasattr(sn, '__len__') and not isinstance(sn, str)):
                    sn = sn[0]
                self.sample_name = sn
                #t = threading.Thread(target=self._copy_and_verify, args=(sn,), daemon=True)
                #t.start()
                if status:
                    self.setParam(reason,value)
                return status
        elif reason == "OUTPUT":
            self.setParam(reason, value)
            return status
        elif reason == "ERROR":
            self.setParam(reason, value)

        elif reason == "GET_UV_RBV":
            self.setParam(reason, value)
        elif reason == "LAST_REASON":
            self.setParam(reason, value)
        elif reason == "UV_dest_path":
            if value == "":
                value = self.getParam("PROC_PATH")
                value.encode("utf-8")
                self.setParam(reason, value)
                self.updatePVs()
            return True
        

        self.busy += 1
        self.lock.acquire()
        if True:
            time.sleep(0.5)  # dummy code
        else:
            status = False
        self.busy -= 1
        self.lock.release()

        # store the values
        if status:
            self.setParam(reason, value)
        return status

if __name__ == '__main__':
    server = SimpleServer()
    server.createPV(prefix, pvdb)
    driver = myDriver()

    # process CA transactions
    while True:
        server.process(0.1)

