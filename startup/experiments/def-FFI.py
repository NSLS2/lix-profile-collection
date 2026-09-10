CRL_STATE_FOCUSING = [1, 1, 1, 0, 0, 0, 0, 1, 0]
SSA_DX_SCANNING = 0.03
SSA_DY_SCANNING = 0.06
DDA_DX_SCANNING = 0.45
DDA_DY_SCANNING = 0.4
SG2_DX_SCANNING = 0.3
SG2_DY_SCANNING = 0.4

SSA_DX_FFI = 0.16
SSA_DY_FFI = 0.001

WAXS1_X_FFI = 54.79
WAXS1_Y_FFI = 84.58
WAXS1_Z_FFI = 950      

WAXS1_Y_SCANNING = 5

WAXS2_X = -62.5
WAXS2_Y = 9
WAXS2_Z = 310

"""
In [268]: crl.x1.position, crl.x2.position, crl.y1.position, crl.y2.position
Out[268]: (4.776171875, 7.03234375, 8.4371875, -18.053828125000003)
"""

"""
alignment target
In [161]: ss.sx.position, ss.sz.position, ss.tx.position, ss.tz.position
Out[161]: (-0.5799909999999999, -4.2999999999999995e-05, 2.00007, 0.0)

standard samples: need to remount to reverse orientation
carbon: y=21
AgBH: y=12.7
"""

def setup_for_scanning():
    print("moving WAXS ...")
    RE(mov(waxs1.y, WAXS1_Y_SCANNING))
    print("moving slits ...")
    RE(mov(dda.dx, DDA_DX_SCANNING, dda.dy, DDA_DY_SCANNING))
    # SSA center position should be set to zero after initial alignment 
    RE(mov(ssa.dx, SSA_DX_SCANNING, ssa.dy, SSA_DY_SCANNING))
    RE(mov(sg2.dx, SG2_DX_SCANNING, sg2.dy, SG2_DY_SCANNING))
    print("inserting CRLs ...")
    crl.saved_states = {'last': CRL_STATE_FOCUSING}
    crl.restore_state()
    update_metadata()

def setup_for_FFI():
    print("moving WAXS ...")
    RE(mov(waxs1.x, WAXS1_X_FFI, waxs1.y, WAXS1_Y_FFI, waxs1.z, WAXS1_Z_FFI))
    print("moving slits ...")
    RE(mov(dda.dx, 2., dda.dy, 2.))
    RE(mov(sg2.dx, 3, sg2.dy, 3))
    RE(mov(ssa.dx, SSA_DX_FFI, ssa.dy, SSA_DY_FFI))
    print("removing CRLs ...")
    crl.remove_all()
    update_metadata()  

def take_test_image(sn):
    ktx22.set_num_images(11)
    fast_shutter.close()
    time.sleep(0.5)
    change_sample(f"{sn}-dark")
    RE(count([ktx22, ext_trig], num=11))

    ss_y_pos = ss.y.position
    ss.y.move(1).wait()
    fast_shutter.open()
    time.sleep(0.5)
    change_sample(f"{sn}-empty")
    RE(count([ktx22, ext_trig], num=11))

    ss.y.move(ss_y_pos).wait()
    time.sleep(0.5)
    change_sample(f"{sn}")
    RE(count([ktx22, ext_trig], num=11))
    fast_shutter.close()

    uids = [db[-1].uid, db[-2].uid, db[-3].uid]
    pack_h5(uids, fn=sn)

    with h5py.File(f"{sn}.h5", "r+") as fh:
        ff = np.average(fh[f'{sn}-empty/primary/data/ktx22_image'], axis=0)
        dd = np.average(fh[f'{sn}-dark/primary/data/ktx22_image'], axis=0)
        ii = np.average(fAdministratorAdministratorh[f'{sn}/primary/data/ktx22_image'], axis=0)
        img = -np.log((ii-dd)/(ff-dd))

        fh.create_dataset("absorption", data=img)

def collect_CT(sn, x1, x2, fov=0.9, nproj=121):
    """ field of view is ~1mm
        
    """
    xsteps = int(np.ceil(np.fabs(x2-x1)/fov))
    xcenter = (x1+x2)/2
    xstart = xcenter-fov*(xsteps-1)/2
    xend = xcenter+fov*(xsteps-1)/2

    ext_trig.set_delay(0.15)
    ktx22.exp_time(0.1)

    ktx22.set_num_images(11)
    fast_shutter.close()
    time.sleep(0.5)
    change_sample(f"{sn}-dark")
    RE(count([ktx22, ext_trig], num=11))
    fast_shutter.open()
    ss.xc.move(5).wait()
    time.sleep(0.5)
    change_sample(f"{sn}-empty")
    RE(count([ktx22, ext_trig], num=11))
    ss.xc.move(SS_XC_POS_MEASURE).wait()
    time.sleep(0.5)

    change_sample(sn)
    ktx22.set_num_images(xsteps*nproj)
    RE(mesh([ktx22,em1ext,ext_trig], ss.x, xstart, xend, int(xsteps), ss.ry, -90, 90, nproj))    

    uids = [db[-1].uid, db[-2].uid, db[-3].uid]
    pack_h5(uids, fn=sn)

import tomopy
from skimage import transform
from scipy.ndimage import shift
import json,h5py,hdf5plugin
import numpy as np

def merge(dds):
    """
        merge arrays, average over valid values
    """
    ret = np.zeros_like(dds[0])
    wt = np.zeros_like(dds[0])
    for dd in dds:
        idx = ~np.isnan(dd)
        ret[idx] += dd[idx]
        wt[idx] += 1

    return ret/wt
    

def procCT(sn, pixel_size=0.000673, offset_y_per_mm=24,  down_sampling=2):
    """ theoretical pixel size is 6.5um/10
        the y position also change since the x-stage is not completely aligned with the camera horizontal dimension
        this is characterized by the number of pixel offset per mm x travel 
        both numbers are based on measurement on a sample that contains a metal pin
    """
    idx = (slice(450,2000), slice(300,2100))
    with h5py.File(f"{sn}.h5", "r+") as fh:
        ff = np.average(fh[f'{sn}-empty/primary/data/ktx22_image'], axis=0)
        dd = np.average(fh[f'{sn}-dark/primary/data/ktx22_image'], axis=0)
        xmax = np.max(fh[f'{sn}/primary/data/ss_x'])
        xmin = np.min(fh[f'{sn}/primary/data/ss_x'])
        img_h = dd[idx].shape[0]
        img_w0 = dd[idx].shape[1]
        img_w = img_w0+ int(np.ceil((xmax-xmin)/pixel_size))
        n_xpos,n_angles = json.loads(fh[sn].attrs['start'])['shape']
        dset = fh[f'{sn}/primary/data']

        mms = []
        for ss,x0 in zip(dset['ktx22_image'],dset['ss_x']):
            mm = (ss-dd)/(ff-dd)
            mm1 = np.full((img_h, img_w), np.nan, dtype=np.float16)
            offset_x = int((x0-xmin)/pixel_size+0.5)
            offset_y = int((x0-(xmax+xmin)/2)*offset_y_per_mm+0.5)
            mm1[:, offset_x:img_w0+offset_x] = shift(mm, (-offset_y, 0), order=0, prefilter=False)[idx]
            # downsampling here, 6.5um pixel, 10x mag, 1.2um optical resolution
            mms.append(transform.downscale_local_mean(mm1, (down_sampling, down_sampling)))

        sino = []
        for i in range(n_angles):
            sino.append(-np.log(merge(mms[i::n_angles])))  # start:end:step

        if "sino" in fh.keys():
            # it's possible for re-processing to result in different data width, e.g. changed pixel size
            data = np.array(sino)
            w0 = fh['sino'].shape[-1]
            w = data.shape[-1]
            if w>w0:
                st = int((w-w0)/2)
                data = data[:,:,st:st+w0]
                fh['sino'][...] = data
            else:
                fh['sino'][:,:,:data.shape[-1]] = data
        else:
            dset = fh.create_dataset("sino", data=np.array(sino))
        dset.attrs['pixel size'] = pixel_size*down_sampling
        dset.attrs['angles'] = np.linspace(-90, 90, n_angles)

