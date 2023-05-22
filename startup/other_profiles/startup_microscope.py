print("loading configuration for microscope-EM ...")

ss = PositioningStackMicroscope()
caput(ss.xc.prefix+".DIR", 1)

ss.x = xps.def_motor("scan.X", "ss_x", direction=-1)
ss.y = xps.def_motor("scan.Y", "ss_y")
#ss.ry = xps.def_motor("rot.rY", "ss_ry")
xps.init_traj("scan")

# fix dir/res of SmarAct gonio 
caput(ss.sx.prefix+".DIR", 1)
caput(ss.sz.prefix+".DIR", 0)
caput(ss.tz.prefix+".MRES", 1e-5)
caput(ss.tx.prefix+".MRES", 1e-5)

try:
    camES1       = setup_cam("camES1")
    camScope     = setup_cam("camScope")
except Exception as e:
    print(f"at least one of the cameras is not avaiable: {e}")


