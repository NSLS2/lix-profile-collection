from ophyd.mca import Saturn, SoftDXPTrigger

class LIXSaturn(Saturn, SoftDXPTrigger):
    pass

vortex = LIXSaturn('XF:16IDC-ES{Det:Sat}:', name='vortex')

