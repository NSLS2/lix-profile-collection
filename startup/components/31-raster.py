print(f"Loading {__file__}...")

"""
raster() is being expanded to work with different trajectories

A trajectory should perfrom a predefined motion that invovles one for two motors: fast axis and slow axis
The fast axis must be "on the list": XPS, or Delta-Tau
The slow axis in principle can be any Ophyd motor

The trajectory should be a flyer
    accomulate data untill collect is called
    following the existing structure for the raster scan: 
        loop over multiple lines, kickoff/complete for each line
    The trajectory (single motor) should implement the following:
        def_traj(), exec_traj(), readback_traj(),
        select_forward_traj()
        clear_readback(), update_read_back() 

flyers need to implement the following methods: 
    kickoff(), complete(), collect(), describe_collect(), 
    read_configuration(), describe_configuration()
    collect_asset_docs(),  

pil and emXext need to be revised to work like a flyer
    the fly scan should collect from the detectors too
    the detectors need to implement kickoff/complete??
        emXext certainly does, since the circular buffer is used for each line
        pil can potentially use kickoff/compelte to pack hdf???
        xsp3 shouldn't need it, single hdf per scan
"""    
        
def rel_raster(exp_time, fast_axis, f_start, f_end, Nfast,
               slow_axis=None, s_start=0, s_end=0, Nslow=1, debug=False, md=None, 
               detectors = [pil, em1ext, em2ext]
              ):

    fm0 = fast_axis.position
    sm0 = slow_axis.position
    yield from raster(exp_time, fast_axis, fm0+f_start, fm0+f_end, Nfast,
                      slow_axis=slow_axis, s_start=sm0+s_start, s_end=sm0+s_end, Nslow=Nslow, 
                      debug=debug, md=md, detectors=detectors)
    
def raster(exp_time, fast_axis, f_start, f_end, Nfast,
           slow_axis=None, s_start=0, s_end=0, Nslow=1, debug=False, md=None,
           detectors = [pil, em1ext, em2ext] 
          ):
    """ raster scan in fly mode using detectors with exposure time of exp_time
        detectors must be a member of pilatus_detectors_ext
        fly on the fast_axis, step on the slow_axis, both specified as Ophyd motors
        the fast_axis must be one of member of xps_trj.motors, for now this is hard-coded
        the specified positions are relative to the current position
        for the fast_axis are the average positions during detector exposure 
        
        use it within the run engine: RE(raster(...))
        update 2020aug: always use the re-defined pilatus detector group
        
    """
    step_size = np.fabs((f_end-f_start)/(Nfast-1))
    dt = exp_time + 0.005    # exposure_period is 5ms longer than exposure_time, as defined in Pilatus

    if not hasattr(fast_axis, "traj"):
        raise exception(f"don't know how to run atrajectory using {fast_axis} ...")
        
    traj = fast_axis.traj
    traj.setup_traj(fast_axis, f_start, f_end, Nfast, step_size, dt, slow_axis, Nslow)
    traj.clear_readback()
    
    if debug:
        print('## trajectory parameters:')
        print(traj.traj_par)
        print(f'## step_size = {step_size}')

    if slow_axis is not None:
        p0_slow = slow_axis.position
        pos_s = np.linspace(s_start, s_end, Nslow)
        motor_names = [slow_axis.name, fast_axis.name]
    else:
        if Nslow != 1:
            raise Exception(f"invlaid input, did not specify slow_axis, but Nslow!=1 ({Nslow})")
        p0_slow = None
        pos_s = [0]   # needed for the loop in inner()
        motor_names = [fast_axis.name]

    print(pos_s)
    print(motor_names)
    
    for det in detectors:
        if isinstance(det, LiXXspress) or isinstance(det, LiXKinetix) :
            det.set_ext_trigger(True)
            det.exp_time(exp_time)
            det.set_num_images(Nfast*Nslow)
        elif isinstance(det, LiXDetectors):
            det.set_trigger_mode(PilatusTriggerMode.ext_multi)
            det.exp_time(exp_time)
            det.set_num_images(Nfast*Nslow)
            det._flying = True
        elif isinstance(det, LiXTetrAMMext):
            det.avg_time.put(exp_time)
            det.npoints.put(Nfast)
            det.rep = Nslow
        else:
            raise Exception(f"{det} is not supported in a raster scan ...")

    print('setting up to collect %d exposures of %.2f sec ...' % (Nfast*Nslow, exp_time))
    
    scan_shape = [Nslow, Nfast]
    _md = {'shape': tuple(scan_shape),
           'plan_args': {'detectors': list(map(repr, detectors))},
           'plan_name': 'raster',
           'plan_pattern': 'outer_product',
           'motors': tuple(motor_names),
           'hints': {},
           }
    _md.update(md or {})
    _md['hints'].setdefault('dimensions', [(('time',), 'primary')])        
   
    def line():
        print("in line()")
        yield from bps.kickoff(traj, wait=False)
        for em in set([em1ext, em2ext])&set(detectors):
            yield from bps.kickoff(em, wait=False)
        yield from bps.complete(traj, wait=False)
        for em in set([em1ext, em2ext])&set(detectors):
            yield from bps.complete(em, wait=False)
        print("leaving line()")

    @bpp.stage_decorator([traj])
    @bpp.stage_decorator(detectors)
    @bpp.run_decorator(md=_md)
    @fast_shutter_decorator()
    def inner(detectors, fast_axis, slow_axis, Nslow, pos_s):
        print("in inner()")
        
        running_forward = traj.traj_par['run_forward_first']
        for sp in pos_s:
            print("start of the loop")
            if slow_axis is not None:
                print(f"moving {slow_axis.name} to {sp}")
                yield from mv(slow_axis, sp)

            print("starting trajectory ...")
            traj.select_forward_traj(running_forward)
            yield from line()
            print("Done")
            running_forward = not running_forward

        for det in detectors:
            yield from bps.complete(det, wait=True)
            #if isinstance(det, LiXDetectors): # pil
            #    yield from bps.complete(det, wait=True)
            #elif isinstance(det, LiXXspress): # xsp3
            #    yield from bps.complete(det, wait=False)

        for flyer in [traj]+detectors:
            print(f"collecting from {flyer.name} ...")
            yield from bps.collect(flyer)
        print("leaving inner()")

    yield from inner(detectors, fast_axis, slow_axis, Nslow, pos_s)
    #yield from sleeplan(1.0)  # give time for the current em1 timeseries monitor to finish, not needed if not used as monitors
         