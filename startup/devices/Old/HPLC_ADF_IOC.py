from pcaspy import Driver, SimpleServer
#import paramiko
from ophyd import (EpicsSignal, EpicsSignalRO, Device, Component as Cpt)
#from scp import SCPClient
import os
import threading
from pathlib import PureWindowsPath
from epics import caget, caput
from pcaspy import Driver, SimpleServer
global data_path
global data_destination, current_cycle, current_sample, proposal_id, run_id, login


prefix = 'XF:16IDC-ES{HPLC}'
windows_ip = '10.66.123.226'


        

# Define PVs and their properties
pvdb = {
    'SampleName': {'type': 'string'},
    'Method':{'type': 'string'},
    'Injection_Volume':{'type': 'string'},
    'Vial_position':{'type': 'string'},
    'TRANSFER': {'type': 'int', 'value': 0, 'scan' : 0.5}, # Trigger PV
    'Buffer_POS':{'type': 'int', 'value': 1}
}


class MyDriver(Driver):
    def __init__(self):
        #super().__init__()
        #self.lock = threading.Lock()
        #self.busy = 0
        super(MyDriver, self).__init__()
        #self.setParam("USERNAME", 'xf16id')
        #self.setParam("PASSWORD", 'xf16id')
        #self.windows_data_dir=PureWindowsPath("C:/Users/xf16id/CDSProjects/HPLC")
        #self.destination_directory = "/nsls2/data/lix/legacy/HPLC/Agilent/"
        #self.setParam("DEST_PATH", self.destination_directory)
        #self.setParam('FILE_SOURCE', self.windows_data_dir)
        #self.setParam("SampleName", current_sample)

    
    def scp_transfer(self, cmd):
        """To handle copying files from lustre to machine running Agilent software and vice versa"""
        try:
            ssh_key = str(pathlib.Path.home())+"/.ssh/id_rsa.pub"
            if not os.path.isfile(ssh_key):
                raise Exception(f"{ssh_key} does not exist!")
            cmd = cmd
            subprocess.run(cmd, check=True, universal_newlines=True)
            time.sleep(1)
            #self.setParam('TRANSFER', 0)  # Reset trigger after successful transfer
            print("Transfer successful!")

        except Exception as e:
            print(f"SCP transfer has failed for {cmd}!")
   
    def move_hplc_files(self, proposal_id=proposal_id, run_id=run_id,csv=False, **kwargs):
        UV_file_prefix = str(f"{run_id}")
        remote_file_dir = kwargs.get('current_sample')
        remote_file_adf = kwargs.get('current_sample')+'.ADF'
        remote_file_csv = kwargs.get('current_sample')+'.dx_DAD1E.CSV'
        UV_data = str(UV_file_prefix + "-" +remote_file_csv)
        print(UV_data)
        remote_dir='C:/Users/xf16id/CDSProjects/HPLC/'
        remote_path = os.path.join(remote_dir, remote_file_dir, remote_file_adf)
        remote_path_csv = os.path.join(remote_dir, remote_file_dir, remote_file_csv)
        cmd = ["scp", f"xf16id@{windows_ip}:{remote_path}", f"/nsls2/data/lix/legacy/HPLC/Agilent/{current_cycle}/{proposal_id}/{run_id}"]
        print(f"Waiting to transfer {remote_file_adf}....")
        scp_transfer(cmd)
        if csv==True:
            cmd = ["scp", f"xf16id@{windows_ip}:{remote_path_csv}", f"/nsls2/data/lix/legacy/HPLC/Agilent/{current_cycle}/{proposal_id}/{run_id}"]
            print(f"fetching CSV files from {remote_path_csv}")
            scp_transfer(cmd)

    def select_buffer_pos(self, buffer_pos=None):
        if buffer_pos is None:
            raise Exception("Location of the Buffer for SEC-SAXS has not been specified! The Value must be and integer between 1 and 6.")
        if not type(buffer_pos) is int:
            raise TypeError("buffer_pos must be an integer")
        if not 1<= buffer_pos => 6:
            raise ValueErorr("Buffer position must be between 1 and 6!)"
        return buffer_pos

    
    def read(self, reason):
        if reason == "TRANSFER":
            value = caget('XF:16IDC-ES{HPLC}TRANSFER')
            return value
        else:
            value = self.getParam(reason)
            return value
        
    def write(self, reason, value):
        """Handles PV writes, especially the TRANSFER trigger PV."""
        self.setParam(reason, value)

        # If the TRANSFER PV is written to 1, initiate the SCP transfer
        if reason == 'TRANSFER' and value == 1:
            print("Value is 1")
            self.move_hplc_files(proposal_id=proposal_id, run_id=run_id, current_sample=current_sample)
        if reason == 'Buffer_POS':
            buffer_pos=self.get_buffer_position()
            self.setParam(reason, buffer_pos)

        return True


    
    
# Start the EPICS server and driver
if __name__ == '__main__':
    server = SimpleServer()
    server.createPV(prefix, pvdb)
    driver = MyDriver()

    print("IOC is running. Modify TRANSFER PV to start SCP transfer.")

    while True:
        server.process(0.1)
