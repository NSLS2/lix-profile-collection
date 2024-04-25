print("loading configuration for microscope-EM ...")

ss = PositioningStackMicroscope()

caput(ss.xc.prefix+".DIR", 1)

ss.x = xps.def_motor("scan.X", "ss_x", direction=-1)
ss.y = xps.def_motor("scan.Y", "ss_y")
xps_traj = XPStraj(xps, "scan")

try:
    camES1       = setup_cam("camES1")
    camScope     = setup_cam("camScope")
except Exception as e:
    print(f"at least one of the cameras is not avaiable: {e}")


