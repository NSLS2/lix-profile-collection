import bluesky.plans as bp

gs.USE_FAST_SHUTTER = True


def fast_shutter_wrapper(plan):
    if gs.USE_FAST_SHUTTER:
        plan = bp.pchain(bp.abs_set(fast_shutter.output, FastShutter.OPEN_SHUTTER, settle_time=FastShutter.SETTLE_TIME), plan)
        plan = bp.finalize_wrapper(plan, 
                                    bp.abs_set(fast_shutter.output,
                                                FastShutter.CLOSE_SHUTTER,
                                                settle_time=FastShutter.SETTLE_TIME))

    RE.md['sample_name'] = current_sample 
    RE.md['saxs'] = ({'saxs_x':saxs.x.position, 'saxs_y':saxs.y.position, 'saxs_z':saxs.z.position})
    RE.md['waxs1'] = ({'waxs1_x':waxs1.x.position, 'waxs1_y':waxs1.y.position, 'waxs1_z':waxs1.z.position})
    RE.md['waxs2'] = ({'waxs2_x':waxs2.x.position, 'waxs2_y':waxs2.y.position, 'waxs2_z':waxs2.z.position}) 
    RE.md['energy'] = ({'mono_bragg': mono.bragg.position, 'energy': getE(), 'gap': get_gap()})    
    RE.md['XBPM'] = XBPM_pos() 
    
    return (yield from plan)

fast_shutter_decorator = bp.make_decorator(fast_shutter_wrapper)


