print("loading configuration for microscope-EM ...")

ss = PositioningStackMicroscope()

## LC type encoder for sx/sz, MCS, mc22
## GxxxS type encoder for tx/tz, MCS, mc15
## may need to cycle power on the MCS for the SmarAct software to perform calib/homing
caput(ss.xc.prefix+".DIR", 1)

ss.x = xps.def_motor("scan.X", "ss_x", direction=-1)
ss.y = xps.def_motor("scan.Y", "ss_y")
if "rot" in xps.groups.keys():
    ss.ry = xps.def_motor("rot.rY", "ss_ry")
xps_traj = XPStraj(xps, "scan")

# fix dir/res of SmarAct gonio 
caput(ss.sx.prefix+".DIR", 1)
caput(ss.sz.prefix+".DIR", 0)
#caput(ss.tz.prefix+".MRES", 1e-5)
#caput(ss.tx.prefix+".MRES", 1e-5)

try:
    camES1       = setup_cam("camES1")
    camScope     = setup_cam("camScope")
except Exception as e:
    print(f"at least one of the cameras is not avaiable: {e}")

scan_park_xc = 100
ready_for_robot([], [], init=True)

def rbt_scanning(state):
    if state == "park":
        ready_for_robot(motors=[ss.x, ss.y, ss.xc, ss.sx, ss.sz], positions=[0, 0.5, scan_park_xc,0,0])
    else:
        ss.xc.move(0)
        ready_for_robot.EMready.put(0)
    
