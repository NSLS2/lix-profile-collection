class VacPositioningStack():
    # S type encoder, SDC2 with step/dir from mc23 (Delta-Tau)
    # note that the SDC2 STEPINC needs to be configured
    #      currently 20nm for X and 1nm for Y
    x = EpicsMotor('XF:16IDC-ES{Ax:sX}Mtr', name='vs_x')
    y = EpicsMotor('XF:16IDC-ES{Ax:sY}Mtr', name='vs_y')
    # mc22 (SmarAct)
    z = EpicsMotor('XF:16IDC-ES:ScanVac{Ax:sZ}Mtr', name='vs_z')

vs = VacPositioningStack()
z1traj = ZEBRAtraj(zebra, [vs.x, vs.y])

