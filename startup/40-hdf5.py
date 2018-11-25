from suitcase import hdf5  #,nexus # available in suitcase 0.6

import h5py,json,os
import suitcase
import numpy as np

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
    
def pack_h5(uids, fn=None, fix_sample_name=True, 
            attach_uv_file=False, delete_old_file=False,
            fields=['em2_current1_mean_value', 'em2_current2_mean_value',
                    'pil1M_image', 'pilW1_image', 'pilW2_image', 
                    'pil1M_ext_image', 'pilW1_ext_image', 'pilW2_ext_image']):
    """ if only 1 uid is given, use the sample name as the file name
        any metadata associated with each uid will be retained (e.g. sample vs buffer)
    """
    if isinstance(uids, list):
        if fn is None:
            raise Exception("a file name must be given for a list of uids.")
        headers = [db[u] for u in uids]
        pns = [h.start.plan_name for h in headers]
        if not (pns[1:]==pns[:-1]):
            raise Exception("mixed plan names in uids: %s" % pns)
    else:
        header = db[uids]
        if fn is None:
            if "sample_name" in list(header.start.keys()):
                fn = header.start['sample_name']
            else:
                fds = db.get_fields(header)
                # find the first occurance of _file_file_name in fields
                f = next((x for x in fds if "_file_file_name" in x), None)
                if f is None:
                    raise Exception("could not automatically select a file name.")
                fn = db.get_table(header, fields=[f])[f][1]
        headers = [header]

    fds0 = db.get_fields(headers[0])
    # only these fields are considered relevant to be saved in the hdf5 file
    fds = list(set(fds0) & set(fields))
    if 'motors' in list(headers[0].start.keys()):
        for m in headers[0].start['motors']:
            fds += [m] #, m+"_user_setpoint"]
    
    if fn[-3:]!='.h5':
        fn += '.h5'

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
    grp = f["%s/hplc/data" % grp_name]
    
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