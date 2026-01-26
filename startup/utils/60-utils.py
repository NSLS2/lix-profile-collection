print(f"Loading {__file__}...")

import os,threading,time
from ophyd import EpicsSignal
from PIL import Image,ImageDraw,ImageChops
from bluesky.suspenders import SuspendFloor
from bluesky.preprocessors import monitor_during_wrapper
import cv2
from itertools import product
from pyzbar.pyzbar import decode,ZBarSymbol
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

import tiled

from blop import RangeDOF, Objective, Agent
import numpy as np

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

c = tiled.client.from_profile('lix')


def intensity_metric(image, background=None, threshold_factor=0.1, edge_crop=0):
    # Convert to grayscale
    image = image.squeeze()
    if len(image.shape) == 3 and image.shape[0] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Crop edges to remove artifacts
    if edge_crop > 0:
        gray = gray[edge_crop:-edge_crop, edge_crop:-edge_crop]
        if background is not None:
            background = background[edge_crop:-edge_crop, edge_crop:-edge_crop]
    
    # Background subtraction
    if background is None:
        background = np.zeros_like(gray)
    else:
        if len(background.shape) == 3:
            background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    corrected = cv2.subtract(gray, background)
    corrected = cv2.GaussianBlur(corrected, (5, 5), 0)
    max_intensity = np.max(corrected)
    if max_intensity == 0:
        return float('inf'), None, {}
        
    thresh_value = threshold_factor * max_intensity
    _, thresh = cv2.threshold(corrected, thresh_value, 255, cv2.THRESH_TOZERO)
    
    # ========== TOTAL INTENSITY ==========
    # Total integrated intensity
    total_intensity = np.sum(thresh)
    
    return total_intensity


def scnSF_intensity_evaluation(
    uid: str,
    suggestions: list[dict],
    threshold_factor: float = 0.1,
    edge_crop: int = 0,
) -> list[dict]:

    run = c[uid]
    images = run[f"primary/{scnSF.cam.name}_image"].read()
    suggestion_ids = [suggestion["_id"] for suggestion in run.metadata["start"]["blop_suggestions"]]
    results = []

    for idx, sid in enumerate(suggestion_ids):
        beam_intensity = intensity_metric(images[idx].squeeze(), threshold_factor=threshold_factor, edge_crop=edge_crop)
        results.append({
            "beam_intensity": beam_intensity,
            "_id": sid
        })

    return results


def bpm_intensity_evaluation(uid: str, suggestions: list[dict], det=em1) -> list[dict]:
    run = c[uid]
    em1_sum_all_mean_value = run[f"primary/{det.name}_sum_all_mean_value"].read()
    suggestion_ids = [suggestion["_id"] for suggestion in run.metadata["start"]["blop_suggestions"]]
    results = []

    for idx, sid in enumerate(suggestion_ids):
        beam_intensity = em1_sum_all_mean_value[idx]
        results.append({
            "beam_intensity": beam_intensity,
            "_id": sid
        })

    return results


def align_crl(rep=32, x_range=0.6, y_range=0.6, det=em1):

    pos_x10 = crl.x1.position
    pos_x20 = crl.x2.position
    pos_y10 = crl.y1.position
    pos_y20 = crl.y2.position

    # crl.x1 4.4
    # crl.x2 7.6
    dofs_x = [
        RangeDOF(
            actuator=crl.x1,
            bounds=(pos_x10-x_range/2, pos_x10+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.x2,
            bounds=(pos_x20-x_range/2, pos_x20+x_range/2),
            parameter_type="float",
        ),
    ]

    dofs_y = [
        RangeDOF(
            actuator=crl.y1,
            bounds=(pos_y10-y_range/2, pos_y10+y_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y2,
            bounds=(pos_y20-y_range/2, pos_y20+y_range/2),
            parameter_type="float",
        ),
    ]

    if det.name == "camSF":
        objective_name = "beam_intensity"
        evaluation_function = scnSF_intensity_evaluation
    else:
        objective_name = f"{det.name}_sum_all_mean_value"
        evaluation_function = bpm_intensity_evaluation

    objectives = [
        Objective(name=objective_name, minimize=False),
    ]

    dets = [det]

    agent_x = Agent(dofs=dofs_x, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    agent_y = Agent(dofs=dofs_y, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    
    agent_x.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )
    agent_y.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )

    RE(fast_shutter_wrapper(agent_x.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    #agent_x.plot_objective(crl.x1.name, crl.x2.name, objective_name)
    best_parameterization = agent_x.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for x: {best_parameterization}")
    crl.x1.move(best_parameterization['crl_x1']) # ['crl_x1'][0]
    crl.x2.move(best_parameterization['crl_x2']) # [0]

    RE(fast_shutter_wrapper(agent_y.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    #agent_y.plot_objective(crl.y1.name, crl.y2.name, objective_name)
    print(f"best parameterization for y: {best_parameterization}")
    best_parameterization = agent_y.ax_client.get_best_parameterization()[0]
    crl.y1.move(best_parameterization['crl_y1']) # [0]
    crl.y2.move(best_parameterization['crl_y2']) # [0]

    return agent_x, agent_y


def get_cnts():
    RE(ct([em1,em2,bpm], num=1))
    #d = db[-1].table()
    d = c[-1]['primary'].read()
    #return {"bpm_int_mean": d['bpm_int_mean'][1], 
    #        "em1_sum_all_mean_value": d['em1_sum_all_mean_value'][1], 
    #        "em2_sum_all_mean_value": d['em2_sum_all_mean_value'][1]}
    return {"bpm_int_mean": float(d['bpm_int_mean'][0]), 
            "em1_sum_all_mean_value": float(d['em1_sum_all_mean_value'][0]), 
            "em2_sum_all_mean_value": float(d['em2_sum_all_mean_value'][0])}


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
        
def align_crl0(mon="em2_sum_all_mean_value"):
    # this could be placed with the current CRL state
    #if "alignment" not in crl.saved_states.keys():
    #    crl.saved_states["alignment"] = [0, 0, 0, 0, 1, 1, 1, 1, 0]
    #crl.restore_state("alignment")

    data = get_cnts()
    if data[mon0]<THRESH_BPM_I0:
        print(f"intensity on the BPM {data[mon0]} is below the threshold {THRESH_BPM_I0}, aborting ...")
        raise Exception()

    scan_for_ctr("x", 0.4, 31, opposite_dir=False, mon=mon)
    scan_for_ctr("x", 0.4, 21, opposite_dir=True, mon=mon)
    scan_for_ctr("y", 0.4, 31, opposite_dir=False, mon=mon)
    scan_for_ctr("y", 0.4, 21, opposite_dir=True, mon=mon)

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

def read_code(img, target="3QR", crop_x=1, crop_y=1, debug=True, fn="cur.jpg"):
        h,w = img.shape[:2]
        x1 = int(w*(1-crop_x)/2)
        x2 = int(w*(1+crop_x)/2)
        y1 = int(h*(1-crop_y)/2)
        y2 = int(h*(1+crop_y)/2)

        f1 = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        #f2 = cv2.convertScaleAbs(f1, alpha=1.6, beta=0)
        #f3 = cv2.medianBlur(f2, 1)
        #f4 = cv2.adaptiveThreshold(f3, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        #                           cv2.THRESH_BINARY, 31, 5)

        ret = {}
        for th,bkg in product(range(21,35,4), range(1,9,2)):
            f4 = cv2.adaptiveThreshold(f1, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                       cv2.THRESH_BINARY, th, bkg)
            d = decode(f4, symbols=[ZBarSymbol.QRCODE])
            for i in range(len(d)):
                k = d[i].data.decode()
                if not k in ret.keys():
                    ret[k] = d[i]
        cs = list(ret.values())
        
        cv2.imwrite(f"img/raw-{fn}", f1)
        cv2.imwrite(f"img/cur0.jpg", f1)
        cv2.imwrite(f"img/cur.jpg", f4)
        #cv2.imwrite(f"img/{fn}", f4)

        if target=="3QR": # expecting 3x QR codes 
            cs = decode(f4, symbols=[ZBarSymbol.QRCODE]) 
            code = {}
            for cc in cs:
                xi = 2-int(cc.rect.left/400) # has to so with the orientation of the camera
                code[chr(xi+ord('a'))] = cc.data.decode("utf-8") 
        elif target=="1QR": # 1x QR code
            cs = decode(f4, symbols=[ZBarSymbol.QRCODE]) 
            #print(cs)
            if len(cs)!=1:
                print(f"ERR: {len(cs)} code(s) were read, expecting 1")
                code = [] 
            else:
                code = [cs[0].data.decode("utf-8")]
                #print(code)
        elif target=="1bar": # 1x code128 barcode
            cs = decode(f4, symbols=[ZBarSymbol.CODE128]) 
            if len(cs)!=1:
                print(f"ERR: {len(cs)} code(s) were read, expecting 1")
                code = []
            else:
                code = [cs[0].data.decode("utf-8")]

        if debug:
            print(cs)
        return code


def sol_cam_roi_trigger_setup(ywidth=80,xwidth=200):
    nd_list = ['upstream','downstream']
    for nd in nd_list:
        print(nd)
        sol.wash_needle(nd)
        fcell = sol.flowcell_nd[nd]
        sol.select_flow_cell(fcell)
        time.sleep(5)
        print('base value = ', sol.cam.watch_list[nd]['base_value'])
        if nd == "upstream":
            img = sol.cam.snapshot()
            #img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            f1=img.sum(axis=1)
            f0=img.sum(axis=0)
            f1_smooth = uniform_filter1d(f1,size=50)
            f0_smooth = uniform_filter1d(f0,size=50)
            peaks, it = find_peaks(f1_smooth, height=np.min(f1_smooth)*10)
            peaks0, it0 = find_peaks(f0_smooth, height=np.min(f0_smooth)*10)
            print(peaks)
            print(peaks0)
            ymin=peaks[1]-ywidth/2
            ysize = ywidth
            xmin = peaks0[2]-xwidth/2
            xsize = xwidth
            xmax = xmin + xsize
            ymax = ymin + ysize
            #baseline = np.sum(img[xmin:xmax,ymin:ymax])
            #baseline=1
            sol.cam.roi4.min_xyz.min_x.put(xmin)
            sol.cam.roi4.min_xyz.min_y.put(ymin)
            sol.cam.roi4.size.x.put(xwidth)
            sol.cam.roi4.size.y.put(ywidth)
            print('roi4 set for solution data triggering')
            baseline = sol.cam.stats4.total.get()
            sol.cam.watch_list[nd]['base_value']=baseline
            thresh=baseline-baseline*0.9
            sol.cam.watch_list[nd]['thresh']=thresh
        else:
            baseline = sol.cam.stats4.total.get()
            sol.cam.watch_list[nd]['base_value']=baseline
            thresh=baseline-baseline*0.9
            sol.cam.watch_list[nd]['thresh']=thresh
    print("new trigger baseline and threshold updated in current BSUI session")
