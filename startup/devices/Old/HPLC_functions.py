#!/opt/conda/bin/python3
import socket
import time
from enum import Enum
ioc_name="HPLC"
data_path=""
current_cycle="2024-3"
proposal_id = "123456"
run_id ="98765"




#from hplcCA import 
TCP_IP = '10.66.122.80'  ##moxa on HPLC cart.  Port 1 is valve, Port 2 is regen pump, Port 3 will contain all VICI valves
Pump_TCP_PORT = 4002
VICI_TCP_PORT = 4003
socket.setdefaulttimeout(10)
timeout=socket.getdefaulttimeout()
print(f'timeout is {timeout}.  This does not mean a connection was established!')
'''
class Valve():
    def __init__(self):
        self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((TCP_IP, VICI_TCP_PORT))
        #self.get_status()
        #self.get_status()
    
    def send_cmd(self,cmd):
        self.sock.sendall(cmd.encode())
        data = self.sock.recv(1024)
        ret=data.decode("UTF-8")
        print(data.decode("UTF-8"))
        print(ret)
        return ret
'''
##temporary class until we can integrate bsui startup
class data_file_path(Enum):
    lustre_legacy = "/nsls2/data4/lix/legacy"

data_destination=data_file_path.lustre_legacy.value
data_path=f"{data_destination}/%s/{current_cycle}/{proposal_id}/{run_id}"

def get_IOC_datapath(ioc_name, substitute_path=None):
    if substitute_path:
        return data_path.replace(data_destination, substitute_path)%ioc_name
    else:
        return data_path%ioc_name



class VICI_valves:
    def __init__(self):
        self.sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((TCP_IP, VICI_TCP_PORT))
        #self.get_status()
        #self.get_status()
        
    def send_valve_cmd(self, cmd, ID, get_ret=False):
        cmd=f"{ID}{cmd}\r"
        print(cmd)
        self.sock.sendall(cmd.encode('ascii'))
        time.sleep(0.5)
        print(f"Command f'{cmd}' has been sent to valve {ID}")
        #time.sleep(0.2)
        if cmd==f'{ID}GOA\r':
            print("changed, no return output")
        elif cmd==f'{ID}GOB\r':
            print("changed, no return output")
        elif cmd==f'{ID}GO\r':
            print("GO issued command, no return output")
        if get_ret:
            a,pos = self.check_valve_pos(ID=ID)
            #ret=self.check_valve_pos(self, ID)
            #time.sleep(0.5)
            #ret=self.sock.recv(1024)
            #ascii_ret=ret.decode("ascii")
            #print(ret)
            #return ret
            #self.sock.close()
            #pos=pos[-3]
            return(pos[-3])
    
    def check_valve_pos(self, ID):
        cmd = f"{ID}CP\r"
        self.sock.sendall(cmd.encode())
        time.sleep(0.1)
        print(f"Getting {ID} Valve status")
        ret = self.sock.recv(1024)
        ascii_ret = ret.decode("ascii")
        #print(ascii_ret)
        #print(ascii_ret[-3])
        return(ret, ascii_ret)
        
    def switch_10port_valve(self, pos="A", ID=1, get_ret=False):
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
    
#VV = VICI_valves()   
#VV=Valve()