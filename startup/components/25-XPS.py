print(f"Loading {__file__}...")

import numpy as np
from collections import ChainMap
from ophyd import DeviceStatus
from ophyd import EpicsSignal, EpicsMotor, EpicsSignalRO, Device, Component 
from ophyd.positioner import PositionerBase
from ophyd.utils.epics_pvs import data_type, data_shape
from ophyd.status import wait as status_wait

import epics
import bluesky.preprocessors as bpp
import bluesky.plan_stubs as bps
from bluesky.plan_stubs import sleep as sleeplan
from collections import OrderedDict

import uuid
import time, getpass

from XPS_Q8_drivers3 import XPS
from ftplib import FTP

import threading

class PositioningStack():
    # coarse x, Misumi
    xc = EpicsMotor('XF:16IDC-ES:Scan{Ax:XC}Mtr', name='ss_xc')
    
    # Newport pusher
    z = EpicsMotor('XF:16IDC-ES:Scan{Ax:Z}Mtr', name='ss_z')

class PositioningStackNonMicroscope(PositioningStack):
    """ 
        NOTE: if USR50 is used as Ry, , the zero position must be set correctly so that Rx is 
        pointing in the x direction once homed, this position is at -6.0
    """
    # coarse y, Kohzu
    #yc = EpicsMotor('XF:16IDC-ES:Scan1{Ax:YC}Mtr', name='ss1_yc')
    # this is the Standa stepper stage
    #rx = EpicsMotor('XF:16IDC-ES:Scan1{Ax:RX}Mtr', name='ss1_rx')
    ry = EpicsMotor('XF:16IDC-ES:Scan1{Ax:RY}Mtr', name='ss1_ry')  
    
class PositioningStackMicroscope(PositioningStack):
    """ this is the stack assembled in Apr 2019
        
    """
    # Newport
    x = None #EpicsMotor('XF:16IDC-ES:Scan2{Ax:X}Mtr', name='ss_x')
    y = None #EpicsMotor('XF:16IDC-ES:Scan2{Ax:Y}Mtr', name='ss_y')
    ry = None #EpicsMotor('XF:16IDC-ES:Scan2{Ax:RY}Mtr', name='ss_ry')  
    # SmarAct stages
    sx = EpicsMotor('XF:16IDC-ES:Scan2-Gonio{Ax:sX}Mtr', name='ss_sx')
    sz = EpicsMotor('XF:16IDC-ES:Scan2-Gonio{Ax:sZ}Mtr', name='ss_sz')
    tx = EpicsMotor('XF:16IDC-ES:Scan2-Gonio{Ax:tX}Mtr', name='ss_tx')
    tz = EpicsMotor('XF:16IDC-ES:Scan2-Gonio{Ax:tZ}Mtr', name='ss_tz')
    try: # may not always be installed
        rx = EpicsMotor('XF:16IDC-ES:Scan2-Gonio{Ax:RX}Mtr', name='ss_rx')
    except:
        rx = None
        print("ss.rx not available")

class XPSController():
    def __init__(self, ip_addr, name):
        self.xps = XPS()
        self.name = name
        self.ip_addr = ip_addr
        self.sID = self.xps.TCP_ConnectToServer(ip_addr, 5001, 0.050)
        # 20 ms timeout is suggested for single-socket communication, per programming manual
        self.groups = {}
        self.traj = None
        self.motors = {}
        self.update()
        self.lock = threading.Lock()
        self.ts = time.time()
        self.status = {}
        self.positions = {}
        self.check_status_interval = 0.05

    def synch_clock(self):
        """ time format follows HardwareDateAndTimeSet("Fri Sep 8 14:43:00 2023")
            time.asctime() output: 'Fri Sep  8 14:48:43 2023'
        """
        err,ret = self.xps.HardwareDateAndTimeSet(self.sID, grp,len(self.groups[grp]))
        if ret>0:
            raise Exception("unable to synch clock on XPS: ", err)
        
    def update(self):
        self.groups = {}
        objs = self.xps.ObjectsListGet(self.sID)[1].split(';;')[0].split(';')
        for obj in objs:
            tl = obj.split('.')
            if len(tl)==1: # this is a group
                err,ret = self.xps.GroupStatusGet(self.sID, tl[0])
                if ret=='11': # ready from homing
                    nmot = sum([1 if f'{tl[0]}.' in obj else 0 for obj in objs])
                    err,ret = self.xps.GroupMoveRelative(self.sID, tl[0], np.zeros(nmot))
                    time.sleep(0.5)
                    err,ret = self.xps.GroupStatusGet(self.sID, tl[0])       
                if ret!='12':
                    print(f"group {tl[0]} is not ready for use, err,status = {err,ret}")
                else:
                    self.groups[tl[0]] = []
            elif tl[0] not in self.groups.keys():
                continue
                #print(f"skipping {obj}: group {tl[0]} is inactive or defined")
            else:
                self.groups[tl[0]].append(obj)
                self.motors[obj] = {}
                self.motors[obj]['group'] = tl[0] 
                self.motors[obj]['index'] = self.groups[tl[0]].index(obj)  
    
    def get_motor_status(self, mot):
        grp = self.motors[mot]['group']
        ts = time.time()
        if ts-self.ts>self.check_status_interval or mot not in self.status.keys():
            self.get_group_status(grp)
        self.ts = ts
        return self.status[mot]
                
    def get_group_status(self, grp):
        self.lock.acquire()
        err,ret = self.xps.GroupMotionStatusGet(self.sID, grp,len(self.groups[grp]))
        if err!='0' or len(ret)==0:
            print(f"trouble getting group status for {grp}...: ", err,ret)
        self.lock.release()
        status = ret.split(',')
        for mot in self.groups[grp]:
            self.status[mot] = (err,status[self.motors[mot]['index']])
        return err,ret
        
    def get_motor_position(self, mot):
        grp = self.motors[mot]['group']
        ts = time.time()
        if ts-self.ts>self.check_status_interval or mot not in self.positions.keys():
            self.get_group_position(grp)
        self.ts = ts
        return self.positions[mot]

    def get_group_position(self, grp):
        self.lock.acquire()
        err,ret = self.xps.GroupPositionCurrentGet(self.sID, grp,len(self.groups[grp]))
        if err!='0' or len(ret)==0:
            print(f"trouble getting group position for {grp} ...: ", err,ret)
        self.lock.release()
        pos = ret.split(',')
        for mot in self.groups[grp]:
            self.positions[mot] = (err,pos[self.motors[mot]['index']])
        return err,ret
        
    def def_motor(self, motorName, OphydName, egu="mm", direction=1): 
        if not motorName in self.motors.keys():
            raise Exception(f"{motorName} is not a valid motor.")
        mot = XPSmotor(self, motorName, OphydName, egu, direction=direction)
        self.motors[motorName]["ophyd"] = mot
        return mot
    
    #def reboot(self):
    #    pass
        
        
class XPSmotor(PositionerBase):
    debug = False
    
    def __init__(self, controller, motorName, OphydName, egu, direction=1, settle_time=0):
        self.controller = controller
        self.motorName = motorName
        super().__init__(name=OphydName)
        self.source = f"{controller.name}-{motorName}"
        self._egu = egu
        self._settle_time = settle_time
        self._status = None
        self._dir = direction
        self._position = None
        self.setpoint = None
        self.user_offset_dir = Signal(parent=self, name="motor dir", value=direction)
        
    def wait_for_stop(self, poll_time=0.1):
        if self.debug:
            print(f"{self.name}: waiting for stop ...")
        while self.moving:
            pos = self.position
            time.sleep(poll_time)
        time.sleep(self.settle_time)
        #pos = self.position
        self._done_moving(success=True, timestamp=time.time())
    
    def move(self, position, wait=True, **kwargs): #moved_cb=None, timeout=None, 
        if self.debug:
            print(f"{self.name}: moving to {position} ...")
        self._started_moving = False
        self.set_point = position*self._dir
        self._status = super().move(self.set_point, **kwargs)
        self._run_subs(sub_type=PositionerBase.SUB_START)
        
        err,ret = self.controller.xps.GroupMoveAbsolute(self.controller.sID, self.motorName, [self.set_point])
        threading.Thread(target=self.wait_for_stop).start() 
        
        try:
            if wait:
                status_wait(self._status)
        except KeyboardInterrupt:
            self.stop()
            raise

        return self._status
        
    @property
    def position(self):
        if self.debug:
            print(f"{self.name}: checking position ...")

        err,ret = self.controller.get_motor_position(self.motorName)
        if int(err):
            print(f"issue getting position from {self.motorName}, err = {err}")
            print(self.controller.xps.errorcodes[err])
        else:
            try:  # ret may not contain the correct info 
                self._position = float(ret)
            except:
                print("error geting position from '{ret}'")
                pass 

        if self.debug:
            print(f"done, returning {self._position*self._dir}")

        return self._position*self._dir
        
    @property
    def moving(self):
        if self.debug:
            print(f"{self.name}: checking move status ...")

        err,ret = self.controller.get_motor_status(self.motorName)
        if int(err):
            print(f"issue getting status from {self.motorName}, err = {err}")
            print(self.controller.xps.errorcodes[err])
            return True
        
        try:  # ret may not contain the correct info 
            self._moving = bool(int(ret))
        except:
            print("error geting status from '{ret}'")
            pass 
        
        if self.debug:
            print(f"done, returning {self._moving}")

        return self._moving
    
    @property
    def egu(self):
        return self._egu

    def get_velocity(self):
        err,ret = self.controller.xps.PositionerSGammaParametersGet(self.controller.sID, self.motorName)
        return float(ret.split(',')[0])    

    def set_velocity(self, v0):
        err,ret = self.controller.xps.PositionerSGammaParametersGet(self.controller.sID, self.motorName)
        pars = ret.split(',')
        pars[0] = v0
        err,ret = self.controller.xps.PositionerSGammaParametersSet(self.controller.sID, self.motorName, *pars)
    
    def stop(self, *, success: bool = False):
        if self.debug:
            print(f"{self.name}: stop requested ...")

        err,ret = self.controller.xps.GroupMoveAbort(self.controller.sID, motorName)
        self._done_moving()
        
    def read(self):
        d = OrderedDict()
        d[self.name] = {'value': self.position,
                        'timestamp': time.time()}
        return d
        
    def describe(self):
        desc = OrderedDict()
        desc[self.name] = {'source': str(self.source),
                           'dtype': data_type(self.position),
                           'shape': data_shape(self.position),
                           'units': self.egu,
                           'lower_ctrl_limit': self.low_limit,
                           'upper_ctrl_limit': self.high_limit,
                           }
        return desc

    def read_configuration(self):
        return OrderedDict()

    def describe_configuration(self):
        return OrderedDict()    
    
            
xps = XPSController("xf16idc-mc-xps-rl4.nsls2.bnl.local", "XPS-RL4")
    
