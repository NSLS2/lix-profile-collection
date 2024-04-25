print(f"Loading {__file__}...")

"""
    define type of experiment, and therefore additional startup script to load
    may need to run this to define the motors used in sample_handler_state
"""
### optical components
## White Beam Mirror
wbm = XYPitchMotor('XF:16IDA-OP{Mir:WBM', name='wbm')

## KB Mirror System
# Horizontal
hfm = KBMirrorHorizontal('XF:16IDA-OP{Mir:KBH', name="hfm")
# Vertical
vfm = KBMirrorVertical('XF:16IDA-OP{Mir:KBV', name='vfm')

## Slits
mps = Blades('XF:16IDA-OP{Slt:1', name='mps')

## Harmonic Rejection Mirror HRM1
#hrm1 = HRM1('XF:16IDC-OP{Mir:HRM1', name='hrm1')
## Harmonic Rejection Mirror HRM2
#hrm2 = HRM2('XF:16IDC-OP{Mir:HRM2', name='hrm2')

crl = Transfocator('XF:16IDC-OP{CRL', 9, 'crl')

### beam conditioning and diagnostics: slits, beam intensity monitors, shutter

## Beam Position Monitor
bpm_pos = XYMotor('XF:16IDB-BI{BPM:1', name='bpm_pos')

bpm2_pos = XYMotor('XF:16IDC-BI{BPM:2', name='bpm2_pos')

## Secondary Source Aperture (SSA)
ssa = Blades('XF:16IDB-OP{Slt:SSA1', name="ssa")

## Attenuator
# Absorber Set #1
#atn1x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X1}Mtr', name='atn1x')
# Absorber Set #2
#atn2x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X2}Mtr', name='atn2x')
# Absorber Set #3
#atn3x = EpicsMotor('XF:16IDB-OP{Fltr:Attn-Ax:X3}Mtr', name='atn3x')

## Divergence Defining Aperture (DDA)
dda = SlitsCenterAndGap('XF:16IDC-OP{Slt:DDA', name='dda')

## Beam Position Monitor (BPM)
#bimy = EpicsMotor('XF:16IDC-BI{BPM:2-Ax:Y}Mtr', name='bimy')

## Guard Slits 1
sg1 = SlitsCenterAndGap('XF:16IDC-OP{Slt:G1', name='sg1')

## Guard Slits 2, blade direction should be configured in EPICS
sg2 = Blades('XF:16IDC-OP{Slt:G2', name='sg2')

microscope = Microscope(name='microscope', concurrent=True)

### sample handling and sample environment
### experiment specific

global vacuum_sample_env

try:
    vacuum_sample_env
except:
    vacuum_sample_env = False

## vacuum system
# Maxi gauge controller IOC running on xf16idc-ioc1
ESVacSys = VacuumSystem(MKSGauge("XF:16IDC-VA{ES-TCG:1}"))

if vacuum_sample_env: # the nosecone and the microscope are connected
    # open the valves on the manifold
    IV1 = SolenoidValve("XF:16IDC-VA{ES-EV:Micrscp}")
    IV2 = SolenoidValve("XF:16IDC-VA{ES-EV:Nosecone}")
    ESVacSys.appendSection("SS", MKSGauge("XF:16IDB-VA{Chm:SS-TCG:2}"), 
                           EVName=["XF:16IDB-VA{Chm:SS-EV:1}", "XF:16IDB-VA{Chm:SS-EV:SoftPump1}"], 
                           VVName=["XF:16IDB-VA{Chm:SS-VV:1}", "XF:16IDB-VA{Chm:SS-VV:SoftPump1}"],
                           downstreamGVName="XF:16IDC-VA{Chm:SS-GV:1}")

    ESVacSys.appendSection("SF", MKSGauge("XF:16IDB-VA{Chm:SF-TCG:1}"), 
                           EVName=["XF:16IDC-VA{ES-EV:2}", "XF:16IDC-VA{ES-EV:SoftPump2}"], 
                           VVName=["XF:16IDC-VA{ES-VV:2}", "XF:16IDC-VA{ES-VV:SoftPump2}"],
                           downstreamGVName="XF:16IDC-VA{Chm:SF-GV:1}")

    ESVacSys.appendSection("sample", MaxiGauge("XF:16IDC-VA:{ES-Maxi:1}"), 
                           EVName=["XF:16IDC-VA{ES-EV:3}", "XF:16IDC-VA{ES-EV:SoftPump3}"], 
                           VVName=["XF:16IDC-VA{ES-VV:3}", "XF:16IDC-VA{ES-VV:SoftPump3}"],                           
                           downstreamGVName="XF:16IDC-VA{EM-GV:1}")

    ESVacSys.appendSection("WAXS", MKSGauge("XF:16IDB-VA{det:WAXS-TCG:1}"), 
                           EVName=["XF:16IDC-VA{ES-EV:4}", "XF:16IDC-VA{ES-EV:SoftPump4}"], 
                           VVName=["XF:16IDC-VA{ES-VV:4}", "XF:16IDC-VA{ES-VV:SoftPump4}"],
                           downstreamGVName=None)    
    # keep these valves at whatever states they are in
    #ESVacSys.VSmap[ESVacSys.VSindex["sample"]]['EV'].close()
    #ESVacSys.VSmap[ESVacSys.VSindex["sample"]]['VV'].close() 
    while IV1.status==0 or IV2.status==0:
        input("For in-vacuum ops, check sys config, open IV1 and IV2, then hit return ...")
else:
    ESVacSys.appendManifold("EMmf", 
                            ["XF:16IDC-VA{ES-EV:3}", "XF:16IDC-VA{ES-EV:SoftPump3}"], 
                            ["XF:16IDC-VA{ES-VV:3}", "XF:16IDC-VA{ES-VV:SoftPump3}"])

    ESVacSys.appendSection("SS", MKSGauge("XF:16IDB-VA{Chm:SS-TCG:2}"), 
                           EVName=["XF:16IDB-VA{Chm:SS-EV:1}", "XF:16IDB-VA{Chm:SS-EV:SoftPump1}"], 
                           VVName=["XF:16IDB-VA{Chm:SS-VV:1}", "XF:16IDB-VA{Chm:SS-VV:SoftPump1}"],
                           downstreamGVName="XF:16IDC-VA{Chm:SS-GV:1}")

    ESVacSys.appendSection("SF", MKSGauge("XF:16IDB-VA{Chm:SF-TCG:1}"), 
                           EVName=["XF:16IDC-VA{ES-EV:2}", "XF:16IDC-VA{ES-EV:SoftPump2}"], 
                           VVName=["XF:16IDC-VA{ES-VV:2}", "XF:16IDC-VA{ES-VV:SoftPump2}"],
                           downstreamGVName="XF:16IDC-VA{Chm:SF-GV:1}")

    ESVacSys.appendSection("microscope", MaxiGauge("XF:16IDC-VA:{ES-Maxi:1}"), #MKSGauge("XF:16IDB-VA{EM-TCG:2}"), 
                           manifoldName="EMmf", IVName="XF:16IDC-VA{ES-EV:Micrscp}",
                           downstreamGVName=None)

    ESVacSys.appendSection("nosecone", MaxiGauge("XF:16IDC-VA:{ES-Maxi:2}"), #MKSGauge("XF:16IDB-VA{EM-TCG:1}", 
                           manifoldName="EMmf", IVName="XF:16IDC-VA{ES-EV:Nosecone}",
                           downstreamGVName="XF:16IDC-VA{EM-GV:1}")

    ESVacSys.appendSection("WAXS", MKSGauge("XF:16IDB-VA{det:WAXS-TCG:1}"), 
                           EVName=["XF:16IDC-VA{ES-EV:4}", "XF:16IDC-VA{ES-EV:SoftPump4}"], 
                           VVName=["XF:16IDC-VA{ES-VV:4}", "XF:16IDC-VA{ES-VV:SoftPump4}"],
                           downstreamGVName=None)


## robot is defined in 19-robot



### detectors, detector positioner, trigger

## Detector Positioning Stages 
saxs = XYZMotor('XF:16IDC-ES{Stg:SAXS', name='saxs')
waxs1 = XYZMotor('XF:16IDC-ES{Stg:WAXS1', name='waxs1')
waxs2 = XYZMotor('XF:16IDC-ES{Stg:WAXS2', name='waxs2')

## SAXS Beamstop
sbs = XYMotor('XF:16IDC-ES{BS:SAXS', name='sbs')
