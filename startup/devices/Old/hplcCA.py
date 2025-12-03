
#!/opt/conda/bin/python3
#
# CA for the Agilent HPLC, communicates to the system using he SDK
#

import threading
import numpy as np
import time,os
import socket
from pathlib import PureWindowsPath,Path
import HPLC_functions as hplc
from APV import APV
import shutil
import os
from epics import caget, caput
from pcaspy import Driver, SimpleServer
from hplccon import AgilentHPLC

##temporary:
current_cycle="2024-3"
proposal_id ="123456"
run_id = "987654"
ADF_LOCATION= PureWindowsPath("C:/Users/xf16id/HPLC/Results/")
sample_name = "mover_test.txt"
# this is the hard-coded location where the new ADF file is expected
#ADF_LOCATION = "C:\\Desktop\"

prefix = 'XF:16IDC-ES{HPLC}'

pvdb = {
    "Connect_HPLC" : {'type' : 'string'},
    "DATA_PATH":     {'type' : 'string', 'scan': 0.5},    
    "SAMPLE_NAME":   {'type' : 'string'},    
    "START_RUN":     {'type' : 'string'},
    "busy":          {'type' : 'short', 'scan' : 0.5}, 
    "HPLC_status":   {'type' : 'string'},    
    "SAMPLER:VALVE_POS"       : {'type' : 'short'},    
    "SAMPLER:VALVE_POS_RBV"   : {'type' : 'string'},     
    "SAMPLER:TEMP"            : {'type' : 'short'},    
    "SAMPLER:TEMP_RBV"        : {'type' : 'short', 'scan' : 0.5},     
    "QUAT_PUMP:FLOWRATE"      : {'type' : 'short'},    
    "QUAT_PUMP:FLOWRATE_RBV"  : {'type' : 'short', 'scan' : 0.5},     
    "QUAT_PUMP:PRESSURE"      : {'type' : 'short'},    
    "QUAT_PUMP:PRESSURE_RBV"  : {'type' : 'short', 'scan' : 0.5},
    "QUAT_PUMP:PURGE_VALVE_POS": {'type' : 'short'},
    "QUAT_PUMP:PURGE_VALVE_POS_RBV" :{'type' : 'string'},
    "PURGE_COLUMN" : {'type' : 'enum', 'enums': ['closed', 'purge'], 'value' : 0},
    "PURGE_COLUMN_RBV" : {'type': 'string'},
    "FILE_MOVER:HPLC_Win_dir" : {'type' : 'string', 'scan' : 60.0},
    "FILE_MOVER:HPLC_DEST" : {'type' : 'short', 'scan' : 60.0},
    "Buffer_VALVE_POS" : {'type': 'int'},
    "Buffer_VALVE_RBV" : {'type': 'int', 'scan' : 0.5}
}

#def move_ADF(fn):
#    for i in fn:
#global data_path
#data_path=f"{data_destination}/{current_cycle}/{proposal_id}/{run_id}"       
#proc_dir = f"{current_cycle}/{proposal_id}/{run_id}"
#path=PureWindowsPath("C:/Users/xf16id/HPLC_testing")
#win_path = (f"{path}/{proc_dir}")
"""
Initiate the HPLC connection
from hplccon
my_hplc=()

"""
class myDriver(Driver):
    def __init__(self):
        super().__init__()                     # python3
        self.lock = threading.Lock()
        self.data_path = ""
        #self.sample_name = ""
        self.busy = 0
        print(self.busy)
        self.VV=hplc.VICI_valves()
        self.hplc = None
        #self.quat_purge_valve_status = "Closed"
    
    def execute(self, action, *arg):
        print("executing %s(%s)" % (action,arg))
        self.busy += 1
        self.lock.acquire()
        action(*arg)
        self.lock.release()
        self.busy -= 1
        print("Done.")

    def move_hplc_files(self, src_path, dest_dir):
        if not os.path.isfile(src_path):
            print (f" Source file {src_path} does not exist!")
            return
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            print(f" Created directory {dest_dir}!")
        filename = os.path.basename(src_path)
        dest_path = os.path.join(dest_dir, filename)
        shutil.move(src_path, dest_path)
        print(f" Moved ADF file '{src_path}' to '{dest_path}'.")
        
    def check_valve_pos():
        pass

    def get_hplc_status(self):
        # return a string that include all component status
        return ""

    def read(self, reason):
        
        if reason == 'busy':
            print('# of requests being processed: %d' % self.busy)
            return self.busy
        
        elif reason in ["DATA_PATH", "SAMPLE_NAME"]:
            value=self.getParam(reason)
            return value

        elif reason == 'QUAT_PUMP:PRESSURE_RBV':
            value = my_hplc.get_pressure()
            return value


        # everything below requires serial communication
        #self.lock.acquire()

            
        elif reason == "Buffer_VALVE_RBV":
            value = APV.valveStatus()
            #print("Buffer_VALVE_RBV", value)
            #self.getParam(value)
            return value
            
        elif reason == 'HPLC_status':
            value = self.get_hplc_status()
            value = 100
            print("HPLC STATUS=",value)
        
        elif reason == 'PURGE_COLUMN_RBV':
            cmd = "CP"
            colpurge = self.VV.send_valve_cmd(cmd=cmd, ID=3, get_ret=True)
            print(f"Column purge status is {colpurge}!")
            if colpurge == 'A':
                value = "Closed"
                print(value)
                return value
            if colpurge == 'B':
                value = "Purge"
                print(value)
                return value
            
        elif reason == 'SAMPLER:VALVE_POS_RBV':
            value = self.VV.send_cmd("1CP\r")
            print(f"10-port_Valve is {value}")
            #time.sleep(1)
            
        elif reason == "QUAT_PUMP:PURGE_VALVE_POS_RBV":
            cmd = "CP"
            pos = self.VV.send_valve_cmd(cmd=cmd, ID=2, get_ret=True)
            print('pos is',pos)
            value = pos
            if pos == 'B':
                value = "Closed"
                print(value)
                print(f'Quat Pump purge valve is {value}!')
                return value
            if pos == 'A':
                value = "Purge"
                print(value)
                print(f"Quat Pump purge valve is {value}")
                return value
            

        
        print("read request: %s" % reason)
        if self.busy>0:
            print("devices busy.")
            return -1
        else:
            value = self.getParam(reason)

        #return value
        #self.lock.release()
        return value

    def write(self, reason, value):
        status = True
        # take proper actions
        print(reason,value)

        if reason == 'Connect_HPLC':
            if value == True and self.hplc is None:
                name = 'HPLC'
                device = 'net.pipe://localhost/Agilent/OpenLAB/'
                instrument_name = 'HPLC_Agilent'
                project_name = 'HPLC
                self.hplc = AgilentHPLC(name, device, instrument_name, project_name)

                print("Agilent HPLC class has been instantiated")
            elif value == False:
                self.hplc = None
                print("Agilent HPLC class has been removed from memory")
            self.setParam(reason, value)
            return True
            

        elif reason == 'START_RUN':
            # this should execuate a HPLC run
            # for now it will only move the ADF file
            move_ADF()
            return status
        
            
        elif reason=='Buffer_VALVE_POS':
            self.setParam(reason, value)
            return status
            
        elif reason=='SAMPLE_NAME':
            self.sample_name = value
            self.setParam(reason, value)
            return status
        elif reason=='DATA_PATH':
            # set value is a linux path, e.g. /nsls2/data/lix/legacy/%s/2024-1/314980/test/
            # should convert to the corresponding Windows path first
            # the SAMBA mount path appears to be \\smb.nsls2.bnl.gov\data4\lix
            #win_path = PureWindowsPath(value.replace('/nsls2/data', '//smb.nsls2.bnl.gov/data4/%') % 'HPLC')
            win_store=PureWindowsPath(f'')
            #win_path = PureWindowsPath(value.replace(data_destination, 'C:/Users/xf16id/HPLC_testing/%s')%win_store)
            win_path = PureWindowsPath(value.replace(data_destination, 'C:/Users/xf16id/MOVE_TEST/%s')%win_store)
            print(win_path)
            # make sure it exists
            if not os.path.exists(win_path):
                os.makedirs(win_path)
                print(f"Directory '{win_path}' has been created!")
            else:
                print(f"Directory '{win_path}' exists!")
            self.data_path = win_path
            #value = win_path
            self.setParam(reason, str(win_path))
            print("Win_path=", win_path)
            return status, win_path
        
        elif reason == "QUAT_PUMP:PURGE_VALVE_POS":
            if value != 0:
                value = 1
                cmd = "GO"
                pos= self.VV.send_valve_cmd(cmd, ID=2, get_ret=True)
                print(pos)
                self.setParam(reason, value)
                return status , value
            
            elif value != 1:
                value = 0
                cmd = "GO"
                pos= self.VV.send_valve_cmd(cmd, ID=2, get_ret=True)
                print(pos)
                self.setParam(reason, value)
                print(status)
                return status , value
        
        elif reason == "PURGE_COLUMN":
            if value != 0:
                value = 1
                cmd = "GOB"
                colpos=self.VV.send_valve_cmd(cmd=cmd, ID=3, get_ret=True)
                print(colpos)
            self.setParam(reason, value)
            return status

        elif reason=="FILE_MOVER:HPLC_DEST":
            if value !=0:
                value=1
                win_path=caget('XF:16IDC-ES{HPLC}DATA_PATH')
                print(win_path)
                self.move_hplc_files(f"{win_path}/{sample_name}", data_path)
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
            #self.setParamEnums(reason, value, states=None)
        return status

if __name__ == '__main__':
    server = SimpleServer()
    server.createPV(prefix, pvdb)
    driver = myDriver()

    # process CA transactions
    while True:
        server.process(0.1)


