print(f"Loading {__file__}...")
import socket
from enum import Enum
import numpy as np
from time import sleep
import signal
import itertools
import pathlib, subprocess
import json
from tabulate import tabulate
windows_ip = '10.66.123.226'
#data_path = "/nsls2/data4/lix/legacy/HPLC/Agilent/"

TCP_IP = '10.66.122.159'  ##moxa on HPLC cart.  Port 2 is Regen_Pump, Port 6 is backup pump (TeledyneRegenerationPump = TRP)
#RegenPump_TCP_PORT = 4002
socket.setdefaulttimeout(10)
timeout=socket.getdefaulttimeout()
pump_params = ['Status','Flow_rate mL/min', 'Upper_Pressure_Limit', 'Lower_Pressure_Limit', 'Pressure_Units', 'Pressure_Value','Start(1)/Stop(0)']
class pumpID(Enum):
    RegenPump = (TCP_IP , 4002)
    PumpB = (TCP_IP, 4006)
    def __init__(self, address, port):
        self.address = address
        self.port = port

class pump_SSI:
    def __init__(self, address, port):
        self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((address, port))
        self.get_status()
       
    
    def send_cmd(self, cmd):
        self.sock.sendall(cmd.encode())
        data = self.sock.recv(1024)
        ret=data.decode("UTF-8")
        
        #print(data.decode("UTF-8"))
        #print(ret)
        return ret
    
    def get_flowrate(self, print_flow=True):
        fret=[]
        data=self.send_cmd("CS")
        a=data.split(",")
        print(a)
        fret.append(a[1])
        ret = float(fret[0])
        return ret
    
    def get_status(self, cmd="CS"):
        """
        Format of output"
        OK, flowrate, Upper pressure limit, lower pressure limit, pressure units, Run/Stop status, a zero (seems to be flowset point?
        Run/Stop Status 0=pump stopped, 1 = running
        """
        ret=self.send_cmd(cmd=cmd)
        ret_dict = ret.split(",")
        ret_dict = dict(zip(pump_params[0::1], ret_dict[0::1]))
        table = [(k, v) for k, v in ret_dict.items()]
        print(tabulate(table, headers=["Parameter", "Value"], tablefmt="fancy_grid"))
        return ret_dict
    
    def start_pump(self, cmd='RU'):
        self.send_cmd(cmd=cmd)
        #print(ret)
    
    def stop_pump(self, cmd="ST"):
        self.send_cmd(cmd=cmd)
        #print(ret)

    def split_decimal(self,flowrate):
        # Split the number into integer and decimal parts since the pump reads FI00000
        integer_part = int(flowrate)
        decimal_part = round(flowrate - integer_part, 3)

        # Convert the integer part to a string and pad with zeros
        integer_str = str(integer_part)
        if len(integer_str) < 2:
            integer_str=integer_str.zfill(2)
            print(integer_str)

        # Convert the decimal part to a string with 3 decimal places
        decimal_str = "{:.3f}".format(decimal_part)[2:]  # remove "0." prefix

        # Pad the decimal string with leading zeros if necessary
        if len(decimal_str) < 3:
            decimal_str = decimal_str.ljust(3, '0')
        elif len(decimal_str) > 5:
            decimal_str = decimal_str[:3]

        # Return the integer and decimal strings
        return integer_str, decimal_str
    
    def set_flowrate(self, flowrate=0.3):
        if int(flowrate) > 12:
            raise Exception("Max flowrate is 12mL/min!")
        else:
            integer_str,decimal_str=self.split_decimal(flowrate)
        self.send_cmd(cmd="FI"+ integer_str + decimal_str)
        
    def read_pressure(self,):
        #read pressure before making changes and monitor if necessary.Should not read values in a regular interval because of message clashing
        press_units=self.send_cmd( cmd="PU")
        current_press=self.send_cmd(cmd="PR")
        return press_units, current_press
    
    def set_upper_pressure_limit(self, upper_pressure=750):
        ##max pressure in psi, this is column dependent. 725psi for the superdex columns
        self.send_cmd(pumpID, "UP"+ str(upper_pressure))
        ret=self.get_status(pumpID)
        print(ret)
    
    def set_lower_pressure_limit(self, lower_pressure=25):
        ##max pressure in psi, this is column dependent. 725psi for the superdex columns
        self.send_cmd("LP"+ str(lower_pressure))
        ret=self.get_status()
        print(ret)
        
        
##class to control methods on regeneration pump
class regen_ctrl(pump_SSI):
    def __init__(self, column_type):
        self.column_type=column_type
        super().__init__(self)
    def setup_method(flowrate=0.1, max_pressure=700, time=None):
        ret=regen_ctrl.get_status()
        if ret[0] == "OK":
            regen_ctrl.set_flowrate(flowrate = flowrate)
            regen_ctrl.set_upper_pressure_limit(max_pressure=max_pressure)
            ret=regen_ctrl.get_status
            print(ret)
        else:
            raise Exception("Pump Status not OK")
        flowrate = flowrate
        
TRP=pump_SSI(pumpID.RegenPump.address, pumpID.RegenPump.port)
TRPB=pump_SSI(pumpID.PumpB.address, pumpID.PumpB.port)