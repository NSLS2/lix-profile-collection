print(f"Loading file {__file__}...")
###Choosing the Experimental Type, ColumnType, Column Position, Buffer Positions will determine the flowpath, either A or B
###need 2 selection valves, one for regen pump and the other for HPLC
####column position 1 should always be to X-ray, Column position 2, regen, etc.  Valve will place these positions in the desired flowpath.
from time import sleep
from enum import Enum
from pathlib import PureWindowsPath, Path
import yaml, json
from gen_SEC_report import *
import threading as th
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import pandas as pd
from epics import caget, caput
from lixtools.samples import parseSpreadsheet, autofillSpreadsheet
#from APV import APV
#from hplccon import AgilentHPLC
global proc_path
ADF_location = PureWindowsPath(r"C:/CDSProjects/HPLC/")
windows_ip  = "xf16id@10.66.123.226"

       
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
    
def get_UV_data(sample_name):
    
     """This will fetch the 280 UV data from the working directory and is used by h5_attach_hplc"""
     uv_file = f"{sample_name}.dx_DAD1E.CSV"
     df = pd.read_csv(f'{proc_path}{sample_name}/{uv_file}')
     k=df.to_numpy(dtype=float) 
     return k

def h5_attach_hplc(fn_h5, grp_name=None):
    
    """ the hdf5 is assumed to contain a structure like this:
        LIX_104
        == hplc
        ==== data
        == primary (em, scattering patterns, ...)
        
        attach the HPLC data to the specified group
        if the group name is not give, attach to the first group in the h5 file
    """
    fn = fn_h5[:-3]
    fn = f"{fn_h5}.h5"
    f = h5py.File(fn, "r+")
    if grp_name == None:
        grp_name = list(f.keys())[0]
    sample_name=list(f.keys())[0]
    k=get_UV_data(sample_name)

    
    # this group is created by suitcase if using flyer-based hplc_scan
    # otherwise it has to be created first
    # it is also possible that there was a previous attempt to populate the data

    if 'hplc' in f[f"{grp_name}"].keys():
        grp = f["%s/hplc/data" % grp_name]
    else:
        grp = f.create_group(f"{grp_name}/hplc/data")
        
    key_list=list(grp.keys())
    for g in grp:
        if g in key_list:
            print("warning: %s already exists, deleting ..." % g)
            del grp[g]
    else:
        print("no UV_data previously present")
    d=np.asarray(k)
    #print(d)
    dset=grp.create_dataset('[LC Chromatogram(Detector A-Ch1)]', data=d)
    dset[:]=d
    f.close()   


class SEC_SAXSCollection(object):
    experiment_type = ["X-ray_UV","MALS_RID", "X-ray_Regen"]
    column_type = ["Superdex", "dSEC2", "Superose_6"]
    buffer_position = [1,2,3,4,5,6]
    if proposal_id is None or run_id is None:
        print("need to login first ...")
        login()
    def __init__(self,
                exp_type = None,
                col_type = None,
                buff_pos = None):
        self.exp_type= exp_type if exp_type is not None else self.experiment_type
        self.col_type= col_type if col_type is not None else self.column_type
        self.column_position= 1
        self.buff_pos= buff_pos if buff_pos is not None else self.buffer_position
        Enum.HPLC_SEL_VAL=1 ## need to define the urls for each selection valve in the inherited class.  leaving this as a placeholder for now
        Enum.REGEN_SEL_VAL=2
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
        
        #super().__init__()
    def _run(self,cmd, timeout=None, capture=True):
        """Run a shell command. Returns (returncode, stdout, stderr)."""
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
   
    def _copy_with_scp(self, sample):
        #proc_path = caget('XF:16IDC-ES{HPLC}PROC_PATH') PV is too complicated converting bytes strings
        win_path = self._windows_dir_for_sample(sample)
        uv_dest_path = self._linux_dir_for_sample(sample)
        os.makedirs(uv_dest_path, exist_ok=True)
        src = f"{windows_ip}:{win_path}"
        cmd = ["scp", "-r", src, str(proc_path)]
        ret = self._run(cmd)
        if ret[0] == 0:
            print("UV files successfully copied")
        if ret[0]!=0:
            print(f"Warning: {sample}_UV files were not copied!")
        return ret                   
    
    
    
    
    def build_exp_df(self, dd, batchID, mals_inj_vol=None):
        df=pd.DataFrame.from_dict(dd, orient='columns')
        df = df.loc[df["batchID"]==batchID].copy()
        num_cols = ["Volume", "buffer_position"]
        df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="raise")
        df["Data file"] = "<S>"
        df["Sample Type"] = "Sample"
        conditional_df = ~df["Exp_Type"].isin(["X-ray_UV", "X-ray_Regen"])
        mals_rows = df.loc[conditional_df].copy()
        if not mals_rows.empty:
            mals_rows["Sample Name"] = mals_rows["Sample Name"] + '_mals'
            if mals_inj_vol == None:
                mals_inj_vol = 20
            mals_rows["Volume"] = mals_inj_vol
            mals_rows["Acq. method"] = mals_rows["Acq. method"].str.replace(r"\.amx$", "_UV.amx", regex=True)
        exp_df = pd.concat([df, mals_rows], ignore_index = True)
        return exp_df

    def hplc_dict_from_df(self, exp_df):
        samples = {}
        valve_position = {}
        experiment_type ={}
        
        for row in exp_df.to_dict(orient="records"):
            sn =row["Sample Name"]
            valve_position[sn] = row.get("Valve Position")
            experiment_type[sn] = row.get("Exp_Type")

            samples[sn] = {
                "acq time": row.get("Run Time"),
                "valve_position": row.get("Valve Position"),
                "md": {
                    "Column type": row.get("Column type"),
                    "Injection Volume (ul)": row.get("Volume"),
                    "Flow Rate (ml_min)": row.get("Flow Rate"),
                    "Sample buffer": row.get("Buffer"),
                    "Slot": row.get("Slot"),
                    "Valve Position": row.get("Valve Position"),
                    "Acq Method": row.get("Acq. method"),
                    "Vial": row.get("Vial"),
                    "experiment_type": row.get("Exp_Type"),
                    "buffer_position": row.get("buffer_position"),
                },
            }

        return samples, valve_position, experiment_type
        
        
        
    def CreateAgilentSeqFile(self, spreadsheet_fn, batchID, sheet_name='Samples', mals_inj_vol = None): 
        """
    Creates the agilent sequence file from the spreadsheet. User input is batchID, sample_name and method for hplc. The other columns are necessary for generating the proper formatted sequence file
    """
        strFields=["Vial", "Sample Name", "Sample Type", "Acq. method", "Proc. method", "Data file", "Buffer", "Valve Position", "Exp_Type", "Slot"]
        numFields=["Volume", "buffer_position"]
        dd=parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
      
        autofillSpreadsheet(dd, fields=["batchID"])

    
        if proposal_id is None or run_id is None:
            print("need to login first ...")
            login()
  
        exp_df = self.build_exp_df(dd, batchID, mals_inj_vol)
        samples, valve_position, experiment_type = self.hplc_dict_from_df(exp_df)
        sequence_path = "/nsls2/data4/lix/legacy/HPLC/Agilent/"
        out_csv = f"{sequence_path}sequence_table.csv"

        exp_df.to_csv(
            out_csv,
            index=False,
            encoding="ASCII",
            columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial",
                     "Acq. method", "Proc. method", "Data file"]
        )
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
            msg = f"SCP has failed with exception {e}!"
            print(msg)
        

        return samples, valve_position, experiment_type
        
        
    
   

    def create_single_run(self,spreadsheet_fn, batch_id, sheet_name="Samples"):
        sample, valve_position = parseSpreadsheet(spreadsheet_fn, batch_id)
    
    def create_sample_param(self,sample_name, samples):
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
            
    def get_pressure_limits(self,column_type):
            pressure = TRP.read_pressure()
            print(f'The current pressure value is {pressure}')##fix the readout so it is not confusing
        
        
    def change_flowpath(self, column_position, column_type, buffer_position):
        ##check which column first and make sure pressure limit is set appropriately
        get_pressure_limits(column_type)
        sleep(1)
        if self.column_position == 1:
            valve_port=switch_10_port_valve(pos="A") ###print some feedback here and return
        else:
            valve_port= switch_10_port_valve(pos="B")  ##print some feedback here and return
        if buffer_position:
            APV.movePosition(buffer_position) ###return feedback
            
        return valve_port

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
    def verify_method_valve(self, method, current_valve_position):
        if method not in self.experiment_type:
            raise ValueError(f"Selected method {method} not in acceptable methods list! Choose {experiment_type}")
        elif method == "X-ray_UV":
            if self.column_locations != current_valve_position:
                self.column_locations = "col_pos2"
            else:
                print(f" {self.column_position}")
        return True
    def detector_selection(self, position):
        if position == "X-ray_UV":
            VV.send_valve_cmd(cmd="GOB", valve=VICI_ID.Detector, valve_ID = 4)
        if position == "MALS":
            VV.send_valve_cmd(cmd="GOA", valve=VICI_ID.Detector, valve_ID = 4)
    def run_MALS_collection(self, method, sample_name):
        self.detector_selection(position="MALS")
        print("Switching to MALS detectors")
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,0)
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,1)
        caput('XF:16IDC-ES{HPLC}SAMPLE_NAME' ,sample_name)
        time.sleep(10)
        if caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "Idle":
            caput('XF:16IDC-ES{HPLC}START_RUN', 1) #starts run via SDK
            time.sleep(1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
            status = "Idle"
        elif caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "PostRun":
            print("PostRun")
            time.sleep(post_run)
            ##get UV data at this step, need to do this with hardware triggering for better timing.
            if method in ["X-ray_UV", "UV_MALS_RID_only"]:
                uv_dest_path = f'{proc_path}'
                
                
            caput('XF:16IDC-ES{HPLC}START_RUN', 1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        print("Running MALS data collection")  
        time.sleep(acq_time_sec)     
        return {"status":state}
  
    def collect_hplc(self, sample_name, exp, post_run, nframes, md=None):
        ##do not include postrun if running 1 sample
        TRP.set_flowrate(5) # to clear any bubbles
        TRP.start_pump()
        time.sleep(5)
        TRP.stop_pump()
        _md = {"experiment": "HPLC"}
        _md.update(md or {})
        change_sample(sample_name)
        pil.use_sub_directory(sample_name)
        #sol.select_flow_cell('middle')
        pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
        #pil.set_num_images(nframes)  ##old way
        set_num_images(dets=[pil],n_triggers=nframes)
        #pil.exp_time(exp)
        set_exp_time(dets=[pil], exp=exp)
        update_metadata()
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,0)
        caput('XF:16IDC-ES{HPLC}HPLC_status' ,1)
        caput('XF:16IDC-ES{HPLC}SAMPLE_NAME' ,sample_name)
        time.sleep(5)
        if caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "Idle":
            caput('XF:16IDC-ES{HPLC}START_RUN', 1) #starts run via SDK
            time.sleep(1)
            caput('XF:16IDC-ES{HPLC}START_RUN', 0)
        elif caget('XF:16IDC-ES{HPLC}HPLCRunStatus') == "PostRun":
            print("PostRun")
            time.sleep(post_run)
                
                
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
        #start_monitor([em1,em2], rate=4)
        #sd.monitor = []
        #sd.monitors.append([em1.sum_all.mean_value, em2.sum_all.mean_value])
        #flowmeters=[sol.saxs_sec_flow,sol.uv_sec_flow]
        RE(monitor_during_wrapper(ct([pil, ext_trig], num=nframes, md=_md), [em1.ts.SumAll, em2.ts.SumAll,]))
        sd.monitors = []
        pil.use_sub_directory()
        change_sample()
    
    def run_hplc_from_spreadsheet(self, spreadsheet_fn, batchID, sheet_name='Samples', exp=2, flowrate = 0.30, post_run=60, generate_report=True, mals_inj_vol=20, copy_with_scp=True):
        
        """
        Runs HPLC experiments based on data from a spreadsheet.

        Args:
            spreadsheet_fn (str): File path of the spreadsheet.
            batchID (str): Identifier for the batch.
            sheet_name (str, optional): Name of the sheet in the spreadsheet. Defaults to 'Samples'.
            exp (int, optional): Exposure time for data collection in seconds. Defaults to 2.
        """
    
        sequence_name = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
        samples, valve_position, experiment_type = self.CreateAgilentSeqFile(spreadsheet_fn, batchID, 
                                                                             sheet_name=sheet_name, mals_inj_vol=mals_inj_vol)
        uv_dest_path = f'{proc_path}'
   
    
        
    
        print(f"HPLC sequence file has been created in: {sequence_name}")
        print('Make sure you have selected the correct flow path for experiment and column type!')
        run_number = 1
        sample_items = list(samples.items())
        number_samples = len(sample_items)
        for run_idx, (sample_name, sample_info) in enumerate(sample_items, start = 1):
            
            print(f"Number of samples to run is: {number_samples}")
            print(f"Starting SEC for sample number {run_idx} of {number_samples}")
            single_sample = self.create_sample_param(sample_name, samples)
            caput('XF:16IDC-ES{HPLC}SAMPLE_NAME', sample_name)
            caput('XF:16IDC-ES{HPLC}SDK_Connection' , 1)
            #caput('XF:16IDC-ES{HPLC}HPLC:TAKE_CTRL' , 0) possibly causing agilent software to crash?
            
            single_sample = json.dumps(self.sample_params)
            caput('XF:16IDC-ES{HPLC}RunParameters' , single_sample)

            valve_pos = sample_info["md"]["Valve Position"]##should be changed to slot position
            print(f"Switching valve to position {valve_pos} for sample {sample_name}...")
            VV.switch_10port_valve(pos=valve_pos, valve=VICI_ID.Valve_10_port,
                                   valve_ID=VICI_ID.Valve_10_port.valve_ID, get_ret=False)

            print(f"Collecting data for {sample_name}...")
            acq_time_sec = sample_info["acq time"] * 60
            nframes = int(acq_time_sec / exp)
            self.collect_hplc(sample_name, exp=exp, nframes=nframes, post_run=post_run, 
                              md={'HPLC': sample_info['md']})  
            uid = db[-1].start['uid']
            #send_to_packing_queue(uid, "HPLC")
            pack_h5_with_lock(uid, dest_dir=proc_path, attach_uv_file=False) #handling uv attachment separately as it might take time to process on windows machine
            pil.use_sub_directory()
            if generate_report:
                gen_SEC_report(f'{sample_name}.h5', "exp.h5")
            else:
                print("No report requested")
        
        while run_number <= len(samples.items()):
            for sample_name, sample_info in samples.items():
                number_samples = len(samples.items())
        
###copy with scp is temporary until UV data is processed into IOC.  Will do processing with windows/Agilent software that will populate IOC with spectrum, but how to move data for safe keeping? Do we need originals?
                if copy_with_scp:
                    max_attempts = 3
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        for attempt in range(1, max_attempts + 1):
                            try:
                                print(f"Attempt {attempt}: Fetching UV data")
                                future = executor.submit(self._copy_with_scp, sample_name)
                                ret = future.result(timeout=3 * 60)
                                if ret[0] == 0:
                                    h5_attach_hplc(sample_name)
                                    return True
                                else:
                                    print(f"Attempt {attempt} failed: scp returned {ret}")
                            except TimeoutError:
                                print(f"Attempl {attempt} timed out!")
                            except Exception as e:
                                print(f"Attempt {attempt} raised exception {e} !")
                    print("failure of copying uv files after 3 attempts")
                    return False
                        
            run_number += 1
            
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