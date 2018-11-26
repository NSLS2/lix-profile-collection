import numpy as np
from collections import ChainMap
from ophyd import DeviceStatus
from ophyd import EpicsSignal, EpicsMotor, EpicsSignalRO, Device, Component 
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

class ScanningExperimentalModule2():
    """ the zero for Ry must be set correctly so that Rx is pointing in the x direction
        once homed, this position i1s at -6.0
    """
    x = EpicsMotor('XF:16IDC-ES:Scan2{Ax:sX}Mtr', name='ss2_x')
    x1 = EpicsMotor('XF:16IDC-ES:Scan2{Ax:X}Mtr', name='ss2_x1')
    y = EpicsMotor('XF:16IDC-ES:Scan2{Ax:sY}Mtr', name='ss2_y')
    z = EpicsMotor('XF:16IDC-ES:InAir{Mscp:1-Ax:F}Mtr', name='focus')
    # this is the Standa stepper stage
    rx = EpicsMotor('XF:16IDC-ES:Scan2{Ax:RX1}Mtr', name='ss2_rx')
    ry = EpicsMotor('XF:16IDC-ES:Scan2{Ax:RY}Mtr', name='ss2_ry')  
    
ss2 = ScanningExperimentalModule2()


class XPStraj(Device):
    def __init__(self, ip_addr, group, name, 
                 devices={'scan.rY': ss2.ry, 'scan.Y': ss2.y, 'scan.X': ss2.x}):
        """ ip_addr: IP of the XPS controller
            group: PVT positioner grouped defined in the controller
            name: 
            devices: the corresponding Ophyd device for the posiitoner group, useful in a scan
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
        
    def collect_asset_docs(self):
        """ adapted from HXN fly scan example
        """
        asset_docs_cache = []

        for det in self.detectors:
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

        for det in self.detectors:
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
        for det in self.detectors:
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
        self.xps.MultipleAxesPVTExecution (self.sID, self.group, traj_fn, 1)
        self.xps.GatheringStopAndSave(self.sID)
        self.xps.EventExtendedRemove(self.sID, eID)
        self.update_readback()

        if self._traj_status != None:
            self._traj_status._finished()
    
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
        self.read_back['fast_axis'] += self.readback_traj()
        # start_time is the beginning of the execution
        # pulse is generated when the positioner enters the segment ??
        # timestamp correspond to the middle of the segment
        N = self.traj_par['no_of_segments']
        Nr = self.traj_par['no_of_rampup_points']
        dt = self.traj_par['segment_duration']
        self.read_back['timestamp'] += list(self.start_time + (0.5 + Nr + np.arange(N+1))*dt)
        if self.traj_par['motor2'] is not None:
            self.read_back['slow_axis'] += [self.traj_par['motor2'].position]
            self.read_back['timestamp2'] += [time.time()]

            
xps_trj = XPStraj('10.16.2.100', 'scan', 'test')

def raster(detectors, exp_time, fast_axis, f_start, f_end, Nfast, 
           slow_axis=None, s_start=0, s_end=0, Nslow=1, md=None):
    """ raster scan in fly mode using detectors with exposure time of exp_time
        detectors must be a member of pilatus_detectors_ext
        fly on the fast_axis, step on the slow_axis, both specified as Ophyd motors
        the fast_axis must be one of member of xps_trj.motors, for now this is hard-coded
        the specified positions are relative to the current position
        for the fast_axis are the average positions during detector exposure 
        
        use it within the run engine: RE(raster(...))
    """
    if not set(detectors).issubset(pilatus_detectors_ext):
        raise Exception("only pilatus_detectors_ext can be used in this raster scan.")
    if fast_axis.name not in xps_trj.device_names:
        raise Exception("the fast_axis is not supported in this raster scan: ", fast_axis.name)
    fast_axis_name = list(xps_trj.devices.keys())[list(xps_trj.devices.values()).index(fast_axis)]
    # 
    step_size = (f_end-f_start)/(Nfast-1)
    dt = exp_time + 0.005    # exposure_period is 5ms longer than exposure_time, as defined in Pilatus
    xps_trj.define_traj(fast_axis_name, Nfast-1, step_size, dt, motor2=slow_axis)
    p0_fast = fast_axis.position
    ready_pos = {}
    ready_pos[True] = p0_fast+f_start-xps_trj.traj_par['rampup_distance']-step_size/2
    ready_pos[False] = p0_fast+f_end+xps_trj.traj_par['rampup_distance']+step_size/2
    xps_trj.clear_readback()
    
    if slow_axis is not None:
        p0_slow = slow_axis.position
        pos_s = p0_slow+np.linspace(s_start, s_end, Nslow)
    else:
        Nslow = 1
    
    if not set(detectors).issubset(pilatus_detectors_ext):
        raise Exception("only pilatus_detectors_ext can be used in this plan.")
    xps_trj.detectors = detectors
    
    pilatus_ct_time(exp_time)
    set_pil_num_images(Nfast*Nslow)
    print('setting up to collect %d exposures of %.2f sec ...' % (Nfast*Nslow, exp_time))
    
    motor_names = [slow_axis.name, fast_axis.name]
    #motors = [fast_axis, slow_axis]
    scan_shape = [Nslow, Nfast]
    _md = {'shape': tuple(scan_shape),
           'plan_args': {'detectors': list(map(repr, detectors))},
           'plan_name': 'raster',
           'plan_pattern': 'outer_product',
           'motors': tuple(motor_names),
           'hints': {},
           }
    _md.update(md or {})
    _md['hints'].setdefault('dimensions', [(('time',), 'primary')])
        
    @bpp.stage_decorator([xps_trj] + detectors)
    @bpp.run_decorator(md=_md)
    @fast_shutter_decorator()
    def inner(detectors, fast_axis, ready_pos, slow_axis, Nslow, pos_s):
        running_forward = True
        #for mo in monitors:
        #    yield from bps.monitor(mo)
        
        for i in range(Nslow):
            if slow_axis is not None:
                yield from mov(fast_axis, ready_pos[running_forward], slow_axis, pos_s[i])
            else:
                yield from mov(fast_axis, ready_pos[running_forward])

            xps_trj.select_forward_traj(running_forward)
            yield from bps.kickoff(xps_trj, wait=True)
            yield from bps.complete(xps_trj, wait=True)
            running_forward = not running_forward
        yield from bps.collect(xps_trj)

        #for mo in monitors:
        #    yield from bps.unmonitor(mo)

    yield from inner(detectors, fast_axis, ready_pos, slow_axis, Nslow, pos_s)
        
    if slow_axis is not None:
        yield from mov(fast_axis, p0_fast, slow_axis, p0_slow)
    else:
        yield from mov(fast_axis, p0_fast)

    
    