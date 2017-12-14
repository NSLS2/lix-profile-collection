from ophyd import Device, Component as Cpt, EpicsMotor, EpicsSignalRO
from epics import caget,caput, PV

state_inserted = 0
state_removed = 1

class Transfocator(Device):
    #za = Cpt(EpicsMotor,'-Ax:Z}Mtr')
    z = Cpt(EpicsMotor,'-Ax:Z1}Mtr')
    x1 = Cpt(EpicsMotor,'-Ax:UX}Mtr')
    y1 = Cpt(EpicsMotor,'-Ax:UY}Mtr')
    x2 = Cpt(EpicsMotor,'-Ax:DX}Mtr')
    y2 = Cpt(EpicsMotor,'-Ax:DY}Mtr')
    busy = Cpt(EpicsSignalRO, "}busy")

    def __init__(self, prefix, num_lens_group, name):
        super().__init__(prefix, name=name)
        self.lens_group = []
        self.lens_group_config = []
        self.num_lens_group = num_lens_group
        for i in range(num_lens_group):
            self.lens_group.append(EpicsSignal(prefix+":%d}sts" % (i+1)))
            self.lens_group_config.append(caget(prefix+(':%d}config' % (i+1))))
    
    def wait(self):
        while self.busy.get()>0:   
            sleep(0.2)
    
    def get_state(self):
        print("inserted lens groups:")
        for i in range(self.num_lens_group):
            if self.lens_group[i].get()==state_inserted:
                print("\tgroup %d: %s" % (i+1, self.lens_group_config[i]))
                
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
        
    def remove_grp(self, grp):
        if grp<1 or grp>self.num_lens_group:
            print("invalid lens group: # %d" % grp)
            return
        self.lens_group[grp-1].put(state_removed)
        self.wait()        
        


## Transfocator CRLs 
p = PV('XF:16IDC-OP{CRL:1}config') 
sleep(1) 
if p.connect():
    crl = Transfocator('XF:16IDC-OP{CRL', 9, 'crl')
else:
    print("transfocator is not available.")
    
del p

