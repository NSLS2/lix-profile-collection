import faulthandler
faulthandler.enable()
import logging
import sys

from bluesky.run_engine import RunEngine
import nslsii


class CustomRunEngine(RunEngine):
    def __call__(self, *args, **kwargs):
        global username
        global proposal_id
        global run_id

        if username is None or proposal_id is None or run_id is None:
            login()

        return super().__call__(*args, **kwargs)

RE = CustomRunEngine()

nslsii.configure_base(get_ipython().user_ns, 'lix', bec=True, pbar=False)

def reload_macros(file='~/.ipython/profile_collection/startup/99-macros.py'):
    ipy = get_ipython()
    ipy.magic('run -i '+file)


def is_ipython():
    ip = True
    if 'ipykernel' in sys.modules:
        ip = False # Notebook
    elif 'IPython' in sys.modules:
        ip = True # Shell
    return ip


# def setup_LIX(user_ns, mode):
#     ns = {}
#     ns.update(lix_base())
#     if mode == 'scanning':
#         user_ns['motor'] = EpicsMotor(...)
# 
#     elif mode == 'solution':
#         ...
# 
#     user_ns.update(ns)
#     return list(ns)
# 
# 
# def new_login():
#     ...
# 
#     setup_LIX(ip.user_ns, ...)


# this is for backward compatibility with bluesky 1.5.x
# eventually this will be removed
from pathlib import Path

import appdirs


try:
    from bluesky.utils import PersistentDict
except ImportError:
    import msgpack
    import msgpack_numpy
    import zict

    class PersistentDict(zict.Func):
        """
        A MutableMapping which syncs it contents to disk.
        The contents are stored as msgpack-serialized files, with one file per item
        in the mapping.
        Note that when an item is *mutated* it is not immediately synced:
        >>> d['sample'] = {"color": "red"}  # immediately synced
        >>> d['sample']['shape'] = 'bar'  # not immediately synced
        but that the full contents are synced to disk when the PersistentDict
        instance is garbage collected.
        """
        def __init__(self, directory):
            self._directory = directory
            self._file = zict.File(directory)
            self._cache = {}
            super().__init__(self._dump, self._load, self._file)
            self.reload()

            # Similar to flush() or _do_update(), but without reference to self
            # to avoid circular reference preventing collection.
            # NOTE: This still doesn't guarantee call on delete or gc.collect()!
            #       Explicitly call flush() if immediate write to disk required.
            def finalize(zfile, cache, dump):
                zfile.update((k, dump(v)) for k, v in cache.items())

            import weakref
            self._finalizer = weakref.finalize(
                self, finalize, self._file, self._cache, PersistentDict._dump)

        @property
        def directory(self):
            return self._directory

        def __setitem__(self, key, value):
            self._cache[key] = value
            super().__setitem__(key, value)

        def __getitem__(self, key):
            return self._cache[key]

        def __delitem__(self, key):
            del self._cache[key]
            super().__delitem__(key)

        def __repr__(self):
            return f"<{self.__class__.__name__} {dict(self)!r}>"

        @staticmethod
        def _dump(obj):
            "Encode as msgpack using numpy-aware encoder."
            # See https://github.com/msgpack/msgpack-python#string-and-binary-type
            # for more on use_bin_type.
            return msgpack.packb(
                obj,
                default=msgpack_numpy.encode,
                use_bin_type=True)

        @staticmethod
        def _load(file):
            return msgpack.unpackb(
                file,
                object_hook=msgpack_numpy.decode,
                raw=False)

        def flush(self):
            """Force a write of the current state to disk"""
            for k, v in self.items():
                super().__setitem__(k, v)

        def reload(self):
            """Force a reload from disk, overwriting current cache"""
            self._cache = dict(super().items())

runengine_metadata_dir = appdirs.user_data_dir(appname="bluesky") / Path("runengine-metadata")

# PersistentDict will create the directory if it does not exist
RE.md = PersistentDict(runengine_metadata_dir)
