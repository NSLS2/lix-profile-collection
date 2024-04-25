print(f"Loading {__file__}...")

from ophyd import (PseudoPositioner, PseudoSingle, EpicsMotor, Signal, EpicsSignalRO)
from ophyd import (Component as Cpt)
from ophyd.pseudopos import (pseudo_position_argument, real_position_argument)
from time import sleep
import numpy as np

class EpicsGapMotor(EpicsMotor):

    def __init__(self, brakeDevice, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.brake = brakeDevice
        
    def move(self, *args, **kwargs):
        if self.brake.get()==0:
            self.brake.set(1).wait()
        return super().move(*args, **kwargs)

class MonoDCM(Device):
    bragg = Cpt(EpicsMotor, '-Ax:Bragg}Mtr')
    x = Cpt(EpicsMotor, '-Ax:X}Mtr')
    y = Cpt(EpicsMotor, '-Ax:Of2}Mtr')
    pitch2 = Cpt(EpicsMotor, '-Ax:P2}Mtr')
    roll2 = Cpt(EpicsMotor, '-Ax:R2}Mtr')
    fine_pitch = Cpt(EpicsMotor, '-Ax:PF2}Mtr')
    ccm_fine_pitch = Cpt(EpicsMotor, '-Ax:CCM_PF}Mtr')
    pitch2_rb = Cpt(EpicsSignalRO, '-Ax:PF_RDBK}Mtr.RBV')

#mono = MonoDCM("XF:16IDA-OP{Mono:DCM", name="dcm")

class XBPM(Device):
    x = Cpt(EpicsSignalRO, 'Pos:X-I')
    y = Cpt(EpicsSignalRO, 'Pos:Y-I')

    def pos(self, navg=5):
        if self.x.connected==False or self.y.connected==False:
            return (np.nan, np.nan)
        
        xpos = np.average([self.x.get() for _ in range(navg)])
        ypos = np.average([self.y.get() for _ in range(navg)])
        return (xpos, ypos)

xbpm = XBPM('SR:C16-BI{XBPM:1}', name="C16XBPM")
        

# arcsec to radians conversion
def arcsec_rad(x):
    ## arcsec to rad conversion
    y=x*4.848136811097625
    print(y,"in radians")


# radians to arcsec conversion
def rad_arcsec(x):
    ## arcsec to rad conversion
    y=x/4.848136811097625
    print(y,"in arcsec")


# undulator Keff was measured, the following is good when the gap < 8.5mm 
# K = 0.0406 g^2 - 0.899 g + 6.231 
# the K correction factor is based on data collected in Oct 2020
def calc_E_from_gap(gap, K_cor_factor=1, n=1):
    Keff = 0.0406*(gap*1.e-3)**2 - 0.899*(gap*1.e-3) + 6.231
    Keff *= K_cor_factor
    lmd0 = 2.3e8 # 23mm
    gamma = 3.e3/0.511 # NSLS-II, 3GeV
    lmd = lmd0/(2.*n*gamma*gamma)*(1.+Keff*Keff/2)
    ene = 1973.*2.*np.pi/lmd
    return ene

def calc_E_from_Bragg(th):
    d = 5.43095
    lmd = 2.0/np.sqrt(3.)*d*np.sin(np.radians(th))
    ene = 1973.*2.*np.pi/lmd
    
    return ene

def calc_Bragg_from_E(ene):
    d = 5.43095
    lmd = 1973.*2.*np.pi/ene
    bragg = np.degrees(np.arcsin(lmd*np.sqrt(3.)/(2.*5.43095)))
    
    return bragg

def get_gap_from_E(ene, min_gap=6000, max_gap=7000):
    """ select a suitable gap value for the given x-ray energy
        keep gap value close to but above 6.3mm
        odd harmonic only
    """
    if ene>18000 or ene<5500:
        raise Exception(f"invalid x-ray energy: {ene} eV, only support between 5.5 and 18 keV.")
    # find harmonic number
    cf = 1.014
    ed = {i: calc_E_from_gap(min_gap, K_cor_factor=cf, n=i) for i in range(3,22,2)}
    k = np.where(np.asarray(list(ed.values()))<ene)[0][-1]
    nh = list(ed.keys())[k]
    # find gap value
    gv = np.linspace(min_gap, max_gap, 101)
    el = calc_E_from_gap(gv, K_cor_factor=cf, n=nh)
    gv0 = np.interp(ene, el, gv)

    return gv0,nh

class Energy(PseudoPositioner):
    # The pseudo positioner axes
    energy = Cpt(PseudoSingle, limits=(6000, 18000))

    # The real (or physical) positioners:
    bragg = Cpt(EpicsMotor, 'XF:16IDA-OP{Mono:DCM-Ax:Bragg}Mtr')
    y = Cpt(EpicsMotor, 'XF:16IDA-OP{Mono:DCM-Ax:Of2}Mtr')
    IVUgapBrake = EpicsSignal("SR:C16-ID:G1{IVU:1}BrakesDisengaged-Sts", 
                              write_pv="SR:C16-ID:G1{IVU:1}BrakesDisengaged-SP")  
    IVUgap = Cpt(EpicsGapMotor, 
                 prefix="SR:C16-ID:G1{IVU:1-Ax:Gap}-Mtr", 
                 brakeDevice=IVUgapBrake, name='IVUgap')
    min_gap = 6000
    max_gap = 7000

    # want mono.y to be -16.4 at high E
    ov = -16.74  # mono.y recently homed, this value gets beam close to the previous "good positon" 
    offset = 20
    
    @property
    def wavelength(self):
        ene = self.energy.position
        lmd = 1973.*2.*np.pi/ene
        return lmd

    @pseudo_position_argument
    def forward(self, target):
        '''Run a forward (pseudo -> real) calculation'''
        brg = calc_Bragg_from_E(target.energy)
        y_calc = self.ov+self.offset*(1.0-np.cos(np.radians(brg)))
        g_calc,nh = get_gap_from_E(target.energy, min_gap=self.min_gap, max_gap=self.max_gap)
        
        return self.RealPosition(bragg=brg, IVUgap=g_calc, y=y_calc)

    @real_position_argument
    def inverse(self, real_pos):
        '''Run an inverse (real -> pseudo) calculation'''
        calc_energy = calc_E_from_Bragg(real_pos.bragg)
        return self.PseudoPosition(energy=calc_energy)

pseudoE = Energy('', name='energy')


