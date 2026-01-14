print(f"Loading {__file__}...")

import time
import pylab as plt
from pathlib import Path
import redis
from py4xs.utils import get_bin_ranges_from_grid
from ophyd import Device
from ophyd.areadetector import EpicsSignalWithRBV

last_scan_uid = None
last_scan_id = None

default_qgrid = np.hstack((np.arange(0.005, 0.0499, 0.001),
                   np.arange(0.05, 0.0999, 0.002),
                   np.arange(0.1, 0.4999, 0.005),
                   np.arange(0.5, 0.9999, 0.01),
                   np.arange(1.0, 3.2, 0.03)))
default_phi_N = 32

def save_qgrid_config_to_redis(qgrid=default_qgrid, phi_N=default_phi_N):
    q_bins = get_bin_ranges_from_grid(qgrid)
    qgrid_attr = {"q_bins": q_bins, "phi_N": phi_N}
    with redis.Redis(host=redis_host, port=redis_port, db=0) as r:
        r.set("qgrid_config", json.dumps(qgrid_attr))
        r.set("qgrid_config_timestamp", time.time())

def save_det_config_to_redis():
    """ use the exp.h5 file in the current directory
        it is expected to have been updated using de.recalibrate()
    """
    de = h5exp("exp.h5")
    dets_attr = [det.pack_dict() for det in de.detectors]
    with redis.Redis(host=redis_host, port=redis_port, db=0) as r:
        r.set("det_config", json.dumps(dets_attr))
        r.set("det_config_timestamp", time.time())

def fetch_scan(**kwargs):
    if len(kwargs) == 0:  # Retrieve last dataset
        header = db[-1]
        return header, header.table(fill=True)
    else:
        headers = db(**kwargs)
        return headers, db.get_table(headers, fill=True)

def list_scans(**kwargs):
    headers = list(db(**kwargs))
    uids = []
    for h in headers:
        s = "%8s%10s%10s" % (h.start['proposal_id'], h.start['run_id'], h.start['plan_name'])
        try:
            s = "%s%8d" % (s, h.start['num_points'])
        except:
            s = "%s%8s" % (s,"")
        t = time.asctime(time.localtime(h.start['time'])).split()
        s = s + (" %s-%s-%s %s " % (t[4], t[1], t[2], t[3])) 
        try:
            s = "%s %s" % (s, h.start['sample_name'])
        except:
            pass
        print(s, h.start['uid'])
        uids.append(h.start['uid'])

    return(uids)

# map xv vlaue from range xm1=[min, max] to range xm2
def x_conv(xm1, xm2, xv):
    a = (xm2[-1]-xm2[0])/(xm1[-1]-xm1[0])
    return xm2[0]+a*(xv-xm1[0])

# example: plot_data(data, "cam04_stats1_total", "hfm_x1", "hfm_x2")
def plot_data(data, ys, xs1, xs2=None, thresh=0.8, take_diff=False, no_plot=False):
    yv = np.array(data[ys])
    xv1 = np.array(data[xs1])
    if take_diff:
        yv = np.fabs(np.diff(yv))
        xv1 = (xv1[1:]+xv1[:-1])/2

    idx = yv>thresh*yv.max()
    xp = np.average(xv1[idx], weights=yv[idx])
    xx = xv1[yv==yv.max()]
    pk_ret = {xs1: xp, ys: np.average(yv[idx])}
    xm1 = [xv1[0], xv1[len(xv1)-1]]
    
    if not no_plot:
        fig = plt.figure(figsize=(8,6))
        ax1 = fig.add_subplot(111)
        ax1.plot(xv1, yv)
        ax1.plot(xv1[idx],yv[idx],"o")
        ax1.plot([xp,xp],[yv.min(), yv.max()])
        ax1.set_xlabel(xs1)
        ax1.set_ylabel(ys)
        ax1.set_xlim(xm1)

    if xs2!=None:
        xv2 = np.asarray(data[xs2])
        if take_diff:
            xv2 = (xv2[1:]+xv2[:-1])/2
        xm2 = [xv2[0], xv2[len(xv2)-1]]
        if not no_plot:
            ax2 = ax1.twiny()
            ax2.set_xlabel(xs2)
            #xlim1 = ax1.get_xlim()
            ax2.set_xlim(xm2)
        print(f"y max at {xs1}={xx}, {xs2}={x_conv(xm1, xm2, xx)[0]}")
        print(f"y center at {xs1}={xp}, {xs2}={x_conv(xm1, xm2, xp)}")
        pk_ret[xs2] = x_conv(xm1, xm2, xp)
    else:
        print(f"y max at {xs1}={xx}")
        print(f"y center at {xs1}={xp}")

    if no_plot:
        return pk_ret
    
    
# this used to be part of 20-pilatus
# moved here so that it can be used in 20-xspress3 as well

from ophyd import Component,EpicsSignalRO
from ophyd.areadetector.filestore_mixins import FileStoreHDF5, FileStoreIterativeWrite
from ophyd.areadetector.plugins import HDF5Plugin,register_plugin,PluginBase

class LiXFileStorePluginBase(FileStoreIterativeWrite):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stage_sigs.update([('auto_increment', 'Yes'),
                                ('array_counter', 0),
                                ('auto_save', 'Yes'),
                                #('num_capture', 0),
                                #('num_capture', self._num_capture),
                                ])
        self._fn = None
        self._fp = None

    def stage(self):
        # Make a filename.
        filename, read_path, write_path = self.make_filename()

        # Ensure we do not have an old file open.
        if self.file_write_mode != 'Single':
            self.capture.set(0).wait()
        # These must be set before parent is staged (specifically
        # before capture mode is turned on. They will not be reset
        # on 'unstage' anyway.
        self.file_path.set(write_path).wait()
        self.file_name.set(filename).wait()
        self.num_capture.set(self.parent._num_captures).wait()
        #self.file_number.set(0).wait()     # only reason to redefine the pluginbase
        super().stage()

        # AD does this same templating in C, but we can't access it
        # so we do it redundantly here in Python.
        self._fn = self.file_template.get() % (read_path,
                                               filename,
                                               # file_number is *next* iteration
                                               self.file_number.get() - 1)
        self._fp = read_path
        if not self.file_path_exists.get():
            raise IOError("Path %s does not exist on IOC server."
                          "" % self.file_path.get())


class LiXFileStoreHDF5(LiXFileStorePluginBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filestore_spec = 'AD_HDF5'  # spec name stored in resource doc
        self.stage_sigs.update([('file_template', '%s%s_%6.6d.h5'),
                                ('file_write_mode', 'Stream'),
                                ('capture', 1)
                                ])

    def stage(self):
        super().stage()
        res_kwargs = {'frame_per_point': self.get_frames_per_point()}
        self._generate_resource(res_kwargs)


class LIXhdfPlugin(HDF5Plugin, LiXFileStoreHDF5):
    run_time = Component(EpicsSignalRO, "RunTime")
    data_type = Component(EpicsSignalWithRBV, "DataType")
    sub_directory = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fnbr = 0
        self.data_dir = "/tmp/"
        self.use_ioc_path = True

    def warmup(self, xsp=True):
        """
        revised from ophyd.areadetector.plugins: 
            xspress3 does not have aquire_period; acquisition time to be set by the caller
        
        A convenience method for 'priming' the plugin.

        The plugin has to 'see' one acquisition before it is ready to capture.
        This sets the array size, etc.
        """
        print(f"in warmup() for {self.parent.name}")
        self.enable.set(1).wait()
        if hasattr(self.parent.cam, 'armed'):
            armed = self.parent.cam.armed
            sigs = OrderedDict(
                [
                    (self.parent.cam.array_callbacks, 1),
                    (self.parent.cam.image_mode, "Single"),
                    (self.parent.cam.trigger_mode, "Internal"),
                    (self.parent.cam.acquire_time, 0.1),
                    (self.parent.cam.acquire_period, 0.105),
                    (self.parent.cam.acquire, 1),
                ]
            )
        elif hasattr(self.parent.cam, 'detector_state'): # Xspress3
            armed = self.parent.cam.detector_state
            sigs = OrderedDict(
                [
                    (self.parent.cam.array_callbacks, 1),
                    (self.parent.cam.image_mode, "Single"),
                    (self.parent.cam.trigger_mode, "Internal"),
                    (self.parent.cam.acquire_time, 0.1),
                    (self.parent.cam.acquire, 1),
                ]
            )
        else:
            raise Exception("don't know how to get detector armed status ...")

        original_vals = {sig: sig.get() for sig in sigs}

        for sig, val in sigs.items():
            ttime.sleep(0.1)  # abundance of caution
            sig.set(val).wait()

        #ttime.sleep(2)  # wait for acquisition
        while armed.get():
            ttime.sleep(0.2)
        
        for sig, val in reversed(list(original_vals.items())):
            ttime.sleep(0.1)
            sig.set(val).wait()

        print("end of warmup()")

    def make_filename(self):
        ''' replaces FileStorePluginBase.make_filename()
        Returns
        -------
        filename : str
            The start of the filename
        read_path : str
            Path that ophyd can read from
        write_path : str
            Path that the IOC can write to
        '''
        global current_sample

        filename = f"{current_sample}_{self.parent.detector_id}"
        write_path = get_IOC_datapath(self.parent.name, self.data_dir) 
        if not self.use_ioc_path:
            write_path = str(Path(self.data_dir))+'/'   # Xspress3 IOC cannot create subdirectories
        if self.sub_directory:
            write_path += f"/{self.sub_directory}"
        read_path = write_path # might want to handle this differently, this shows up in res/db
        return filename, read_path, write_path
    
    def describe(self):
        dtype_strs = {"UInt16": "<u2",  
                      "Int16": "<i2",  
                      "UInt32": "<u4",
                      "Int32": "<i4",
                      "Float64": "<f8",
                     }
        # copied from XPD per Max
        description = super().describe()
        key = f"{self.parent.name}_image"
        if not description:
            description[key] = self.parent.make_data_key()
        shape = list(description[key]["shape"])
        shape[0] = self.get_frames_per_point()
        shape = tuple(shape)
        description[key].update({
            "shape": shape,
            "dtype_str": dtype_strs[self.data_type.get(as_string=True)],
        })

        return description
    
    def get_frames_per_point(self):
        """ In fly scans, this should be the total number images recorded during the scan
            For step scans this should be 1??
            Could be cases it's neither: time-resolved, one trigger, multiple images 
        """
        return self.parent._num_captures    


@register_plugin
class CodecPlugin(PluginBase):
    _default_suffix = "Codec1:"
    _suffix_re = r"Codec\d:"
    _plugin_type = "NDPluginCodec" 

"""
@register_plugin
class PvaPlugin(PluginBase):
    _default_suffix = "Pva1:"
    _suffix_re = r"Pva\d:"
    _plugin_type = "NDPluginPva"
"""
