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

pil and em2ext need to be revised to work like a flyer
    the fly scan should collect from the detectors too
    the detectors need to implement kickoff/complete??
        em2ext certainly does, since the circular buffer is used for each line
        pil can potentially use kickoff/compelte to pack hdf???
        xsp3 shouldn't need it, single hdf per scan
"""    
        
def rel_raster(exp_time, fast_axis, f_start, f_end, Nfast,
               slow_axis=None, s_start=0, s_end=0, Nslow=1, debug=False, md=None):

    fm0 = fast_axis.position
    sm0 = slow_axis.position
    yield from raster(exp_time, fast_axis, fm0+f_start, fm0+f_end, Nfast,
                      slow_axis=slow_axis, s_start=sm0+s_start, s_end=sm0+s_end, Nslow=Nslow, 
                      debug=debug, md=md)
    
def raster(exp_time, fast_axis, f_start, f_end, Nfast,
           slow_axis=None, s_start=0, s_end=0, Nslow=1, debug=False, md=None,
           em2_dt=0.005, traj_dict = {"ss_x": xps.traj, "ss_y": xps.traj}
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
    #detectors = [pil, em2ext]
    detectors = [em2ext]

    step_size = np.fabs((f_end-f_start)/(Nfast-1))
    dt = exp_time + 0.005    # exposure_period is 5ms longer than exposure_time, as defined in Pilatus

    traj = traj_dict[fast_axis.name]
    traj.define_traj(fast_axis, Nfast-1, step_size, dt, motor2=slow_axis)
    p0_fast = fast_axis.position
    motor_pos_sign = fast_axis.user_offset_dir()
    run_forward_first = ((motor_pos_sign>0 and f_start<f_end) or (motor_pos_sign<0 and f_start>f_end))
    # forward/back trajectory = fast axis motor postion increasing/decreasing
    # rampup_distance and step_size are both positive
    # ready positions are dial positions
    ready_pos_FW = np.min(np.array([f_start, f_end])*motor_pos_sign)-(traj.traj_par['rampup_distance']+step_size/2)
    ready_pos_BK = np.max(np.array([f_start, f_end])*motor_pos_sign)+(traj.traj_par['rampup_distance']+step_size/2)
    traj.traj_par['ready_pos'] = [ready_pos_FW, ready_pos_BK]
    #traj.traj_par['Nem1'] = int(((Nfast+2)*(exp_time+0.005)+0.3)*Nslow/0.05) # estimated duration of the scan
    traj.traj_par['Nem2'] = Nfast*Nslow
    traj.traj_par['Nfast'] = Nfast
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
    
    if pil in detectors:
        pil.set_trigger_mode(PilatusTriggerMode.ext_multi)
        pil.exp_time(exp_time)
        pil.set_num_images(Nfast*Nslow)
    if em2ext in detectors:
        em2ext.avg_time.put(exp_time)
        em2ext.npoints.put(Nfast)
        em2ext.rep = Nslow

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
        if em2ext in detectors:
            yield from bps.kickoff(em2ext, wait=False)
        yield from bps.complete(traj, wait=False)
        if em2ext in detectors:
            yield from bps.complete(em2ext, wait=False)
        print("leaving line()")

    @bpp.stage_decorator([traj])
    @bpp.stage_decorator(detectors)
    @bpp.run_decorator(md=_md)
    @fast_shutter_decorator()
    def inner(detectors, fast_axis, slow_axis, Nslow, pos_s):
        print("in inner()")
        
        running_forward = run_forward_first
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

        for flyer in [traj]+detectors:
            print(f"collecting from {flyer.name} ...")
            yield from bps.collect(flyer)
        print("leaving inner()")

    yield from inner(detectors, fast_axis, slow_axis, Nslow, pos_s)
    yield from sleeplan(1.0)  # give time for the current em1 timeseries monitor to finish
         