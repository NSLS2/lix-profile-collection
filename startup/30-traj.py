print(f"Loading {__file__}...")

class trajControl(Device):
    def __init__(self, *args, **kwargs):
        
        super().__init__(*args, **kwargs)
        
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
        self.flying_motor = None
        
        
    def stage(self):
        self.aborted = False
        self.clear_readback()

    def unstage(self):
        """ abort whatever is still going on??
        """
        #self.abort_traj()
        while self.moving():
            time.sleep(0.2)
        self._traj_status = None
        
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
    
    def setup_traj(self, fast_axis, f_start, f_end, Nfast, step_size, dt, slow_axis=None, Nslow=1):
        """ Nfast triggers, Nfast-1 segments 
            f_start and f_end are absolute positions
        """
        self.define_traj(fast_axis, Nfast-1, step_size, dt)
        
        if isinstance(fast_axis, EpicsMotor):  # trajectory is based on user/Ophyd position
            motor_pos_sign = 1   
            p0_fast = fast_axis.position
        elif isinstance(fast_axis, XPSmotor): # trajectory is based on dial/controller position
            motor_pos_sign = (-1 if fast_axis.user_offset_dir.get() else 1)
            p0_fast = fast_axis.position
        else:
            raise Exception("unkown motor type: ", fast_axis)
            
        # forward/back trajectory = fast axis motor postion increasing/decreasing
        # rampup_distance and step_size are both positive
        # ready positions are dial positions
        # To-do: verify that this also works for EPICS motors (originally coded for XPS motors) 
        ready_pos_FW = np.min(np.array([f_start, f_end])*motor_pos_sign)-(self.traj_par['rampup_distance']+step_size/2)
        ready_pos_BK = np.max(np.array([f_start, f_end])*motor_pos_sign)+(self.traj_par['rampup_distance']+step_size/2)
        if isinstance(fast_axis, EpicsMotor):  # trajectory is based on user/Ophyd position
            motor_pos_sign = 1   
        
        #self.traj_par['ready_pos'] = [p0_fast+ready_pos_FW, p0_fast+ready_pos_BK]
        self.traj_par['ready_pos'] = [ready_pos_FW, ready_pos_BK]
        self.traj_par['Nem2'] = Nfast*Nslow
        self.traj_par['Nfast'] = Nfast
        self.traj_par['run_forward_first'] = ((motor_pos_sign>0 and f_start<f_end) or (motor_pos_sign<0 and f_start>f_end))
        self.traj_par['fast_axis'] = fast_axis.name
        self.slow_axis = slow_axis
        if slow_axis is not None:
            self.traj_par['slow_axis'] = slow_axis.name  
        else:
            self.traj_par['slow_axis'] = None
        
    def select_forward_traj(self, op=True):
        if op:
            self.traj_par['run_forward_traj'] = True
        else:
            self.traj_par['run_forward_traj'] = False
        
    def moving(self):
        if self.flying_motor is None:
            return False
        return self.flying_motor.moving
    
    def abort_traj(self):
        if self.flying_motor is not None:
            self.flying_motor.stop()
        return
        
    def kickoff(self):
        """
        run the trajectory
        """
        print("kicking off traj ...")
        if self.verified==False:
            raise Exception("trajectory not defined/verified.")
        
        self._traj_status = DeviceStatus(self)
      
        th = threading.Thread(target=self.exec_traj, args=(self.traj_par['run_forward_traj'], ) )
        th.start() 
        
        print("traj kicked off ...")
        return self._traj_status
        
    def complete(self):
        """
            according to run_engine.py: Tell a flyer, 'stop collecting, whenever you are ready'.
            Return a status object tied to 'done'.
        """
        print("completing traj ...")
        if self._traj_status is None:
            raise RuntimeError("must call kickoff() before complete()")
        while not self._traj_status.done:
            print(f"{time.asctime()}: waiting for the trajectory to finish ...   \r", end='')
            time.sleep(1)
        if self.aborted:
            raise Exception("unable to complete the scan due to hardware issues ...")
        print("traj completed ...")
             
        return self._traj_status
        
    def collect(self):
        """
        this is the "event"???
        save position data, called at the end of a scan (not at the end of a trajectory)
        this is now recorded in self.readback, as accumulated by self.update_readback()
        also include the detector image info
        """
        print("in traj collect ...")
        now = time.time()
        data = {}
        ts = {}

        data[self.traj_par['fast_axis']] = self.read_back['fast_axis']
        ts[self.traj_par['fast_axis']] = self.read_back['timestamp']  # timestamps
        if self.slow_axis is not None:
            data[self.traj_par['slow_axis']] = self.read_back['slow_axis']
            ts[self.traj_par['slow_axis']] = self.read_back['timestamp2']
                
        ret = {'time': time.time(),
               'data': data,
               'timestamps': ts,
              }
        print("done collecting traj")
        yield ret

    def describe_collect(self):
        '''Describe details for the flyer collect() method'''
        print("in traj describe_collect ...")
        ret = {}
        ret[self.traj_par['fast_axis']] = {'dtype': 'number',
                                           'shape': (len(self.read_back['fast_axis']),),
                                           'source': 'PVT trajectory readback position'}
        if self.slow_axis is not None:
            ret[self.traj_par['slow_axis']] = {'dtype': 'number',
                                               'shape': (len(self.read_back['slow_axis']),),
                                               'source': 'motor position readback'}
                
        return {self.name: ret}
    
    def define_traj(self, motor, N, dx, dt, Nr=2):
        raise Exception("this function is not implemented.")

    def exec_traj(self, forward=True, **kwargs):
        raise Exception("this function is not implemented.")

    def readback_traj(self):
        raise Exception("this function is not implemented.")

    def clear_readback(self):
        self.read_back = {}
        self.read_back['fast_axis'] = []
        self.read_back['timestamp'] = []
        if self.slow_axis is not None:
            self.read_back['slow_axis'] = []
            self.read_back['timestamp2'] = []
        
    def update_readback(self):
        pos = self.readback_traj()
        # start_time is the beginning of the execution
        # pulse is generated when the positioner enters the segment ??
        # timestamp correspond to the middle of the segment
        N = self.traj_par['no_of_segments']
        Nr = self.traj_par['no_of_rampup_points']
        dt = self.traj_par['segment_duration']
        ts = self.start_time + (0.5 + Nr + np.arange(N+1))*dt
        if len(pos)!=N+1:
            print(f"Warning: incorrect readback length {len(pos)}, expecting {N+1}")
            print(pos)
        self.read_back['fast_axis'] += list(pos)
        self.read_back['timestamp'] += list(ts)

        if self.slow_axis is not None:
            self.read_back['slow_axis'].append(self.slow_axis.position)
            self.read_back['timestamp2'].append(time.time())

        print("traj data updated ..")


class XPStraj(trajControl):
    def __init__(self, controller, group):
        """ controller is a XPS controller instance
            fast_axis is a XPS motor name, e.g. scan.X
        """        
        assert isinstance(controller, XPSController)
        if not group in controller.groups.keys():
            raise Exception(f"{fast_axis} is not a valid motor")
        # also need to make sure that the group is a MultiAxis type
            
        super().__init__(name=controller.name+"_traj")
        self.controller = controller
        self.group = group
        self.motors = {}
        for m in controller.groups[group]:
            if "ophyd" in controller.motors[m].keys():
                omotor = controller.motors[m]['ophyd']
                self.motors[omotor.name] = m
                omotor.traj = self
        self.Nmot = len(self.motors.keys())
        self.xps = controller.xps
        self.sID = controller.sID
        
        self.verified = False
        uname = getpass.getuser()
        self.traj_files = ["TrajScan_FW.trj-%s" % uname, "TrajScan_BK.trj-%s" % uname]
    
        
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

        if motor.name not in self.motors.keys():
            # motor is an Ophyd device 
            print(f"{motor.name} not in the list of motors: ", self.motors)
            raise Exception
        self.flying_motor = self.controller.motors[self.motors[motor.name]]['ophyd']
        
        err,ret = self.xps.PositionerMaximumVelocityAndAccelerationGet(self.sID, self.motors[motor.name])
        mvel,macc = np.asarray(ret.split(','), dtype=float)
        midx = self.controller.motors[self.motors[motor.name]]['index']
        
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
        ftp = FTP(self.controller.ip_addr)
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
            err,ret = self.xps.MultipleAxesPVTVerificationResultGet (self.sID, self.motors[motor.name])
        self.verified = True
        self.traj_par = {'run_forward_traj': True, 
                         'no_of_segments': N, 
                         'no_of_rampup_points': Nr,
                         'segment_displacement': dx,
                         'segment_duration': dt,
                         'motor': self.motors[motor.name],
                         'rampup_distance': self.ramp_dist,
                        }

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
        
        print("moving into starting position ...")
        pos = (self.traj_par['ready_pos'][0] if forward else self.traj_par['ready_pos'][1])
        err,ret = self.xps.GroupMoveAbsolute(self.sID, self.traj_par['motor'], [pos])
            
        # otherwise starting the trajectory might generate an error
        while self.moving():
            time.sleep(0.2)
        
        print("executing trajectory ...")
        # first set up gathering
        self.xps.GatheringReset(self.sID)        
        # pulse is generated when the positioner enters the segment
        print("starting a trajectory with triggering parameters: %d, %d, %.3f ..." % (Nr+1, N+Nr+1, dt))
        self.xps.MultipleAxesPVTPulseOutputSet(self.sID, self.group, Nr+1, N+Nr+1, dt)
        self.xps.MultipleAxesPVTVerification(self.sID, self.group, traj_fn)
        self.xps.GatheringConfigurationSet(self.sID, [motor+".CurrentPosition"])        
        self.xps.EventExtendedConfigurationTriggerSet(self.sID,
                                                      ["Always", f"{self.group}.PVT.TrajectoryPulse"],
                                                      ["0", "0"], ["0", "0"], ["0", "0"], ["0", "0"])
        self.xps.EventExtendedConfigurationActionSet(self.sID,
                                                     ["GatheringOneData"], ["0"], ["0"], ["0"], ["0"])
                
        # all trigger event for gathering should be removed
        if clean_event_queue:
            err,ret = self.xps.EventExtendedAllGet(self.sID)
            if err=='0':
                for ev in ret.split(';'):
                    self.xps.EventExtendedRemove(self.sID, ev) 
        eID = self.xps.EventExtendedStart(self.sID)[1]
        self.start_time = time.time()
        
        [err, ret] = self.xps.MultipleAxesPVTExecution(self.sID, self.group, traj_fn, 1)
        if err!='0':
            self.safe_stop()
            print("motion group re-initialized ...")
            #    break
            print(f'An error (code {err}) as occured when starting trajectory execution') #, retry #{i+1} ...')
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
            
    def readback_traj(self):
        print('reading back trajectory ...')
        err,ret = self.xps.GatheringCurrentNumberGet(self.sID)
        ndata = int(ret.split(',')[0])
        err,ret = self.xps.GatheringDataMultipleLinesGet(self.sID, 0, ndata)
        
        return [float(p) for p in ret.split('\n') if p!='']
    

class ZEBRAtraj(trajControl):
    def __init__(self, controller, motors, **kwargs):
        """ controller should be a valid Zebra device
            motors should be a list of Ophyd motors, consistent with the Zebra IOC definition
        """
        
        assert isinstance(controller, Zebra)
        super().__init__(name=controller.name+"_traj", **kwargs)
        self.controller = controller

        # need to revise Zebra IOC to get PV names for connected motors
        # self.motors provides the encoder number based on the PV name of the motor
        self.motors = {}
        motor_pvs = {}
        for m in motors:
            assert isinstance(m, EpicsMotor)
            motor_pvs[m.prefix] = m 
        
        for i in [1,2,3,4]:
            sig = controller.pc.__dict__['_signals'][f'enc_mot{i}_prefix']
            if sig.connected:
                prefix = sig.get()
                if prefix in motor_pvs.keys():
                    self.motors[prefix] = i
                    motor_pvs[prefix].traj = self
            
        self.verified = False
        
    def define_traj(self, motor, N, dx, dt):
        """ N+1 triggers, ramping-up + N segments + ramping-down  
        """
        self.verified = False

        if motor.traj.controller!=self.controller:
            # motor is an Ophyd device 
            print(f"{motor.name} not under the control of ", self.controller.name)
            raise Exception
        self.flying_motor = motor
        
        mn = self.motors[motor.prefix]
        # signals/PVs (all under self.controller.pc) to be set when defining the trajectory
        # these sometimes take strange values
        self.controller.pc.__dict__["_signals"][f'enc_off{mn}'].set(0).wait()
        mres = self.controller.pc.__dict__["_signals"][f'enc_res{mn}']
        mres.set(np.fabs(mres.get())).wait()
        self.controller.pc.__dict__["_signals"][f'enc_pos{mn}_sync'].put(1)
        
        #   enc: Enc1/Enc2 or 0/1
        #   gate_width/gate_step/pulse_start/pulse_width/pulse_step/pulse_max: independent of traj direction
        self.controller.pc.enc.set(f"Enc{self.motors[motor.prefix]}").wait()
        self.controller.pc.gate_source.set('Position').wait()
        self.controller.pc.pulse_source.set('Position').wait()
        self.controller.pc.gate_width.set((N+1)*dx).wait()
        self.controller.pc.gate_step.set((N+2)*dx).wait()
        self.controller.pc.pulse_start.set(0).wait()
        self.controller.pc.pulse_step.set(dx).wait()
        self.controller.pc.pulse_width.set(dx/5).wait()
        self.controller.pc.pulse_max.set(0).wait()   # disarm once gate is low
        
        self.ramp_dist = dx
        self.verified = True
        self.traj_par = {'run_forward_traj': True, 
                         'no_of_segments': N, 
                         'no_of_rampup_points': 1,
                         'segment_displacement': dx,
                         'segment_duration': dt,
                         'rampup_distance': self.ramp_dist,
                        }

        self.time_modified = time.time()
        
    def exec_traj(self, forward=True):
        """
           execuate either the foward or backward trajectory
        """
        if self.verified==False:
            raise Exception("trajectory not defined/verified.")

        motor = self.flying_motor
        dx0 = self.traj_par['rampup_distance']
        ready_pos = self.traj_par['ready_pos'][0 if forward else 1]
        vel0 = motor.velocity.get()
        vel = self.traj_par['segment_displacement']/self.traj_par['segment_duration']
        # set motor speed
        motor.velocity.set(vel).wait()
        
        # the following need to be changed every time the trajectory is reversed
        #   dir: Positive/Negative or 0/1
        #   gate_start: ready_position +/- step
        if forward: 
            self.controller.pc.dir.set("Positive").wait()
            self.controller.pc.gate_start.set(ready_pos+dx0).wait()
        else:
            self.controller.pc.dir.set("Negative").wait()
            self.controller.pc.gate_start.set(ready_pos-dx0).wait()
        
        print("moving into starting position ...")
        motor.move(ready_pos, wait=True)
        
        print("arming Zebra PC ...")
        self.controller.pc.arm.set(0).wait()  # the value doesn't seem to matter
        while (not self.controller.pc.armed.get()):
            time.sleep(0.1)
            
        print(f"moving {self.flying_motor.name} ...")
        target_pos = self.traj_par['ready_pos'][1 if forward else 0]
        motor.move(target_pos, wait=True)

        self.update_readback()
        print('end of trajectory execution, ', end='')
            
        # reset motor speed
        motor.velocity.set(vel0).wait()
        
        if self._traj_status!=None:
            self._traj_status._finished()
            
    def readback_traj(self):
        print("waiting for Zebra PC to disarm ...")
        while (self.controller.pc.armed.get()):
            time.sleep(0.1)
        
        print('reading back trajectory ...')  
        data = self.controller.pc.data.read()
        return data[f'Zebra_pc_data_enc{self.motors[self.flying_motor.prefix]}']['value']

    
