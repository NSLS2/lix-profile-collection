#!/opt/conda/bin/python3
#
# CA for the Agilent HPLC, communicates to the system using he SDK
#

import threading, subprocess, shlex, sys
import numpy as np
import time,os
from pathlib import PureWindowsPath,Path
import json
import warnings
from epics import caget, caput


from pcaspy import Driver, SimpleServer

##SDK and AGilent stuff
import pythonnet
#import hplccon
#from hplccon import AgilentHPLC as AG
name='SEC-SAXS'
device = "net.pipe://localhost/Agilent/OpenLAB/"
instrument_name = "Agilent_HPLC"
project_name = "HPLC"
# this is the hard-coded location where the new ADF file is expected
ADF_LOCATION = ""
data_path = Path("C:/CDSProjects/HPLC")

prefix = 'XF:16IDC-ES{HPLC}'

pvdb = {
    "DATA_PATH":     {'type' : 'string'},    
    "SAMPLE_NAME":   {'type' : 'string'},    
    "START_RUN":     {'type' : 'int', 'value': 0},
    "busy":          {'type' : 'short', 'scan' : 0.5}, 
    "HPLC_status":   {'type' : 'int', 'value' : 0},
    "HPLC_status_RBV" : {'type': 'int', 'value' :0},
    "SAMPLER:VALVE_POS"       : {'type' : 'short'},    
    "SAMPLER:VALVE_POS_RBV"   : {'type' : 'short', 'scan' : 0.5},     
    "SAMPLER:TEMP"            : {'type' : 'short'},    
    "SAMPLER:TEMP_RBV"        : {'type' : 'short', 'scan' : 0.5},     
    "QUAT_PUMP:FLOWRATE"      : {'type' : 'short', 'value' :0},    
    "QUAT_PUMP:FLOWRATE_RBV"  : {'type' : 'short', 'scan' : 0.5},     
    "QUAT_PUMP:PRESSURE"      : {'type' : 'float', 'value' : 0},    
    "QUAT_PUMP:PRESSURE_RBV"  : {'type' : 'float', 'scan' : 0.5},
    "SDK_Connection" : {'type' : 'int', 'value' : 0},
    "HPLC:TAKE_CTRL" : {'type': 'int', 'value' : 1},
    "HPLCRunStatus" : {'type' :'string', 'value': ''},
    "RunParameters" : {'type':'char', 'count':1024, 'value':'{}'},
    "Result_Path" : {'type' : 'char', 'count':60, 'value' : 'test'},
    "Result_Name" : {'type': 'char', 'count':1024, 'value' : '<S>'},
    "HPLC:GetUVTrigger" : {'type' : 'int', 'value': 0, 'scan' : 0.5},
    "HPLC:UVDATA" : {'type': 'float' , 'count' :5000},
    "COMMAND" : {'type': 'string', 'asyn': True},
    "OUTPUT" : {'type': 'string'},
    "STATUS" : {'type' : 'enum', 'enums' : ['DONE', 'BUSY']},
    "ERROR" : {'type' : 'string'}
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
        #self.hplc = AG(self.name, self.device, self.instrument_name, self.project_name)
        self.hplc = "test"
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
     
    def move_UVdata(self, sample_name):
        win_path = PureWindowsPath("C:\CDSProjects\HPLC\")
        for i in sample name:
            
     '''       
            
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
        elif reason == "QUAT_PUMP:FLOWRATE_RBV":
            #self.getParam(reason)
            value = caget("XF:16IDC-ES{HPLC}QUAT_PUMP:FLOWRATE")
            self.setParam(reason, value)
            return value
        elif reason == "QUAT_PUMP:PRESSURE_RBV":
            value=self.getParam(reason)
            return value
        elif reason in ["DATA_PATH", "SAMPLE_NAME"]:
            self.getParam(reason)
            value =[self.sample_name, self.data_path]
            return value
        
        elif reason == 'SDK_Connection':
            value = self.getParam(reason)
            return value
        elif reason == 'HPLCRunStatus':
            value = self.getParam(reason)
            return value
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
                self.tid = threading.Thread(target=self.runShell, args=(command,))
                self.tid.start()
                if status:
                    self.setParam(reason, value)
                return status
            else:
                status = False
                
        elif reason == "HPLC:TAKE_CTRL":
            if value == 0:
                self.execute(self.take_control)
            self.setParam(reason,value)
            self.updatePVs()
        elif reason == "QUAT_PUMP:FLOWRATE":
            if self.hplc.controller.IsConnected == True:
                self.hplc.set_flow_rate(value)
                self.setParam("QUAT_PUMP:FLOWRATE_RBV",value)
                self.updatePVs()
            else:
                print("Not connected to SDK")
        elif reason == "QUAT_PUMP:PRESSURE":
            if self.hplc.controller.IsConnected == True:
                value = self.hplc.get_pressure()
                self.setParam("QUAT_PUMP:PRESSURE_RBV", value)
                self.updatePVs()
            else:
                print("Not connected to SDK")
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
            self.updatePVs()
            self.sample_name = value
            return status
        
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
            value=self.getParam(reason, value)
            self.updatePVs()
            return value

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


