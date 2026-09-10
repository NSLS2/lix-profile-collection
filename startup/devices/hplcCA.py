#!/opt/conda/bin/python3
#
# CA for the Agilent HPLC, communicates to the system using he SDK
#

import threading, subprocess, shlex
import numpy as np
import time,os
from pathlib import PureWindowsPath,Path
import json
import warnings
from epics import caget, caput
import h5py


from pcaspy import Driver, SimpleServer

##SDK and AGilent stuff
import pythonnet
import hplccon
from hplccon import AgilentHPLC as AG
name='SEC-SAXS'
device = "net.pipe://localhost/Agilent/OpenLAB/"
instrument_name = "Agilent_HPLC"
project_name = "HPLC"
# this is the hard-coded location where the new ADF file is expected
ADF_LOCATION = PureWindowsPath("C:/CDSProjects/HPLC/")
"DAD Spectral output after run"
MAX_NLAM = 1024
MAX_NFR = 9000
MAX_DATA = 7500
#MAX_DATA = MAX_NLAM*MAX_NFR
TIM_IN_MIN = True

prefix = 'XF:16IDC-ES{HPLC}'

pvdb = {
    "DATA_PATH":     {'type' : 'string'},    
    "SAMPLE_NAME":   {'type' : 'string'}, 
    "SAMPLE_NAME_RBV":{'type' :'string'},
    "START_RUN":     {'type' : 'int', 'value': 0},
    "busy":          {'type' : 'short', 'scan' : 0.5}, 
    "HPLC_status":   {'type' : 'int', 'value' : 0},
    "HPLC_status_RBV" : {'type': 'int', 'value' :0},
    "SAMPLER:VALVE_POS"       : {'type' : 'short'},    
    "SAMPLER:VALVE_POS_RBV"   : {'type' : 'short', 'scan' : 0.5},     
    "SAMPLER:TEMP"            : {'type' : 'short'},    
    "SAMPLER:TEMP_RBV"        : {'type' : 'short', 'scan' : 0.5},     
    "QUAT_PUMP:FLOWRATE"      : {'type' : 'short', 'value' :0},    
    "QUAT_PUMP:FLOWRATE_RBV"  : {'type' : 'float', 'scan' : 100},     
    "QUAT_PUMP:PRESSURE"      : {'type' : 'float', 'value' : 0},    
    "QUAT_PUMP:PRESSURE_RBV"  : {'type' : 'float', 'scan' : 0.5},
    "QUAT_PUMP:PRESSURE_HIGH_LIMIT" : {'type' : 'float', 'value' : 0},
    "SDK_Connection" : {'type' : 'int', 'value' : 0},
    "SDK_Connection_RBV" : {'type' :'string'},
    "HPLC:TAKE_CTRL" : {'type': 'int', 'value' : 1},
    "HPLCRunStatus" : {'type' :'string', 'value': ''},
    "RunParameters" : {'type':'char', 'count':1024, 'value':'{}'},
    "Result_Path" : {'type' : 'char', 'count':60, 'value' : 'test'},
    "Result_Name" : {'type': 'char', 'count':1024, 'value' : '<S>'},
    "HPLC:GetUVTrigger" : {'type' : 'int', 'value': 0, 'scan' : 0.5},
    "HPLC:UVDATA" : {'type': 'int', 'value': 0},
    "COMMAND" : {'type': 'string', 'count' :128, 'asyn': True},
    "OUTPUT" : {'type': 'char', 'count' :500},
    "STATUS" : {'type' : 'enum', 'enums' : ['DONE', 'BUSY']},
    "ERROR" : {'type' : 'string'},
    "HPLC:UV:SPEC:GET" : {'type':'int', 'value': 0},
    "HPLC:UV:SPEC:DONE" : {'type' : 'int', 'value': 0},
    "HPLC:UV:SPEC:NLAM" : {'type' : 'int', 'value' : 0},
    "HPLC:UV:SPEC:NFR" : {'type' : 'int', 'value' :0},
    "HPLC:UV:SPEC:WL" : {'type' : 'float', 'count': MAX_NLAM},
    "HPLC:UV:SPEC:T" : {'type' : 'float', 'count' : MAX_NFR},
    "HPLC:UV:SPEC:DATA" : {'type' : 'float', 'count' :MAX_DATA},
 
    
}
print("Through database")   
class myDriver(Driver):
    def __init__(self):
        super().__init__()                     # python3
        self.lock = threading.Lock()
        self.data_path = ""
        self.sample_name = ""
        self.name= name
        self.device = device
        self. instrument_name = instrument_name
        self.project_name = project_name
        self.busy = 0
        print(self.busy)
        self.hplc = AG(self.name, self.device, self.instrument_name, self.project_name)
        self.runparam_dict={}
        self.result_name = None
        self.result_path = None
        self.sequence_name= 'Test'
        self.hplc_status = None
        self.tid = None

    def execute(self, action, *arg):
        print("executing %s(%s)" % (action,arg))
        self.busy += 1
        self.lock.acquire()
        action(*arg)
        self.lock.release()
        self.busy -= 1
        print("Done.")
    
    def connect_sdk(self):
        if self.hplc==None:
            self.hplc = AG(self.name, self.device, self.instrument_name, self.project_name)
            time.sleep(5)
            print("HPLC not connected to SDK, starting a connection...")
            if self.hplc.controller.IsConnected == True:
                print(f"connecting to HPLC {self.name}")
                self.setParam('SDK_Connection', 1)
                print(f"{self.instrument_name} is connected to SDK")
            else:
                warnings.warn("Connection not esstablished to SDK", UserWarnings)
        else:
            print(f"HPLC is connect {self.hplc.name}")
            
            
    def _extract_dx(self, adf_name):
        sd = adf_name['data-cube']
        return sd
    def _prop(self, obj, name):
        return obj.GetType().GetProperty(name).GetValue(obj, None)

    _TIME_UNIT_SCALE = {"Milliseconds": 1e-3, "Seconds": 1.0, "Minutes": 60.0, "Hours": 3600.0}

    def _frame_time_seconds(self,frame):
        t_val = _prop(frame, "Time")          # nullable double
        if t_val is None:
            return np.nan
        t = float(t_val)
        unit = _prop(frame, "TimeUnit")       # enum
        scale = _TIME_UNIT_SCALE.get(unit.ToString(), 1.0)
        return t * scale

    # --- read EquidistantData from one frame ---
    def _read_frame_equidistant(self,frame):
        ed = _prop(frame, "Data")             # EquidistantData
        xmin  = float(_prop(ed, "XMin"))
        xstep = float(_prop(ed, "XStep"))
        y     = np.array(list(_prop(ed, "YValues")), dtype=float)   # 1D
        return xmin, xstep, y

    # --- main: SpectraData -> (wavelengths, times, matrix) ---
    def spectra_from_spectra_data(self, sd, signal_meta=None, time_in_minutes=False):
        """
        sd: Agilent.OpenLab.Framework.DataAccess.CoreTypes.SpectraData
        Returns:
          wl_nm : (nλ,) wavelength grid in nm
          t     : (nF,) times (seconds by default; minutes if time_in_minutes=True)
          Y     : (nF, nλ) intensities (mAU)
        """
        it = iter(sd.Data)
        try:
            first = next(it)
        except StopIteration:
            raise RuntimeError("No frames in SpectraData.Data")

        xmin, xstep, y0 = _read_frame_equidistant(first)
        nlam = y0.size
        wl_nm = xmin + xstep * np.arange(nlam, dtype=float)

        Y_rows = [y0]
        times  = [_frame_time_seconds(first)]

        # loop remaining frames
        for frame in it:
            xmin_i, xstep_i, yi = _read_frame_equidistant(frame)
            if abs(xmin_i - xmin) > 1e-9 or abs(xstep_i - xstep) > 1e-12 or yi.size != nlam:
                raise ValueError("Wavelength grid changed across frames—resampling required.")
            Y_rows.append(yi)
            times.append(_frame_time_seconds(frame))

        Y = np.vstack(Y_rows)
        t = np.array(times, dtype=float)

        # fill time if all missing
        if np.isnan(t).all():
            if signal_meta is not None:
                t0 = float(getattr(signal_meta, "StartTime", 0.0))
                t1 = float(getattr(signal_meta, "EndTime",   len(Y)-1))
                t = np.linspace(t0, t1, len(Y))
            else:
                t = np.arange(len(Y), dtype=float)

        if time_in_minutes:
            t = t / 60.0

        return wl_nm, t, Y         
    
    def get_hplc_status(self):
        # return a string that include all component status
        if self.hplc:
            self.hplc_status = self.hplc.get_instrument_status()
            print(f"This is the hplc status: {self.hplc_status}")
            caput('XF:16IDC-ES{HPLC}HPLCRunStatus', self.hplc.status)
        else:
            self.execute(self.connect_sdk)
            print("HPLC not connected to SDK, starting a connection...")
            if self.hplc.controller.IsConnected == True:
                print(f"connecting to HPLC {self.name}")
                self.setParam('SDK_Connection', 1)
                print(f"{self.instrument_name} is connected to SDK")
            else:
                warnings.warn("Connection not esstablished to SDK", UserWarnings)
            
                
                
        return self.hplc_status
    
    def take_control(self):
        """
        Takes control of an agilent device
        """
        control = self.hplc.controller.TakeInstrumentControl()
        return control
    
    def runShell(self, command):
        print("DEBUG : Run ", command)
        self.setParam('STATUS' , 1)
        self.updatePVs()
        try:
            time.sleep(0.01)
            proc = subprocess.Popen(shlex.split(command),
                                    stdout= subprocess.PIPE,
                                    stderr = subprocess.PIPE)
            proc.wait()
        except OSError:
            self.setParam('ERROR', str(sys.exc_info()[1]))
            self.setParam('OUTPUT', '')
        else:
            self.setParam('ERROR' , proc.stderr.read().rstrip())
            self.setParam('OUTPUT', proc.stdout.read().rstrip())
        self.callbackPV("COMMAND")
        self.setParam('STATUS', 0)
        self.updatePVs()
        self.tid = None
        print("DEBUG: Finish " , command)
    
    def get_ADF_filename(self):
        sample_name = caget('XF:16IDC-ES{HPLC}SAMPLE_NAME_RBV', as_string=True)
        print(sample_name)
        #sample_name=self.sample_name
        fn = f'SiSa_{sample_name}.ADF'
        print(f'looking for ADF file {fn}..')
        path=PureWindowsPath("ADF_LOCATION/sample_name/fn")
        print(f'looking in windows directory {path}')
        return fn, path
        
    def get_UV_data_from_ADF(self, path, fn):
        
        with h5py.File(path, "r") as fh5:
            for k in fh5['data-cubes'].keys():
                if not "DAD1I" in k: # this is apparently the 2D data
                    continue
                kkk = list(fh5['data-cubes'][k]['measures'].keys())[0]
                return fh5['data-cubes'][k]['measures'][kkk][...]

        return None
    def read(self, reason):
        if reason == 'busy':
            print('# of requests being processed: %d' % self.busy)
            return self.busy
        elif reason == "QUAT_PUMP:FLOWRATE_RBV":
            #self.getParam(reason)
            value = self.hplc.get_flow_rate()
            self.setParam(reason, value)
            return value

        elif reason == "QUAT_PUMP:PRESSURE_HIGH_LIMIT":
            self.getParam(reason)
            high_press_limit = self.hplc.get_high_pressure_limit()
            self.setParam(reason, high_press_limit)
            print(f"High pressure limit is {high_press_limit} BAR!")
            return high_press_limit
        elif reason in ["DATA_PATH"]:
            self.getParam(reason)
            value =[ self.data_path]
            return value
        
        elif reason == 'SDK_Connection_RBV':
            self.getParam(reason)
            value = self.hplc_status
            self.setParam(reason, value)
            print(value)
            return value
        elif reason == 'HPLCRunStatus':
            value = self.getParam(reason)
            return value
        elif reason == 'SAMPLE_NAME':
            self.getParam(reason)
        elif reason == 'SAMPLE_NAME_RBV':
            self.getParam(reason)
        elif reason == 'HPLC:UVDATA':
            value = self.getParam(reason)
            print("Reading UVDATA PV")

        elif reason == 'HPLC_status_RBV':
            value=self.getParam(reason)
            if value == 1:
                if self.hplc_status == "Idle" :
                    print("The state of the HPLC is IDLE")
                    #self.setParam("HPLCRunStatus", self.hplc_status)
                elif self.hplc_status == "RUN":
                    print("The state of the HPLC is RUN")
                    #self.setParam("HPLCRunStatus", self.hplc_status)
                else:
                    self.hplc_status=self.hplc.get_instrument_status()
                    print(f" The state of the HPLC is {self.hplc_status}")
                    #self.setParam("HPLCRunStatus", self.hplc_status)

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

        if reason == 'START_RUN':
            # this should execuate a HPLC run
            if value == 1 and self.hplc:
                self.execute(self.hplc.submit_single_sample, self.sequence_name,
                             self.runparam_dict, self.result_path, self.result_name)
            self.setParam(reason,value)
            print(f"Starting single sample run on for {self.sample_name}")
        elif reason == "COMMAND":
            if not self.tid:
                command = value
                if command:
                    self.tid = threading.Thread(target=self.runShell, args=(command,))
                    self.tid.start()
            else:
                status = False
                
        elif reason == "HPLC:TAKE_CTRL":
            if value == 0:
                self.execute(self.take_control)
            self.setParam(reason,value)
            self.updatePVs()
        
        
        elif reason == "HPLC:GetUVTrigger":
            pass
        elif reason == "HPLC_status":
            if value == 1:
                def check_hplc_status():
                    status=self.hplc.get_instrument_status()
                
                    if status == "Idle" :
                        print("The state of the HPLC is IDLE")
                        self.hplc_status = "Idle"
                    elif status == "RUN":
                        print("The state of the HPLC is RUN")
                        self.hplc_status = "RUN"
                    else:
                        print(f" The state of the HPLC is {status}")
                        self.hplc_status = status
                    
                    self.setParam("HPLCRunStatus", self.hplc_status)
                    self.updatePVs()
                threading.Thread(target=check_hplc_status).start()
            
            
            
            self.setParam(reason,value)
            self.setParam("HPLC_status_RBV", value)
            self.updatePVs()
            


            
        elif reason=='SAMPLE_NAME': 
            self.setParam(reason, value)
            #self.sample_name = value
            self.setParam("SAMPLE_NAME_RBV", value)
            self.updatePVs()
        
        elif reason=='DATA_PATH':
            # set value is a linux path, e.g. /nsls2/data/lix/legacy/%s/2024-1/314980/test/
            # should convert to the corresponding Windows path first
            # the SAMBA mount path appears to be \\smb.nsls2.bnl.gov\data4\lix
            win_path = PureWindowsPath(value.replace('/nsls2/data', '//smb.nsls2.bnl.gov/data4') % 'HPLC')
            # make sure it exists
            os.makedirs(win_path)
            self.data_path = win_path
            self.setParam(reason, win_path)
            return status
        
        elif reason=='SDK_Connection':
            if value == 1 and self.hplc is None:
                self.execute(self.connect_sdk)
                #self.hplc=AG(name,device, instrument_name, project_name)
                print(f"connecting to HPLC {name}")
                self.setParam('HPLCRunStatus', 'Connected')
            elif value == 2 and self.hplc:
                self.hplc.disconnect()
                self.hplc_status = None
                self.setParam('HPLCRunStatus', 'Disconnected')
            return status
        
        elif reason == 'RunParameters':
            self.runparam_dict = json.loads(value)
            self.sample_name = self.runparam_dict['sample_name']
            print(self.sample_name)
            print(f"These are the run parameters {self.runparam_dict}")
        
        elif reason == "Result_Path":
            self.result_path = value
            self.setParam(reason,value)
            print(f"Result path is set to : {self.result_path}")
        
        elif reason == "Result_Name":
            self.result_name = value
            self.setParam(reason, value)
            print(f"Result Name is set to: {self.result_name}")
    
        elif reason == "HPLC:UVDATA":
            print("first step")
            v =int(value)
            print(v)
            self.setParam("HPLC:UVDATA" , v)
            if v == 1:
                ###run a function to generate numpy array
                self.setParam("HPLC:UVDATA" , 0)
                print("starting to get adf file")
                fn, path = self.get_ADF_filename()
                data = self.get_UV_data_from_ADF(path, fn)
                spec_array = np.asarray(data, dtype=np.float32)
                self.setParam("HPLC:UV:SPEC:DATA",spec_array)
                self.updatePVs()
                return status

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


