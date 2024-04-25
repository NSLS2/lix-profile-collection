print(f"Loading {__file__}...")

from ophyd import Device, Component as Cpt, EpicsMotor, EpicsSignalRO
from epics import caget,caput, PV

state_inserted = 0
state_removed = 1

class Transfocator(Device):
    #za = Cpt(EpicsMotor,'-Ax:Z}Mtr')
    z = Cpt(EpicsMotor,'-Ax:Z}Mtr')
    x1 = Cpt(EpicsMotor,'-Ax:UX}Mtr')
    y1 = Cpt(EpicsMotor,'-Ax:UY}Mtr')
    x2 = Cpt(EpicsMotor,'-Ax:DX}Mtr')
    y2 = Cpt(EpicsMotor,'-Ax:DY}Mtr')
    busy = Cpt(EpicsSignalRO, "}busy")
    saved_states = {}
    current_state = None

    def __init__(self, prefix, num_lens_group, name):
        super().__init__(prefix, name=name)
        self.lens_group = []
        self.lens_group_config = []
        self.num_lens_group = num_lens_group
        for i in range(num_lens_group):
            self.lens_group.append(EpicsSignal(prefix+":%d}sts" % (i+1)))
            self.lens_group_config.append(caget(prefix+(':%d}config' % (i+1))))
        self.current_state = [self.lens_group[i].get() for i in range(self.num_lens_group)]
            
    def wait(self):
        while self.busy.get()>0:   
            sleep(0.2)
    
    def state(self):
        self.get_state(silent=True)
        return self.current_state
    
    def get_state(self, silent=False):
        if not silent:
            print("inserted lens groups:")
        for i in range(self.num_lens_group):
            self.current_state[i] = self.lens_group[i].get()
            if self.current_state[i]==state_inserted and not silent:
                print("\tgroup %d: %s" % (i+1, self.lens_group_config[i]))
        
        if not 'CRL' in RE.md['CRL'].keys():
            RE.md['CRL'] = {}
        RE.md['CRL']['state'] = self.current_state
                
    def get_focal_length(self):
        pass
    
    def set_focal_length(self):
        pass
    
    def insert_grp(self, grp):
        if grp<1 or grp>self.num_lens_group:
            print("invalid lens group: # %d" % grp)
            return
        self.lens_group[grp-1].put(state_inserted)
        self.wait()
        self.get_state(silent=True)
        
    def remove_grp(self, grp):
        if grp<1 or grp>self.num_lens_group:
            print("invalid lens group: # %d" % grp)
            return
        self.lens_group[grp-1].put(state_removed)
        self.wait()  
        self.get_state(silent=True)
        
    def restore_state(self, name="last"):
        for i in range(len(self.saved_states[name])):
            self.lens_group[i].put(self.saved_states[name][i])
            self.wait()
        self.get_state(silent=True)
        
    def save_state(self, name="last"):
        self.get_state(silent=True)
        self.saved_states[name] = self.current_state
        
    def remove_all(self):
        for i in range(self.num_lens_group):
            self.lens_group[i].put(state_removed)
            self.wait()
        self.get_state(silent=True)

try:
    crl = Transfocator('XF:16IDC-OP{CRL', 9, 'crl')
except TimeoutError:
    print("transfocator is not available.")

