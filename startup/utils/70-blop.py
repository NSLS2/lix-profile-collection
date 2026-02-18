from blop import RangeDOF, Objective, Agent

def intensity_metric(image, background=None, threshold_factor=0.4, edge_crop=0):
    # Convert to grayscale
    image = image.squeeze()
    if len(image.shape) == 3 and image.shape[0] == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # crop the image to remove noise around the edges
    gray = gray[200:600, 600:1000]

    # Crop edges to remove artifacts
    if edge_crop > 0:
        gray = gray[edge_crop:-edge_crop, edge_crop:-edge_crop]
        if background is not None:
            background = background[edge_crop:-edge_crop, edge_crop:-edge_crop]
    
    # Background subtraction
    if background is None:
        background = np.zeros_like(gray)
    else:
        if len(background.shape) == 3:
            background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
    corrected = cv2.subtract(gray, background)
    corrected = cv2.GaussianBlur(corrected, (5, 5), 0)
    max_intensity = np.max(corrected)
    if max_intensity == 0:
        return float('inf'), None, {}
        
    thresh_value = threshold_factor * max_intensity
    _, thresh = cv2.threshold(corrected, thresh_value, 255, cv2.THRESH_TOZERO)
    
    # ========== TOTAL INTENSITY ==========
    # Total integrated intensity
    total_intensity = np.sum(thresh)
    
    return total_intensity


def scnSF_intensity_evaluation(
    uid: str,
    suggestions: list[dict],
    threshold_factor: float = 0.4,
    edge_crop: int = 0,
) -> list[dict]:

    run = c[uid]
    images = run[f"primary/data/{scnSF.cam.name}_image"].read()
    suggestion_ids = [suggestion["_id"] for suggestion in run.metadata["start"]["blop_suggestions"]]
    results = []

    for idx, sid in enumerate(suggestion_ids):
        beam_intensity = intensity_metric(images[idx].squeeze(), threshold_factor=threshold_factor, edge_crop=edge_crop)
        results.append({
            "beam_intensity": beam_intensity / 1e6,
            "_id": sid
        })

    return results


def bpm_intensity_evaluation(uid: str, suggestions: list[dict], det=em1) -> list[dict]:
    run = c[uid]
    em1_sum_all_mean_value = run[f"primary/data/{det.name}_sum_all_mean_value"].read()
    suggestion_ids = [suggestion["_id"] for suggestion in run.metadata["start"]["blop_suggestions"]]
    results = []

    for idx, sid in enumerate(suggestion_ids):
        beam_intensity = em1_sum_all_mean_value[idx]
        results.append({
            "beam_intensity": beam_intensity,
            "_id": sid
        })

    return results


def align_crl(rep=32, x_range=0.6, y_range=0.6, det=em1, optim_steps=10):

    pos_x10 = crl.x1.position
    pos_x20 = crl.x2.position
    pos_y10 = crl.y1.position
    pos_y20 = crl.y2.position

    dofs_x = [
        RangeDOF(
            actuator=crl.x1,
            bounds=(pos_x10-x_range/2, pos_x10+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.x2,
            bounds=(pos_x20-x_range/2, pos_x20+x_range/2),
            parameter_type="float",
        ),
    ]

    dofs_y = [
        RangeDOF(
            actuator=crl.y1,
            bounds=(pos_y10-y_range/2, pos_y10+y_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y2,
            bounds=(pos_y20-y_range/2, pos_y20+y_range/2),
            parameter_type="float",
        ),
    ]

    if det.name == "camSF":
        objective_name = "beam_intensity"
        evaluation_function = scnSF_intensity_evaluation
    else:
        objective_name = f"{det.name}_sum_all_mean_value"
        evaluation_function = bpm_intensity_evaluation

    objectives = [
        Objective(name=objective_name, minimize=False),
    ]

    dets = [det]

    agent_x = Agent(dofs=dofs_x, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    agent_y = Agent(dofs=dofs_y, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    
    agent_x.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )
    agent_y.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )

    RE(fast_shutter_wrapper(agent_x.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    if optim_steps > 1:
        RE(fast_shutter_wrapper(agent_x.optimize(iterations=optim_steps)))
    best_parameterization = agent_x.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for x: {best_parameterization}")
    crl.x1.move(best_parameterization['crl_x1']) # ['crl_x1'][0]
    crl.x2.move(best_parameterization['crl_x2']) # [0]

    RE(fast_shutter_wrapper(agent_y.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    if optim_steps > 1:
        RE(fast_shutter_wrapper(agent_y.optimize(iterations=optim_steps)))
    best_parameterization = agent_y.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for y: {best_parameterization}")
    crl.y1.move(best_parameterization['crl_y1']) # [0]
    crl.y2.move(best_parameterization['crl_y2']) # [0]

    return agent_x, agent_y

def align_crl2(rep=32, x_range=0.6, y_range=0.6, det=em1, optim_steps=10):

    pos_x10 = crl.x1.position
    pos_x20 = crl.x2.position
    pos_y10 = crl.y1.position
    pos_y20 = crl.y2.position

    dofs_1 = [
        RangeDOF(
            actuator=crl.x1,
            bounds=(pos_x10-x_range/2, pos_x10+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y1,
            bounds=(pos_y10-y_range/2, pos_y10+y_range/2),
            parameter_type="float",
        ),
    ]

    dofs_2 = [
        RangeDOF(
            actuator=crl.x2,
            bounds=(pos_x20-x_range/2, pos_x20+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y2,
            bounds=(pos_y20-y_range/2, pos_y20+y_range/2),
            parameter_type="float",
        ),
    ]

    if det.name == "camSF":
        objective_name = "beam_intensity"
        evaluation_function = scnSF_intensity_evaluation
    else:
        objective_name = f"{det.name}_sum_all_mean_value"
        evaluation_function = bpm_intensity_evaluation

    objectives = [
        Objective(name=objective_name, minimize=False),
    ]

    dets = [det]

    agent_1 = Agent(dofs=dofs_1, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    agent_2 = Agent(dofs=dofs_2, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    
    agent_1.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )
    agent_2.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )

    RE(fast_shutter_wrapper(agent_1.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    if optim_steps > 1:
        RE(fast_shutter_wrapper(agent_1.optimize(iterations=optim_steps)))
    best_parameterization = agent_1.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for x: {best_parameterization}")
    crl.x1.move(best_parameterization['crl_x1']) # ['crl_x1'][0]
    crl.y1.move(best_parameterization['crl_y1']) # [0]

    RE(fast_shutter_wrapper(agent_2.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    if optim_steps > 1:
        RE(fast_shutter_wrapper(agent_2.optimize(iterations=optim_steps)))
    best_parameterization = agent_2.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for y: {best_parameterization}")
    crl.x2.move(best_parameterization['crl_x2']) # [0]
    crl.y2.move(best_parameterization['crl_y2']) # [0]

    return agent_1, agent_2

def align_crl3(rep=32, x_range=0.6, y_range=0.6, det=em1, optim_steps=10):

    pos_x10 = crl.x1.position
    pos_x20 = crl.x2.position
    pos_y10 = crl.y1.position
    pos_y20 = crl.y2.position

    dofs_1 = [
        RangeDOF(
            actuator=crl.x1,
            bounds=(pos_x10-x_range/2, pos_x10+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y1,
            bounds=(pos_y10-y_range/2, pos_y10+y_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.x2,
            bounds=(pos_x20-x_range/2, pos_x20+x_range/2),
            parameter_type="float",
        ),
        RangeDOF(
            actuator=crl.y2,
            bounds=(pos_y20-y_range/2, pos_y20+y_range/2),
            parameter_type="float",
        ),
    ]

    if det.name == "camSF":
        objective_name = "beam_intensity"
        evaluation_function = scnSF_intensity_evaluation
    else:
        objective_name = f"{det.name}_sum_all_mean_value"
        evaluation_function = bpm_intensity_evaluation

    objectives = [
        Objective(name=objective_name, minimize=False),
    ]

    dets = [det]

    agent_1 = Agent(dofs=dofs_1, objectives=objectives, sensors=dets, evaluation_function=evaluation_function)
    
    agent_1.ax_client.configure_generation_strategy(
        initialization_budget=rep,
        initialize_with_center=False,
    )

    RE(fast_shutter_wrapper(agent_1.optimize(iterations=1, n_points=rep))) #, iterations=4))) 
    if optim_steps > 1:
        RE(fast_shutter_wrapper(agent_1.optimize(iterations=optim_steps)))
    best_parameterization = agent_1.ax_client.get_best_parameterization()[0]
    print(f"best parameterization for x: {best_parameterization}")
    crl.x1.move(best_parameterization['crl_x1']) # ['crl_x1'][0]
    crl.y1.move(best_parameterization['crl_y1']) # [0]
    crl.x2.move(best_parameterization['crl_x2']) # [0]
    crl.y2.move(best_parameterization['crl_y2']) # [0]

    return agent_1


