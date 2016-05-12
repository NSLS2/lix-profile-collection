username = None
proposal_id = None
run_id = None

def login():
    """Ask the user for his credentials and proposal information for the data collection"""
    #TODO: Use PASS and LDAP integration when possible.
    global username
    global proposal_id
    global run_id

    correct_info = False

    while not correct_info:
        username = input("Please enter your username: ")
        proposal_id = input("Please enter your proposal number: ")
        run_id = input("Please enter your run unique ID: ")

        print("You informed: \nUsername: {}\nProposal: {}\nRun ID:{}".format(username, proposal_id, run_id))
        correct_info = (input("Are the information above correct? [Y, N]: ") in ['Y', 'y'])

    RE.md['owner'] = username
    RE.md['proposal_id'] = proposal_id
    RE.md['run_id'] = run_id

def logoff():
    global username
    global proposal_id
    global run_id

    """Clear the login information"""
    if (input("Are you sure you want to logout? [Y, N]: ") in ['Y', 'y']):
        username = None
        proposal_id = None
        run_id = None

        del RE.md['owner']
        del RE.md['proposal_id']
        del RE.md['run_id']      
 
