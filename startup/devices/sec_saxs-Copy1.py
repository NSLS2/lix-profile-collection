print(f"Loading file {__file__}...")
###Choosing the Experimental Type, ColumnType, Column Position, Buffer Positions will determine the flowpath, either A or B
###need 2 selection valves, one for regen pump and the other for HPLC
####column position 1 should always be to X-ray, Column position 2, regen, etc.  Valve will place these positions in the desired flowpath.
from time import sleep
from enum import Enum
from pathlib import PureWindowsPath, Path
import yaml, json
import threading as th
import pandas as pd
from epics import caget, caput
import warnings
from lixtools.samples import parseSpreadsheet, autofillSpreadsheet
#from APV import APV
#from hplccon import AgilentHPLC
global proc_path
import copy
ADF_location = PureWindowsPath(r"C:/CDSProjects/HPLC/")
windows_ip  = "xf16id@10.66.123.226"
'''
TCP_IP = '10.66.122.80'  ##moxa on HPLC cart.  Port 1 is valve, Port 2 is regen pump, Port 3 will contain all VICI valves
Pump_TCP_PORT = 4002
VICI_TCP_PORT = 4003
socket.setdefaulttimeout(10)
timeout=socket.getdefaulttimeout()
print(timeout)
'''

'''
class VICI_ID(Enum):
    regen_valve = 1
    buffer_purge = 2
    Column_1_purge = 3
    Column_2_purge = 4
'''    
'''
class VICI_valves:
    def __init__(self):
        self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((TCP_IP, VICI_TCP_PORT))
        #self.vici_id = VICI_ID(vici_id) don't need to setuep a separate call for each valve
        #self.get_status()
        #self.get_status()
        
    def send_valve_cmd(self, cmd):
        cmd=f"{ID}{cmd}\r"
        self.sock.sendall(cmd.encode())
        print(f"Command {cmd} has been sent")
        time.sleep(0.2)
        ret=self.sock.recv(1024)
        ascii_ret=ret.decode("ascii")
        print(ascii_ret)
        
        #self.sock.close()
    
    def check_valve_pos(self):
        cmd = f"{ID}CP\r"
        self.sock.sendall(cmd.encode())
        print("Getting 10-port Valve status")
        ret = self.sock.recv(1024)
        ascii_ret = ret.decode("ascii")
        print(ascii_ret)
        print(ascii_ret[-3])
        return ascii_ret
        
    def switch_10port_valve(self, pos="A", ID=1):
        cur_pos=self.check_valve_pos(ID=ID)  ## format is "Postion is A' \r"
        if cur_pos[-3] == pos:
            print(f"10-port Valve already at {pos}!")
        
        elif cur_pos[-3] != pos:
            if pos=="A":
                self.send_valve_cmd("GOA", ID=ID)
            elif pos=="B":
                self.send_valve_cmd("GOB", ID=ID)
        else:
            raise Exception(f"{pos} is not a valid command to change 10-port valve! Use 'A' or 'B'.")
    
VV = VICI_valves()   

'''





"""
def switch_10port_valve(pos="A"):
    if pos=="A":
        #send_valve_cmd("GOA")
        print("A")
    elif pos=="B":
            #send_valve_cmd("GOB")
            print("B")
            
    else:
        raise Exception(f"{pos} is not a valid command to change 10-port valve! Use 'A' or 'B'.")
"""       
def open_purge_pump(channel=None, flowrate=3, ID=2):
    """
    This will be used to prime the buffers in the Agilent Pump only.  A purge of the superloop up to column will be a second valve 
    and should be combined into this function.
    The aurora pro selection valve will select the buffer, ID2 VIVI valve will turn to waste.
    Flowrate should be increased after valves switched.
    """
    #Valve_ID=2 ##VICI purge valve
    input("Before purging the pump, check to make sure you are purging correct buffer line in Agilent and that it is purged in water before switching to another buffer.  Then hit enter:")
    cmd=(f'{ID}GOA')
    VV.send_valve_cmd(cmd, ID)
    time.sleep(0.5)
    status= VV.check_valve_pos(ID)
    print(status)
    #if status==f"{ID} Position is "A"":
        #do something in SDK to set flow
        
    return status

    
class Columns():
    '''
    Define columns here.  New columns can be instantiated with attributes, column_type, pressure (bar), flow rate (ml/min) and location on HPLC.
    Pos 1 goes to X-ray flow cell.  Pos 2 is the regen/UV/MALS/RID line.  Remember that one will have to create a new method in Agilent SDK or in the GUI for the particular column.
    '''
    
    def __init__(self, 
                column_type = None,
                pressure = None,
                flow_rate = None,
                location = None):
        self.column_type = column_type if column_type is not None else column_type in self.column_parameters['column_type'].keys()
        self.pressure_sv = pressure if pressure is not None else 1
        self.high_pressure_limit = None
        self.location = location if location is not None else 1 #currently only 1 or 2.  2 is regeneration location
        self.flow_rate_sv = flow_rate if flow_rate is not None else 0.1  #ml/min
        self.flow_rate_limit = None

class SEC_SAXSCollection():
    column_parameters = {"column_type": {"Superdex_200_5_150" : {"max_pressure" : 32, "max_flow" : 0.35}, 
                                   "dSEC2":{"max_pressure" : 120, "max_flow" : 0.35}, 
                                   "Superose_6": {"max_pressure" : 32, "max_flow" : 0.35}, }}
    
    experiment_type = ["X-ray_UV","X-ray_only","X-ray_UV_MALS_RID", "X-ray_Regen","UV_MALS_RID_only"]
    buffer_position = [1,2,3,4,5,6]
    if proposal_id is None or run_id is None:
        print("need to login first ...")
        #login()
    def __init__(self,
                exp_type = None,
                buff_pos = None,
                sec_slots = {'col_pos1': {"status" : True, "column_type" : "Superdex_200_5_150"},
                              'col_pos2': {"status" : False, "column_type" : "dSEC2"}}
                ):
        #super().__init__()
        self.column_locations = sec_slots
        self.exp_type= exp_type if exp_type is not None else self.experiment_type
        self.buff_pos= buff_pos if buff_pos is not None else self.buffer_position
        caput('XF:16IDC-ES{HPLC}SDK_Connection', 1) ## PV not resetting properly, need to fix.  Also need to disconnect from SDK first
        caget('XF:16IDC-ES{HPLC}HPLCRunStatus')
        caput('XF:16IDC-ES{HPLC}Result_Path' , '')
        self.hplc_status = None
        self.injection_vol = 50 #default
        self.acq_method = None
        self.proc_method = 'CSV_ADF_export'
        self.sample_loc = None ##format D1F-XXX
        self.sample_name = None
        self.sample_description = 'api_single_run'
        self.sample_type = 'Sample'
        self.sample_params = {'proc_method':self.proc_method,
                             'sample_type':self.sample_type,
                             'sample_descrip':self.sample_description,
                             'injection_vol': self.injection_vol}
        self.result_path = None
        self.result_name = "<S>"
        caput('XF:16IDC-ES{HPLC}Result_Name' , self.result_name)
        
    def update_ctype_cpos_(self, position, column_type, new_status=True ):
        if not column_type in self.column_parameters["column_type"].keys():
            raise ValueError(f"{column_type} is not defined, please create a definition for the column!")
        elif position in self.column_locations.keys():
            self.column_locations[position]["status"] = new_status
            self.column_locations[position]["column_type"] = column_type
        else:
            raise ValueError(f"{position} is not a valid position for a column.  Positions are col_pos1 or col_pos2")
    
    def get_current_column_positions(self):
        return self.column_locations
    
    def set_column_parameters(self, cfg, col_type, **kwargs):
        """
        Generate a dictionary of column types and parameters for a sample in an experiment
        """
        allowed_keys = {"max_pressure", "max_flow"}
        unkown_keys = set(kwargs) - allowed_keys
        if unkown_keys:
            raise ValueError(f"Unkown Keys: {sorted(unkown_keys)}; keys allowed are: {sorted(allowed_keys)}")
        cfg.setdefault("column_type", {})
        cfg["column_type"].setdefault(col_type, {})
        cfg["column_type"][col_type].update(kwargs)
        return cfg 
    
    def override_col_parameters(self, cfg, col_type, **kwargs):
        """
        For use when adjusting standard parameters for a column.
        """
        cparams_copy = copy.deepcopy(cfg)
        cparams_copy=self.set_column_parameters(cparams_copy, col_type, **kwargs)
        return cparams_copy

    
    def _run(self,cmd, timeout=None, capture=True):
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
    
    def _windows_dir_for_sample(self, sample):
        # Windows path: C:/CDSProjects/HPLC/<sample>/
        sample = caget('XF:16IDC-ES{HPLC}SAMPLE_NAME')
        sample = sample
        win_path = str(f'{ADF_location}\{sample}')
        print(f'windows path for UV_data for sample {sample} is {win_path}')
        return win_path
    def _linux_dir_for_sample(self, sample):
        uv_dest_dir = str(Path(proc_path))
        return uv_dest_dir
    def _make_remote_manifest(self, win_path):
        """
        Ask Windows (over SSH) for a JSON list of files with sizes under win_dir.
        Uses PowerShell to emit JSON: [{FullName:..., Length:...}, ...]
        """
        ps = (
            "powershell -NoProfile -Command "
            "\"Get-ChildItem -LiteralPath '{}' -Recurse -File | "
            "Select-Object FullName,Length | ConvertTo-Json -Compress\""
        ).format(win_path.replace("'", "''")) ##escapes single quotes that windows does not like
        rc, out, err = _run(["ssh", windows_ip, ps])
        if rc != 0 or not out.strip():
            return rc, None, err
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            # Normalize to relative paths using Windows separator -> POSIX for comparison
            base = PureWindowsPath(win_path)
            manifest = {}
            for entry in data:
                full = PureWindowsPath(entry["FullName"])
                rel = str(full.relative_to(base)).replace("\\", "/")
                manifest[rel] = int(entry.get("Length", 0))
            return 0, manifest, ""
        except Exception as e:
            return 1, None, f"manifest_parse_error: {e}"

    def _make_local_manifest(self, uv_dest_path):
        uv_dest_path = Path(uv_dest_path)
        manifest = {}
        for root, _, files in os.walk(uv_dest_path):
            for f in files:
                p = Path(root) / f
                rel = str(p.relative_to(uv_dest_path)).replace("\\", "/")
                try:
                    sz = p.stat().st_size
                except FileNotFoundError:
                    sz = -1
                manifest[rel] = sz
                print(manifest)
        return manifest        
    def _verify_dir(self, sample):
        """Compare Windows -> Linux manifests for the sample directory."""
        win_path = self._windows_dir_for_sample(sample)
        uv_dest_path = self._linux_dir_for_sample(sample)
        rc, src_manifest, err = self._make_remote_manifest(win_path)
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
        #proc_path = caget('XF:16IDC-ES{HPLC}PROC_PATH') PV is too complicated converting bytes strings
        win_path = self._windows_dir_for_sample(sample)
        uv_dest_path = self._linux_dir_for_sample(sample)
        os.makedirs(uv_dest_path, exist_ok=True)
        src = f"{windows_ip}:{win_path}"
        cmd = ["scp", "-r", src, str(proc_path)]
        return self._run(cmd)
    def _copy_and_verify(self, sample):
        """Main workflow: copy then verify, flip PVs accordingly."""
        caput('XF:16IDC-ES{HPLC}STATUS', 1)  # BUSY--Need to put this on ioc2?
        caput('XF:16IDC-ES{HPLC}GET_UV_RBV', 0)
        caput('XF:16IDC-ES{HPLC}LAST_REASON', "")
        
        try:
            rc, out, err = self._copy_with_scp(sample)
            method = "scp"

            caput('XF:16IDC-ES{HPLC}OUTPUT', (out or "").strip())
            caput('XF:16IDC-ES{HPLC}ERROR', (err or "").strip())

            if rc != 0:
                caput('XF:16IDC-ES{HPLC}GET_UV_RBV', 0)
                caput('XF:16IDC-ES{HPLC}LAST_REASON', f"{method}_failed_rc{rc}")
                return

            ok, reason = self._verify_dir(sample)
            caput('XF:16IDC-ES{HPLC}GET_UV_RBV', 1 if ok else 0)
            caput('XF:16IDC-ES{HPLC}LAST_REASON', reason)
            if ok == 1:
                print(f'UV file moved and verified for {sample}')
                return ok
        except Exception as e:
            print("Failure to fetch UV file")
            caput('XF:16IDC-ES{HPLC}ERROR', str(e))
            caput('XF:16IDC-ES{HPLC}GET_UV_RBV', 0)
            caput('XF:16IDC-ES{HPLC}LAST_REASON', f"exception:{e}")
        finally:
            caput('XF:16IDC-ES{HPLC}STATUS', 0)  # DONE

    def generate_run_parameters(self, sample_info):
        """
        Generates a working dictionary for a sample that includes column type and set values for pressure, flow rate and sec slot.
        This should be generated for each sample in a batch of HPLC runs
        """
        run_parameters = {}
        keys = ["method", "slot", "column_type", "flow_rate", "pressure"]
        for key in keys:
            if key not in sample_info['md']:
                raise KeyError(f"The key {key} is not in your sample info dictionary.  Check create Agilent seq file and spreadsheet for {sorted:{sample_info['md'][key]}}")
            else:
                run_parameters.setdefault(key)
                run_parameters[key] = sample_info['md'][key]
        print(f"constructed run_parameters dictionary!")
        return run_parameters
    def generate_working_deck(self, run_parameters:dict, column_parameters:dict, sec_slots:dict):
        """
        validates run_parameters with column limits and sec slot limits and returns a validated working deck.
        This will be the final parameters for each sample in a batch of HPLC runs that will be employed in bsui and Agilent SDK.
        """
        
        working_deck = run_parameters
        ###validate with sec_slot dictionary --need to validate position is TRUE, need to validate valve positions set correctly, need to validate pump flow rate
        ### validate with column_parameters dictionary for column_type
        return True, working_deck
    
    def CreateAgilentSeqFile(self, spreadsheet_fn, batchID, sheet_name='Samples'): 
        """
    Creates the agilent sequence file from the spreadsheet. User input is batchID, sample_name and method for hplc. The other columns are necessary for generating the proper formatted sequence file
    """
        strFields=["Vial", "Sample Name", "Sample Type", "Acq. method", "Proc. method", "Data file", "Buffer", "Valve Position", "Exp_Type", "Slot"]
        numFields=["Volume", "buffer_position"]
        dd=parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
        print(f"this is {dd}")
        autofillSpreadsheet(dd, fields=["batchID"])
        print(dd['batchID'].keys())
        print(dd['batchID'].values())
        print(dd['Valve Position'].values())
        print(dd['Exp_Type'].values())
        '''
    
        if proposal_id is None or run_id is None:
            print("need to login first ...")
            login()
        '''   
        ridx=[i for i in dd['batchID'].keys() if dd['batchID'][i]==batchID]
        print(f"{ridx} this is ridx")

    
        samples = {}
        experiment_type = {}
        dfile = f"<S>" 
        dd["Data file"] = {}
        dd["Sample Type"] = {}
        valve_position = {}
        
        for i in ridx:
            for f in numFields:
                if not (isinstance(dd[f][i], int or isinstance(dd[f][i], float))):
                    raise Exception(f"not a numeric value for {f}: {dd[f][i].values()}, replace with number")
            valve_position[i] = dd["Valve Position"][i]
            experiment_type[i] = dd["Exp_Type"][i]
            print(f"{valve_position}, {experiment_type}")
            sn = dd['Sample Name'][i]
            samples[sn] = {"acq time": dd['Run Time'][i], 
                           "valve_position":valve_position[i],
                           "md": {"Column type": dd['Column type'][i],
                                  "Injection Volume (ul)": dd['Volume'][i],
                                  "Flow Rate (ml_min)": dd['Flow Rate'][i],
                                  "Sample buffer":dd['Buffer'][i],
                                  "Slot" : dd['Slot'][i],
                                  "Valve Position":valve_position[i],
                                 "Acq Method": dd['Acq. method'][i],
                                 "Vial" : dd['Vial'][i],
                                 "experiment_type" : experiment_type[i],
                                 "buffer_position": dd['buffer_position'][i]}
                          }
            dd["Data file"][i] = dfile
            dd["Valve Position"][i]
            dd["Sample Type"][i] = "Sample"
        sequence_path="/nsls2/data4/lix/legacy/HPLC/Agilent/"
        df=pd.DataFrame.from_dict(dd, orient='columns')
        conditional_df = df["experiment_type"] != "X-ray_only"
        uv_rows = df[conditional_df].copy()
        uv_rows["Sample Name"] = uv_rows["Sample Name"] + '_UV'
        exp_df = pd.concat([df, uv_rows], ignore_index = True)
        print(exp_df)
        
        ##parameters needed for Agilent
        exp_df[exp_df['batchID']==batchID].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                        columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data file" ])
        source_file = f"{sequence_path}"+'sequence_table.csv'
        destination_loc = "xf16id@10.66.123.226:C:/CDSProjects/HPLC/"
        try:
                ssh_key = str(pathlib.Path.home())+"/.ssh/id_rsa.pub"
                if not os.path.isfile(ssh_key):
                    raise Exception(f"{ssh_key} does not exist!")
                cmd = ["scp", "/nsls2/data4/lix/legacy/HPLC/Agilent/sequence_table.csv", destination_loc] ##hardcoded path for sequence file
                #print(cmd)
                subprocess.run(cmd)
                print("Sequence_table sucessfully sent")
        except Exception as e:
            print("SCP transfer has failed for!")

        return samples, valve_position, experiment_type  
        
        
    
   

    def create_single_run(self,spreadsheet_fn, batch_id, sheet_name="Samples"):
        sample, valve_position = parseSpreadsheet(spreadsheet_fn, batch_id)
    
    def create_sample_param(self,sample_name, samples):
        run_parameters = {}
        caput('XF:16IDC-ES{HPLC}ResultPath' , sample_name)
        self.sample_name = sample_name
        self.sample_params['sample_name']= self.sample_name
        print(f"Creating sample parameters dictionary for {sample_name}")
        ##place a check to make sure the sample name matches the intented
        self.acq_method = samples[self.sample_name]['md']['Acq Method']
        self.sample_params['acq_method']=self.acq_method
        print(self.acq_method)
        self.sample_loc = samples[self.sample_name]['md']['Vial']
        self.sample_params['sample_loc']=self.sample_loc
        self.injection_vol = samples[self.sample_name]['md']['Injection Volume (ul)']
        self.sample_params['injection_vol'] = self.injection_vol
        print (f"This is the sample params dictionary {self.sample_params}")
        return run_parameters
            
    def get_pressure_limits(self,column_type, method):
        
        curr_pres_limit = caget("XF:16IDC-ES{HPLC}QUAT_PUMP:PRESSURE")
        #check current PV on agilent for pressure and on regen pump and make sure they are appropriate to column type
        if method in ["X-ray_only"]:
            if column_type == "Superdex" and curr_pres_limit > 32:
                raise ValueError("Pressure limit must be set to max 32bar!") 
            elif column_type == "dSEC" and curr_pres_limit > 120:
                raise ValueError("Pressure limit must be set to max 120bar!") 
            else:
                return curr_pres_limit
        else:
            pass
                
        pressure = TRP.read_pressure()
        print(f'The current pressure value is {pressure}')##fix the readout so it is not confusing

    def safe_to_change(self, column_parameters : dict, run_parameters : dict):
        limits = column_parameters.get("column_type" , {})
        print(f"these are column_limit {limits}")
        wcols = run_parameters.get("column_type", {})
        unkown = set(wcols) - set(limits)
        if unkown:
            raise KeyError(f"Unkown column_type in run parameters, {sorted:{unkown}}")
    '''    
    def safe_to_change(self, curr_pressure=None, curr_high_press_limit=None, pressure_sv=None,col_max_pressure=None, 
                       curr_flwr=None, flwr_sv=None, col_max_flwr=None,
                       regen_flwr_sv=None, regen_col_max_flwr=None,
                       regen_high_press_limit=None, regen_col_max_pressure=None, catalog : dict, working : dict):
        """
        compare pressure limits and flowrate for a column to the current values on pumps (includes Agilent and teledyne pumps) to ensure any valve changes are safe

        """
        limits = catalog.get("column_type", {})
        wcols = working.get("column_type" ,{})
        unknown = set(wcols) - set(limits)
        if unknown:
            raise KeyError(f"Unknown column types in working config: {sorted(unknown)}")
        msgs = []
        for ctype, w in wcols.items():
            mp = float(limits[ctype]["max_pressure"])
            mf = float(limits[ctype]["max_flow"])
            p  = float(w.get("max_pressure", 0.0))
            f  = float(w.get("max_flow", 0.0))

            if p > mp:
                msgs.append(f"{ctype}: pressure {p} > max_pressure {mp}")
            if f > mf:
                msgs.append(f"{ctype}: flow {f} > max_flow {mf}")

        if msgs:
            raise ValueError("Setpoint limit violations:\n  - " + "\n  - ".join(msgs))
        curr_pressure = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PRESSURE_RBV')
        pressure_sv = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PRESSURE')
        curr_high_press_limit = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:PRESSURE_HIGH_LIMIT')
        col_max_pressure =self.pressure if col_max_pressure is None else warnings.warn(f"You have set the Column max pressure to {col_max_pressure}, proceed with caution!")
        sleep(1)
        flwr_sv = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:FLOWRATE')
        curr_flwr = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:FLOWRATE_RBV')
        col_max_flwr = self.flow_rate if col_max_flwr is None else warning.warn(f"You have set the Column max flowrate to {col_max_flwr}, proceed with caution!")
        sleep(1)
        if not (curr_pressure < curr_high_press_limit <= col_max_pressure):
            raise ValueError(
                f"High limit pressure limit: {curr_high_press_limit} must be > current pressure {curr_pressure} "
                f"and ≤ column max {col_max_pressure}"
            )

        
        if not ((curr_flwr <= col_max_flwr) and (flwr_sv <= col_max_flwr)):
            raise ValueError(
                f"Current flowrate {curr_flwr} and flowrate set value must be ≤ column max {col_max_flwr}")
            """
            Check to make sure line 2 contains a column and if so, make sure it is safe to turn valve.
            """
        if self.column_locations['col_pos2']:
            ##pressure needs to be in PSI for regen pumps
            print("Pressure needs to be in PSI for regen pumps")
            curr_regen_flwr = TRP.get_flowrate()
            curr_regen_pressure = TRP.read_pressure()
            regen_hpl = TRP.high_pressure_limit()
            if not (curr_regen_pressure < regen_hpl <= regen_col_max_pressure):
                raise ValueError(
                    f" Renegeration Pump high pressure limit is {regen_hpl} must be > current_pressure {curr_regen_pressure}"
                    f" and ≤ regen_column max pressure {regen_col_max_pressure}")
            if not ((curr_regen_flwr <= col_max_flwr) and (regen_flwr_sv <= regen_col_max_flwr)):
                raise ValueError(f"Regeneration pump has column attached and current flowrate {curr_regen_flwr} must be <= {regen_col_max_flwr}")
            
        else:
            return True
       '''     
                
    def change_flowpath(self, buffer_position, method=None,column_type = None):
        ##check which column first and make sure pressure limit is set appropriately
        if self.safe_to_change():
            pl=self.get_pressure_limits(self.column_type, method)
            fr = self.flow_rate
            sleep(1)
            if self.column_location == "col_pos1":
                valve_port=VV.switch_10port_valve(pos="A") ###print some feedback here and return
            else:
                valve_port= VV.switch_10port_valve(pos="B")  ##print some feedback here and return
            if buffer_position:
                APV.movePosition(buffer_position) ###return feedback
            
        return valve_port
    def get_flowrate(self, pump=None):
        pumps = ["Agilent", "Regen", "Co-Flow"]
        if pump in pumps:
            if pump == "Agilent":
                #callback from SDK about flowrate is slow
                tries = 3
                for attempt in range(1, tries + 1):
                    try:
                        curr_flow_rate = caget('XF:16IDC-ES{HPLC}QUAT_PUMP:FLOWRATE_RBV')
                        if attempt < tries:
                            sleep(1)
                        else:
                            return curr_flow_rate
                            print(f"Current Agilent flowrate is {curr_flow_rate} mL/min")
                    finally:
                        print("Completed attempt at fetching Agilent flowrate")
                    
            elif pump == "Regen":
                regen_flowrate = TRP.get_flowrate()
                print(f"current flowrate of regeneration pump is {regen_flowrate} mL/min")
                return regen_flowrate
            elif pump == "Co-Flow":
                co_flow_flowrate = TRPB.get_flowrate()
                return co_flow_flowrate
            else:
                return None
        else:
            print(f"Pump {pump} is not in list of pumps!")
                
        

    def agilent_buffer_pos(self, buffer_pos=None):
        if buffer_pos is None:
            raise Exception("Location of the Buffer for SEC-SAXS has not been specified! The Value must be an integer between 1 and 6.")
        if not type(buffer_pos) is int:
            raise TypeError("buffer_pos must be an integer")
        if not (1<= buffer_pos <= 6):
            raise ValueError("Buffer position must be between 1 and 6!")
        cur_buffer_pos=APV.valveStatus()
        print(f" Current Valve position is {cur_buffer_pos}.")
        
        if buffer_pos == cur_buffer_pos:
            caget("XF:16IDC-ES{HPLC}Buffer_VALVE_RBV")
            print(f"Buffer valve is currently in position {buffer_pos} and will not change")
            caput("XF:16IDC-ES{HPLC}Buffer_VALVE_POS", buffer_pos)
        else:
            APV.movePosition(buffer_pos)
            caput("XF:16IDC-ES{HPLC}Buffer_VALVE_POS", buffer_pos)
            sleep(0.5)
            print(caget("XF:16IDC-ES{HPLC}Buffer_VALVE_RBV"))
            #print(f"Buffer Readback Value is {buffer_pos}")
        
        return
    def regen_buffer_pos(self, buffer_pos=None):
        if buffer_pos is None:
            raise Exception("Location of the Buffer for SEC-SAXS has not been specified! The Value must be an integer between 1 and 6.")
        if not type(buffer_pos) is int:
            raise TypeError("buffer_pos must be an integer")
        if not (1<= buffer_pos <= 6):
            raise ValueError("Buffer position must be between 1 and 6!")
        cur_buffer_pos=APV.valveStatus()
        print(f" Current Valve position is {cur_buffer_pos}.")
        
        if buffer_pos == cur_buffer_pos:
            caget("XF:16IDC-ES{HPLC}Buffer_VALVE_RBV")
            print(f"Buffer valve is currently in position {buffer_pos} and will not change")
            caput("XF:16IDC-ES{HPLC}Buffer_VALVE_POS", buffer_pos)
        else:
            APV.movePosition(buffer_pos)
            caput("XF:16IDC-ES{HPLC}Buffer_VALVE_POS", buffer_pos)
            sleep(0.5)
            print(caget("XF:16IDC-ES{HPLC}Buffer_VALVE_RBV"))
            #print(f"Buffer Readback Value is {buffer_pos}")
        
        return
    def collect_hplc(self, sample_name, get_uv, method, exp, post_run, nframes,md=None ):
        ##do not include postrun if running 1 sample
        TRPB.set_flowrate(5) # to clear any bubbles
        TRPB.start_pump()
        time.sleep(5)
        TRP.stop_pump()
        _md = {"experiment": "HPLC"}
        _md.update(md or {})
        change_sample(sample_name)
        pil.use_sub_directory(sample_name)
        sol.select_flow_cell('middle')
        pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
        pil.set_num_images(nframes)
        pil.exp_time(exp)
        update_metadata()
        #check_beam
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,0)
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,1)
        caput('XF:16IDC-ES{HPLC}SAMPLE_NAME' ,sample_name)
        time.sleep(10)
        if caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "Idle":
            caput('XF:16IDC-ES{HPLC}START_RUN', 1) #starts run via SDK
            time.sleep(1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        elif caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "PostRun":
            print("PostRun")
            time.sleep(post_run)
            ##get UV data at this step, need to do this with hardware triggering for better timing.
            if get_uv:
                try:
                    uv_dest_path = f'{proc_path}'
                    self.run_UV_collection(method=method)
                
                
            caput('XF:16IDC-ES{HPLC}START_RUN', 1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        else:
            status = caget('XF:16IDC-ES{HPLC}HPLCRunStatus')
            print("HPLC is not ready and cannot start run")
            print(status)
      
        #sol.ready_for_hplc.set(1)
        while sol.hplc_injected.get()==0:
            if sol.hplc_bypass.get()==1:
                sol.hplc_bypass.put(0)
                break
            sleep(0.2)

        #sol.ready_for_hplc.set(0)
        start_monitor([em1,em2], rate=4)
        RE(monitor_during_wrapper(ct([pil], num=nframes, md=_md), [em1.ts.SumAll, em2.ts.SumAll]))
        sd.monitors = []
        pil.use_sub_directory()
        change_sample()
    
    def verify_method_valve(self, method, current_valve_position):
        if method not in self.experiment_type:
            raise ValueError(f"Selected method {method} not in acceptable methods list! Choose {experiment_type}")
        elif method == "X-ray_only":
            if self.column_locations != current_valve_position:
                self.column_locations = "col_pos1"
            else:
                print(f" {self.column_position}")
        return True
    def detector_selection(self, position):
        if position == "X-ray":
            VV.send_valve_cmd(cmd="GOB", valve=VICI_ID.Detector, valve_ID = 4)
        if position == "UV":
            VV.send_valve_cmd(cmd="GOA", valve=VICI_ID.Detector, valve_ID = 4)
    def run_UV_collection(self, method):
        self.detector_selection(position="UV")
        print("Switching to UV detectors")
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,0)
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,1)
        caput('XF:16IDC-ES{HPLC}SAMPLE_NAME' ,sample_name)
        time.sleep(10)
        if caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "Idle":
            caput('XF:16IDC-ES{HPLC}START_RUN', 1) #starts run via SDK
            time.sleep(1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        elif caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "PostRun":
            print("PostRun")
            time.sleep(post_run)
            ##get UV data at this step, need to do this with hardware triggering for better timing.
            if method in ["X-ray_UV", "UV_MALS_RID_only"]:
                uv_dest_path = f'{proc_path}'
                
                
            caput('XF:16IDC-ES{HPLC}START_RUN', 1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        return
    def run_hplc_from_spreadsheet(self, spreadsheet_fn, batchID, sheet_name='Samples', exp=2, flowrate = 0.35, post_run=60, get_uv=False):
        
        
        """
        Runs HPLC experiments based on data from a spreadsheet.

        Args:
            spreadsheet_fn (str): File path of the spreadsheet.
            batchID (str): Identifier for the batch.
            sheet_name (str, optional): Name of the sheet in the spreadsheet. Defaults to 'Samples'.
            exp (int, optional): Exposure time for data collection in seconds. Defaults to 2.
        """

    
        sequence_name = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
        samples, valve_position, experiment_type = self.CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)

   
    
        
    
        print(f"HPLC sequence file has been created in: {sequence_name}")
        print('Make sure you have selected the correct flow path for experiment and column type!')
        #input("Please start Sequence in Agilent software by importing sequence_table.csv (under sequence tab), click run, then come back to this machine and then hit enter:")
        run_number = 1
        while run_number <= len(samples.items()):
            for sample_name, sample_info in samples.items():
                run_parameters = self.generate_run_parameters(sample_info)
                number_samples = len(samples.items())
                print(f"Number of samples to run is: {number_samples}")
                print(f"Starting SEC for sample number {run_number} of {number_samples}")
                single_sample = self.create_sample_param(sample_name, samples)
                caput('XF:16IDC-ES{HPLC}SAMPLE_NAME', sample_name)
                caput('XF:16IDC-ES{HPLC}HPLC:SNUV', sample_name)
                caput('XF:16IDC-ES{HPLC}SDK_Connection' , 1)
                #caput('XF:16IDC-ES{HPLC}HPLC:TAKE_CTRL' , 0)
                single_sample = json.dumps(self.sample_params)
                caput('XF:16IDC-ES{HPLC}RunParameters' , single_sample)
                valve_pos = sample_info["md"]["Valve Position"]
                #if samples['column_type'] is not self.column_locations
                ##get method from spreadsheet, check position in spreadsheet to align with method. Once column_type, and dictionaries are updated, then proceed to changing flowpath 
                method = sample_info["md"]["experiment_type"]
                print(f" Method {method} has been selected")
                if method == "X-ray_only":
                    self.detector_selection(position="X-ray")
                elif method != "X-ray_only":
                    get_uv=True
                self.column_type = sample_info["md"]["Column type"]
   
                curr_col_valve_position = sample_info["valve_position"]
                
                if self.verify_method_valve(method, curr_col_valve_position):
                    fp=self.change_flowpath(method=sample_info["md"]["experiment_type"], buffer_position=sample_info["md"]["buffer_position"], 
                                        column_type=self.column_type)
                    self.update_ctype_cpos_(position="col_pos1", column_type = self.column_type, status = True)
                else:
                    print("Unable to verify current column position and orientation of 10-port Valve from Spreadsheet")
                
                
                #print(f"Switching valve to position {valve_pos} for sample {sample_name}...")
                #print(f"Adjusting flow path for experiment type: {fp}")
                #VV.switch_10port_valve(pos=valve_pos, valve=VICI_ID.Valve_10_port,
                 #                      valve_ID=VICI_ID.Valve_10_port.valve_ID, get_ret=False)
        
                print(f"Collecting data for {sample_name}...")
                acq_time_sec = sample_info["acq time"] * 60
                nframes = int(acq_time_sec / exp)

                if get_uv:
                    self.collect_hplc(sample_name, get_uv=get_uv, exp=exp, method=method, nframes=nframes, post_run=post_run, md={'HPLC': sample_info['md']})
                    uid = db[-1].start['uid']
                    send_to_packing_queue(uid, "HPLC")
                    try:
                        sleep(post_run)
                        t = threading.Thread(target=self.run_UV_collection, args=(method=method), daemon = True)
                        ##t = threading.Thread(target=self._copy_and_verify, args=(sample_name,),
                        #                     daemon=True)
                        t.start()
                    except Exception as e:
                        msg = f"[Run {current_run}] failed to start thread: {e}"
                        print(msg)
                        caput('XF:16IDC-ES{HPLC}ERROR', str(e))
                        caput('XF:16IDC-ES{HPLC}LAST_REASON', 'thread_start_failed')
                        caput('XF:16IDC-ES{HPLC}OUTPUT', msg)
                if not get_uv:
                    self.collect_hplc(sample_name, get_uv=get_uv, exp=exp, method=method, nframes=nframes, post_run=post_run, md={'HPLC': sample_info['md']})
                    uid = db[-1].start['uid']
                    send_to_packing_queue(uid, "HPLC")
                    
                    
                    
                '''
                    max_attempts = 3
                    cutoff = 3*60
                    attempt = 0
                    while True:
                        attempt += 1
                        try:
                            t = threading.Thread(target=self._copy_and_verify, args=(sample_name,),
                                             daemon=True)
                            t.start()
                            if t == 1:
                                print("File copied!")
                            else:
                                if attempt >= max_attempts:
                                    print("failure of uv after 3 attempts")
                                    return False
                        
                        except Exception as e:
                            msg = f"[Run {current_run}] failed to start thread: {e}"
                            print(msg)
                            caput('XF:16IDC-ES{HPLC}ERROR', str(e))
                            caput('XF:16IDC-ES{HPLC}LAST_REASON', 'thread_start_failed')
                            caput('XF:16IDC-ES{HPLC}OUTPUT', msg)
                '''    
                   
                        
                run_number += 1
    
            #pil.use_sub_directory()
            #caput('XF:16IDC-ES{HPLC}SDK_Connection' , 2) #Disconnect from SDK each time.  Seems to get stuck if you dont
            #run_number += 1
        print(f'Sequence collection finished for batch {batchID} from {spreadsheet_fn}')

'''  

def change_flowpath(column_position, columntype, buffer_position):
        ##check which column first and make sure pressure limit is set appropriately
        get_pressure_limits(columntype)
        sleep(1)
        if column_position == 1:
            valve_port=switch_10_port_valve(pos="A") ###print some feedback here and return
        else:
            valve_port= switch_10_port_valve(pos="B")  ##print some feedback here and return
        if buffer_position:
            APV.movePosition(buffer_position) ###return feedback
            
        return valve_port

def get_experiment_and_column_type(experiment_type, column_type_name=None):
    """
    Read the sec_experiment_parameters YAML file, check if the experiment type exists, and return the experiment type and column type.

    Args:
        experiment_type (str): Name of the experiment type to search for. This is obtained in Spreadsheet.

    Returns:
        str, dict: Experiment type and corresponding column type if found, otherwise None.
    """
    yaml_file = '/nsls2/data/lix/shared/config/bluesky/profile_collection/startup/devices/sec_experiment_parameters.yaml'  # Specify the fixed YAML file path here
    
    try:
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)
    except FileNotFoundError:
        print("Error: YAML file not found.")
        
    sec_exper_column = {}
    experiment_types = data.get('experiment_types', [])
    column_types = data.get('column_types', [])
    #print(experiment_types)
    for experiment in experiment_types:
            if experiment == experiment_type:
                sec_exper_column["experiment_type"] = experiment_type
                #print(sec_exper_column)
            if experiment != experiment_type:
                print(f"Error: Experiment type '{experiment_type}' not found in YAML file.")
          ##chose column type
            if column_type_name is None:
                print("NO column specified: Default to Superdex 200 Increase 5/150GL (small)")
                sec_exper_column["column_type"] = "Superdex 200 Increase 5/150 GL"
                print(sec_exper_column)
            else:
                
                for column in column_types:
                    if column == column_type_name:
                        sec_exper_column["column_type"] = column_type_name
                if column != column_type_name:
                    print(f"column name {column_type_name} is not in the list of approved columns! Approved columns are {column_types.keys()}")
            return sec_exper_column
    


def prepare_hplc_flowpath(experiment_type, column_position, buffer_position, columntype):
    """ This will need to also send the proper arguments to agilent so that it pulls from correct pump line

    experiment_info, column_info = get_experiment_and_column_type(experiment_type)
    """
    if experiment_info is None:
        raise Exception("Experiment type is not in the list of approved experiments!")
    
    # Rest of the function logic goes here
    if experiment_type == "X-ray_only":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "X-ray_UV_MALS_RID":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "X-ray_Regen":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "UV_MALS_RID_only":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
        
'''        



'''
def create_agilent_seq_file(spreadsheet_fn, batch_id, proposal_id=None, run_id=None, current_cycle=None, sheet_name='Samples'):
    """
    Creates an Agilent sequence file from the spreadsheet.
    
    Args:
        spreadsheet_fn (str): File path of the spreadsheet.
        batch_id (str): Identifier for the batch.
        proposal_id (str, optional): Identifier for the proposal. Defaults to None.
        run_id (str, optional): Identifier for the run. Defaults to None.
        current_cycle (str, optional): Identifier for the current cycle. Defaults to None.
        sheet_name (str, optional): Name of the sheet in the spreadsheet. Defaults to 'Samples'.
    
    Returns:
        dict, dict: Samples dictionary, Valve position dictionary.
    """
    # Define the columns mapping for flexibility
    column_mapping = {
        "Vial": "Vial",
        "Sample Name": "Sample Name",
        "Injection Volume": "Volume",
        "Acq. method": "Acq. method",
        "Proc. method": "Proc. method",
        "Data file": "Data file",
        "Experiment Type": "Experiment Type"
        
    }
    
    # Read spreadsheet into a dictionary
    spreadsheet_data = parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
    print(f"Spreadsheet data: {spreadsheet_data}")
    
    # Autofill the spreadsheet
    autofillSpreadsheet(spreadsheet_data, fields=["batchID"])
    
    # Check if login is required
    if proposal_id is None or run_id is None:
        print("Login is required...")
        #login()
    
    # Get indices of rows with matching batch ID
    matching_indices = [i for i, value in spreadsheet_data['batchID'].items() if value == batch_id]
    print(f"Matching indices: {matching_indices}")
    
    # Initialize dictionaries for samples and valve positions
    samples = {}
    valve_positions = {}
    
    # Define data file path
    data_file_path = f"{current_cycle}/{proposal_id}/{run_id}/<S>" 
    
    for i in matching_indices:
        # Process each row
        for key in spreadsheet_data.keys():
            if key in ["Injection_Volume"]:
                if not isinstance(spreadsheet_data[key][i], (int, float)):
                    raise Exception(f"Not a numeric value for {key}: {spreadsheet_data[key][i]}, replace with a number")
                spreadsheet_data[column_mapping[key]][i] = spreadsheet_data[key][i]
        
        # Get valve position
        valve_positions[i] = spreadsheet_data.get("Valve Position", {}).get(i)
        print(valve_positions)
        
        # Get sample name
        sample_name = spreadsheet_data.get('Sample Name', {}).get(i)
        if sample_name:
            samples[sample_name] = {
                "acq time": spreadsheet_data.get('Run Time', {}).get(i), 
                "valve_position": valve_positions[i],
                "md": {
                    "Column type": spreadsheet_data.get('Column type', {}).get(i),
                    "Injection Volume (ul)": spreadsheet_data.get('Volume', {}).get(i),
                    "Flow Rate (ml_min)": spreadsheet_data.get('Flow Rate', {}).get(i),
                    "Sample buffer": spreadsheet_data.get('Buffer', {}).get(i),
                    "Valve Position": valve_positions[i]
                }
            }
        
        # Set data file path
        spreadsheet_data["Data file"][i] = data_file_path
    
    # Define the sequence path
    sequence_path = "/nsls2/data/lix/legacy/HPLC/Agilent/"
    
    # Convert spreadsheet data to DataFrame
    df = pd.DataFrame.from_dict(spreadsheet_data, orient='columns')
    
    # Write DataFrame to CSV
    df[df['batchID'] == batch_id].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                                         columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data file"])
    
    return samples, valve_positions
    
'''      
def run_hplc_SDK(spreadsheet_fn, batchID, sheet_name="Samples", exp=2, flowrate=0.35, column_type="Superdex 200 Increase 5/150 GL"):
    
    return experiment_type




SEC=SEC_SAXSCollection()
