from py4xs.hdf import h5exp
import time,sys,random,openpyxl
import pandas as pd
from bluesky.preprocessors import monitor_during_wrapper
from lixtools.samples import parseHolderSpreadsheet as get_samples
from lixtools.samples import get_holders_under_config,autofillSpreadsheet,parseSpreadsheet
from py4xs.utils import get_grid_from_bin_ranges
q_bin_ranges = [[[0.0045, 0.0995], 95], [[0.0975, 0.6025], 101], [[0.605, 2.905], 150]]
qgrid2 = get_grid_from_bin_ranges(q_bin_ranges)
qgrid= np.hstack((np.arange(0.007, 0.0999, 0.001),
                   np.arange(0.1, 2.995, 0.005),
                   np.arange(3.0, 3.13, 0.01),
                   np.arange(3.14, 3.2, 0.02)))
ss = PositioningStack()
ss.x = xps.def_motor("scan.X", "ss_x", direction=-1)
ss.y = xps.def_motor("scan.Y", "ss_y")
xps_traj = XPStraj(xps, "scan")
#xps.init_traj("scan")
#ss.x.traj = xps.traj
#ss.y.traj = xps.traj

sol = SolutionScatteringExperimentalModule(camName="camES2")

reload_macros("/nsls2/data/lix/shared/config/SolutionScattering/config.py")
sol.ready_for_hplc.set(0)

import pandas
import numpy as np

min_load_volume = 20

def gettimestamp():
    ts = time.localtime()
    return f"{ts.tm_year}-{ts.tm_mon:02d}-{ts.tm_mday:02d}_{ts.tm_hour:02d}{ts.tm_min:02d}"

def pack_ref_h5(run_id, **kwargs):
    uids = list_scans(run_id=run_id, holderName="reference", **kwargs)
    send_to_packing_queue('|'.join(uids), "multi")    
    # consider adding the ref intensity to the h5 file, need to know when the file is ready
    
def plot_ref_h5():
    pass
    
def collect_std(r_range=1.5):
    holderName = "std"
    md = {'holderName': holderName}
    pil.use_sub_directory(holderName)
    pil.set_trigger_mode(PilatusTriggerMode.soft)
    pil.set_num_images(1)
    pil.exp_time(0.2)
    ts = gettimestamp()

    sol.select_flow_cell('std', r_range=r_range)    

    change_sample(f"AgBH-{ts}")
    RE(ct([pil,em1,em2], num=1, md=md))
    
    pil.use_sub_directory()

    # now pack h5 file and recalibrate
    pack_h5([last_scan_uid], fn="std.h5")
    dexp = h5exp("exp.h5")
    dexp.recalibrate("std.h5",energy=pseudoE.energy.readback.value/1000)

    dexp.detectors[0].fix_scale = 0.93
    dexp.detectors[1].fix_scale = (dexp.detectors[0].exp_para.Dd/dexp.detectors[1].exp_para.Dd)**2
    dexp.save_detectors()
    
def collect_reference_from_tube12():
    nd_list = ['upstream','downstream']
    holderName='reference'
    md = {'holderName': holderName}
    pil.use_sub_directory(holderName)
    ts = gettimestamp()   
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.set_num_images(5)
    pil.exp_time(1)
    
    sol.select_flow_cell("empty")
    sname = f"empty_{ts}"
    change_sample(sname)
    sd.monitors = []
    RE(ct([pil,em1,em2], num=5, md=md))

    for pos in [1,2]:
        nd = sol.verify_needle_for_tube(pos, None)
        fcell = sol.flowcell_nd[nd]
        sol.select_flow_cell(fcell)
        sol.wash_needle(nd) #, option="wash only")
        sname = f"{fcell}_blank_{ts}"
        change_sample(sname)
        sd.monitors = []
        RE(ct([pil,em1,em2], num=5), md=md)
        sname = f"{fcell}_water_{ts}"
        sol.measure(pos, sample_name=sname, exp=1, repeats=5, md=md)
    pil.use_sub_directory()

def collect_reference():
    nd_list = ['upstream','downstream']
    holderName='reference'
    md = {'holderName': holderName}
    pil.use_sub_directory(holderName)
    ts = gettimestamp()   
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.set_num_images(5)
    pil.exp_time(1)
    
    sol.select_flow_cell("empty")
    sname = f"empty_{ts}"
    change_sample(sname)
    RE(ct([pil,em1,em2], num=5, md=md))

    for nd in nd_list:
        fcell = sol.flowcell_nd[nd]
        sol.select_flow_cell(fcell)
        sol.wash_needle(nd) #, option="wash only")
        
        for ref in ['blank', 'water']:  #,'blank']:
            sname = f"{fcell}_{ref}_{ts}"
            #if ref=='blank':
            #    sol.wash_needle(nd, option="dry only")
            if ref=='water':
                sol.ctrl.water_pump_spd.put(0.3) 
                sol.wash_needle(nd, option="wash only")
                sol.ctrl.water_pump_spd.put(0.8)         
                sol.load_water(nd, vol=50)
            change_sample(sname)
            RE(ct([pil,em1,em2], num=5, md=md))
            sol.wash_needle(nd, option="dry only")
    pil.use_sub_directory()

                
def measure_holder(spreadSheet, holderName, sheet_name='Holders', exp_time=0.5, repeats=10, vol=45, 
                   returnSample=True, concurrentOp=False, checkSampleSequence=False, 
                   em2_thresh=30000,  check_bm_period=900, check_beam=True):
    #print('collecting reference')
    #collect_reference()
    #pack_ref_h5(run_id)
    samples = get_samples(spreadSheet, holderName=holderName, sheet_name=sheet_name)

    uids = []
    if concurrentOp: # and checkSampleSequence:
        # count on the user to list the samples in the right sequence, i.e. alternating 
        # even and odd tube positions, so that concurrent op makes sense
        spos = np.asarray([samples[k]['position'] for k in samples.keys()])
        if ((spos[1:]-spos[:-1])%2 == 0).any():
            raise Exception('the sample sequence is not optimized for concurrent ops.')
    
    update_metadata()
    pil.use_sub_directory(holderName)
    print(holderName)
    print(samples)
    sol.wash_needle('downstream')
    sol.wash_needle('upstream')
    for k,s in samples.items():
        check_pause()
        if 'exposure' in s.keys():
            exp_time = s['exposure']
        if 'volume' in s.keys():
            vol = s['volume']
        while True:
            # make sure the beam is on, wait if not
            while not verify_beam_on() and check_beam:
                time.sleep(check_bm_period)

            sol.measure(s['position'], vol=vol, exp=exp_time, repeats=repeats, sample_name=k, 
                        returnSample=returnSample, concurrentOp=concurrentOp, md={'holderName': holderName})
            
            # check beam again, in case that the beam dropped out during the measurement
            while check_beam: 
                if verify_beam_on():
                    break
                # wash the needle first in case we have to wait for the beam to recover
                sol.wash_needle(sol.verify_needle_for_tube(s['position'], None))   
                time.sleep(check_bm_period)
            # check whether the beam was on during data collection; if not, repeat the previous sample
            bim = db[-1].table(stream_name='em2_sum_all_mean_value_monitor')['em2_sum_all_mean_value'] 
            if np.average(bim[-10:])>em2_thresh or not check_beam:  
                break
                # otherwise while loop repeats, the sample is measured again
            
        uids.append(db[-1].start['uid'])
        print(k,":",s)
        
    pil.use_sub_directory()
    HT_pack_h5(samples=samples, uids=uids)
        
    for nd in sol.needle_dirty_flag.keys():
        if sol.needle_dirty_flag[nd]:
            sol.wash_needle(nd)
    
    return uids,samples


def check_pause():
    if sol.ctrl.pause_request.get():
        sol.ctrl.pause_request.put(2)
        rbt.park()
        print("data collection paused ... ", end="")
        t0 = time.time()
    else:
        return
    
    
    while sol.ctrl.pause_request.get()>0:
        print(f"data collection paused ... {int(time.time()-t0)}  \r", end="")
        sys.stdout.flush()
        time.sleep(1)
    rbt.goHome()
            
    
def auto_measure_samples(spreadSheet, configName, exp_time=0.5, repeats=10, vol=45, sim_only=False,
                        returnSample=True, concurrentOp=False, checkSampleSequence=False):
    """ measure all sample holders defined in a given configuration in the spreadsheet
    """
    if data_path is None:
        raise exception("login first !")
    if sol.HolderPresent.get():
        raise Exception("A sample holder is still in the sample handler !")

    if isinstance(configName, str): # for on-site measurements, read configuration from spreadsheet 
        sheet_name = "Holders"
        samples = get_samples(spreadSheet, sheet_name=sheet_name, configName=configName)
        holders = get_holders_under_config(spreadSheet, configName)
    else: # for mail-in, derive configuration for the all existing holders
        sheet_name = 0
        holders = configName  # called from measure_mailin_spreadsheets()

    rbt.goHome()
    for p in list(holders.keys()):
        sol.select_flow_cell('bottom')
        print('mounting tray from position', p)
        
        sol.disable_ctrlc()
        rbt.loadTray(p)
        #sol.select_tube_pos('park')
        sol.park_sample()
        rbt.mountTray()
        sol.enable_ctrlc()

        print('mounted tray =', p)
        holderName = holders[p]

        if sim_only:
            sol.select_tube_pos(1)
            countdown("simulating data collection ", 60)
        else:
            uids,samples = measure_holder(spreadSheet, holderName, sheet_name=sheet_name,
                                          exp_time=exp_time, repeats=repeats, vol=vol,
                                          returnSample=returnSample, concurrentOp=concurrentOp,
                                          checkSampleSequence=checkSampleSequence)

        #sol.select_tube_pos('park')
        sol.park_sample()
        sol.disable_ctrlc()
        try:  # this sometimes craps out, but never twice in a row
            rbt.unmountTray()
        except:
            rbt.unmountTray()
        #rbt.unloadTray(d['holderPosition'][i])
        rbt.unloadTray(p)
        sol.enable_ctrlc()

    rbt.park()

import socket,time,json

class sock_client:
    def __init__(self, sock_addr):
        self.sock_addr = sock_addr
        self.delay = 0.05
    
    def clean_up(self):
        if self.sock is not None:
            self.sock.close()

    def send_msg(self, msg):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(self.sock_addr)   
        sock.send(msg.encode('ascii'))
        time.sleep(self.delay)
        ret = sock.recv(1024).decode('ascii')
        sock.close()
        return ret

def checkQRcodes(cs, locs):
    Flocs = []
    Fuids = []
    camcmd = {"target": "1QR", "zoom": 400, "focus": 45, "exposure": 140}

    rbt.goHome()
    for loc in locs:
        sol.disable_ctrlc()
        rbt.loadTray(loc)
        for tt in range(80,150,5):
            camcmd['exposure'] = tt
            camcmd['slot'] = loc
            uid = json.loads(cs.send_msg(json.dumps(camcmd)))
            if len(uid)>0:
                Flocs.append(loc)
                Fuids.append(uid[0])
                print(f"found {uid[0]} in pos {loc}")
                break
        rbt.unloadTray(loc)
        sol.enable_ctrlc()

    return Flocs,Fuids

def measure_mailin_spreadsheets(sh_list, sample_locs=None, check_QR_only=False):
    """ each spreadsheet should contain:
            1. the first sheet is named as proposal#_SAF#
            2. a "UIDs" tab that lists all sample holder names and UIDs
    """
    cs = sock_client(('10.66.123.29', 9999)) # webcam on merkat - xf16id-ioc2

    if sample_locs is None:
        sample_locs = list(range(1,21))
    all_locs = [i for i in sample_locs if caget(f"XF:16IDC-ES:Chalet{{ctrl}}tray{i:02d}_sts")>0]
    storage_locs = []
    storage_uids = []
    Slocs = all_locs

    while True:
        locs,uids = checkQRcodes(cs, Slocs)
        storage_locs += locs
        storage_uids += uids
        if len(storage_locs)==len(all_locs):
            break
        Slocs = [loc for loc in all_locs if not loc in storage_locs]
        print(f"QR codes were not found at these locations: {Slocs}")
        ans = input("Retry?? (type 'no' to skip): ") 
        if 'n' in ans or 'N' in ans:
            break

    print(f"found sample holders with QR codes at these locations: {storage_locs}")
    print(f"UIDs: {storage_uids}")

    if check_QR_only:
        return         
    
    if isinstance(sh_list, str):
        sh_list = [sh_list]
    for sh in sh_list:
        wb = openpyxl.load_workbook(sh)
        try:
            [prop_id, saf_id] = np.asarray((wb.sheetnames[0].split("-")), dtype=int)
        except:
            print(f"Unable to get proposal and SAF IDs from {wb.sheetnames[0]}")
            continue
        if not "UIDs" in wb.sheetnames:
            print(f"{sh} does not contain holder UIDs.")
            continue

        login("bot", f"{prop_id}", f"{saf_id}")
        hdict = parseSpreadsheet(sh, "UIDs", ["holderName"])
        hlist = list(hdict['holderName'].values())
        ulist = list(hdict['UID'].values())
        holders = {}
        for hn,uid in zip(hlist,ulist):
            if not uid in storage_uids:
                print(f"holder {hn} is not in storge.")
                continue
            loc = storage_locs[storage_uids.index(uid)]
            holders[loc] = hn
        auto_measure_samples(sh, holders)
        logoff(quiet=True)


def HT_pack_h5(spreadSheet=None, holderName=None, 
               run_id=None, samples=None, uids=None, **kwargs):
    """ this is useful for packing h5 after the experiment
        it will not perform buffer subtraction
    """
    if samples is None:
        samples = get_samples(spreadSheet, holderName=holderName, sheet_name=0)
    if uids is None:
        uids = list_scans(run_id=run_id, holderName=holderName, **kwargs)

    sb_dict = {}
    for s in samples.keys():
        if 'bufferName' in samples[s].keys():
            sb_dict[s] = [samples[s]['bufferName']]
    uids.append(json.dumps(sb_dict))
    send_to_packing_queue('|'.join(uids), "sol")
    

# the following functions are for SEC measurements      
""" 
def CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name='Samples'):
    Creates the agilent sequence file from the spreadsheet. User input is batchID, sample_name and method for hplc. The other columns are necessary for generating the proper formatted sequence file

    strFields=["Vial", "Sample Name", "Sample Type", "Acq. method", "Proc. method", "Data file", "Buffer", "Valve Position"]
    numFields=["Volume"]
    dd=parseSpreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
    print(f"this is {dd}")
    autofillSpreadsheet(dd, fields=["batchID"])
    print(dd['batchID'].keys())
    print(dd['batchID'].values())
    print(dd['Valve Position'].values())
    
    if proposal_id is None or run_id is None:
        print("need to login first ...")
        login()
    
    ridx=[i for i in dd['batchID'].keys() if dd['batchID'][i]==batchID]
    print(f"{ridx} this is ridx")

    
    samples = {}
    dfile = f"{current_cycle}/{proposal_id}/{run_id}/<S>" 
    dd["Data File"] = {}
    dd["Sample Type"] = {}
    valve_position = {}
        
    for i in ridx:
        for f in numFields:
            if not (isinstance(dd[f][i], int or isintance(dd[f][i], float))):
                raise Exception(f"not a numeric value for {f}: {dd[f][i].values()}, replace with number")
        valve_position[i] = dd["Valve Position"][i]
        print(valve_position)
        sn = dd['Sample Name'][i]
        samples[sn] = {"acq time": dd['Run Time'][i], 
                       "md": {"Column type": dd['Column type'][i],
                              "Injection Volume (ul)": dd['Volume'][i],
                              "Flow Rate (ml_min)": dd['Flow Rate'][i],
                              "Sample buffer":dd['Buffer'][i],
                              "Valve Position":valve_position[i]}
                      }
        dd["Data File"][i] = dfile
        dd["Valve Position"][i]
        dd["Sample Type"][i] = "Sample"
    sequence_path="/nsls2/data/lix/legacy/HPLC/Agilent/"
    df=pd.DataFrame.from_dict(dd, orient='columns')
    df[df['batchID']==batchID].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                    columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data File" ])

    return samples, valve_position  
"""
    
def collect_hplc(sample_name, exp, nframes,md=None):
    _md = {"experiment": "HPLC"}
    _md.update(md or {})
    change_sample(sample_name)
    pil.use_sub_directory(sample_name)
    sol.select_flow_cell('middle')
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.set_num_images(nframes)
    pil.exp_time(exp)
    update_metadata()
      
    #sol.ready_for_hplc.set(1)
    while sol.hplc_injected.get()==0:
        if sol.hplc_bypass.get()==1:
            sol.hplc_bypass.put(0)
            break
        sleep(0.2)

    #sol.ready_for_hplc.set(0)
    start_monitor([em1,em2], rate=4)
    RE(monitor_during_wrapper(ct([pil], num=nframes, md=_md), [em1.ts.SumAll, em2.ts.SumAll]))
    sd.monitors = []
    pil.use_sub_directory()
    change_sample()
     
"""
def run_hplc_from_spreadsheet(spreadsheet_fn, batchID, sheet_name='Samples', exp=1, shutdown=False):
    batch_fn = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
    samples, valve_position = CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)
    print(f"HPLC sequence file has been created: {batch_fn}")
    input("please start batch data collection from the Agilent software, then hit enter:")
    for sn in samples.keys():
        print(f"collecting data for {sn} ...")
        # for hardware multiple trigger, the interval between triggers is slightly longer
        #    than exp. but this extra time seems to fluctuates. it might be safe not to include
        #    it in the caulcation of nframes
        collect_hplc(sn, exp=exp, nframes=int(samples[sn]["acq time"]*60/exp), md={'HPLC': samples[sn]['md']})   
        uid=db[-1].start['uid']
        send_to_packing_queue(uid, "HPLC")
    pil.use_sub_directory()    
    print('batch collection collected for %s from %s' % (batchID,spreadsheet_fn))
"""

# solution scattering, prep function
def prime_syringe(loops=1):
    sol.select_tube_pos(0)
    sol.ctrl.sv_drain1.put('on')
    sol.ctrl.sv_drain2.put('on')
    for a in range(0,loops):
        sol.ctrl.valve_pos.put('res')
        sol.ctrl.pump_mvA(240)
        sol.ctrl.wait()
        sol.ctrl.valve_pos.put('sam')
        sol.ctrl.pump_mvA(10)
        sol.ctrl.wait()
        print('done sequence number {}'.format(a))
    sol.ctrl.sv_drain1.put('off')
    sol.ctrl.sv_drain2.put('off')

def tube_load(tn=2,vol=45,option="uptocell"):
    row=sol.verify_needle_for_tube(tn,nd=None)
    sol.select_tube_pos(tn)
    sol.load_sample(vol)
    sol.prepare_to_measure(row)
    if option != "uptocell":
        print('flowing sample through the cell')
        sol.ctrl.pump_mvR(vol)
    else:
        print(row)
        print('liquid stopped before the cell')

def recalibrate_trigger(delay=5,tlist=[1,2],push=15,thresh=0.5):
    nd_list = ['upstream','downstream']
    for nd in nd_list:
        print(nd)
        sol.wash_needle(nd)
        fcell = sol.flowcell_nd[nd]
        sol.select_flow_cell(fcell)
        time.sleep(5)
        sol.cam.watch_list[nd]['base_value']=sol.cam.stats1.total.get()
        print('base value = ', sol.cam.watch_list[nd]['base_value'])
        if nd == "upstream":
            for num in tlist:
                if num % 2 == 0:
                    print(num, end=" ")
                    tube_load(tn=num,vol=45,option=None)
                    sol.ctrl.wait()
        else:
            for num in tlist:
                if num % 2 != 0:
                    print(num, end=" ")
                    tube_load(tn=num,vol=45,option=None)
                    sol.ctrl.wait()
        #sol.ctrl.pump_mvR(push)
        #sol.ctrl.wait()
        #time.sleep(delay)
        st_filled=sol.cam.stats1.total.get()
        diff1=np.abs(sol.cam.watch_list[nd]['base_value']-st_filled)
        print(diff1)
        diff=np.abs(sol.cam.watch_list[nd]['base_value']-st_filled)*thresh
        print('threshhold = ',diff)
        sol.cam.watch_list[nd]['thresh']=diff
        sol.return_sample()
        sol.wash_needle(nd)
    print("new trigger baseline and threshold updated in current BSUI session")
    

# the following functions are for fixed sample measurements 
    
def mc_pack_h5(spreadSheet, holderName, run_id, T=None,
               froot=data_file_path.ramdisk, **kwargs ):
    if T is None:
        samples = get_samples(spreadSheet, holderName, check_sname=False)
    else:
        ts = get_samples(spreadSheet, holderName, check_sname=False)
        samples = {}
        for sn in ts.keys():
            sn1 = sn+('_T%.1fC' % T)
            samples[sn1] = ts[sn]
        holderName += ('_T%.1fC' % T)

    uids = list_scans(run_id=run_id, holderName=holderName, **kwargs)
    send_to_packing_queue('|'.join(uids), "multi", froot)    

def mc_measure_sample(pos, sname='test', exp=0.5, rep=1, check_sname=True, cell_form=None):
    pil.exp_time(exp)
    pil.set_num_images(rep)
    change_sample(sname, check_sname=check_sname)
    sol.mc_move_sample(pos, cell_form)
    RE(ct([pil,em1,em2], num=rep))
    
def mc_measure_sample_dscanx(pos, sname='test', exp=0.5, y_points=5, yrange=4, x_points=5, xrange=0.5,offset_y=0.3,check_sname=True, cell_form=None,):
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.exp_time(exp)
    pil.set_num_images(x_points)
    change_sample(sname, check_sname=check_sname)
    sol.mc_move_sample(pos, cell_form)
    time.sleep(1)
    #ss.y.move(ss.y.position+offset_y)
    RE(dscan([pil,em1,em2],ss.x, -xrange/2,xrange/2,x_points))
    
def mc_measure_sample_dscany(pos, sname='test', exp=0.5, y_points=5, yrange=4, x_points=5, xrange=0.5,offset_y=0.3,check_sname=True, cell_form=None):
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.exp_time(exp)
    pil.set_num_images(y_points)
    change_sample(sname, check_sname=check_sname)
    sol.mc_move_sample(pos, cell_form)
    time.sleep(1)
    #ss.y.move(ss.y.position+offset_y)
    RE(dscan([pil,em1,em2],ss.y, -yrange/2,yrange/2,y_points))
    
def mc_measure_sample_mesh(pos, sname='test', exp=0.5, y_points=5, yrange=4, x_points=5, xrange=0.5,offset_y=0.3,check_sname=True, cell_form=None):
    pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
    pil.exp_time(exp)
    pil.set_num_images(y_points*x_points)
    change_sample(sname, check_sname=check_sname)
    sol.mc_move_sample(pos, cell_form)
    time.sleep(1)
    ss.y.move(ss.y.position+offset_y)
    RE(dmesh([pil,em1,em2],ss.y, -yrange/2,yrange/2,y_points, ss.x, -xrange/2,xrange/2,x_points))
    
def mc_measure_sample_scany(pos, sname='test', exp=0.5, 
                            y_points=10, yrange=4, x_points=2, xrange=0.5, offset_y=0.3,
                            check_sname=True, cell_form=None):
    change_sample(sname, check_sname=check_sname)
    sol.mc_move_sample(pos, cell_type=cell_form)
    time.sleep(1)

    RE(monitor_during_wrapper(rel_raster(exp, 
                                         ss.y, -yrange/2+offset_y, yrange/2+offset_y, y_points, 
                                         ss.x, -xrange/2, xrange/2, x_points, 
                                         md={"experiment": "powder"}), [em1.ts.SumAll]))
    
    sol.mc_move_sample(pos, cell_type=cell_form)
    
def mc_measure_holder(spreadSheet, holderName,sheet_name='Holders', exp=1, rep=1, check_sname=True, 
                      scan=False, y_points=10, yrange=2.5, x_points=2, xrange=0.5, offset_y=0.3, 
                      T=None, delay_time=60, dead_band=0.5, cell_form=None):
    sol.mc_move_sample(1, cell_type=cell_form)
    if T is None:
        samples = get_samples(spreadSheet, holderName=holderName, sheet_name=sheet_name)
    else:
        #ts = get_samples(spreadSheet, holderName)
        ts = get_samples(spreadSheet, holderName=holderName, sheet_name=sheet_name)
        samples = {}
        for sn in ts.keys():
            sn1 = sn+('_T%.1fC' % T)
            samples[sn1] = ts[sn]
            if check_sname:
                check_sample_name(sn1)
        holderName += ('_T%.1fC' % T)
        
        sol.tctrl.waitT(T, delay_time, dead_band=dead_band)
        
    print(samples)    
    
    uids = []
    pil.use_sub_directory(holderName)
    RE.md['holderName'] = holderName 
    for s in samples.keys():
        if scan==True:
            mc_measure_sample_scany(samples[s]['position'], s, exp, 
                                    y_points=y_points, yrange=yrange, 
                                    x_points=x_points, xrange=xrange, offset_y=offset_y, 
                                    check_sname=check_sname, cell_form=cell_form)
            #sleep(60)
        elif scan == "mesh":
            mc_measure_sample_mesh(samples[s]['position'],s,exp,y_points=y_points,yrange=yrange, 
                                    x_points=x_points, xrange=xrange, 
                                    check_sname=check_sname, cell_form=cell_form)
        elif scan == "dscanx":
            mc_measure_sample_dscanx(samples[s]['position'],s,exp, x_points=x_points, xrange=xrange, 
                                    check_sname=check_sname, cell_form=cell_form)
        elif scan == "dscany":
            mc_measure_sample_dscany(samples[s]['position'],s,exp, y_points=y_points, yrange=yrange, 
                                    check_sname=check_sname, cell_form=cell_form)
        else:    
            mc_measure_sample(samples[s]['position'], s, exp, rep, 
                              check_sname=check_sname, cell_form=cell_form)
        uids.append(db[-1].start['uid'])
    del RE.md['holderName']
    pil.use_sub_directory()

    pack_h5(uids, fn=holderName)    
    dt = h5xs(holderName+".h5", [dexp.detectors, qgrid], transField='em2_sum_all_mean_value')
    #dt.load_data(debug='quiet')    

def mc_auto_measure_samples(spreadSheet, configName, exp=1, rep=1, check_sname=True, 
                      scan=False, y_points=10, yrange=2.5, x_points=2, xrange=0.5, offset_y=0.3, 
                      T=None, delay_time=60, dead_band=0.5, cell_form=None):
    """ measure all sample holders defined in a given configuration in the spreadsheet
    """
    if data_path is None:
        raise exception("login first !")
    if sol.HolderPresent.get():
        raise Exception("A sample holder is still in the sample handler !")

    if isinstance(configName, str): # for on-site measurements, read configuration from spreadsheet 
        sheet_name = "Holders"
        samples = get_samples(spreadSheet, sheet_name=sheet_name, configName=configName)
        holders = get_holders_under_config(spreadSheet, configName)
    else: # for mail-in, derive configuration for the all existing holders
        sheet_name = 0
        holders = configName  # called from measure_mailin_spreadsheets()

    rbt.goHome()
    for p in list(holders.keys()):
        sol.park_sample()
        print('mounting plate from position', p)
        
        rbt.loadPlate(p)
        sol.park_sample()
        rbt.mountPlate()

        print('mounted tray =', p)
        holderName = holders[p]

        mc_measure_holder(spreadSheet, holderName,
                                          exp=exp, rep=rep,
                                          y_points=y_points, yrange=yrange, x_points=x_points, xrange=xrange, offset_y=0.3, 
                                          cell_form='flat15',scan=scan)

        #sol.select_tube_pos('park')
        sol.park_sample()
        try:  # this sometimes craps out, but never twice in a row
            rbt.unmountPlate()
        except:
            rbt.unmountPlate()
        #rbt.unloadTray(d['holderPosition'][i])
        rbt.unloadPlate(p)

    rbt.park()
    


try:
    sol.tctrl = tctrl_FTC100D(("xf16idc-tsvr-sena", 7002))
except:
    print("cannot connect to sample storage temperature controller")





