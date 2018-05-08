import logging

logger = logging.getLogger('BSUIDEBUG')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('/home/xf16id/logs/bsui-debug-2018-08-08')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
logger.addHandler(fh)

# 'application' code
#logger.debug('debug message')
#logger.info('info message')
#logger.warn('warn message')
#logger.error('error message')
#logger.critical('critical message')

# now test teh RE  loop


import numpy as np

import time

def scan_gel(step=29,sample_name="test2",xstep=10,width=0.25,cts=1):
    ystep= np.linspace(0,28,step)
    #sample_name="test2"
    i=0
    DETS=[em1, em2, pil1M_ext,pilW1_ext,pilW2_ext]
    set_pil_num_images(xstep)
    pilatus_ct_time(cts)
    ss2.y.move(0)
    yorig=ss2.y.position

    
    N = len(ystep)
    logger.info("Starting new step scan")
    for i, a in enumerate(ystep):
        logger.info("Step {} of {}".format(i, N))
        ss2.y.move(a)
        change_sample(sample_name+("_%1.2f_y" % a))
        RE(dscan(DETS, xstep, ss2.x, -width,width))
        i=i+1
    
    ss2.y.move(0)

logger.info("Begin the tests")
while True:
    # run forever
    scan_gel()
