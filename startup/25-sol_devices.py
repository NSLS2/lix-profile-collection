# part of the ipython profile for data collection
from ophyd import (EpicsSignal, Device, Component as Cpt)
from time import sleep
import threading

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
            time.sleep(0.5)

    def pump_mvA(self, des):
        self.piston_pos.put(des)

    def pump_mvR(self, dV):
        cur = self.piston_pos.get()
        self.piston_pos.put(cur+dV)

    def delayed_mvR(self, dV):
        cur = self.piston_pos.get()
        while self.ready.get()==0:
            sleep(1.0)
        self.ready.put(0)
        self.piston_pos.put(cur+dV)
        
        
default_solution_scattering_config_file = '/GPFS/xf16id/config.solution'
# y position of the middle flow-cell
# y spacing between flow cells

class SolutionScatteringExperimentalModule():
    
    ctrl = SolutionScatteringControlUnit('XF:16IDC-ES:Sol{ctrl}', name='sol_ctrl')
    pcr_v_enable = EpicsSignal("XF:16IDC-ES:Sol{ctrl}SampleAlign")    # 1 means PCR tube holder can go up 
    
    sample_y = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:YU}Mtr', name='sol_sample_y')
    sample_x = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Xu}Mtr', name='sol_sample_x')
    holder_x = EpicsMotor('XF:16IDC-ES:Sol{Enc-Ax:Xl}Mtr', name='sol_holder_x')
    
    # the needles are designated 1 (upstream) and 2
    # the flow cells are designated 1 (bottom), 2 and 3
    # needle 1 is connected to the bottom flowcell, needle 2 connected to the top, HPLC middle
    flowcell_nd = {'upstream': 'bottom', 'downstream': 'top'}
    flowcell_pos = {'top': -1.16, 'middle': 3.541, 'bottom': 7.94}
    # this is the 4-port valve piosition necessary for the wash the needle
    p4_needle_to_wash = {'upstream': 1, 'downstream': 0}
    # this is the 4-port valve piosition necessary to load throug the needle
    p4_needle_to_load = {'upstream': 0, 'downstream': 1}
    needle_dirty_flag = {'upstream': True, 'downstream': True}
    
    # need to home holder_x position to 0
    # tube postion 1 is on the inboard side
    drain_pos = 0.
    park_pos = 37.5

    # selection valve in the syringe pump box, see sol_devices.py
    sel_valve = {'water': 0, 'N2': 1}
    # time needed to pump enough water to fill the drain well
    # assume that tube is empty
    wash_duration = 0.3
    drain_duration = 2.

    # drain valve
    drain = {'upstream': ctrl.sv_drain1, 'downstream': ctrl.sv_drain2}
    
    # syringe pump 
    default_piston_pos = 175
    default_pump_speed = 1500
    default_load_pump_speed = 600
    vol_p4_to_cell = {'upstream': -137, 'downstream': -140}
    vol_tube_to_cell = {'upstream': 94, 'downstream': 97}
    vol_sample_headroom = 13
    
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
        
    def save_config(self):
        pass

    def save_config(self, fn):
        pass
    
    def select_flow_cell(self, cn):
        print('move to flow cell %s ...' % cn)
        self.sample_y.move(self.flowcell_pos[cn])
    
    def select_tube_pos(self, tn):
        '''1 argument accepted: 
        position 1 to 12 from, 1 on the inboard side
        position 0 is the washing well '''
        if tn not in range(0,13) and tn!='park':
            raise RuntimeError('invalid tube position %d, must be 0 (drain) or 1-12, or \'park\' !!' % tn)
            
        if self.ctrl.sv_pcr_tubes.get(as_string=True)!='down':
            raise RuntimeError('PCR tube holder should be down right now !!')

        self.tube_pos = tn
        if tn=='park':
            #if sol.ctrl.sv_door_lower.get(as_string=True)=='close':
            #raise RuntimeError('Attempting to park the PCR tube holder while the sample door is closed !!')
            self.holder_x.move(self.park_pos)
            print('move to PCR tube holder park position ...')        
        else:
            tube1_pos = -15.95     # relative to well position
            tube_spc = -9.0      # these are mechanically determined and should not change
            pos = self.drain_pos
            if tn>0:
                pos += (tube1_pos + tube_spc*(tn-1))
            print('move to PCR tube position %d ...' % tn)
            self.holder_x.move(pos)
    
    def move_tube_holder(self, pos):
        '''1 argument accepted:
        'up' or 'down'
        up allowed only when the hodler is anligned to needle
        '''
        if pos=='down':
            print('PCR tube holder down ...')
            self.ctrl.sv_pcr_tubes.put('down')
            self.ctrl.wait() 
        elif pos=='up':
            if self.pcr_v_enable.get()==0 and (self.holder_x.position**2>1e-4 and self.tube_pos!=12):
                raise RuntimeError('attempting to raise PCR tubes while mis-aligned !!')
            print('PCR tube holder up ...')
            self.ctrl.sv_pcr_tubes.put('up')
            self.ctrl.wait()        
    
    def wash_needle(self, nd, repeats=3, dry_duration=55):
        if nd not in ('upstream', 'downstream'):
            raise RuntimeError('unrecoganized neelde (must be \'upstream\' or \'downstream\') !!', nd)
        
        self.select_tube_pos(0) 
        
        self.ctrl.vc_4port.put(self.p4_needle_to_wash[nd])
        self.move_tube_holder('up')
        
        # repeats=0 is useful for jsut drying the cell
        if repeats>0:
            for n in range(repeats):
                print("current wash loop %d of %d" % (n+1,repeats))
                self.ctrl.sv_sel.put(self.sel_valve['water'])
                self.ctrl.water_pump.put('on')
                sleep(self.wash_duration)
                self.ctrl.water_pump.put('off')
        
                self.drain[nd].put('on')
                sleep(self.drain_duration)
                self.drain[nd].put('off')

        self.drain[nd].put('on')
        self.ctrl.sv_sel.put(self.sel_valve['N2'])
        self.ctrl.sv_N2.put('on')
        countdown("drying for ", dry_duration)
        self.ctrl.sv_N2.put('off')
        self.drain[nd].put('off')        
        
        self.needle_dirty_flag[nd] = False
        self.move_tube_holder('down')
        
    def prepare_to_load_sample(self, tn, nd):
        if self.needle_dirty_flag[nd]:
            self.wash_needle(nd)
        
        self.select_tube_pos(tn)
        
    def load_sample(self, nd, vol):
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
        self.ctrl.pump_mvR(self.vol_p4_to_cell[nd]) ## fill the tubing with water only upto the end of the flow channel
        self.ctrl.wait()

        self.return_piston_pos = self.ctrl.piston_pos.get()
        self.ctrl.pump_spd.put(self.default_load_pump_speed)
        self.move_tube_holder('up') 
        self.ctrl.pump_mvR(vol+self.vol_sample_headroom)
        #self.ctrl.pump_mvR(self.vol_tube_to_cell[nd]) ## load the sample fron the PCR tube into the cell
        self.ctrl.wait()
        
        self.move_tube_holder('down')
        self.ctrl.pump_mvA(self.return_piston_pos+self.vol_tube_to_cell[nd])
        self.ctrl.wait()
           
    
    def collect_data(self, vol, exp, repeats, sample_name='test'):
        pilatus_ct_time(exp)
        pilatus_number_reset(False)
        
        change_sample(sample_name)
        RE.md['sample_name'] = current_sample 
        RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
        RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
        RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs1_y':waxs2.y.position, 'waxs1_z':waxs2.z.position}) 
        RE.md['energy'] = ({'mono_bragg': mono.bragg.position, 'energy': getE(), 'gap': get_gap()})
        RE.md['XBPM'] = XBPM_pos() 
        
        gs.DETS=[em1, em2, pil1M, pilW1, pilW2]
        
        # pump_spd unit is ul/min
        #self.ctrl.pump_spd.put(60.*vol/exp)
        #for n in range(repeats):
        #    print('collecting data, %d of %d repeats ...' % (n+1, repeats))
        #    self.ctrl.pump_mvR(vol)
        #    RE(ct(num=1))
        #    self.ctrl.wait()
        #    vol=-vol

        # pump_spd unit is ul/min
        self.ctrl.pump_spd.put(60.*vol/(repeats*exp))
        #print('collecting data, %d of %d repeats ...' % (n+1, repeats))
        #self.ctrl.pump_mvR(vol)
        th = threading.Thread(target=self.ctrl.delayed_mvR, args=(vol, ) )
        th.start()
        RE(ct(num=repeats))
        self.ctrl.wait()
        
        pilatus_number_reset(True)
        self.ctrl.pump_spd.put(self.default_pump_speed)
        if vol<0:  # odd number of repeats, return sample to original position
            self.ctrl.pump_mvR(vol)
        self.ctrl.wait()

        del RE.md['sample_name']
        del RE.md['saxs']
        del RE.md['waxs1']
        del RE.md['waxs2']
        del RE.md['energy']
        del RE.md['XBPM']
    
    def return_sample(self):
        ''' assuming that the sample has just been measured
            dump the sample back into the PCR tube
        '''
        self.ctrl.valve_pos.put("sam")
        self.move_tube_holder('up')
        self.ctrl.pump_mvA(self.return_piston_pos)
        self.ctrl.wait()       
        self.move_tube_holder('down')
        
    def measure(self, tn, nd, vol, exp, repeats, sample_name='test'):
        ''' measure(self, tn, nd, vol, exp, repeats, sample_name='test')
            tn: tube number: 1-12
            nd: needle, 1/2
            exp: exposure time
            repeats: # of exposures
        '''
        
        self.select_flow_cell(self.flowcell_nd[nd])
        self.prepare_to_load_sample(tn, nd)
        self.load_sample(nd, vol)
        self.collect_data(vol, exp, repeats, sample_name)
        self.return_sample()
        
        self.wash_needle(nd)
        
        
    def measure_list(self, sample_list):
        ''' a list of subset of necessary parameters for single sample data collection
        '''
        pass

sol = SolutionScatteringExperimentalModule()
