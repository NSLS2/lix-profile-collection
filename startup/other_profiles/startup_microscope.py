print("loading configuration for microscope-EM ...")
#global DET_replace_data_path
#DET_replace_data_path = True
PilatusFilePlugin.froot = data_file_path.gpfs
PilatusCBFHandler.froot = data_file_path.gpfs

ss = PositioningStackMicroscope()
xps_trj = XPStraj('10.16.2.104', 'scan', 'test', devices={'scan.rY': ss.ry, 'scan.Y': ss.y, 'scan.X': ss.x})

camOAM       = StandardProsilica("XF:16IDA-BI{Cam:OAM}", name="camOAM")
camScope     = setup_cam("XF:16IDC-BI{Cam:Stereo}", "camScope")

#def raster(detectors, exp_time, fast_axis, f_start, f_end, Nfast, 
def raster(exp_time, fast_axis, f_start, f_end, Nfast,
           slow_axis=None, s_start=0, s_end=0, Nslow=1, md=None):
    """ raster scan in fly mode using detectors with exposure time of exp_time
        detectors must be a member of pilatus_detectors_ext
        fly on the fast_axis, step on the slow_axis, both specified as Ophyd motors
        the fast_axis must be one of member of xps_trj.motors, for now this is hard-coded
        the specified positions are relative to the current position
        for the fast_axis are the average positions during detector exposure 
        
        use it within the run engine: RE(raster(...))
        update 2020aug: always use the re-defined pilatus detector group 
    """
    #if not set(detectors).issubset(pilatus_detectors_ext):
    #    raise Exception("only pilatus_detectors_ext can be used in this raster scan.")
    pil.set_trigger_mode(PilatusTriggerMode.ext)
    detectors = [pil]
    if fast_axis.name not in xps_trj.device_names:
        raise Exception("the fast_axis is not supported in this raster scan: ", fast_axis.name)
    fast_axis_name = list(xps_trj.devices.keys())[list(xps_trj.devices.values()).index(fast_axis)]
    # 
    step_size = (f_end-f_start)/(Nfast-1)
    dt = exp_time + 0.005    # exposure_period is 5ms longer than exposure_time, as defined in Pilatus
    xps_trj.define_traj(fast_axis_name, Nfast-1, step_size, dt, motor2=slow_axis)
    p0_fast = fast_axis.position

    ready_pos = {}
    # the user motor position may be defined in opposite sign compared to the dial position (XPS)
    running_forward = (fast_axis.user_offset_dir.get()==0)
    ready_pos[running_forward] = p0_fast+f_start-xps_trj.traj_par['rampup_distance']-step_size/2
    ready_pos[not running_forward] = p0_fast+f_end+xps_trj.traj_par['rampup_distance']+step_size/2
    xps_trj.clear_readback()
    
    if slow_axis is not None:
        p0_slow = slow_axis.position
        pos_s = p0_slow+np.linspace(s_start, s_end, Nslow)
        motor_names = [slow_axis.name, fast_axis.name]
    else:
        if Nslow != 1:
            raise Exception(f"invlaid input, did not pass slow_axis, but passed Nslow != 1 ({Nslow})")
        p0_slow = None
        pos_s = []
        motor_names = [fast_axis.name]

    xps_trj.detectors = detectors
    
    #pilatus_ct_time(exp_time)
    #PilatusFilePlugin.file_number_reset = 1
    #set_pil_num_images(Nfast) #*Nslow)
    pil.exp_time(exp_time)
    pil.number_reset(True)  # set file numbers to 0
    pil.number_reset(False) # but we want to auto increment
    pil.set_num_images(Nfast)
    print('setting up to collect %d exposures of %.2f sec ...' % (Nfast*Nslow, exp_time))
    
    #motors = [fast_axis, slow_axis]
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
        
   
    @bpp.stage_decorator(detectors)
    @fast_shutter_decorator()
    def line():
        print("in line()")
        yield from bps.kickoff(xps_trj, wait=True)
        yield from bps.complete(xps_trj, wait=True)
        yield from bps.collect(xps_trj)
        print("leaving line()")

    @bpp.stage_decorator([xps_trj]) # + detectors)
    @bpp.run_decorator(md=_md)
    def inner(detectors, fast_axis, ready_pos, slow_axis, Nslow, pos_s):
        running_forward = True
        
        print("in inner()")
        for i in range(Nslow):
            print("start of the loop")
            if slow_axis is not None:
                yield from mv(fast_axis, ready_pos[running_forward], slow_axis, pos_s[i])
            else:
                yield from mv(fast_axis, ready_pos[running_forward])

            xps_trj.select_forward_traj(running_forward)
            yield from line()
            running_forward = not running_forward
            if PilatusFilePlugin.file_number_reset:
                PilatusFilePlugin.file_number_reset = 0
        print("leaving inner()")
    
    yield from inner(detectors, fast_axis, ready_pos, slow_axis, Nslow, pos_s)
    #PilatusFilePlugin.file_number_reset = 1    
    
    if slow_axis is not None:
        yield from mov(fast_axis, p0_fast, slow_axis, p0_slow)
    else:
        yield from mov(fast_axis, p0_fast)
