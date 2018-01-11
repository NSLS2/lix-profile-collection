from filestore.handlers_base import HandlerBase
import filestore.api as fs
import fabio

# this is a temporary fix to get around the bug that the frames per point were are 
# recorded correctly before 2018
global pilatus_fpp
pilatus_fpp = 1

class PilatusCBFHandler(HandlerBase):
    specs = {'AD_CBF'} | HandlerBase.specs

    def __init__(self, rpath, template, filename, frame_per_point=1, initial_number=1):
        #print("CBF handler init(), ", rpath, template, filename, frame_per_point, initial_number)
        # temporary fix
        if pilatus_fpp>1:
            frame_per_point = pilatus_fpp
            # file name should look like test_000125_SAXS_00001.cbf, instead of test_000125_SAXS.cbf
            template = template[:-4]+"_%05d.cbf"
        self._path = rpath
        self._fpp = frame_per_point
        self._template = template
        self._filename = filename
        self._initial_number = initial_number

    def __call__(self, point_number):
        start = self._initial_number + point_number
        stop = start + 1 
        ret = []
        #print("CBF handler called: start=%d, stop=%d" % (start, stop))
        #print("  ", self._initial_number, point_number, self._fpp)
        #print("  ", self._template )
        for j in range(start, stop):
            for k in range(self._fpp):
                if self._fpp>1:
                    fn = self._template % (self._path, self._filename, j, k)
                else:
                    fn = self._template % (self._path, self._filename, j)
                #print("  reading "+fn)
                img = fabio.open(fn)
                ret.append(img.data)
        return np.array(ret).squeeze()

    """
    def get_file_list(self, datum_kwargs_gen):
        file_list = []
        print("CBF handler get_filelist()", datum_kwargs_gen)
        for dk in datum_kwargs_gen:
            point_number = dk['point_number']
            start = self._initial_number
            stop = self._initial_number + point_number
            print("  ", self._initial_number, point_number, self._fpp)
            ret = []
            for j in range(start, stop):
                fn = self._template % (self._path, self._filename, j)
                file_list.append(fn)
        return file_list
    """

try:
    db.fs.register_handler('AD_CBF', PilatusCBFHandler)
except:
    print("could not register PilatusCBFHandler.")

