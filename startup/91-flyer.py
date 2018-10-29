import numpy as np
from collections import ChainMap
from ophyd import DeviceStatus
from ophyd import EpicsSignal, EpicsSignalRO, Device, Component 
import epics
from bluesky.preprocessors import (monitor_during_decorator, run_decorator,
                                   stage_decorator, subs_decorator)
from bluesky.plan_stubs import (complete, kickoff, collect, monitor, unmonitor,
                                trigger_and_read)
from bluesky.callbacks import LivePlot
from collections import OrderedDict
from threading import Thread

import uuid
import time, getpass

from XPS_Q8_drivers3 import XPS
from ftplib import FTP

import threading

## make sure PVs and BlueSky names are consistent for XPS motors

class XPStraj(Device):
    def __init__(self, ip_addr, group, name, BSdevice=None):
        """ ip_addr: IP of the XPS controller
            group: PVT positioner grouped defined in the controller
            name: 
            BSdevice: the corresponding BlueSky device for the posiitoner group, useful in a scan
        """
        super().__init__(name=name)
        self.xps = XPS()
        self.ip_addr = ip_addr
        self.sID = self.xps.TCP_ConnectToServer(ip_addr, 5001, 0.050)
        # 20 ms timeout is suggested for single-socket communication, per programming manual
        
        objs = self.xps.ObjectsListGet(self.sID)[1].split(';;')[0].split(';')
        if group not in objs:
            print("group %s does not exist." % group)
            print("valid objects are", objs)
            raise Exception
        self.group = group
        self.motors = [mot for mot in objs if (group+'.') in mot] 
        self.Nmot = len(self.motors) 
        self.verified = False
        uname = getpass.getuser()
        self.traj_files = ["TrajScan_FW.trj-%s" % uname, "TrajScan_BK.trj-%s" % uname]
        self.traj_par = {'run_forward_traj': True, 
                         'no_of_segments': 0, 
                         'no_of_rampup_points': 0,
                         'segment_displacement': 0,
                         'segment_duration': 0,
                         'motor': None,
                         'rampup_distance': 0
                        }
        self.time_modified = time.time()
        self.start_time = 0
        self._traj_status = None
        
    def stage(self):
        pass
    
    def unstage(self):
        """ abort whatever is still going on??
        """
        self.abort_traj()
        self._traj_status = None
        
    def pulse(self, duration=0.00001):
        # GPIO3.DO, pin 4
        mask = '1'   # it seems that only DO1 works
        self.xps.GPIODigitalSet(self.sID, "GPIO3.DO", mask, 1)
        #time.sleep(duration)
        self.xps.GPIODigitalSet(self.sID, "GPIO3.DO", mask, 0)
        
    def read_configuration(self):
        ret = [(k, {'value': self.traj_par[k], 
                    'timestamp': self.time_modified}) for k in self.traj_par.keys()]
        return OrderedDict(ret)
        
    def describe_configuration(self):
        pass
        
    def select_forward_traj(self, op=True):
        if op:
            self.traj_par['run_forward_traj'] = True
        else:
            self.traj_par['run_forward_traj'] = False
        
    def moving(self):
        err,msg = self.xps.GroupMotionStatusGet(self.sID, self.group, self.Nmot)
        if (np.asarray(msg.split(','))=='0').all():
            return False
        return True
    
    def abort_traj(self):
        if self.moving():
            err,msg = self.xps.GroupMoveAbort(self.sID, self.group)
            return err,msg
        return
        
    def kickoff(self):
        """
        run the trajectory
        """
        if self.verified==False:
            raise Exception("trajectory not defined/verified.")
        
        #self._traj_status = DeviceStatus(self.ExecuteState)
        self._traj_status = DeviceStatus(self)
      
        ##self.exec_traj(self.traj_par['run_forward_traj'])  # should not block
        th = threading.Thread(target=self.exec_traj, args=(self.traj_par['run_forward_traj'], ) )
        th.start() 
        # always done, the scan should never even try to wait for this
        #status = DeviceStatus(self)
        #status._finished()
        return self._traj_status
        
    def complete(self):
        """
        Return a status object tied to 'done'.
        """
        #if self._traj_status is None:
        #    raise RuntimeError("must call kickoff() before complete()")
        self._traj_status.done = not self.moving()
        
        return self._traj_status
        
    def collect(self):
        """
        save position data
        """
        # if self.ExecuteState.get(as_string=True) != 'Done':
        #     raise RuntimeError('Trajectory execution still in progress. Call complete() first.')

        rd = self.readback_traj()  # positions of the motor when the triggers were generated 
        print(f'rd: {rd}')
        now = time.time()
        for i, r in enumerate(rd):
            yield {'time': time.time(),
                   'data': {'position': r},
                   'timestamps': {'position': time.time()},
                   'seq_num': i+1,
                  }

    def describe_collect(self):
        '''Describe details for the flyer collect() method'''
        return {self.name: {'position': {'dtype': 'number',
                                         'shape': (1,),
                                         'source': 'PVT trajectory readback position'}}}
        
    def define_traj(self, motor, N, dx, dt, Nr=2):
        """ the idea is to use FW/BK trjectories in a scan
            each trajactory involves a single motor only
            relative motion, N segements of length dx from the current position
            duration of each segment is dt
            
            Additional segments (Nr, at least 2) are required to ramp up and down, e.g.:
            
            # dt,  x,  v_out
            1.0,  0.16667, 0.5
            1.0,  1.0,     1.0
            ... ...
            1.0,  1.0,     1.0
            1.0,  0.83333, 0.5
            1.0,  0,0,     0.0
            detector triggering should start from the 5th segment
            
        """        
        self.verified = False

        if motor not in self.motors:
            print("motor %s not in the list of motors: "%motor, self.motors)
            raise Exception
        err,ret = self.xps.PositionerMaximumVelocityAndAccelerationGet(self.sID, motor)
        mvel,macc = np.asarray(ret.split(','), dtype=np.float)
        midx = self.motors.index(motor)
        
        jj = np.zeros(Nr+N+Nr)
        jj[0] = 1; jj[Nr-1] = -1
        jj[-1] = 1; jj[-Nr] = -1
        # these include the starting state of acc=vel=disp=0
        disp = np.zeros(Nr+N+Nr+1)
        vel = np.zeros(Nr+N+Nr+1)
        acc = np.zeros(Nr+N+Nr+1)

        for i in range(N+2*Nr):
            acc[i+1] = acc[i] + jj[i]*dt
            vel[i+1] = vel[i] + acc[i]*dt + jj[i]*dt*dt/2
            disp[i+1] = vel[i]*dt + acc[i]*dt*dt/2 + jj[i]*dt*dt*dt/6
        vel = vel/vel.max()*dx/dt
        disp = disp/disp.max()*dx
        self.ramp_disp = disp[1:Nr+1].sum()
        
        # rows in a PVT trajectory file correspond ot the segments  
        # for each row/segment, the elements are
        #     time, axis 1 displancement, axis 1 velocity out, axsi 2 ... 
        ot1 = np.zeros((Nr+N+Nr, 1+2*self.Nmot))
        ot1[:, 0] = dt
        ot1[:, 2*midx+1] = disp[1:] 
        ot1[:, 2*midx+2] = vel[1:] 
        ot2 = np.zeros((Nr+N+Nr, 1+2*self.Nmot))
        ot2[:, 0] = dt
        ot2[:, 2*midx+1] = -disp[1:] 
        ot2[:, 2*midx+2] = -vel[1:] 
        
        np.savetxt("/tmp/"+self.traj_files[0], ot1, fmt='%f', delimiter=', ')
        np.savetxt("/tmp/"+self.traj_files[1], ot2, fmt='%f', delimiter=', ')
        ftp = FTP(self.ip_addr)
        ftp.connect()
        ftp.login("Administrator", "Administrator")
        ftp.cwd("Public/Trajectories")
        for fn in self.traj_files:
            file = open("/tmp/"+fn, "rb")
            ftp.storbinary('STOR %s' % fn, file)
            file.close()
        ftp.quit()
        
        for fn in self.traj_files:
            err,ret = self.xps.MultipleAxesPVTVerification(self.sID, self.group, fn)
            if err!='0':
                print(ret)
                raise Exception("trajectory verification failed.")
            err,ret = self.xps.MultipleAxesPVTVerificationResultGet (self.sID, motor)
        self.verified = True
        self.traj_par = {'run_forward_traj': True, 
                         'no_of_segments': N, 
                         'no_of_rampup_points': Nr,
                         'segment_displacement': dx,
                         'segment_duration': dt,
                         'motor': motor,
                         'rampup_distance': self.ramp_disp
                        }
        self.time_modified = time.time()
        
    def exec_traj(self, forward=True, clean_event_queue=False):
        """
           execuate either the foward or backward trajectory
        """
        if self.verified==False:
            raise Exception("trajectory not defined/verified.")

        N = self.traj_par['no_of_segments']
        Nr = self.traj_par['no_of_rampup_points']
        motor = self.traj_par['motor']
        dt = self.traj_par['segment_duration']
        
        if forward: 
            traj_fn = self.traj_files[0]
        else:
            traj_fn = self.traj_files[1]
        
        # first set up gathering
        self.xps.GatheringReset(self.sID)        
        # pulse is generated when the positioner enters the segment
        self.xps.MultipleAxesPVTPulseOutputSet (self.sID, self.group, Nr+1, N+Nr+1, dt)
        self.xps.MultipleAxesPVTVerification(self.sID, self.group, traj_fn)
        self.xps.GatheringConfigurationSet(self.sID, [motor+".CurrentPosition"])
        self.xps.sendAndReceive(self.sID, 
                                'EventExtendedConfigurationTriggerSet('+
                                'Always,0,0,0,0,%s.PVT.TrajectoryPulse,0,0,0,0)'%self.group )
        self.xps.sendAndReceive(self.sID, 
                                'EventExtendedConfigurationActionSet('+
                                'GatheringOneData,0,0,0,0)')
        # all trigger event for gathering should be removed
        if clean_event_queue:
            err,ret = self.xps.EventExtendedAllGet(self.sID)
            if err=='0':
                for ev in ret.split(';'):
                    self.xps.EventExtendedRemove(self.sID, ev) 
        eID = self.xps.EventExtendedStart(self.sID)[1]
        self.start_time = time.time()
        self.xps.MultipleAxesPVTExecution (self.sID, self.group, traj_fn, 1)
        self.xps.GatheringStopAndSave(self.sID)
        self.xps.EventExtendedRemove(self.sID, eID)
        if self._traj_status != None:
            self._traj_status._finished()
    
    def readback_traj(self):
        err,ret = self.xps.GatheringCurrentNumberGet(self.sID)
        ndata = int(ret.split(',')[0])
        err,ret = self.xps.GatheringDataMultipleLinesGet(self.sID, 0, ndata)
        return [float(p) for p in ret.split('\n') if p!='']

def flyRasterXPS(stepMotor, sStart, sEnd, nStep, 
                 flyMotor, fStart, fEnd, nSeg):
    """ collect data on Pilatus detectors
        monitor on em1,em2
    """
    
    
