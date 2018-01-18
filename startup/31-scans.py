from collections import deque
from ophyd.sim import motor, det

# NO LONGER SUPPORTED
# Need to use bluesky alternatives
#from bluesky.spec_api import ct, ascan, d2scan, mesh, inner_spec_decorator, partition

import bluesky.plans as bp
# rename them slightly different so they're easier to find
#relative_inner_product_scan_fs = fast_shutter_decorator(bp.relative_inner_product_scan)
#count_fs = fast_shutter_decorator(bp.count)
#grid_scan_fs = fast_shutter_decorator()(bp.grid_scan)

# NOTE: 
# the syntax for asca/dscan is:   ascan(detecotrs, n_steps, motro1, start1, end1, ...)
# the syntax for mesh is:         mesh(detectors, motor1, start1, end1, nstep1, ...)
ascan = fast_shutter_decorator()(bp.inner_product_scan)
dscan = fast_shutter_decorator()(bp.relative_inner_product_scan)
ct = fast_shutter_decorator()(bp.count)
mesh = fast_shutter_decorator()(bp.grid_scan)


#ct = fast_shutter_decorator()(ct)
#abscan = fast_shutter_decorator()(ascan)
#dscan = fast_shutter_decorator()(d2scan)
#mesh = fast_shutter_decorator()(mesh)

#DETS = [det]



#def dscan(*args, time=None, md=None):
#    """
#    Scan over one multi-motor trajectory relative to current positions.
#
 #   Parameters
  #  ----------
   # *args
    #    patterned like (``motor1, start1, stop1,`` ...,
     #                   ``motorN, startN, stopN, intervals``)
     #   where 'intervals' in the number of strides (number of points - 1)
     #   Motors can be any 'setable' object (motor, temp controller, etc.)
   # time : float, optional
   #     applied to any detectors that have a `count_time` setting
   # md : dict, optional
    #    metadata
    #"""
#    if len(args) % 3 != 1:
#        raise ValueError("wrong number of positional arguments")
#    motors = []
#    for motor, start, stop, in partition(3, args[:-1]):
#        motors.append(motor)

#    intervals = list(args)[-1]
#    num = 1 + intervals

#    inner = inner_spec_decorator('d2scan', time, motors=motors)(
 #       bp.relative_inner_product_scan)
#
 #   return (yield from inner(DETS, num, *(args[:-1]), md=md, 
  #                           per_step=one_nd_step_with_shutter))
