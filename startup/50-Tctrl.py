import socket
import numpy,enum
from time import sleep

class serial_port:
    debug = False
    
    def __init__(self, sock_addr):
        self.delay = 0.05
        self.sock = socket.create_connection(sock_addr)

    def comm(self, data, n_ret=32):
        """ data: hex string (a list) to be sent 
            n_ret: buffer size
        """
        buf = np.asarray(data, dtype=np.uint8)
        if self.debug:
            txt = ", ".join([f"0x{v:02x}" for v in buf])
            print(f"sending: {txt}")
        self.sock.send(buf)
        sleep(self.delay)
        ret =  np.frombuffer(self.sock.recv(n_ret), np.uint8)
        if self.debug:
            txt = ", ".join([f"0x{v:02x}" for v in ret])
            print(f"received: {txt}")
        return ret

    def set_delay(self, t):
        self.delay = t

class ctrl_code(enum.Enum):
    ENQ = 0x05
    STX = 0x02
    ETX = 0x03
    ACK = 0x06
    CR = 0x0D
    SOH = 0x01
    
class com_code(enum.Enum):
    setT = 0x31
    getTs = 0x31
    getT = 0x32
    getT_ext = 0x33
    get_alarm = 0x34
    #set_offset = 0x36 # not supported
        
class SMCchiller(serial_port):

    def __init__(self, sock_addr):
        super().__init__(sock_addr)
        
    def f2a(self, f, maxV=60, minV=0):
        """ convert float to a 4-byte array
            value must be between minV and maxV
        """
        if f>maxV or f<minV:
            raise Exception(f"data out of range: {f}")
        f = 0.1*f
        a = []
        for i in range(4):
            v = int(f)
            a.append(v+0x30)  # 0x30 is 0, 0x31 is 1, ...
            f -= v
            f *= 10

        return a

    def a2f(self, a):
        """ convert to float from a 4-byte array
        """
        if len(a)!=4:
            raise Exception(f"not a 4-byte array: {a}")
        a1 = np.asarray(a, dtype=np.int)-0x30
        s = f"{a1[0]}{a1[1]}.{a1[2]}{a1[3]}"
        return float(s)

    def make_msg(self, com, data=None, unit=None):
        """ data is the argument for the command, i.e. set point
         """
        cs = 0

        if data is None:
            prefix = ctrl_code.ENQ.value
        else:
            prefix = ctrl_code.STX.value

        if not isinstance(com, com_code):
            raise Exception(f"invalid command: {com}")
        if unit is not None: # only need when multiple devices are present
            # testing only, not checking the unit number here
            msg = [ctrl_code.SOH.value, unit+0x30, prefix, com.value]
        else:
            msg = [prefix, com.value]
        cs += np.sum(msg[1:])

        if data is not None:
            a = self.f2a(data)
            msg += a
            cs += np.sum(a)
            msg.append(ctrl_code.ETX.value)

        msg.append(int(cs/16)+0x30)
        msg.append(cs%16+0x30)
        msg.append(ctrl_code.CR.value)

        return msg

    def alarm_msg(self, msg):
        return f"{np.binary_repr(msg[0])[-4:]} {np.binary_repr(msg[1])[-4:]} {np.binary_repr(msg[2])[-4:]}"

    def read_data(self, msg, as_err=False):
        """ return message that contains data:
                starts with SOH it is contains unit information, two bytes 
                followed by STX and 4-byte data (temperature or error code)
            retrun message that simply acknowlwdges the command:
                ACK [unit] CR 
        """
        # unit can be ingored, since it should be specified in the query 
        if msg[0]==ctrl_code.ACK.value:
            return 
        if msg[0]==ctrl_code.SOH.value:
            msg = msg[2:]
        if as_err:
            return self.alarm_msg(msg[2:5])
        return self.a2f(msg[2:6])

    def setT(self, st):
        ret = self.comm(self.make_msg(com_code.setT, st))
        #return read_data(ret)

    def getT(self):
        ret = self.comm(self.make_msg(com_code.getT))
        return self.read_data(ret)

    def get_set_point(self):
        ret = self.comm(self.make_msg(com_code.getTs))
        return self.read_data(ret)
        
    def get_alarm(self):
        ret = self.comm(self.make_msg(com_code.get_alarm))
        return self.read_data(ret, as_err=True)
   
    
class tctrl_FTC100D(serial_port):
    """
    This works with the FTC100D temperature controller from AccuThermo
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
    def __init__(self, sock_addr):
        super().__init__(sock_addr)

    def getT(self, print_T=True):
        ret = self.comm([0x01,0x04,0x10,0x00,0x00,0x01])  #, 5)
        #if ret[1]>0x80:
        #    raise Exception("error reading temperature: code %d" % ret[2])
        v = 0.1*(ret[-1]+256*ret[-2])
        if print_T:
            print("current tmeperature is %.1f C" % v)
        return v

    def get_enable_status(self):
        ret = self.comm([0x01,0x03,0x00,0x06,0x00,0x01])  #, 5)
        if ret[-1]==0x20: # OFF
            print("temeprature control is disabled.")
        elif ret[-1]==0x21: # EnOn
            print("temperature control is enabled.")
            return True
        else:
            print("the returned value is 0x%2x" % ret[-1])
        return False
            
    def get_set_point(self, verbose=True):
        ret = self.comm([0x01,0x03,0x00,0x00,0x00,0x01]) #, 5)
        v = 0.1*(ret[-1]+256*ret[-2])
        if verbose:
            print("current set point is %.1f C" % v)
        return v

    def setT(self, v):
        v = np.int(v*10+0.5)
        v1 = v/256
        v2 = v%256
        ret = self.comm([0x01,0x06,0x00,0x00,v1,v2]) #, 6)
        if ret[1]>0x80:
            raise Exception("error setting temperatore, code %d" % ret[2]) 
        self.get_set_point()

    def enable(self, status):
        if status:  # enable, EnOn, 21
            v2 = 0x21
        else: # disabel, OFF, 20
            v2 = 0x20
        ret = self.comm([0x01,0x06,0x00,0x06,0x00,v2]) #, 6)
        if ret[1]>0x80:
            raise Exception("error enableing/disabling, code %d" % ret[2]) 
        self.get_enable_status()
        

#tctrl = tctrl_FTC100D(("xf16idc-tsvr-sena", 7002))
#smc = SMCchiller(("xf16idc-tsvr-sena", 7005))



