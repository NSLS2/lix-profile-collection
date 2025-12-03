#!/opt/conda/bin/python3
#
# CA for the Agilent HPLC, communicates to the system using he SDK
#

import threading
import numpy as np
import time,os
import subprocess
from pathlib import PureWindowsPath,Path
import pathlib
import json
import warnings
from epics import caget, caput

from pcaspy import Driver, SimpleServer

##SDK and AGilent stuff
#from hplccon import AgilentHPLC as AG
from Regen_Pump import pumpID, pump_SSI
name='SEC-SAXS'
device = "net.pipe://localhost/Agilent/OpenLAB/"
instrument_name = "Agilent_HPLC"
project_name = "HPLC"
# this is the hard-coded location where the new ADF file is expected
ADF_LOCATION = PureWindowsPath("C://CDSProjects/HPLC/")
data_path = "/nsls2/data4/lix/legacy/HPLC/Agilent/"
windows_ip = "10.66.123.226"


'setup connection to pump(s)'

#TRP_B=pump_SSI(pumpID.PumpB.address, pumpID.PumpB.port) ##for co-flow or spare to regen 3rd column

prefix = 'XF:16IDC-ES{HPLC}'

pvdb = {
    "busy":          {'type' : 'short', 'scan' : 0.5}, 
    "HPLC:GETUV" : {'type' : 'short', 'scan' : 0.5, 'value':0},
    "HPLC:SNUV" : { 'type' : 'string', 'value' : " "},
    "REGEN:FLOWRATE" : {'type' : 'int', 'value' : 0},
    "REGEN:FLOWRATE_RBV" : {'type' :'short', 'scan': 0.5},
    "REGEN:RUN_STATUS" : {'type' : 'enum', 'enums' : ['RUN', 'STOP'], 'value' : 1, 'scan': 0.5},
    "REGEN:RUN" : {'type' : 'string', 'value' : 'STOP'}
}

class myDriver(Driver):
    def __init__(self):
        super().__init__()                     # python3
        self.lock = threading.Lock()
        self.data_path = ""
        self.sample_name = ""
        self.busy = 0
        self.result_name = None
        self.result_path = None
        self.regen_pump_ctrl = pump_SSI(pumpID.RegenPump.address, pumpID.RegenPump.port)

    def execute(self, action, *arg):
        print("executing %s(%s)" % (action,arg))
        self.busy += 1
        self.lock.acquire()
        action(*arg)
        self.lock.release()
        self.busy -= 1
        print("Done.")
    
    def move_UV_data(self, sample_name):
        ssh_key = str(pathlib.Path.home())+"/.ssh/id_rsa"
        if not os.path.isfile(ssh_key):
            raise Exception(f"{ssh_key} does not exist!")
        print(f"initiating UV transfer for {sample_name}....")
        cmd = ["scp", "-i", ssh_key, "-r", f"xf16id@{windows_ip}:{ADF_LOCATION}/{sample_name}", data_path ]
        #proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        th = threading.Thread(target=subprocess.run, args=(cmd,))
        th.start()
                  

    def get_hplc_status(self):
        # return a string that include all component status
        if self.hplc is not None:
            self.hplc_status = self.hplc.get_instrument_status()
            print(f"This is the hplc status: {self.hplc_status}")
        else:
            self.execute(self.connect_sdk)
            print("HPLC not connected to SDK, starting a connection...")
            if self.hplc.controller.IsConnected == True:
                print(f"connecting to HPLC {self.name}")
                value = self.setParam('SDK_Connection', 1)
                print(f"{self.instrument_name} is connected to SDK")
            else:
                warnings.warn("Connection not esstablished to SDK", UserWarnings)
            
                
                
        return self.hplc_status
    
    def read(self, reason):
        if reason == 'busy':
            print('# of requests being processed: %d' % self.busy)
            return self.busy
        
        elif reason in ["DATA_PATH", "SAMPLE_NAME"]:
            self.getParam(reason)
            return value
        
        elif reason == "HPLC:SNUV":
            value = self.getParam(reason)
            return value
        elif reason == "REGEN:FLOWRATE_RBV":
            value = self.getParam(reason)
            return value
        elif reason == "REGEN:RUN_STATUS":
            self.getParam(reason)
            ret_dict = self.regen_pump_ctrl.get_status()
            time.sleep(1)
            value = ret_dict['Start(1)/Stop(0)']
            print(f"reading start stop from pump: {value}")
            value = int(value)
            self.setParam(reason, value)
            return value
 
        elif reason == 'SDK_Connection':
            value = self.getParam(reason)
            return value
        elif reason == 'HPLC_status_RBV':
            value=self.getParam(reason)
            if value == 1:
                self.hplc_status = self.get_hplc_status()
                if self.hplc_status == "Idle" :
                    print("The state of the HPLC is IDLE")
                    self.setParam("HPLCRunStatus", self.hplc_status)
                elif self.hplc_status == "RUN":
                    print("The state of the HPLC is RUN")
                    self.setParam("HPLCRunStatus", self.hplc_status)
                else:
                    self.hplc_status=self.hplc.get_instrument_status()
                    print(f" The state of the HPLC is {self.hplc_status}")
                    self.setParam("HPLCRunStatus", self.hplc_status)
            
            
            self.updatePVs()
            return value
        
        


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
        elif reason == "HPLC:SNUV":
            self.setParam(reason,value)
            return status
        elif reason == 'REGEN:FLOWRATE':
            self.setParam(reason, value)
            print(reason, value)
            flwr = self.regen_pump_ctrl.get_flowrate()
            print(f'current flowrate for regen pump is {flwr}')
            self.execute(self.regen_pump_ctrl.set_flowrate, value)
            self.setParam("REGEN:FLOWRATE_RBV", value)
            return status
        elif reason == "REGEN:RUN": 
            if value == "RUN":
                self.execute(self.regen_pump_ctrl.start_pump)
                self.setParam("REGEN:RUN_STATUS", 0)
            elif value == "STOP":
                self.execute(self.regen_pump_ctrl.stop_pump)
                self.setParam("REGEN:RUN_STATUS", 1)
            else:
                print("Warning, not an acceptable pump function, must be RUN or STOP")
            return status
        
        elif reason == "HPLC:GETUV":
            self.getParam(reason)
            if value == 1:
                sample_name=self.getParam('HPLC:SNUV')
                print(sample_name)
                self.move_UV_data(sample_name)
            return status
        elif reason == "HPLC_status":
            if "HPLC_status" == 1:
                self.execute(self.connect_sdk)
                print("connecting....")
                #self.hplc_status = self.get_hplc_status()
                #if self.hplc_status == "Idle" :
                 #   print("The state of the HPLC is IDLE")
                  #  self.hplc_status = value
                #elif self.hplc_status == "RUN":
                 #   print("The state of the HPLC is RUN")
                  #  self.hplc_status = value
                #else:
                 #   print(f" The state of the HPLC is {self.hplc_status}")
                  #  self.hplc_status = value
            self.setParam(reason,value)
            self.setParam("HPLC_status_RBV", value)
            self.updatePVs()
            
            return status


            
        elif reason=='SAMPLE_NAME':
            self.sample_name = value
            self.setParam(reason, value)
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


