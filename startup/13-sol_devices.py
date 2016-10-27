# part of the ipython profile for data collection
from ophyd import (EpicsSignal, Device, Component as Cpt)

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
    vc_4port = Cpt(EpicsSignal, "vc_4port_valve")
    
    def halt(self):
        self.halt_pump.set(1)
        self.water_pump.set('off')
        self.sv_N2.set('off')
        self.sv_drain1.set('off')
        self.sv_drain2.set('off')
        
    def reset(self):
        self.reset_pump.set(1)
        
    def wait(self):
        while True:
            if self.status.get()==0:
                break
            time.sleep(0.5)

    def pump_mvA(self, des):
        self.piston_pos.set(des)

    def pump_mvR(self, dV):
        cur = self.piston_pos.get()
        self.piston_pos.set(cur+dV)
    
    
sol_ctrl = SolutionScatteringControlUnit('XF:16IDC-ES:Sol{ctrl}', name='sol_ctrl')