import socket
import numpy
from time import sleep

"""
This works with the FTC100D temperature controller from AccuThermo
The controller is connected to port 2 on the Moxa device shared with the pizeo controller (10.16.2.50)
port setting: 38400, 8N1
Communication is not MODBUS, not ascii 
The protocol is complicated

Send command to device: 
    address (1 byte)     function (1 byte)   data (several bytes) 

Device returns: ???
    address (1 byte)     function (1 byte)   data (several bytes)         
or when there is an error:
    address (1 byte)     function+0x80 (1 byte)   error code (1 byte)

function:
    03  read register
    04  read process value (current T)
    05  write register
    
"""

class tctrl_FTC100D:
    def __init__(self, sock_addr):
        self.delay = 0.05
        self.sock = socket.create_connection(sock_addr)
        
    def comm(self, data, n_ret):
        """ data: hex string (a list) to be sent 
            n_ret: number of bytes expected to read back
        """
        buf = np.asarray(data, dtype=np.uint8)
        self.sock.send(buf)
        sleep(self.delay)
        ret =  np.frombuffer(self.sock.recv(n_ret), np.uint8)
        return ret
        
    def set_delay(self, t):
        self.delay = t

    def getT(self, print_T=True):
        ret = self.comm([0x01,0x04,0x10,0x00,0x00,0x01], 5)
        #if ret[1]>0x80:
        #    raise Exception("error reading temperature: code %d" % ret[2])
        v = 0.1*(ret[-1]+256*ret[-2])
        if print_T:
            print("current tmeperature is %.1f C" % v)
        return v

    def get_enable_status(self):
        ret = self.comm([0x01,0x03,0x00,0x06,0x00,0x01], 5)
        if ret[-1]==0x20: # OFF
            print("temeprature control is disabled.")
        elif ret[-1]==0x21: # EnOn
            print("temperature control is enabled.")
        else:
            print("the returned value is 0x%2x" % ret[-1])

    def get_set_point(self, verbose=True):
        ret = self.comm([0x01,0x03,0x00,0x00,0x00,0x01], 5)
        v = 0.1*(ret[-1]+256*ret[-2])
        if verbose:
            print("current set point is %.1f C" % v)
        return v

    def setT(self, v):
        v = np.int(v*10+0.5)
        v1 = v/256
        v2 = v%256
        ret = self.comm([0x01,0x06,0x00,0x00,v1,v2], 6)
        if ret[1]>0x80:
            raise Exception("error setting temperatore, code %d" % ret[2]) 
        self.get_set_point()

    def enable(self, status):
        if status:  # enable, EnOn, 21
            v2 = 0x21
        else: # disabel, OFF, 20
            v2 = 0x20
        ret = self.comm([0x01,0x06,0x00,0x06,0x00,v2], 6)
        if ret[1]>0x80:
            raise Exception("error enableing/disabling, code %d" % ret[2]) 
        self.get_enable_status()
        

#tctrl = tctrl_FTC100D(("10.16.2.50", 7002))



