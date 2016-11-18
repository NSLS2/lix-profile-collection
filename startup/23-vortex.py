from ophyd.mca import EpicsMCA, EpicsDXP

# Vortex MCA

class Vortex(Device):
    mca = Cpt(EpicsMCA, 'mca1')
    vortex = Cpt(EpicsDXP, 'dxp1:')

    @property
    def trigger_signals(self):
        return [self.mca.erase_start]

# Saturn interface for Vortex MCA detector
vortex = Vortex('XF:16IDC-ES{Det:Sat}:', name='vortex')
vortex.read_attrs = ['mca.spectrum', 'mca.preset_live_time', 'mca.rois.roi0.count']

