import logging

import nslsii

# TODO : move to /etc/databroker/lix.yml
# and use :
# nslsii.configure_base(get_ipython().user_ns, 'lix')
config = {
    'description' : 'LIX production mongo',
    'metadatastore' : {
        'module': 'databroker.headersource.mongo',
        'class' : 'MDS',
        'config' :{
            'host': 'xf16idc-ca',
            'port': 27017,
            'database': 'metadatastore_production_v1',
            'timezone': 'US/Eastern'
        },
    },
    'assets': {
        'module' : 'databroker.assets.mongo',
        'class' : 'Registry',
        'config':{
            'host': 'xf16idc-ca',
            'port': 27017,
            'database': 'filestore',
        },
    },
}

db = Broker.from_config(config)

nslsii.configure_base(db)

import ophyd
ophyd.utils.startup.setup()


#import bluesky
#from ophyd import *
#from ophyd.commands import *

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
