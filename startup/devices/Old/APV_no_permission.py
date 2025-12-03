# for Aurora Pro 6-port selection valve
# should work with other models, just need to specify n_pos
# when used with Moxa, specify the url for the corresponding serial port, e.g. 'socket://10.66.122.154:4003/'

import sys
import logging
import serial
import struct
import time
import numpy as np


logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-5.5s]  %(message)s",
)

def findUsbPort(vid=None, pid=None, hwid=None):
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        print("found device", p.hwid)
        if vid==p.vid and pid==p.pid or hwid==p.hwid:
            logging.info("ERV found on %s", p)
            return p.device     
    logging.error("ERV not found") 
    raise RuntimeError(f"232 adaptor with VID:PID={vid:04X}:{pid:04X} not found")

class APV:
    pos_home = b'\xCC\x00\x45\x00\x00\xDD\xEE\x01' #move valve to home position
    req_valve = b'\xcc\x00\x3e\x00\x00\xDD\xE7\x01' #request valve status
    req_motor = b'\xCC\x00\x4A\x00\x00\xDD\xF3\x01' #request motor status
    
    def __init__(self, n_pos=6, url=None):
        self.n_pos = n_pos
        if url:
            self.ser = serial.serial_for_url(url)   # e.g. 'socket://10.66.122.154:4003/'
            self.port = url
        else:  
            self.port = findUsbPort(vid=0x1A86, pid=0x7523)   # USB
            #self.port = findUsbPort(hwid='ACPI\\PNP0501\\1')  # serial port
            self.ser = serial.Serial(port=self.port, baudrate = 9600, timeout=1)
            self.ser.open()
        self.ser.flushInput()
        self.ser.flushOutput()

    def valveStatus(self): 
        while not self.motorReady(): 
            time.sleep(1)
        self.ser.flushInput()
        self.ser.flushOutput()
        self.ser.write(self.req_valve)
        response = self.ser.read(8)
        logging.info(f'received {len(response)} bytes: {response}')
        b3 = struct.unpack('BBBBBBBb',response)[3:5]  #B3 byte indicates position
        pos = b3[0]
        if (pos==0): logging.info('Valve is in Home Position')
        elif (pos>= 1 and pos<=self.n_pos): logging.info(f'Valve is in Position {pos}')
        else:
            logging.error('%s is an unknown position', str(response))
            raise RuntimeError(str(response) + ' is an unknown position')
        return pos

    def motorReady(self):
        self.ser.write(self.req_motor)
        time.sleep(.1)
        response = self.ser.read(8)
        logging.info(f'received {len(response)} bytes: {response}')
        b2 = struct.unpack('BBBBBBBb',response)[2] #B2 == 00 means that the motor is ready
        if (b2 == 0x00):
            return True
        else: 
            logging.info('Waiting for motor')
            return False

    def reset(self):
        while not self.motorReady(): 
            time.sleep(1)
        self.ser.write(self.pos_home)
        self.ser.read(8)
        logging.info('Moving to home position')
    
    def movePosition(self, position):
        if position<1 or position>self.n_pos:
            raise Exception(f"invalid valve position: {position}")
        command = b'\xCC\x00\x44' + position.to_bytes(1, 'little') + b'\x00\xDD'
        checksum = int(np.sum([b for b in command])).to_bytes(2, 'little')
        command += checksum        
        self.ser.write(command)
        self.ser.read(8)        
        logging.info('Moving to position 1')
        pos = self.valveStatus()
        if not (position == pos): 
            logging.error('ERV movement failure')
            raise RuntimeError("ERV failed to move: {} != {}".format(position,pos))
