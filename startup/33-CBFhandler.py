import os
from databroker.assets.handlers_base import HandlerBase
from databroker.assets.base_registry import DuplicateHandler
import fabio

# for backward compatibility, fpp was always 1 before Jan 2018
#global pilatus_fpp
#pilatus_fpp = 1
global pilatus_trigger_mode

class PilatusCBFHandler(HandlerBase):
    specs = {'AD_CBF'} | HandlerBase.specs

    def __init__(self, rpath, template, filename, frame_per_point=1, initial_number=1):
        if frame_per_point>1:
            # file name should look like test_000125_SAXS_00001.cbf, instead of test_000125_SAXS.cbf
            template = template[:-4]+"_%05d.cbf"
        self._path = os.path.join(rpath, '')
        self._fpp = frame_per_point
        self._template = template
        self._filename = filename
        self._initial_number = initial_number

    def __call__(self, point_number):
        start = self._initial_number #+ point_number
        stop = start + 1 
        ret = []
        #print("CBF handler called: start=%d, stop=%d" % (start, stop))
        #print("  ", self._initial_number, point_number, self._fpp)
        #print("  ", self._template )
     
        if pilatus_trigger_mode == triggerMode.software_trigger_single_frame:
            fn = self._template % (self._path, self._filename, point_number+1)
            img = fabio.open(fn)
            ret.append(img.data)
        elif pilatus_trigger_mode == triggerMode.software_trigger_multi_frame:
            for i in range(self._fpp):
                fn = self._template % (self._path, self._filename, point_number+1, i) 
                img = fabio.open(fn)
                ret.append(img.data)
        elif pilatus_trigger_mode == triggerMode.external_trigger:
            fn = self._template % (self._path, self._filename, start, point_number)
            img = fabio.open(fn)
            ret.append(img.data)
        
        return np.array(ret).squeeze()

db.reg.register_handler('AD_CBF', PilatusCBFHandler, overwrite=True)
