current_sample="sample"

def change_sample(sample_name):
    global current_sample
    if sample_name is None or sample_name == "":
        current_sample = "sample"
    else:
        current_sample = sample_name

