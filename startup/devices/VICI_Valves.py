print(f"Loading {__file__}...")
import socket
import os
import numpy as np
from time import sleep
import signal
import itertools
from enum import Enum
from tabulate import tabulate

TCP_IP = '10.66.122.159'  ##moxa on HPLC cart.  Port 3 is 10 port valve for column selection, port 4 is agilent purge, port5  is col1_purge, port 7 col2_purge

socket.setdefaulttimeout(10)
timeout=socket.getdefaulttimeout()


class VICI_ID(Enum):
    Valve_10_port = (TCP_IP , 4003, 1)
    Agilent_purge = (TCP_IP, 4004, 2)
    Col1_purge = (TCP_IP , 4005, 3)
    Detector = (TCP_IP , 4007, 4)
    
    def __init__(self, address, port, valve_ID):
        self.address = address
        self.port = port
        self.valve_ID = valve_ID
        
class VICI_valves:
    def __init__(self):
        self.sockets = {}
        for valve in VICI_ID:
            try:
                print(f"connecting to {valve} at {valve.address}:{valve.port}")
                sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((valve.address, valve.port))
                self.sockets[valve]= sock
                self.check_valve_pos(valve,valve.valve_ID)
                
            except(socket.error, OSError) as e:
                print(f"WARNING: Failed to connect to {valve.name} at {valve.address}:{valve.port}: {e}")
                
    def send_valve_cmd(self, cmd, valve=None, valve_ID=None, get_ret=False):
        cmd=f"{valve_ID}{cmd}\r"
        print(f"this is the command being sent: {cmd}")
        self.sockets[valve].sendall(cmd.encode())
        sleep(1)
        print(f"Command {cmd} has been sent to valve {valve} with ID {valve_ID}")
        sleep(0.2)
        if cmd==f'{valve_ID}GOA':
            sleep(2)
            cur_pos=self.check_valve_pos(valve=valve, valve_ID=valve_ID)
            if cur_pos[-3] == cmd[-1]:
                print(f"changed to pos {cmd[-1]}")
            else:
                raise ValueError(f"Valve {valve} did not change to {cmd[-1]}!")
        elif cmd==f'{valve_ID}GOB':
            sleep(2)
            cur_pos=self.check_valve_pos(valve=valve, valve_ID=valve_ID)
            if cur_pos[-3] == cmd[-1]:
                print(f"changed to pos {cmd[-1]}")
            else:
                raise ValueError(f"Valve {valve} did not change to {cmd[-1]}!")
        elif cmd==f'{valve_ID}GO\r':
            cur_pos = self.check_valve_pos(valve=valve, valve_ID=valve_ID)
            print(f"GO issued command, and now at {cur_pos}")
        if get_ret:
            ret=self.sockets[valve].recv(1024)
            ascii_ret=ret.decode("ascii")
            print(ascii_ret)
            return ret, ascii_ret
            
    
    def check_valve_pos(self, valve, valve_ID):
        cmd = f"{valve_ID}CP\r"
        self.sockets[valve].sendall(cmd.encode())
        sleep(0.1)
        print(f"Getting {valve}:{valve_ID} Valve status")
        ret = self.sockets[valve].recv(1024)
        ascii_ret = ret.decode("ascii")
        #print(ascii_ret)
        print(f"{valve} is in position {ascii_ret[-3]}")
        return ascii_ret
        
    def switch_10port_valve(self, pos="A", valve = VICI_ID.Valve_10_port, valve_ID=VICI_ID.Valve_10_port.valve_ID, get_ret=False):
        cur_pos=self.check_valve_pos(valve, valve_ID=valve_ID)  ## format is "Postion is A' \r"
        if cur_pos[-3] == pos:
            print(f"10-port Valve already at {pos}!")
        
        elif cur_pos[-3] != pos:
            if pos=="A":
                self.send_valve_cmd("GOA", valve=valve, valve_ID=valve_ID) 
            elif pos=="B":
                self.send_valve_cmd("GOB", valve=valve, valve_ID=valve_ID)
            elif pos=="GO":
                self.send_valve_cmd("GO", valve=valve, valve_ID=valve_ID)
        else:
            raise Exception(f"{pos} is not a valid command to change 10-port valve! Use 'A' or 'B'.")

VV = VICI_valves()