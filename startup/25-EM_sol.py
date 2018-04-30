# part of the ipython profile for data collection
from ophyd import (EpicsSignal, EpicsMotor, Device, Component as Cpt)
from time import sleep
import threading
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
    sv_sel = Cpt(EpicsSignal, "sv_sel")
    sv_N2 = Cpt(EpicsSignal, "sv_N2")
    sv_drain1 = Cpt(EpicsSignal, "sv_drain1")
    sv_drain2 = Cpt(EpicsSignal, "sv_drain2")
    sv_door_upper = Cpt(EpicsSignal, "sv_door_upper")
    sv_door_lower = Cpt(EpicsSignal, "sv_door_lower")
    sv_pcr_tubes = Cpt(EpicsSignal, "sv_pcr_tubes")
    sv_8c_gripper = Cpt(EpicsSignal, "sv_8c_fill_gripper")
    sv_bubble = Cpt(EpicsSignal, "sv_bubble_removal")
    vc_4port = Cpt(EpicsSignal, "vc_4port_valve")
    serial_busy = Cpt(EpicsSignal, "busy")
    ready = Cpt(EpicsSignal, "ready")
    
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
            sleep(.2)
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
        
        
default_solution_scattering_config_file = '/GPFS/xf16id/config.solution'
# y position of the middle flow-cell
# y spacing between flow cells

class SolutionScatteringExperimentalModule():
    
    ctrl = SolutionScatteringControlUnit('XF:16IDC-ES:Sol{ctrl}', name='sol_ctrl')
    pcr_v_enable = EpicsSignal("XF:16IDC-ES:Sol{ctrl}SampleAligned")    # 1 means PCR tube holder can go up 
    pcr_holder_down = EpicsSignal("XF:16IDC-ES:Sol{ctrl}HolderDown")
    EMready = EpicsSignal("XF:16IDC-ES:Sol{ctrl}EMSolready")
    HolderPresent = EpicsSignal("XF:16IDC-ES:Sol{ctrl}HolderPresent")
    DoorOpen = EpicsSignal("XF:16IDC-ES:Sol{ctrl}DoorOpen")
    
    sample_y = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:YU}Mtr', name='sol_sample_y')
    sample_x = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Xu}Mtr', name='sol_sample_x')
    holder_x = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Xl}Mtr', name='sol_holder_x')
    
    # the needles are designated 1 (upstream) and 2
    # the flow cells are designated 1 (bottom), 2 and 3
    # needle 1 is connected to the bottom flowcell, needle 2 connected to the top, HPLC middle
    flowcell_nd = {'upstream': 'top', 'downstream': 'bottom'}
    flowcell_pos = {'bottom': 3.15, 'middle': -1.348, 'top': -5.985}  # 2017/10/11
    #{'top': -6.33, 'middle': -1.36, 'bottom': 3.15} # SC changed bottom from 3.78 07/12/17
    # this is the 4-port valve piosition necessary for the wash the needle
    p4_needle_to_wash = {'upstream': 1, 'downstream': 0}
    # this is the 4-port valve piosition necessary to load throug the needle
    p4_needle_to_load = {'upstream': 0, 'downstream': 1}
    needle_dirty_flag = {'upstream': True, 'downstream': True}
    tube_holder_pos = "down"
    bypass_tube_pos_ssr = True  # if true, ignore the optical sensor for tube holder position
    
    # need to home holder_x position to 0; use home_holder()
    # tube postion 1 is on the inboard side
    drain_pos = 0.
    park_pos = 31.0
    
    disable_flow_cell_move = False
    
    # selection valve in the syringe pump box, see sol_devices.py
    sel_valve = {'water': 0, 'N2': 1}
    # time needed to pump enough water to fill the drain well
    # assume that tube is empty
    wash_duration = 0.3
    drain_duration = 2.

    # drain valve
    drain = {'upstream': ctrl.sv_drain1, 'downstream': ctrl.sv_drain2}
    
    # syringe pump 
    default_piston_pos = 165
    default_pump_speed = 1500
    # SC changed the value from 600 on 7/9/17
    default_load_pump_speed = 350     
    vol_p4_to_cell = {'upstream': -140, 'downstream': -140}
    # SC done changes 02/13/18 --> 
    #   downstream value reduced to (92 from 104) 7/9/17, upstream changed from 110 to 100 
    vol_tube_to_cell = {'upstream': 84, 'downstream': 67} 
    vol_sample_headroom = 13
    
    # these numbers are for the 2016 version tube holder
    #tube1_pos = -15.95     # relative to well position
    #tube_spc = -9.0      # these are mechanically determined and should not change
    # 2017 march version of tube holder with alterate tube/empty holes
    Ntube = 18
    tube1_pos=-18.75    #12/20/17 by JB
    tube_spc = -5.8417     # these are mechanically determined and should not change
            
    def __init__(self):
        # important to home the stages !!!!!
        #     home sample y (SmarAct) from controller
        #     home sample_x and holder_x manually 
        #          move stage to default position and set_current_position(0)
        #          sample_x: beam centered on cell,   holder_x: needles aligned to washing wells/drains 
        #
        # load configuration
        #self.load_config(default_solution_scattering_config_file)
        self.return_piston_pos = self.default_piston_pos
        self.ctrl.pump_spd.put(self.default_pump_speed)

    # needle vs tube position
    # this applies for the tube holder that has the alternate tube/empty pattern
    # in the current design the even tube position is on the downstream side
    def verify_needle_for_tube(self, tn, nd):
        # if both are allowed, simpluy return nd
        #return nd
        if tn%2==0: # even tube number
            return("upstream")
        else: # odd tube number
            return("downstream")

    def move_door(self, state):
        """ state = 'open'/'close'
        """
        if state not in ['open', 'close']:
            raise Exception("the door state should be either open or close.")
            
        self.ctrl.sv_door_lower.put(state)
        
        if state=='open':
            for i in range(10):
                if self.DoorOpen.get():
                    break
                sleep(0.5)
            if self.DoorOpen.get()==0:
                raise Exception("Sample door is not open.")
        else: 
            for i in range(10):
                if self.DoorOpen.get()==0:
                    break
                sleep(0.5)
            if self.DoorOpen.get()==1:
                raise Exception("Sample door is still open.")
        
    # homing procedure without encoder strip [obsolete]:
    #     reduce motor current, drive sol.holder_x in the possitive direction to hit the hard stop
    #     move the motor back by 0.5mm, set the current position to 37.5 ("park" position)
    #     set software limits:
    #          caput("XF:16IDC-ES:Sol{Enc-Ax:Xl}Mtr.LLM", -119)
    #          caput("XF:16IDC-ES:Sol{Enc-Ax:Xl}Mtr.HLM", 31.5)
    #     change the motor current back
    # keep motor current low?
    def home_holder(self):
        mot = sol.holder_x
    
        self.move_door('open')
        mot.acceleration.put(0.2)
        mot.velocity.put(25)
        caput(mot.prefix+".HLM", mot.position+120)
        # move holder_x to hard limit toward the door
        mot.move(mot.position+100)
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
    
    def select_flow_cell(self, cn):
        if self.disable_flow_cell_move:
            print("flow cell motion disabled !!!")
        else:
            print('move to flow cell %s ...' % cn)
            self.sample_y.move(self.flowcell_pos[cn])
    
    def select_tube_pos(self, tn):
        ''' 1 argument accepted: 
            position 1 to 18 from, 1 on the inboard side
            position 0 is the washing well 
        '''
        # any time the sample holder is moving, the solution EM is no longer ready
        self.EMready.put(0)

        if tn not in range(0,self.Ntube+1) and tn!='park':
            raise RuntimeError('invalid tube position %d, must be 0 (drain) or 1-18, or \'park\' !!' % tn)
        if self.pcr_holder_down.get()!=1:
            raise RuntimeError('Cannot move holder when it is not down!!')

        self.tube_pos = tn
        if tn=='park':
            self.move_door('open')
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
            self.EMready.put(1)
        elif self.DoorOpen.get()==1:
            self.move_door('close')
         
            
    def move_tube_holder(self, pos):
        '''1 argument accepted:
           'up' or 'down'
           up allowed only when the hodler is anligned to needle
        '''
        if pos=='down':
            print('moving PCR tube holder down ...')
            self.ctrl.sv_pcr_tubes.put('down')
            self.ctrl.wait() 
            # wait for the pneumatic actuator to settle
            #addtition of new position sensor for sample holder actuator 12/2017:
            while self.pcr_holder_down.get()!=1:
                    sleep(0.5)
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

            
    def dry_needle(self, nd, repeats=3, dry_duration=35):
        if nd not in ('upstream', 'downstream'):
            raise RuntimeError('unrecoganized neelde (must be \'upstream\' or \'downstream\') !!', nd)
        
        self.select_tube_pos(0) 
        
        self.ctrl.vc_4port.put(self.p4_needle_to_wash[nd])
        self.move_tube_holder('up')
        
        self.drain[nd].put('on')
        self.ctrl.sv_sel.put(self.sel_valve['N2'])
        self.ctrl.sv_N2.put('on')
        countdown("drying for ", dry_duration)
        self.ctrl.sv_N2.put('off')
        self.drain[nd].put('off')  
        
        self.move_tube_holder('down')
    
    def wash_needle(self, nd, repeats=3, dry_duration=55, option=None):
        """ option: "wash only", skip drying
                    "dry only", skip washing
        """
        if nd not in ('upstream', 'downstream'):
            raise RuntimeError('unrecoganized neelde (must be \'upstream\' or \'downstream\') !!', nd)
        
        self.select_tube_pos(0) 
        
        self.ctrl.vc_4port.put(self.p4_needle_to_wash[nd])
        self.move_tube_holder('up')
        
        if option!="dry only":
            for n in range(repeats):
                print("current wash loop %d of %d" % (n+1,repeats))
                self.ctrl.sv_sel.put(self.sel_valve['water'])
                self.ctrl.water_pump.put('on')
                sleep(self.wash_duration)
                self.ctrl.water_pump.put('off')
        
                self.drain[nd].put('on')
                sleep(self.drain_duration)
                self.drain[nd].put('off')

        if option!="wash only":
            self.drain[nd].put('on')
            self.ctrl.sv_sel.put(self.sel_valve['N2'])
            self.ctrl.sv_N2.put('on')
            countdown("drying for ", dry_duration)
            self.ctrl.sv_N2.put('off')
            self.drain[nd].put('off')        
        
            self.needle_dirty_flag[nd] = False

        self.move_tube_holder('down')
        
    def prepare_to_load_sample(self, tn, nd=None):
        nd = self.verify_needle_for_tube(tn, nd)    
        if self.needle_dirty_flag[nd]:
            self.wash_needle(nd)
        self.select_tube_pos(tn)
        
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
        # fill the tubing with water only upto the end of the flow channel
        self.ctrl.pump_mvR(self.vol_p4_to_cell[nd]) 
        self.ctrl.wait()

        self.return_piston_pos = self.ctrl.piston_pos.get()
        a=self.return_piston_pos
        self.ctrl.pump_spd.put(self.default_load_pump_speed)
        self.move_tube_holder('up') 
        self.ctrl.pump_mvR(vol+self.vol_sample_headroom)
        #self.ctrl.pump_mvR(self.vol_tube_to_cell[nd]) ## load the sample fron the PCR tube into the cell
        self.ctrl.wait()
        
        self.move_tube_holder('down')
        if self.pcr_holder_up.get()==0:
            raise RuntimeError('sample holder is not down!!')
        else:
            print('Sample holder is down.')
        self.ctrl.pump_mvA(self.return_piston_pos+self.vol_tube_to_cell[nd])
        self.ctrl.wait()
           
    
    def collect_data(self, vol=45, exp=2, repeats=3, sample_name='test'):
        global DETS
        pilatus_ct_time(exp)
        pilatus_number_reset(False)
        
        updata_metadata()
        
        change_sample(sample_name)
        DETS=[em1, em2, pil1M_ext,pilW1_ext,pilW2_ext]
        set_pil_num_images(repeats)
        
        # pump_spd unit is ul/min
        self.ctrl.pump_spd.put(60.*vol/(repeats*exp))
        print('collecting data, %d of %d repeats ...' % (n+1, repeats))
        th = threading.Thread(target=self.ctrl.delayed_mvR, args=(vol, ) )
        th.start() 
        set_pil_num_images(repeats)
        RE(ct(DETS, num=1))
        self.ctrl.wait()
        
        pilatus_number_reset(True)
        self.ctrl.pump_spd.put(self.default_pump_speed)
        if vol<0:  # odd number of repeats, return sample to original position
            self.ctrl.pump_mvR(vol)
        self.ctrl.wait()

    def collect_oscill_data(self, vol=45, exp=2, repeats=3, sample_name='test'):
        pilatus_ct_time(exp)
        pilatus_number_reset(False)
        
        updata_metadata()
        
        change_sample(sample_name)
        
        DETS=[em1, em2, pil1M, pilW1, pilW2]
        #DETS=[em1, em2, pil1M_ext,pilW1_ext,pilW2_ext]
        #set_pil_num_images(repeats)
        
        # pump_spd unit is ul/min
        #self.ctrl.pump_spd.put(60.*vol/exp)
        #for n in range(repeats):
        #    print('collecting data, %d of %d repeats ...' % (n+1, repeats))
        #    self.ctrl.pump_mvR(vol)
        #    RE(count_fs(DETS, num=1))
        #    self.ctrl.wait()
        #    vol=-vol

        # pump_spd unit is ul/min
        self.ctrl.pump_spd.put(60.*vol/exp)
        #print('collecting data, %d of %d repeats ...' % (n+1, repeats))
        #self.ctrl.pump_mvR(vol)
        th = threading.Thread(target=self.ctrl.delayed_oscill_mvR, args=(vol, repeats, ) )
        th.start() 
        # single image per trigger
        #RE(ct(DETS, num=repeats))
        # take multiple images per trigger
        #pilatus_set_Nimage(repeats)
        set_pil_num_images(repeats)
        RE(ct(DETS, num=1))
        self.ctrl.wait()
        
        pilatus_number_reset(True)
        self.ctrl.pump_spd.put(self.default_pump_speed)
        if vol<0:  # odd number of repeats, return sample to original position
            self.ctrl.pump_mvR(vol)
        self.ctrl.wait()

            
    def return_sample(self):
        ''' assuming that the sample has just been measured
            dump the sample back into the PCR tube
        '''
        self.ctrl.valve_pos.put("sam")
        self.move_tube_holder('up')
        self.ctrl.pump_mvA(self.return_piston_pos)
        self.ctrl.wait()       
        self.move_tube_holder('down')
        
    # delay is after load_sample and measure, this is useful for temperature control    
    def measure(self, tn, nd=None, vol=50, exp=5, repeats=3, sample_name='test', 
                delay=0, returnSample=True, washCell=True):
        ''' measure(self, tn, nd, vol, exp, repeats, sample_name='test')
            tn: tube number: 1-18
            nd: needle, "upstream" or "downstream", if need to specify
            exp: exposure time
            repeats: # of exposures
        '''
        
        nd = self.verify_needle_for_tube(tn, nd)
        
        self.select_flow_cell(self.flowcell_nd[nd])
        self.prepare_to_load_sample(tn, nd)
        self.load_sample(vol)
        if delay>0:
            countdown("delay before exposure:",delay)
        self.collect_data(vol, exp, repeats, sample_name)
        
        if returnSample:
            self.return_sample()
        if returnSample and washCell:
            self.wash_needle(nd)
                
    def measure_oscill(self, tn, nd=None, vol=50, exp=5, repeats=3, sample_name='test', delay=0):
        ''' measure(self, tn, nd, vol, exp, repeats, sample_name='test')
            tn: tube number: 1-18
            nd: needle, "upstream" or "downstream", if need to specify
            exp: exposure time
            repeats: # of exposures
        '''
        
        nd = self.verify_needle_for_tube(tn, nd)
        
        #self.select_flow_cell(self.flowcell_nd[nd])
        self.prepare_to_load_sample(tn, nd)
        self.load_sample(vol)
        if delay>0:
            countdown("delay before exposure:",delay)
        self.collect_oscill_data(vol, exp, repeats, sample_name)
        self.return_sample()
        
        self.wash_needle(nd)
        
        
    def measure_list(self, sample_list, vol=45, exp=2, repeats=3, delay=0, nd=None):
        ''' a list of subset of necessary parameters for single sample data collection
        '''
        i=0
        for a in sample_list[0]:
            sample_name=sample_list[1][i]
            nd = self.verify_needle_for_tube(a, nd)
            self.prepare_to_load_sample(a, nd)
            #self.load_sample(vol)
            if delay>0:
                countdown("delay before exposure:",delay)
            th1=threading.Thread(target=self.collect_data,args=(vol, exp, repeats, sample_name,))
            th1.start()
            i+=1
            if i<sample_list.shape[1]:
                c=sample_list[0][i]
                ndn = self.verify_needle_for_tube(c, nd=None)
                if nd!=ndn:
                    #th2=threading.Thread(target=self.wash_needle,args=(ndn,))
                    #th2.start()
                    self.wash_needle(ndn)
                    while th1.is_alive():
                        th1.join(0.2)
            self.select_tube_pos(a)
            self.return_sample()
            nd=None

    def mov_delay(self, length):
        while self.ctrl.ready.get()==0:
            sleep(0.2)
        self.ctrl.ready.put(0)
        mov_all(self.sample_x,-length,wait=False,relative=True)
    
    ## Revised SC 2nd April
    def meas_opencell(self, exp, repeats, sample_name='test'):
        pilatus_ct_time(exp)
        pilatus_number_reset(False)
        
        updata_metadata()
        DETS=[em1, em2, pil1M, pilW1, pilW2]
        #pilatus_set_Nimage(repeats)
        set_pil_num_images(repeats)
        length=7.5
        #self.ctrl.wait()
        self.sample_x.velocity.put(length/((repeats*exp)+4))
        th = threading.Thread(target=self.mov_delay, args=(length, ) )
        th.start()
        RE(count_fs(DETS, num=1))
        self.sample_x.velocity.put(0)
        movr(self.sample_x, length)
        
        
p = PV('XF:16IDC-ES:Sol{ctrl}busy') 
sleep(1)  # after 2017C1 shtdown, this delay becomes necessary
if p.connect():
    sol = SolutionScatteringExperimentalModule()
else:
    print("solution scattering EM is not available.")
    
del p
