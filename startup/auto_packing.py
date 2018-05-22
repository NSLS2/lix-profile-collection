import h5py
from pathlib import Path
from collections import defaultdict
import itertools
from bluesky.callbacks import CallbackBase


def plan():
    detectors = [pil1M]
    yield from rel_scan(detectors, ss2.x, -1, 1, 5)
    yield from count(detectors, 5)
    yield from count(detectors, 3)


class Packer(CallbackBase):
    def __init__(self, directory, max_frames_per_file, handler_class):
        self.directory = directory 
        self.max_frames_per_file = max_frames_per_file
        self.handler_class = handler_class
        self.resources = {}  # map resource_uid to resource dict
        self.datums = defaultdict(list)  # map resource_uid to list of datums
        self.start_doc = None

    def start(self, doc):
        self.start_doc = doc
        self.chunk_counter = itertools.count()

    def event(self, doc):
        ...

    def resource(self, doc):
        self.resources[doc['uid']] = doc
        
    def datum(self, doc):
        self.datums[doc['resource']].append(doc)
        # Assume one datum == one frame. Can be more careul later.
        if len(self.datums) == self.max_frames_per_file:
            self.export()

    def stop(self, doc):
        # Export even if we haven't reached the limit yet.
        # No file should bridge across more than one run.
        self.export()

    def export(self):
        # Read in the images and stack them up.
        for resource_uid, datums in self.datums.items():
            resource = self.resources[resource_uid]
            stack = []
            rpath = Path(resource['root']) / Path(resource['resource_path'])
            handler = self.handler_class(rpath=rpath,
                                         **resource['resource_kwargs'])
            for datum in datums:
                image = handler(**datum['datum_kwargs'])
                stack.append(image)
        stack = np.stack(stack)

        # Write the HDF5 file.
        md = self.start_doc
        i = next(self.chunk_counter)
        filename = (f"{md['uid'][:8]}_"
                    f"chunk{i}_"
                    f"{md.get('sample_name', 'sample_name_not_recorded')}")
        filepath = Path(self.directory) / Path(filename)
        with h5py.File(filepath) as f:
            f.create_dataset('data', data=stack)
            shape = f['data'].shape
        print(f"write {filename} with shape {shape}")
            

packer = Packer(max_frames_per_file=2,
                directory='/tmp/dan/',
                handler_class=PilatusCBFHandler)

# RE.subscribe(packer)
