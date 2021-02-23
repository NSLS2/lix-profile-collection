import os
from databroker.assets.handlers_base import HandlerBase
from databroker.assets.base_registry import DuplicateHandler
import fabio

# for backward compatibility, fpp was always 1 before Jan 2018
#global pilatus_fpp
#pilatus_fpp = 1

# this is used by the CBF file handler        
from enum import Enum
class triggerMode(Enum):
    software_trigger_single_frame = 1
    software_trigger_multi_frame = 2
    external_trigger = 3
    fly_scan = 4
    #external_trigger_multi_frame = 5  # this is unnecessary, difference is fpp

#global pilatus_trigger_mode
#global default_data_path_root
#global substitute_data_path_root
#global CBF_replace_data_path

#pilatus_trigger_mode = triggerMode.software_trigger_single_frame

# if the cbf files have been moved already
#CBF_replace_data_path = False

class PilatusCBFHandler(HandlerBase):
    specs = {'AD_CBF'} | HandlerBase.specs
    froot = data_file_path.gpfs 
    subdir = None
    trigger_mode = triggerMode.software_trigger_single_frame
    # assuming that the data files always have names with these extensions 
    std_image_size = {
        'SAXS': (1043, 981),
        'WAXS1': (619, 487),
        'WAXS2': (1043, 981)      # orignal WAXS2 was (619, 487)
    }

    def __init__(self, rpath, template, filename, frame_per_point=1, initial_number=1):
        print(f'Initializing CBF handler for {self.trigger_mode} ...')
        self._template = template
        self._fpp = frame_per_point
        self._filename = filename
        self._initial_number = initial_number
        self._image_size = None
        self._default_path = os.path.join(rpath, '')
        self._path = ""
        
        for k in self.std_image_size:
            if template.find(k)>=0:
                self._image_size = self.std_image_size[k]
        if self._image_size is None:
            raise Exception(f'Unrecognized data file extension in filename template: {template}')

        for fr in data_file_path:
            if self._default_path.find(fr.value)==0:
                self._dir = self._default_path[len(fr.value):]
                return
        raise Exception(f"invalid file path: {self._default_path}")
    
    def update_path(self):
        # this is a workaround for data that are save in /exp_path then moved to /nsls2/xf16id1/exp_path
        if not self.froot in data_file_path:
            raise Exception(f"invalid froot: {self.froot}")
        self._path = self.froot.value+self._dir 
        print(f"updating path, will read data from {self._path} ...")
    
    def get_data(self, fn):
        """ the file may not exist
        """
        try:
            img = fabio.open(fn)
            data = img.data
            if data.shape!=self._image_size:
                print(f'got incorrect image size from {fn}: {data.shape}') #, return an empty frame instead.')
        except:
            print(f'could not read {fn}, return an empty frame instead.')
            data = np.zeros(self._image_size)
        #print(data.shape)
        return data
        
    def __call__(self, point_number):
        start = self._initial_number #+ point_number
        stop = start + 1 
        ret = []

        tplt = self._template.replace("6.6d", "06d") # some early templates are not correctly formatted
        tl = tplt.replace(".", "_").split("_") 
        # e.g. ['%s%s', '%06d', 'SAXS', 'cbf'], ['%s%s', '%06d', 'SAXS', '%05d', 'cbf']
        # resulting in file names like test_000125_SAXS.cbf vs test_000125_SAXS_00001.cbf 
        if self.trigger_mode != triggerMode.software_trigger_single_frame and self._fpp>1:
            # the template needs to have two number fileds
            if len(tl)==4:
                tl = tl[:-1]+["%05d"]+tl[-1:] 
        elif len(tl)==5:
            tl = tl[:-2]+tl[-1:]
        self._template = "_".join(tl[:-1])+"."+tl[-1]

        print("CBF handler called: start=%d, stop=%d" % (start, stop))
        print("  ", self._initial_number, point_number, self._fpp)
        print("  ", self._template, self._path, self._initial_number)
        self.update_path()
        if self.subdir is not None:
            self._path += f"{self.subdir}/"
     
        if self.trigger_mode == triggerMode.software_trigger_single_frame or self._fpp == 1:
            fn = self._template % (self._path, self._filename, self._initial_number+point_number)
            ret.append(self.get_data(fn))
        elif self.trigger_mode in [triggerMode.software_trigger_multi_frame,
                                      triggerMode.fly_scan]:
            for i in range(self._fpp):
                fn = self._template % (self._path, self._filename, start, point_number+i) 
                ret.append(self.get_data(fn))
        elif self.trigger_mode==triggerMode.external_trigger:
            fn = self._template % (self._path, self._filename, start, point_number)
            ret.append(self.get_data(fn))
        
        return np.array(ret).squeeze()

db.reg.register_handler('AD_CBF', PilatusCBFHandler, overwrite=True)
