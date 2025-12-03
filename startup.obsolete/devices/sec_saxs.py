###Choosing the Experimental Type, ColumnType, Column Position, Buffer Positions will determine the flowpath, either A or B
###need 2 selection valves, one for regen pump and the other for HPLC
####column position 1 should always be to X-ray, Column position 2, regen, etc.  Valve will place these positions in the desired flowpath.
from time import sleep
from enum import Enum
import yaml
import pandas as pd

'''
class APV:
    def __init__(self):
        print("class APV called")
    def movePosition(self, buffer_position):
        print(f'I will move regen selection valve to {buffer_position}')
'''        
def switch_10port_valve(pos="A"):
    if pos=="A":
        #send_valve_cmd("GOA")
        print("A")
    elif pos=="B":
            #send_valve_cmd("GOB")
            print("B")
            
    else:
        raise Exception(f"{pos} is not a valid command to change 10-port valve! Use 'A' or 'B'.")


'''
class SEC_SAXS_collection(APV):
    experiment_type = ["X-ray_only","X-ray_UV_MALS_RID", "X-ray_Regen","UV_MALS_RID_only"]
    def __init__(self, experiment_type, columntype, column_position, buffer_position):
        self.exp_type= experiment_type
        self.columntype=columntype
        self.column_position=column_position
        self.buffer_position=buffer_position
        Enum.HPLC_SEL_VAL=1 ## need to define the urls for each selection valve in the inherited class.  leaving this as a placeholder for now
        Enum.REGEN_SEL_VAL=2
        super().__init__(self)
        
    def get_pressure_limits(columntype):
            pressure = TRP.read_pressure()
            print(f'The current upper pressure limit is {a}')
        
        
    def change_flowpath(column_position, columntype, buffer_position):
        ##check which column first and make sure pressure limit is set appropriately
        get_pressure_limits(columntype)
        sleep(1)
        if self.column_position == 1:
            valve_port=switch_10_port_valve(pos="A") ###print some feedback here and return
        else:
            valve_port= switch_10_port_valve(pos="B")  ##print some feedback here and return
        if buffer_position:
            APV.movePosition(buffer_position) ###return feedback
            
        return valve_port
'''    

def change_flowpath(column_position, columntype, buffer_position):
        ##check which column first and make sure pressure limit is set appropriately
        get_pressure_limits(columntype)
        sleep(1)
        if column_position == 1:
            valve_port=switch_10_port_valve(pos="A") ###print some feedback here and return
        else:
            valve_port= switch_10_port_valve(pos="B")  ##print some feedback here and return
        if buffer_position:
            APV.movePosition(buffer_position) ###return feedback
            
        return valve_port

def get_experiment_and_column_type(experiment_type, column_type_name=None):
    """
    Read the sec_experiment_parameters YAML file, check if the experiment type exists, and return the experiment type and column type.

    Args:
        experiment_type (str): Name of the experiment type to search for. This is obtained in Spreadsheet.

    Returns:
        str, dict: Experiment type and corresponding column type if found, otherwise None.
    """
    yaml_file = '/nsls2/data/lix/shared/config/bluesky/profile_collection/startup/devices/sec_experiment_parameters.yaml'  # Specify the fixed YAML file path here
    
    try:
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)
    except FileNotFoundError:
        print("Error: YAML file not found.")
        
    sec_exper_column = {}
    experiment_types = data.get('experiment_types', [])
    column_types = data.get('column_types', [])
    #print(experiment_types)
    for experiment in experiment_types:
            if experiment == experiment_type:
                sec_exper_column["experiment_type"] = experiment_type
                #print(sec_exper_column)
            if experiment != experiment_type:
                print(f"Error: Experiment type '{experiment_type}' not found in YAML file.")
          ##chose column type
            if column_type_name is None:
                print("NO column specified: Default to Superdex 200 Increase 5/150GL (small)")
                sec_exper_column["column_type"] = "Superdex 200 Increase 5/150 GL"
                print(sec_exper_column)
            else:
                
                for column in column_types:
                    if column == column_type_name:
                        sec_exper_column["column_type"] = column_type_name
                if column != column_type_name:
                    print(f"column name {column_type_name} is not in the list of approved columns! Approved columns are {column_types.keys()}")
            return sec_exper_column
    


def prepare_hplc_flowpath(experiment_type, column_position, buffer_position, columntype):
    """ This will need to also send the proper arguments to agilent so that it pulls from correct pump line
    """
    experiment_info, column_info = get_experiment_and_column_type(experiment_type)
    
    if experiment_info is None:
        raise Exception("Experiment type is not in the list of approved experiments!")
    
    # Rest of the function logic goes here
    if experiment_type == "X-ray_only":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "X-ray_UV_MALS_RID":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "X-ray_Regen":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
    elif experiment_type == "UV_MALS_RID_only":
        valve_port = change_flowpath(column_position, column_info, buffer_position)
        print(valve_port)
        
        

def create_agilent_seq_file(spreadsheet_fn, batch_id, proposal_id=None, run_id=None, current_cycle=None, sheet_name='Samples'):
    """
    Creates an Agilent sequence file from the spreadsheet.
    
    Args:
        spreadsheet_fn (str): File path of the spreadsheet.
        batch_id (str): Identifier for the batch.
        proposal_id (str, optional): Identifier for the proposal. Defaults to None.
        run_id (str, optional): Identifier for the run. Defaults to None.
        current_cycle (str, optional): Identifier for the current cycle. Defaults to None.
        sheet_name (str, optional): Name of the sheet in the spreadsheet. Defaults to 'Samples'.
    
    Returns:
        dict, dict: Samples dictionary, Valve position dictionary.
    """
    # Define the columns mapping for flexibility
    column_mapping = {
        "Vial": "Vial",
        "Sample Name": "Sample Name",
        "Injection Volume": "Volume",
        "Acq. method": "Acq. method",
        "Proc. method": "Proc. method",
        "Data file": "Data File",
        "Experiment Type": "Experiment Type"
        # Add more mappings as needed
    }
    
    # Read spreadsheet into a dictionary
    spreadsheet_data = parse_spreadsheet(spreadsheet_fn, sheet_name=sheet_name, return_dataframe=False)
    print(f"Spreadsheet data: {spreadsheet_data}")
    
    # Autofill the spreadsheet
    autofill_spreadsheet(spreadsheet_data, fields=["batchID"])
    
    # Check if login is required
    if proposal_id is None or run_id is None:
        print("Login is required...")
        login()
    
    # Get indices of rows with matching batch ID
    matching_indices = [i for i, value in spreadsheet_data['batchID'].items() if value == batch_id]
    print(f"Matching indices: {matching_indices}")
    
    # Initialize dictionaries for samples and valve positions
    samples = {}
    #valve_positions = {}
    
    # Define data file path
    data_file_path = f"{current_cycle}/{proposal_id}/{run_id}/<S>" 
    
    for i in matching_indices:
        # Process each row
        for key in spreadsheet_data.keys():
            if key in column_mapping:
                # Map columns according to the defined mapping
                if not isinstance(spreadsheet_data[key][i], (int, float)):
                    raise Exception(f"Not a numeric value for {key}: {spreadsheet_data[key][i]}, replace with a number")
                spreadsheet_data[column_mapping[key]][i] = spreadsheet_data[key][i]
        
        # Get valve position
        valve_positions[i] = spreadsheet_data.get("Valve Position", {}).get(i)
        print(valve_positions)
        
        # Get sample name
        sample_name = spreadsheet_data.get('Sample Name', {}).get(i)
        if sample_name:
            samples[sample_name] = {
                "acq time": spreadsheet_data.get('Run Time', {}).get(i), 
                "valve_position": valve_positions[i],
                "md": {
                    "Column type": spreadsheet_data.get('Column type', {}).get(i),
                    "Injection Volume (ul)": spreadsheet_data.get('Volume', {}).get(i),
                    "Flow Rate (ml_min)": spreadsheet_data.get('Flow Rate', {}).get(i),
                    "Sample buffer": spreadsheet_data.get('Buffer', {}).get(i),
                    "Valve Position": valve_positions[i]
                }
            }
        
        # Set data file path
        spreadsheet_data["Data File"][i] = data_file_path
    
    # Define the sequence path
    sequence_path = "/nsls2/data/lix/legacy/HPLC/Agilent/"
    
    # Convert spreadsheet data to DataFrame
    df = pd.DataFrame.from_dict(spreadsheet_data, orient='columns')
    
    # Write DataFrame to CSV
    df[df['batchID'] == batch_id].to_csv(f"{sequence_path}sequence_table.csv", index=False, encoding="ASCII",
                                         columns=["Vial", "Sample Name", "Sample Type", "Volume", "Inj/Vial", "Acq. method", "Proc. method", "Data File"])
    
    return samples, valve_positions
    
        
def run_hplc_SDK(spreadsheet_fn, batchID, sheet_name="Samples", exp=2, flowrate=0.35, column_type="Superdex 200 Increase 5/150 GL"):
    return experiment_type, 
def run_hplc_from_spreadsheet(spreadsheet_fn, batchID, sheet_name='Samples', exp=1, flowrate = 0.35, ):
    """
    Runs HPLC experiments based on data from a spreadsheet.

    Args:
        spreadsheet_fn (str): File path of the spreadsheet.
        batchID (str): Identifier for the batch.
        sheet_name (str, optional): Name of the sheet in the spreadsheet. Defaults to 'Samples'.
        exp (int, optional): Exposure time for data collection in seconds. Defaults to 1.
    """
    sequence_name = '/nsls2/data/lix/legacy/HPLC/Agilent/sequence_table.csv'
    samples, valve_position = CreateAgilentSeqFile(spreadsheet_fn, batchID, sheet_name=sheet_name)
    
    print(f"HPLC sequence file has been created in: {sequence_name}")
    print('Make sure you have selected the correct flow path for experiment and column type!')
    input("Please start Sequence in Agilent software by importing sequence_table.csv (under sequence tab), click run, then come back to this machine and then hit enter:")
    
    for sample_name, sample_info in samples.items():
        valve_pos = sample_info["md"]["Valve Position"]
        print(f"Switching valve to position {valve_pos} for sample {sample_name}...")
        switch_10port_valve(pos=valve_pos)
        
        print(f"Collecting data for {sample_name}...")
        acq_time_sec = sample_info["acq time"] * 60
        nframes = int(acq_time_sec / exp)
        collect_hplc(sample_name, exp=exp, nframes=nframes, md={'HPLC': sample_info['md']})   
        
        uid = db[-1].start['uid']
        send_to_packing_queue(uid, "HPLC")
    
    pil.use_sub_directory()    
    print(f'Sequence collection finished for batch {batchID} from {spreadsheet_fn}')

            


