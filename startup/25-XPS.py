import numpy as np
from collections import ChainMap
from ophyd import DeviceStatus
from ophyd import EpicsSignal, EpicsMotor, EpicsSignalRO, Device, Component 
from ophyd.utils.epics_pvs import data_type, data_shape
import epics
import bluesky.preprocessors as bpp
import bluesky.plan_stubs as bps
from collections import OrderedDict
from threading import Thread

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
    x = EpicsMotor('XF:16IDC-ES:Scan2{Ax:X}Mtr', name='ss_x')
    y = EpicsMotor('XF:16IDC-ES:Scan2{Ax:Y}Mtr', name='ss_y')
    ry = EpicsMotor('XF:16IDC-ES:Scan2{Ax:RY}Mtr', name='ss_ry')  
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

class XPStraj(Device):
    def __init__(self, ip_addr, group, name, devices=None):
        """ ip_addr: IP of the XPS controller
            group: PVT positioner grouped defined in the controller
            name: 
            devices: the corresponding Ophyd device for the posiitoner group, useful in a scan
        """
        
        if devices is None:
            raise Exception("devices is None: the corelation between XPS and bs motor names must be defined.")
        
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
        
        self.devices = devices
        for m in devices.keys():
            if m not in self.motors:
                raise Exception('invalid motor: ', m)
            print(m, devices[m].name)
        self.device_names = [devices[k].name for k in devices.keys()]
        
        self.verified = False
        uname = getpass.getuser()
        self.traj_files = ["TrajScan_FW.trj-%s" % uname, "TrajScan_BK.trj-%s" % uname]
        self.traj_par = {'run_forward_traj': True, 
                         'no_of_segments': 0, 
                         'no_of_rampup_points': 0,
                         'segment_displacement': 0,
                         'segment_duration': 0,
                         'motor': None,
                         'rampup_distance': 0,
                         'motor2': None
                        }
        self.time_modified = time.time()
        self.start_time = 0
        self._traj_status = None
        self.detectors = None
        self.datum = None
        
    def stage(self):
        self.datum = {}
        self.aborted = False
    
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
        ret = [(k, {'value': val, 
                    'timestamp': self.time_modified}) for k, val in self.traj_par.items() if val is not None]
        return OrderedDict(ret)
        
    def describe_configuration(self):
        return {
          k: {"source": "trajectory_state", "dtype": data_type(val), "shape": data_shape(val)}
          for k, val
          in self.traj_par.items()
          if val is not None
        }
        
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
            according to run_engine.py: Tell a flyer, 'stop collecting, whenever you are ready'.
            Return a status object tied to 'done'.
        """
        if self._traj_status is None:
            raise RuntimeError("must call kickoff() before complete()")
        while not self._traj_status.done:
            print(f"{time.asctime()}: waiting for the trajectory to finish ...   ", end='')
            time.sleep(1)
        if self.aborted:
            raise Exception("unable to complete the scan due to hardware issues ...")
        print("Done.")
        
        return self._traj_status
        
    def collect_asset_docs(self):
        """ when the run eigine process the "collect" message, 3 functions are called (see bluesky.bundlers)
                collect_asset_docs(): returns resource and datum document (name, doc)
                                      RE emit(DocumentNames(name), doc)
                                      called once per scan? name is always "resource"?
                describe_collect(): returns a dictionary of {stream_name: data_keys, ...}
                                    RE emit(DocumentNames.descriptor, doc) 
                collect(): returns a list of events [ev, ...], 
                           RE emit(DocumentNames.event, ev) or add to bulk data for later emit() call
            DocumentNames is defined in event_model, enum

            followed HXN example
        """
        asset_docs_cache = []

        #for det in self.detectors:
        for det in pil.active_detectors:
            k = f'{det.name}_image'
            #det.dispatch(k, ttime.time())
            (name, resource), = det.file.collect_asset_docs()
            assert name == 'resource'
            asset_docs_cache.append(('resource', resource))
            resource_uid = resource['uid']
            datum_id = '{}/{}'.format(resource_uid, 0)
            self.datum[k] = [datum_id, ttime.time()]
            datum = {'resource': resource_uid,
                     'datum_id': datum_id,
                     'datum_kwargs': {'point_number': 0}}
            asset_docs_cache.append(('datum', datum))
            
        return tuple(asset_docs_cache)
            
        
    def collect(self):
        """
        save position data, called at the end of a scan (not at the end of a trajectory)
        this is now recorded in self.readback, as accumulated by self.update_readback()
        """
        now = time.time()
        data = {}
        ts = {}
        
        data[self.traj_par['fast_axis']] = self.read_back['fast_axis']
        ts[self.traj_par['fast_axis']] = self.read_back['timestamp']
        if self.traj_par['motor2'] is not None:
            data[self.traj_par['slow_axis']] = self.read_back['slow_axis']
            ts[self.traj_par['slow_axis']] = self.read_back['timestamp2']

        #for det in self.detectors:
        for det in pil.active_detectors:
            # first make sure that all data file are saved, otherwise next time when the detector is
            # staged, the files that are not yet saved will be lost
            Ni = det.cam.num_images.get() 
            #Nc1 = 0
            t0 = time.time()
            
            while det.cam.detector_state.get(as_string=True) is "Acquire":
                time.sleep(0.1)
            
            """
            while True:
                Nc = det.cam.array_counter.get()
                #if Ni==Nc or Nc==Nc1:
                if Ni==Nc or time.time()-t0>5:  
                    # either the final file count is reached, or waited for too long (5s) and no new files 
                    # show up, which can happen if one or more trajectories were cut short during the raster
                    break
                #Nc1 = Nc
                print('data files are still being written for %s, %d -> %d' % (det.name, Nc, Ni))
                #time.sleep(5)
                time.sleep(0.5)
            """
                
            k = f'{det.name}_image'
            (data[k], ts[k]) = self.datum[k]
            for k,desc in det.read().items():
                data[k] = desc['value']
                ts[k] = desc['timestamp']
                
        ret = {'time': time.time(),
               'data': data,
               'timestamps': ts,
              }
        
        yield ret

    def describe_collect(self):
        '''Describe details for the flyer collect() method'''
        ret = {}
        ret[self.traj_par['fast_axis']] = {'dtype': 'number',
                                           'shape': (1,),
                                           'source': 'PVT trajectory readback position'}
        if self.traj_par['motor2'] is not None:
            ret[self.traj_par['slow_axis']] = {'dtype': 'number',
                                               'shape': (1,),
                                               'source': 'motor position readback'}
        #for det in self.detectors:
        for det in pil.active_detectors:
            ret[f'{det.name}_image'] = det.make_data_key() 
            for k,desc in det.describe().items():
                ret[k] = desc
                
        return {'primary': ret}
        
    def define_traj(self, motor, N, dx, dt, motor2=None, dy=0, Nr=2):
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
        self.ramp_dist = disp[1:Nr+1].sum()
        
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
                         'rampup_distance': self.ramp_dist,
                         'motor2': motor2,
                         'motor2_disp': dy
                        }
        self.traj_par['fast_axis'] = xps_trj.devices[motor].name
        if motor2 is not None:
            self.traj_par['slow_axis'] = motor2.name
        self.time_modified = time.time()
        
    def exec_traj(self, forward=True, clean_event_queue=False, n_retry=5):
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
        
        # otherwise starting the trajectory might generate an error
        while self.moving():
            time.sleep(0.2)
        
        # first set up gathering
        self.xps.GatheringReset(self.sID)        
        # pulse is generated when the positioner enters the segment
        print("starting a trajectory with triggering parameters: %d, %d, %.3f ..." % (Nr+1, N+Nr+1, dt))
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
        
        for i in range(n_retry):
            # can this generate some triggers and then fail? if so this failure should kill the run
            # as there is no book keeping to know which images from the detectors are garbage
            # and the postions and image sequences will be off
            [err, ret] = self.xps.MultipleAxesPVTExecution(self.sID, self.group, traj_fn, 1)
            if err=='0': 
                break
            elif i==n_retry-1:
                self.safe_stop()
                print("motion group re-initialized ...")
                break
            print(f'An error (code {err}) as occured when starting trajectory execution, retry #{i+1} ...')
            #if err=='-22': # Group state must be READY                
            [err, ret] = self.xps.GroupMotionEnable(self.sID, self.group)
            print(f"attempted to re-enable motion group: ", end='')
            time.sleep(1)
        
        if not self.aborted:
            self.xps.GatheringStopAndSave(self.sID)
            self.xps.EventExtendedRemove(self.sID, eID)
            self.update_readback()
            print('end of trajectory execution, ', end='')

        if self._traj_status != None:
            self._traj_status._finished()

        # for testing only
        #if caget('XF:16IDC-ES:XPSAux1Bi0'):
        #    self.aborted = True
            
    def safe_stop(self):
        fast_shutter.close()
        
        # generate enough triggers to complete exposure 
        #det = self.detectors[0]
        det = pil.active_detectors[0]
        Ni = det.cam.num_images.get() 
        Nc = det.cam.array_counter.get()
        """for i in range(Ni-Nc):
            det.trigger()
            print('%d more data points to complete exposure ...   ' % (Ni-Nc-i), end='\r')
            time.sleep(self.traj_par['segment_duration'])     
        """
        st = self.xps.GroupStatusGet(self.sID, 'scan') 
        if st==['0', '1']: # group likely need initilization and homing
            self.xps.GroupInitialize(self.sID, 'scan')
            time.sleep(1)
            st = self.xps.GroupStatusGet(self.sID, 'scan')
            if st==['0', '42']: # ready for home search
                self.xps.GroupHomeSearch(self.sID, 'scan') 
                time.sleep(1)
                st = self.xps.GroupStatusGet(self.sID, 'scan')
                if st==['0', '11']: # home search successful 
                    print('stages re-initialized ... ')
        
        self.aborted = True
        print("giving up the current scan ...")
        #raise Exception('a hardware error has occured, aborting ... ')
    
    def readback_traj(self):
        print('reading back trajectory ...')
        err,ret = self.xps.GatheringCurrentNumberGet(self.sID)
        ndata = int(ret.split(',')[0])
        err,ret = self.xps.GatheringDataMultipleLinesGet(self.sID, 0, ndata)
        return [float(p) for p in ret.split('\n') if p!='']
    
    def clear_readback(self):
        self.read_back = {}
        self.read_back['fast_axis'] = []
        self.read_back['timestamp'] = []
        if self.traj_par['motor2'] is not None:
            self.read_back['slow_axis'] = []
            self.read_back['timestamp2'] = []
        
    def update_readback(self):
        self.read_back['fast_axis'] = self.readback_traj()
        # start_time is the beginning of the execution
        # pulse is generated when the positioner enters the segment ??
        # timestamp correspond to the middle of the segment
        N = self.traj_par['no_of_segments']
        Nr = self.traj_par['no_of_rampup_points']
        dt = self.traj_par['segment_duration']
        self.read_back['timestamp'] = list(self.start_time + (0.5 + Nr + np.arange(N+1))*dt)
        if self.traj_par['motor2'] is not None:
            self.read_back['slow_axis'] = self.traj_par['motor2'].position
            self.read_back['timestamp2'] = time.time()

            
    
