print("loading configuration for generic EM ...")

ss = PositioningStackMicroscope()

caput(ss.xc.prefix+".DIR", 1)

ss.x = xps.def_motor("scan.X", "ss_x", direction=-1)
ss.y = xps.def_motor("scan.Y", "ss_y")
xps_traj = XPStraj(xps, "scan")

try:
    ss.msy = EpicsMotor('XF:16IDC-ES:Scan{Ax:msY}Mtr', name="ss_msy")
except:
    print('ss.msy for muscle experiments is absent ...')

try:
    camES1       = setup_cam("camES1")
    camScope     = setup_cam("camScope")
except Exception as e:
    print(f"at least one of the cameras is not avaiable: {e}")


