# part of the ipython profile for data collection
from ophyd import (EpicsSignal, EpicsMotor, Device, Component as Cpt)
from time import sleep
import threading,signal,random
from epics import PV
import bluesky.plans as bp    

class SolutionScatteringControlUnit(Device):
    reset_pump = Cpt(EpicsSignal, 'pp1c_reset')
    halt_pump = Cpt(EpicsSignal, 'pp1c_halt')
    piston_pos = Cpt(EpicsSignal, 'pp1c_piston_pos')
    valve_pos = Cpt(EpicsSignal, 'pp1c_valve_pos')
    pump_spd = Cpt(EpicsSignal, 'pp1c_spd')
    status = Cpt(EpicsSignal, 'pp1c_status')
    water_pump = Cpt(EpicsSignal, "sv_water")
    water_pump_spd = Cpt(EpicsSignal, "water_pump_spd")
    sv_sel = Cpt(EpicsSignal, "sv_sel")
    sv_N2 = Cpt(EpicsSignal, "sv_N2")
    sv_N2_box = Cpt(EpicsSignal, "sv_N2_box")
    sv_drain1 = Cpt(EpicsSignal, "sv_drain1")
    sv_drain2 = Cpt(EpicsSignal, "sv_drain2")
    sv_door_upper = Cpt(EpicsSignal, "sv_door_upper")
    sv_door_lower = Cpt(EpicsSignal, "sv_door_lower")
    sv_pcr_tubes = Cpt(EpicsSignal, "sv_pcr_tubes")
    sv_fan = Cpt(EpicsSignal, "sv_fan")
    fan_power = Cpt(EpicsSignal, "fan_power")
    sampleT = Cpt(EpicsSignal, "sample_temp")
    sampleTs = Cpt(EpicsSignal, "sample_temp_SP")
    sampleTCsts = Cpt(EpicsSignal, "sample_TCsts")
    vc_4port = Cpt(EpicsSignal, "vc_4port_valve")
    serial_busy = Cpt(EpicsSignal, "busy")
    ready = Cpt(EpicsSignal, "ready")
    pause_request = Cpt(EpicsSignal, "pause")
 
    def halt(self):
        self.halt_pump.put(1)
        self.water_pump.put('off')
        self.sv_N2.put('off')
        self.sv_drain1.put('off')
        self.sv_drain2.put('off')
        
    def reset(self):
        self.reset_pump.put(1)
        
    def wait(self):
        while True:
            if self.status.get()==0 and self.serial_busy.get()==0:
                break
            sleep(0.5)

    def pump_mvA(self, des):
        self.piston_pos.put(des)

    def pump_mvR(self, dV):
        cur = self.piston_pos.get()
        self.piston_pos.put(cur+dV)

    def delayed_mvR(self, dV):
        cur = self.piston_pos.get()
        while self.ready.get()==0:
            sleep(.1)
        self.ready.put(0)
        self.piston_pos.put(cur+dV)
        
    def delayed_oscill_mvR(self, dV, times):
        cur = self.piston_pos.get()
        dO=dV-10
        #self.piston_pos.put(cur+3)
        dV=dV-10
        while self.ready.get()==0:
            sleep(.2)
        self.ready.put(0)
        for n in range(times):
            cur1 = self.piston_pos.get()
            self.piston_pos.put(cur1+dV)
            self.wait()
            dV=-dO
        
default_solution_scattering_config_file = '/nsls2/xf16id1/config.solution'
# y position of the middle flow-cell
# y spacing between flow cells

class SolutionScatteringExperimentalModule():
    
    ctrl = SolutionScatteringControlUnit('XF:16IDC-ES:Sol{ctrl}', name='sol_ctrl')
    pcr_v_enable = EpicsSignal("XF:16IDC-ES:Sol{ctrl}SampleAligned")    # 1 means PCR tube holder can go up 
    pcr_holder_down = EpicsSignal("XF:16IDC-ES:Sol{ctrl}HolderDown")
    EMready = EpicsSignal("XF:16IDC-ES:Sol{ctrl}EMSolReady")
    HolderPresent = EpicsSignal("XF:16IDC-ES:Sol{ctrl}HolderPresent")
    DoorOpen = EpicsSignal("XF:16IDC-ES:Sol{ctrl}DoorOpen")
    
    sample_y = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Yu}Mtr', name='sol_sample_y')
    holder_x = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Xl}Mtr', name='sol_holder_x')
    xc = EpicsMotor('XF:16IDC-ES:Scan{Ax:XC}Mtr', name='ss_xc')

    # the needles are designated 1 (upstream) and 2
    # the flow cells are designated 1 (bottom), 2 and 3
    # needle 1 is connected to the bottom flowcell, needle 2 connected to the top, HPLC middle
    flowcell_nd = {'upstream': 'top', 'downstream': 'bottom'}

    # the center flow flow cell should be aligned to the beam
    # the addtional positions are for the standard sample, a empty space for checking scattering background,
    #    and for the scintillator for check the beam shape
    # this information should be verified every time we setup for solution scattering
    flowcell_pos = {'bottom': [4.48 ,0], 
                    'middle': [0, 0],
                    'top':    [-4.5, 0],
                    'std':    [-12., 0],
                    'empty':  [-15., 0],
                    'scint':  [-17., 0]}  
    
    # this is the 4-port valve piosition necessary for the wash the needle
    p4_needle_to_wash = {'upstream': 1, 'downstream': 0}
    # this is the 4-port valve piosition necessary to load throug the needle
    p4_needle_to_load = {'upstream': 0, 'downstream': 1}
    needle_dirty_flag = {'upstream': True, 'downstream': True}
    tube_holder_pos = "down"
    bypass_tube_pos_ssr = False  # if true, ignore the optical sensor for tube holder position
    
    # need to home holder_x position to 0; use home_holder()
    # tube postion 1 is on the inboard side
    drain_pos = 0.
    park_pos = 33.0
    
    disable_flow_cell_move = False
    
    # selection valve in the syringe pump box, see sol_devices.py
    sel_valve = {'water': 1, 'N2': 0}
    # time needed to pump enough water to fill the drain well
    # assume that tube is empty
    wash_duration = 1.
    drain_duration = 2.

    # drain valve
    drain = {'upstream': ctrl.sv_drain1, 'downstream': ctrl.sv_drain2}
    
    # syringe pump 
    default_piston_pos = 150
    default_pump_speed = 1500
    default_load_pump_speed = 350     
    vol_p4_to_cell = {'upstream': -120, 'downstream': -120}
    vol_tube_to_cell = {'upstream': 95, 'downstream': 95} 
    vol_sample_headroom = 13 
    vol_flowcell_headroom = 20  
    watch_list = {'stats1.total': 0.2e7}
    
    Ntube = 18
    tube1_pos=-18.83   #4/10/20 sc[new sensor]    #12/20/17 by JB
    tube_spc = -5.8417     # these are mechanically determined and should not change

    default_dry_time = 20
    default_wash_repeats = 5
    
    cam = None 
    
    def __init__(self, camName="camES1"):
        # important to home the stages !!!!!
        # how to home sample_y???
        
        # load configuration
        #self.load_config(default_solution_scattering_config_file)
        self.return_piston_pos = self.default_piston_pos
        self.ctrl.pump_spd.put(self.default_pump_speed)
        self.ctrl.water_pump_spd.put(0.9)
        self.load_vol = 0

        self.holder_x.acceleration.put(0.2)
        self.holder_x.velocity.put(25)

        self.int_handler = signal.getsignal(signal.SIGINT)
        self.cam = setup_cam(camName)

    def set_xc_limits(self):
        self.xc.set_current_position(0)
        self.xc.set_limits(-1,1)

    def enable_ctrlc(self):
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self.int_handler)
            print("ctrl-C re-enabled ...")
        else:
            print("not in the main thread, cannot change ctrl-C handler ... ")

    def disable_ctrlc(self):
        if threading.current_thread() is threading.main_thread():
            self.int_hanlder = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            print("ctrl-C disabled ...")
        else:
            print("not in the main thread, cannot change ctrl-C handler ... ")
            
    def verify_needle_for_tube(self, tn, nd):
        """  needle vs tube position
             in the current design the even tube position is on the downstream side
        """        
        if tn%2==0: # even tube number
            return("upstream")
        else: # odd tube number
            return("downstream")

    def move_door(self, state):
        """ state = 'open'/'close'
        """
        if state not in ['open', 'close']:
            raise Exception("the door state should be either open or close.")
            
        if state=='open':
            setSignal(sol.ctrl.sv_door_lower, 1, sol.DoorOpen)
        else: 
            setSignal(sol.ctrl.sv_door_lower, 0, sol.DoorOpen)
            
    def home_holder(self):
        mot = sol.holder_x
    
        self.move_door('open')
        mot.velocity.put(25)
        caput(mot.prefix+".HLM", mot.position+160)
        # move holder_x to hard limit toward the door
        mot.move(mot.position+155)
        while mot.moving:
            sleep(0.5)
            
        # washing well position will be set to zero later
        # the value of the park position is also the distance between "park" and "wash"
        mot.move(mot.position-self.park_pos+0.5)

        pv = 'XF:16IDC-ES:Sol{ctrl}SampleAligned'

        while caget(pv)==0:                      
            mot.move(mot.position-0.1)
        p1 = mot.position

        mot.move(p1-1)
        while caget(pv)==0:                      
            mot.move(mot.position+0.1)
        p2 = mot.position

        mot.move((p1+p2)/2)
        while mot.moving:
            sleep(0.5)
        mot.set_current_position(0)
        caput(mot.prefix+".HLM", self.park_pos+0.5)
        caput(mot.prefix+".LLM", self.tube1_pos+self.tube_spc*(self.Ntube-1)-0.5)

        self.move_door('close')

        
    def save_config(self):
        pass

    def load_config(self, fn):
        pass
        
    def select_flow_cell(self, cn, r_range=0):
        if self.disable_flow_cell_move:
            print("flow cell motion disabled !!!")
        else:
            #self.sample_y.home('forward')
            offset = [r_range*(random.random()-0.5), r_range*(random.random()-0.5)]
            print('move to flow cell %s ...' % cn)
            self.xc.move(self.flowcell_pos[cn][1] + offset[1])
            self.sample_y.move(self.flowcell_pos[cn][0] + offset[0])
    
    def select_tube_pos(self, tn):
        ''' 1 argument accepted: 
            position 1 to 18 from, 1 on the inboard side
            position 0 is the washing well 
        '''
        # any time the sample holder is moving, the solution EM is no longer ready
        setSignal(self.EMready, 0)

        if tn not in range(0,self.Ntube+1) and tn!='park':
            raise RuntimeError('invalid tube position %d, must be 0 (drain) or 1-18, or \'park\' !!' % tn)
        if self.pcr_holder_down.get()!=1:
            self.move_tube_holder("down")
            #raise RuntimeError('Cannot move holder when it is not down!!')

        self.tube_pos = tn
        if tn=='park':
            self.move_door('open')
            self.xc.move(0) # so that the robot doesn't have to change trajectory
            self.holder_x.move(self.park_pos)
            print('move to PCR tube holder park position ...')        
        else:
            pos = self.drain_pos
            if tn>0:
                pos += (self.tube1_pos + self.tube_spc*(tn-1))
            print('move to PCR tube position %d ...' % tn)
            self.holder_x.move(pos)

        while self.holder_x.moving:
            sleep(0.5)
        print('motion completed.')
        if tn=='park':
            setSignal(self.EMready, 1)
        elif self.DoorOpen.get()==1:
            self.move_door('close')
         
            
    def move_tube_holder(self, pos, retry=5):
        '''1 argument accepted:
           'up' or 'down'
           up allowed only when the hodler is anligned to needle
        '''
        if pos=='down':
            print('moving PCR tube holder down ...')
            while retry>0:
                self.ctrl.sv_pcr_tubes.put('down')
                self.ctrl.wait() 
                # wait for the pneumatic actuator to settle
                #addtition of new position sensor for sample holder actuator 12/2017:
                if self.pcr_holder_down.get()==1:
                    break
                sleep(0.5)
                retry -= 1
            if retry==0:
                raise Exception("could not move the holder down.")
            self.tube_holder_pos = "down"                
        elif pos=='up':
            # if self.pcr_v_enable.get()==0 and (self.holder_x.position**2>1e-4 and self.tube_pos!=12):
            # revised by LY, 2017Mar23, to add bypass
            if self.pcr_v_enable.get()==0 and self.bypass_tube_pos_ssr==False:
                raise RuntimeError('attempting to raise PCR tubes while mis-aligned !!') 
            print('moving PCR tube holder up ...')
            self.ctrl.sv_pcr_tubes.put('up')
            self.ctrl.wait()        
            self.tube_holder_pos = "up"
    
    def wash_needle(self, nd, repeats=-1, dry_duration=-1, option=None):
        """ option: "wash only", skip drying
                    "dry only", skip washing
        """
        if nd not in ('upstream', 'downstream'):
            raise RuntimeError('unrecoganized neelde (must be \'upstream\' or \'downstream\') !!', nd)
        
        if dry_duration<0:
            dry_duration = self.default_dry_time
        if repeats<0:
            repeats = self.default_wash_repeats

        self.select_tube_pos(0) 
        
        self.ctrl.vc_4port.put(self.p4_needle_to_wash[nd])
        self.move_tube_holder('up')
        
        if option!="dry only":
            # the selection valve might leak water, disable ctrl-C until the valve is switched back to N2
            self.disable_ctrlc()    
            self.ctrl.sv_sel.put(self.sel_valve['water'])
            for n in range(repeats):
                print("current wash loop %d of %d" % (n+1,repeats))
                # first turn on watch to fill the drain well
                print("water")
                self.ctrl.water_pump.put('on')
                sleep(self.wash_duration)
                # now turn on the drain but keep flushing water
                self.drain[nd].put('on')
                sleep(self.drain_duration)
                # turn off water first
                self.ctrl.water_pump.put('off')
                self.drain[nd].put('off')
            self.ctrl.sv_sel.put(self.sel_valve['N2'])
            self.enable_ctrlc()

        if option!="wash only":
            self.drain[nd].put('on')
            print('n2')
            self.ctrl.sv_sel.put(self.sel_valve['N2'])
            self.ctrl.sv_N2.put('on')
            countdown("drying for ", dry_duration)
            self.ctrl.sv_N2.put('off')
            self.drain[nd].put('off')        
        
            self.needle_dirty_flag[nd] = False

        self.move_tube_holder('down')
        
    def reload_syringe_pump(self):
        # make room to load sample from the PCR tube
        if np.fabs(self.ctrl.piston_pos.get()-self.default_piston_pos)<1.:
            return
        
        print(time.asctime(), ": reloading the syringe pump.")
        self.ctrl.pump_spd.put(self.default_pump_speed)
        self.ctrl.valve_pos.put("res")
        self.ctrl.pump_mvA(self.default_piston_pos)
        self.ctrl.wait()
        print(time.asctime(), ": finished reloading the syringe pump.")
    
    
    def prepare_to_load_sample(self, tn, nd=None):
        nd = self.verify_needle_for_tube(tn, nd)    
        if self.needle_dirty_flag[nd]:
            self.wash_needle(nd)
        self.select_tube_pos(tn)
    
    def load_water(self,nd=None, vol=45):
        #loading water for reference measurement
        self.ctrl.vc_4port.put(self.p4_needle_to_load[nd])
        # make room to load sample from teh PCR tube
        self.ctrl.pump_spd.put(self.default_pump_speed)
        self.ctrl.valve_pos.put("res")
        print('loading water')
        self.ctrl.pump_mvA(self.default_piston_pos)
        self.ctrl.wait()
        self.ctrl.valve_pos.put("sam")
        print('towards cell')
        # fill the tubing with water only upto the end of the flow channel
        self.ctrl.pump_mvR(self.vol_p4_to_cell[nd]) 
        self.ctrl.wait()
        self.ctrl.pump_mvR(-vol)
    
    def load_sample(self, vol, nd=None):
        nd = self.verify_needle_for_tube(self.tube_pos, nd)
        if nd not in ('upstream', 'downstream'):
            raise RuntimeError('unrecoganized neelde (must be \'upstream\' or \'downstream\') !!', nd)

        self.needle_dirty_flag[nd] = True
    
        self.ctrl.vc_4port.put(self.p4_needle_to_load[nd])
        # make room to load sample from teh PCR tube
        self.ctrl.pump_spd.put(self.default_pump_speed)
        self.ctrl.valve_pos.put("res")
        self.ctrl.pump_mvA(self.default_piston_pos)
        self.ctrl.wait()
        self.ctrl.valve_pos.put("sam")
        print('4p valve to flowcell')
        # fill the tubing with water only upto the end of the flow channel
        self.ctrl.pump_mvR(self.vol_p4_to_cell[nd]) 
        self.ctrl.wait()

        self.return_piston_pos = self.ctrl.piston_pos.get()
        a=self.return_piston_pos
        self.ctrl.pump_spd.put(self.default_load_pump_speed)
        self.move_tube_holder('up') 
        print("loading sample")
        self.load_vol = vol
        self.ctrl.pump_mvR(vol)
        #self.ctrl.pump_mvR(self.vol_tube_to_cell[nd]) ## load the sample fron the PCR tube into the cell
        self.ctrl.wait()
        self.move_tube_holder('down')
        if self.pcr_holder_down.get()==0:
            raise RuntimeError('sample holder is not down!!')
        else:
            print('Sample holder is down.')
        #self.ctrl.pump_mvA(self.return_piston_pos+self.vol_tube_to_cell[nd])
        #self.ctrl.wait()
    
    def prepare_to_measure(self, nd, wait=True):
        """ move the sample from the injection needle to just before the sample cell
            self.return_piston_pos is the piston position before the sample aspirated into the needle 
        """
        print("moving sample closer to cell")
        self.ctrl.pump_mvA(self.return_piston_pos+self.vol_tube_to_cell[nd])
        if wait:
            self.ctrl.wait()
    
    def prepare_to_return_sample(self, wait=True):
        """ move the sample back to the injection needle
            self.return_piston_pos is the piston position before the sample aspirated into the needle 
        """
        self.ctrl.pump_mvA(self.return_piston_pos+self.load_vol)
        if wait:
            self.ctrl.wait()
           
    def collect_data(self, vol=45, exp=2, repeats=3, sample_name='test', check_sname=True):
        nd = self.verify_needle_for_tube(self.tube_pos, nd=None)
        
        change_sample(sample_name, check_sname=check_sname)

        pil.set_trigger_mode(PilatusTriggerMode.ext)
        pil.exp_time(exp)
        pil.number_reset(True)
        pil.set_num_images(repeats, rep=1)
        em1.averaging_time.put(0.25)
        em2.averaging_time.put(0.25)
        em1.acquire.put(1)
        em2.acquire.put(1)
        sd.monitors = [em1.sum_all.mean_value, em2.sum_all.mean_value]
        # pump_spd unit is ul/min
        self.ctrl.pump_spd.put(60.*vol/(repeats*exp)) # *0.85) # this was necesary when there is a delay between frames
        
        # stage the pilatus detectors first to be sure that the detector are ready
        pil.stage()
        pil.trigger_lock.acquire()
        threading.Thread(target=self.cam.watch_for_change, 
                         kwargs={"lock": pil.trigger_lock, "watch_name": nd}).start()
        self.ctrl.pump_mvR(vol+self.vol_flowcell_headroom)
        RE(ct([pil], num=1))   # number of exposures determined by pil.set_num_images()
        sd.monitors = []
        change_sample()
        
        self.ctrl.wait()
        self.ctrl.pump_spd.put(self.default_pump_speed)
    
    
    def return_sample(self):
        ''' assuming that the sample has just been measured
            dump the sample back into the PCR tube
        '''
        self.ctrl.valve_pos.put("sam")
        self.move_tube_holder('up')
        self.ctrl.pump_mvA(self.return_piston_pos)
        self.ctrl.wait()       
        self.move_tube_holder('down')
        
    def measure(self, tn, nd=None, vol=50, exp=5, repeats=3, sample_name='test', 
                delay=0, returnSample=True, washCell=True, concurrentOp=False, check_sname=True):
        ''' tn: tube number: 1-18
            exp: exposure time
            repeats: # of exposures
            returnSample: if False, the sample is washed into the drain, can save time
            concurrentOp: wash the other cell while the scattering measurement takes place
            washCell: wash cell after the measurements, ignored if running concurrent ops 
            delay: pause after load_sample, may be useful for temperature control    
        '''        
        
        nd = self.verify_needle_for_tube(tn,nd)
        # this should have been completed already in normal ops
        if self.needle_dirty_flag[nd]:
            self.wash_needle(nd)
            
        self.select_tube_pos(tn)                
        # load_sample() knows which injection needle to use
        # headroom may need to be adjusted depending on the mode of operations
        # can be minimal if sample cam is used to trigger data collection, but never zero
        print('loading')
        self.load_sample(vol + self.vol_sample_headroom)
        print('done')
        # this is where operations can be concurrent on both flow channels
        if concurrentOp:
            # the other needle
            nd1 = self.verify_needle_for_tube(tn+1,nd)
            th = threading.Thread(target=self.wash_needle, args=(nd1, ) )
            th.start()        
        
        # move the sample to just before the flow cell
        self.select_flow_cell(self.flowcell_nd[nd])
        self.prepare_to_measure(nd)
        if delay>0:
            countdown("delay before exposure:",delay)
        
        print('****************')
        print('collecting data %s' %sample_name)
        self.collect_data(vol, exp, repeats, sample_name, check_sname=check_sname)
        
        if returnSample:
            # move the sample back to the end of the injection needle
            self.prepare_to_return_sample()
        
        if concurrentOp:
            # get the syringe pump ready for the next step
            self.reload_syringe_pump()
            # make sure wash_needel() is completed for the other needle
            th.join()  
        # end of concurrent operations
        
        if returnSample:
            self.select_tube_pos(tn)                
            self.return_sample()
        if washCell and not concurrentOp:  
            th = threading.Thread(target=self.wash_needle, args=(nd, ) )
            th.start()        
            self.reload_syringe_pump()
            th.join()                

    def mov_delay(self, length):
        while self.ctrl.ready.get()==0:
            sleep(0.2)
        self.ctrl.ready.put(0)
        #mov_all(self.sample_x,-length,wait=False,relative=True)
    
