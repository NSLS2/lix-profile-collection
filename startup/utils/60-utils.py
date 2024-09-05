print(f"Loading {__file__}...")

import os,threading,time
from ophyd import EpicsSignal
from PIL import Image,ImageDraw,ImageChops
from bluesky.suspenders import SuspendFloor
from bluesky.preprocessors import monitor_during_wrapper

beam_current = EpicsSignal('SR:OPS-BI{DCCT:1}I:Real-I')
bpm_current = EpicsSignal('XF:16IDB-CT{Best}:BPM0:Int')
PShutter = EpicsSignal('XF:16IDB-PPS{PSh}Enbl-Sts')
PShutter_open=EpicsSignal('XF:16IDA-PPS{PSh}Cmd:Opn-Cmd')
PShutter_close=EpicsSignal('XF:16IDA-PPS{PSh}Cmd:Cls-Cmd')
previous_beam_on_status = True
check_bm_period = 600
pauseFlag = EpicsSignal('XF:16IDC-ES{Zeb:1}:SOFT_IN:B1')

THRESH_BPM_I0 = 2.0e-7
THRESH_EM1_I0 = 0.1e6   # optimal should be >1.5e6

mon0 = "bpm_int_mean"

def get_cnts():
    RE(ct([em1,em2,bpm], num=1))
    d = db[-1].table()
    return {"bpm_int_mean": d['bpm_int_mean'][1], 
            "em1_sum_all_mean_value": d['em1_sum_all_mean_value'][1], 
            "em2_sum_all_mean_value": d['em2_sum_all_mean_value'][1]}

def scan_for_ctr(ax, scan_range=0.3, npts=31, opposite_dir=False,
                 mon="em1_sum_all_mean_value", nedge=4):
    """ ax should be "x" or "y"
    """
    
    if ax=='x':
        motors = [crl.x1, crl.x2]
    elif ax=='y':
        motors = [crl.y1, crl.y2]
    else:
        raise Exception(f"Unknown axis {ax} for CRL alignment")

    ref_cnts = get_cnts()
        
    if opposite_dir:
        RE(dscan([em1,em2,bpm], 
                 motors[0], -scan_range/2, scan_range/2,
                 motors[1], scan_range/2, -scan_range/2,
                 npts))
    else:
        RE(dscan([em1,em2,bpm], 
                 motors[0], -scan_range/2, scan_range/2,
                 motors[1], -scan_range/2, scan_range/2,
                 npts))
    
    data = db[-1].table()
    new_cnts = plot_data(data, mon, motors[0].name, motors[1].name, thresh=0.98, no_plot=True)
    
    if new_cnts[mon]<THRESH_EM1_I0 and new_cnts[mon]-ref_cnts[mon]<0.1*THRESH_EM1_I0:
        print(f"no obvious improvement in beam intensity ({ref_cnts[mon]} vs {new_cnts[mon]}), aborting ...")
        raise Exception()
    
    RE(mov(motors[0], new_cnts[motors[0].name],
           motors[1], new_cnts[motors[1].name]))
    
    # re-run alignment if the peak appears at the end of the scan
    pk_pos = np.argmax(data[mon])
    if pk_pos<nedge or pk_pos>len(data[mon])-nedge:
        print("peak too close to the edge, scan again ...")
        scan_for_ctr(ax=ax, scan_range=scan_range, npts=npts, opposite_dir=opposite_dir, mon=mon, nedge=nedge)
    else:
        print("done ...")
        
def align_crl():
    # this could be placed with the current CRL state
    #if "alignment" not in crl.saved_states.keys():
    #    crl.saved_states["alignment"] = [0, 0, 0, 0, 1, 1, 1, 1, 0]
    #crl.restore_state("alignment")

    data = get_cnts()
    if data[mon0]<THRESH_BPM_I0:
        print(f"intensity on the BPM {data[mon0]} is below the threshold {THRESH_BPM_I0}, aborting ...")
        raise Exception()

    scan_for_ctr("x", 0.3, 31, opposite_dir=False)
    scan_for_ctr("x", 0.3, 21, opposite_dir=True)
    scan_for_ctr("y", 0.3, 31, opposite_dir=False)
    scan_for_ctr("y", 0.3, 21, opposite_dir=True)

ref_beam_intensity = {"em1": 4200000, "em2": 160000}
beam_intensity_history = {"em1": [], "em2": [], "timestamp": []}    
    
def log_ref_intensity(thresh=0.05, update=False, md=None):    
    RE(ct([em1,em2], num=10, md=md)) 
    
    h = db[-1]
    sn='em1_sum_all_mean_value_monitor' if 'em1_sum_all_mean_value_monitor' in h.stream_names else 'primary' 
    Io = np.average(h.table(stream_name=sn)['em1_sum_all_mean_value'])        
    sn='em2_sum_all_mean_value_monitor' if 'em2_sum_all_mean_value_monitor' in h.stream_names else 'primary' 
    It = np.average(h.table(stream_name=sn)['em2_sum_all_mean_value'])        

    if update:
        ref_beam_intensity['em1'] = Io
        ref_beam_intensity['em2'] = It
    if np.fabs(ref_beam_intensity['em1']-It)/It>thresh:
        # do a scan if the intensity got higher as well
        return False
    beam_intensity_history['em1'].append(Io)
    beam_intensity_history['em2'].append(It)
    beam_intensity_history['timestamp'].append(time.time())
    return True
    
def check_beam(It_thresh=10000):
    md={'tag': 'alignment_check'}
    if ref_beam_intensity['em1'] is not None:
        if log_ref_intensity(md=md):
            return 
    
    mono.y.settle_time = 2
    RE(dscan([em1,em2], mono.y, -0.3, 0.3, 40, md=md))
    mono.y.settle_time = 0

    d = db[-1].table()
    x = d['dcm_y']
    y = d['em2_current1_mean_value']
    if np.max(y)<It_thresh:
        raise Exception("not seeing enough intensity on em2, a more thorough check is needed !")
    
    x0 = np.average(x[y>(1.-thresh)*np.max(y)])
    RE(mv(mono.y, x0))
    log_ref_intensity(update=True, md=md)
    
def verify_beam_on(beam_cur_thresh=300, bpm_cur_thresh=1.e-7):
    global previous_beam_on_status
    # returns True is the beam intensity is normal
    # for now just check ring current
    beam_on_status = (beam_current.get()>=beam_cur_thresh)
    if beam_on_status and not previous_beam_on_status:
        # if the ring current recovers from below the threshold, check alignment
        #log_ref_intensity()
        # for now just wait a bit longer
        time.sleep(600)
    previous_beam_on_status = beam_on_status
    # in case someone forgot to open the shutter
    if beam_on_status and previous_beam_on_status:
        while np.average(bpm_current.get())<bpm_cur_thresh:
            if not PShutter.get():
                input("open the shutter and hit any key to continue ...")
                return verify_beam_on(beam_cur_thresh, bpm_cur_thresh)
            else:
                raise Exception("BPM counts too low, check beam ...")
                print("BPM counts too low, attempting to re-align the beam ...")
                check_beam()
    return beam_on_status
    

def align_guardslit():
    gs_slits=['sg2.outboard','sg2.inboard','sg2.top','sg2.bottom']
    '''
    for i in gs_slits:
        print(i)
        #RE(dscan([em1,em2], i, -0.5,0.5,50))
        #h,d = fetch_scan()
    return i
    '''
    # scan outboard 
    print('scanning outboard slits')
    RE(dscan([em1,em2], sg2.outboard, -0.25,0.5,50))
    h,d = fetch_scan()
    xv=list(d.sg2_outboard)
    yv=list(d.em2_sum_all_mean_value)
    pk =  find_plateau_start(yv)
    sg2.outboard.move(xv[pk+1])
    print('outboard moved to %f',xv[pk+1])
    
    RE(dscan([em1,em2], sg2.inboard, -0.25,0.5,50))
    h,d = fetch_scan()
    xv=list(d.sg2_inboard)
    yv=list(d.em2_sum_all_mean_value)
    pk =  find_plateau_start(yv)
    sg2.inboard.move(xv[pk+1])
    print('inboard moved to %f',xv[pk+1])
    
    RE(dscan([em1,em2], sg2.top, -0.25,0.5,50))
    h,d = fetch_scan()
    xv=list(d.sg2_top)
    yv=list(d.em2_sum_all_mean_value)
    pk =  find_plateau_start(yv)
    sg2.top.move(xv[pk+1])
    print('top moved to %f',xv[pk+1])
    
    RE(dscan([em1,em2], sg2.bottom, -0.25,0.5,50))
    h,d = fetch_scan()
    xv=list(d.sg2_bottom)
    yv=list(d.em2_sum_all_mean_value)
    pk =  find_plateau_start(yv)
    sg2.bottom.move(xv[pk+1])
    print('bottom moved to %f',xv[pk+1])
    
def detector_config(motors, positions):
    #print(motors, positions)
    for mot,pos in zip(motors, positions):
        mot.move(pos).wait()
        time.sleep(0.5)
        #ready_for_robot.subid[mot.name] = mot.subscribe(cb, event_type='start_moving')   # any time the motor moves
    waxs_config.motors = motors

def detector_exp_move(config):
        if config=='solution':
            detector_config(motors=[saxs.x,saxs.y,saxs.z, waxs2.x, waxs2.y,waxs2.z], positions=[439,730,4000, 80, -105,281.5]) 
            print('moved detectors to solution config ...')
        elif config=='scanning':
            detector_config(motors=[saxs.x,saxs.y,saxs.z,waxs2.x, waxs2.y,waxs2.z], positions=[444,730,4250,51, -104.5,281.5]) 
            print('moved detectors to scanning config ...')
        else:
            raise Exception(f"unknown () for config={config}")
    
def find_plateau_start(data,thresh=1.005):
    """Finds the start of the plateau in a list of numbers.
    """

    # Initialize the start of the plateau to -1.
    start_of_plateau = -1

    # Iterate over the data.
    for i in range(len(data)):
        #print(i)
        # If the current value is different from the previous value,
        # then we have reached the start of the plateau.
        if not data[i+1] > thresh*data[i]:
            #print(data[i],data[i-1])
            start_of_plateau = i
            break

    # Return the start of the plateau.
    return start_of_plateau