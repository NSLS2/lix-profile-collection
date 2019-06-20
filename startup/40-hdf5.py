from suitcase import hdf5  #,nexus # available in suitcase 0.6

import h5py,json,os
import threading
import numpy as np
import epics,socket
from collections import deque

#global default_data_path_root
#global substitute_data_path_root
#global DET_replace_data_path
global proc_path

def lsh5(hd, prefix='', top_only=False):
    if top_only:
        print(list(hd.keys()))
        return
    for k in list(hd.keys()):
        print(prefix, k)
        if isinstance(hd[k], h5py.Group):
            print(list(hd[k].attrs.items()))
            lsh5(hd[k], prefix+"==")
            
def h5_fix_sample_name(fn_h5):
    """ the hdf5 file is assumed to have top-level groups that each corresponds to a sample
    """
    f = h5py.File(fn_h5, "r+")
    grps = list(f.keys())
    for g in grps:
        header = json.loads(f[g].attrs.get('start'))
        if 'sample_name' in header.keys():
            sn = header['sample_name']
            f.move(g, sn)
    f.close()

pack_h5_lock = threading.Lock()

def pack_h5_with_lock(*args, **kwargs):
    pack_h5_lock.acquire()
    #try:
    ret = pack_h5(*args, **kwargs)
    #except:
    #    print("an error occur when packing h5.")
    #    ret = None
    pack_h5_lock.release()    
    return ret
    
def pack_h5(uids, dest_dir='', fn=None, fix_sample_name=True, 
            attach_uv_file=False, delete_old_file=True, 
            fields=[#'em2_current1_mean_value', 'em2_current2_mean_value',
                    'em1_sum_all_mean_value', 'em2_sum_all_mean_value',
                    'pil1M_image', 'pilW1_image', 'pilW2_image', 
                    'pil1M_ext_image', 'pilW1_ext_image', 'pilW2_ext_image']):
    """ if only 1 uid is given, use the sample name as the file name
        any metadata associated with each uid will be retained (e.g. sample vs buffer)
        
        to avoid multiple processed requesting packaging, only 1 process is allowed at a given time
        this is i
    """
    if isinstance(uids, list):
        if fn is None:
            raise Exception("a file name must be given for a list of uids.")
        headers = [db[u] for u in uids]
        pns = [h.start['plan_name'] for h in headers]
        if not (pns[1:]==pns[:-1]):
            raise Exception("mixed plan names in uids: %s" % pns)
    else:
        header = db[uids]
        if fn is None:
            if "sample_name" in list(header.start.keys()):
                fn = header.start['sample_name']
            else:
                fds = header.fields()
                # find the first occurance of _file_file_name in fields
                f = next((x for x in fds if "_file_file_name" in x), None)
                if f is None:
                    raise Exception("could not automatically select a file name.")
                fn = header.table(fields=[f])[f][1]
        headers = [header]

    fds0 = headers[0].fields()
    # only these fields are considered relevant to be saved in the hdf5 file
    fds = list(set(fds0) & set(fields))
    if 'motors' in list(headers[0].start.keys()):
        for m in headers[0].start['motors']:
            fds += [m] #, m+"_user_setpoint"]
    
    if fn[-3:]!='.h5':
        fn += '.h5'

    if dest_dir!='':
        if not os.path.exists(dest_dir):
            raise Exception(f'{dest_dir} does not exist.')
        fn = dest_dir+'/'+fn
        
    if delete_old_file:
        try:
            os.remove(fn)
        except OSError:
            pass
        
    print(fds)
    hdf5.export(headers, fn, fields=fds, use_uid=False) #, mds= db.mds, use_uid=False) 
    
    # by default the groups in the hdf5 file are named after the scan IDs
    if fix_sample_name:
        h5_fix_sample_name(fn)
        
    if attach_uv_file:
        # by default the UV file should be saved in /GPFS/xf16id/Windows/
        h5_attach_hplc(fn, '/GPFS/xf16id/Windows/hplc_export.txt')
    
    print(f"finished packing {fn} ...")
    return fn


def h5_attach_hplc(fn_h5, fn_hplc, grp_name=None):
    """ the hdf5 is assumed to contain a structure like this:
        LIX_104
        == hplc
        ==== data
        == primary (em, scattering patterns, ...)
        
        attach the HPLC data to the specified group
        if the group name is not give, attach to the first group in the h5 file
    """
    f = h5py.File(fn_h5, "r+")
    if grp_name == None:
        grp_name = list(f.keys())[0]
    # this group is created by suitcase if using flyer-based hplc_scan
    # otherwise it has to be created first
    #grp = f["%s/hplc/data" % grp_name]
    grp = f.create_group(f"{grp_name}/hplc/data")
    
    hdstr, dhplc = readShimadzuDatafile(fn_hplc)
    
    if grp.attrs.get('header') == None:
        grp.attrs.create("header", np.asarray(hdstr, dtype=np.string_))
    else:
        grp.attrs.modify("header", np.asarray(hdstr, dtype=np.string_))
    
    existing_keys = list(grp.keys())
    for k in dhplc.keys():
        d = np.asarray(dhplc[k]).T
        if k in existing_keys:
            print("warning: %s already exists." % k)
        dset = grp.require_dataset(k, d.shape, d.dtype)
        dset[:] = d
    
    f.close()

from py4xs.detector_config import create_det_from_attrs
from py4xs.hdf import h5sol_HPLC,h5sol_HT,h5xs
import json

import socket
packing_queue_sock_port = 9999

def send_to_packing_queue(uid, datatype, froot=data_file_path.ramdisk):
    """ data_type must be one of ["scan", "flyscan", "HPLC", "sol", "multi"]
        single uid only for "scan", "flyscan", "HPLC"
        uids must be concatenated using '|' for "multi" and "sol"
    """
    if datatype not in ["scan", "flyscan", "HPLC", "multi", "sol"]:
        raise Exception("invalid data type: {datatype}, valid options are scan and HPLC.")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    s.connect(('10.16.0.4', packing_queue_sock_port))
    msg = f"{datatype}::{uid}::{proc_path}::{froot.name}"
    s.send(msg.encode('ascii'))
    s.close()

from py4xs.hdf import h5exp    
    
def pack_and_move(data_type, uid, dest_dir):
    # useful for moving files from RAM disk to GPFS during fly scans
    # 
    # assume other type of data are saved on RAM disk as well (GPFS not working for WAXS2)
    # these data must be moved manually to GPFS
    global pilatus_trigger_mode  #,CBF_replace_data_path 
    
    print(f"packing: {data_type}, {uid}, {dest_dir}")
    print(f"data source: {PilatusCBFHandler.froot}")
    t0 = time.time()
    # if the dest_dir contains exp.h5, read detectors/qgrid from it
    try:
        dt_exp = h5exp(dest_dir+'/exp.h5')
    except:
        dt_exp = None

    dir_name = None
    
    if data_type in ["multi", "sol"]:
        uids = uid.split('|')
        if data_type=="sol":
            sb_dict = json.loads(uids.pop())
            pilatus_trigger_mode = triggerMode.fly_scan
        else:
            pilatus_trigger_mode = triggerMode.external_trigger
        ## assume that the meta data contains the holderName
        if 'holderName' not in list(db[uids[0]].start.keys()):
            print("cannot find holderName from the header, using tmp.h5 as filename ...")
            fh5_name = "tmp.h5"
        else:
            dir_name = db[uids[0]].start['holderName']
            fh5_name = dir_name+'.h5'
        fn = pack_h5_with_lock(uids, dest_dir, fn="tmp.h5")
        if fn is not None and dt_exp is not None:
            print('processing ...')
            if data_type=="sol":    
                dt = h5sol_HT(fn, [dt_exp.detectors, dt_exp.qgrid])
                dt.assign_buffer(sb_dict)
                dt.process(filter_data=True, sc_factor=0.998, debug='quiet')
                dt.export_d1s(path=dest_dir+"/processed/")
            else:
                dt = h5xs(fn, [dt_exp.detectors, dt_exp.qgrid], transField='em2_sum_all_mean_value')
                dt.load_data(debug="quiet")
            dt.fh5.close()
            if fh5_name is not "tmp.h5":  # temporary fix, for some reason other processes cannot open the packed file
                os.system(f"cd {dest_dir} ; cp tmp.h5 {fh5_name} ; rm tmp.h5")
            del dt,dt_exp            
    elif data_type=="HPLC":
        uids = [uid]
        #if db[uid].start['plan_name']!="hplc_scan":
        #    print("not HPLC data ...")
        #    return
        # this was software_trigger_single_frame when using the flyer-based hplc_scan
        pilatus_trigger_mode = triggerMode.software_trigger_multi_frame
        fn = pack_h5_with_lock(uid, dest_dir=dest_dir, attach_uv_file=True)
        if fn is not None and dt_exp is not None:
            print('procesing ...')
            dt = h5sol_HPLC(fn, [dt_exp.detectors, dt_exp.qgrid])
            dt.process(debug='quiet')
            dt.fh5.close()
            del dt,dt_exp
    elif data_type=="flyscan" or data_type=="scan":
        if data_type=="flyscan":
            pilatus_trigger_mode = triggerMode.fly_scan
        else:
            pilatus_trigger_mode = triggerMode.external_trigger
        uids = [uid]
        fn = pack_h5_with_lock(uid, dest_dir)
    else:
        print(f"invalid data type: {data_type} .")
        return

    if fn is None:
        return # packing unsuccessful, 
    print(f"{time.asctime()}: finished packing/processing, total time lapsed: {time.time()-t0:.1f} sec ...")

    if PilatusCBFHandler.froot==data_file_path.gpfs:
        return
    
    for uid in uids:
        print(f'moving files for {uid} from RAMDISK to GPFS ...')
        h = db[uid]        
        p1 = h.start['data_path']  
        #p2 = p1.replace(default_data_path_root, '/ramdisk/')
        p2 = p1.replace(data_file_path.gpfs.value, '/ramdisk')
        sample_name = h.start['sample_name']
        if dir_name is not None:
            cmd = f"rsync -ahv --remove-source-files det@10.16.0.14:{p2}{dir_name} {p1}"
        elif os.system(f"ssh -q det@10.16.0.14 [[ -d {p2}{sample_name} ]]")==0:
            # if sample name is a directory on the RAMDISK, move the entire directory
            cmd = f"rsync -ahv --remove-source-files det@10.16.0.14:{p2}{sample_name} {p1}"
        else:        
            cmd = f"rsync -ahv --remove-source-files det@10.16.0.14:{p2}{sample_name}_*.* {p1}"
            #os.system(f"rsync -ahv --remove-source-files det@10.16.0.14:{p2}{h.start['sample_name']}_*.log {p1}")          
        print(cmd)
        os.system(cmd)

            
def process_packing_queue():
    """ this should only run on xf16idc-gpu1
        needed for HPLC run and microbeam mapping
    """    
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    host = socket.gethostname()                           
    if host!='xf16idc-gpu1':
        raise Exception("this function can only run on xf16idc-gpu1.")
    serversocket.bind(('10.16.0.4', packing_queue_sock_port))  
    serversocket.listen(5)
    print('listening ...')
    
    while True:
        clientsocket,addr = serversocket.accept()      
        print(f"{time.asctime()}: got a connection from {addr} ...")
        msg = clientsocket.recv(8192).decode()
        print(msg)
        clientsocket.close()
        data_type,uid,path,frn = msg.split("::") 
        if data_type not in ["multi", "sol"]: # single UID
            if 'exit_status' not in db[uid].stop.keys():
                print(f"in complete header for {uid}.")
                return
            if db[uid].stop['exit_status'] != 'success': # the scan actually finished
                print(f"scan {uid} was not successful.")
                return 
        #print(uid)
        #print(path)
        PilatusCBFHandler.froot = data_file_path[frn]
        threading.Thread(target=pack_and_move, args=(data_type,uid,path,)).start() 
                    

