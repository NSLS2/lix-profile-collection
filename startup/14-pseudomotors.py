from ophyd import (PseudoPositioner, PseudoSingle, EpicsMotor, Signal)
from ophyd import (Component as Cpt)
from ophyd.pseudopos import (pseudo_position_argument, real_position_argument)


class Energy(PseudoPositioner):
    # The pseudo positioner axes
    energy = Cpt(PseudoSingle, limits=(-100000, 100000))

    # The real (or physical) positioners:
    bragg = Cpt(EpicsMotor, 'XF:16IDA-OP{Mono:DCM-Ax:Bragg}Mtr')
    y = Cpt(EpicsMotor, 'XF:16IDA-OP{Mono:DCM-Ax:Of2}Mtr')

    # Variables
    ov = Cpt(Signal, value=-10.243, 
             doc='ov is the correction needed to get actual Y value')

    @pseudo_position_argument
    def forward(self, target):
        '''Run a forward (pseudo -> real) calculation'''
        d = 5.43095
        offset = 20.0
        lmd = 1973.*2.*np.pi/target.energy
        brg = np.degrees(np.arcsin(lmd*np.sqrt(3.)/(2.*d)))
        y0 = offset/(2.0*np.cos(np.radians(brg)))
        y_calc = y0+self.ov.get()

        return self.RealPosition(bragg=brg,
                                 y=y_calc)


    @real_position_argument
    def inverse(self, real_pos):
        '''Run an inverse (real -> pseudo) calculation'''
        # Si(111) lattice constant is 5.43095A
        d = 5.43095
        # q = 2pi / d * sqrt(3.)
        # q = 4pi / lmd * sin(bragg)
        #
        lmd = 2.0/np.sqrt(3.)*d*np.sin(np.radians(real_pos.bragg))
        calc_energy = 1973.*2.*np.pi/lmd
        return self.PseudoPosition(energy=calc_energy)


pseudo_energy = Energy('', name='energy')
energy = pseudo_energy.energy
