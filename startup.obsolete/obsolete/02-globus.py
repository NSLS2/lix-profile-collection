print(f"Loading {__file__}...")

# mostly written by Jun
import globus_sdk
from globus_sdk import TransferClient

global globus_dict

CLIENT_ID = "f72be8ea-938d-4701-960d-d969de28775c"   # registered by LY

def native_app_authenticate():
    confidential_client = globus_sdk.NativeAppAuthClient(client_id=CLIENT_ID)
    confidential_client.oauth2_start_flow()

    authorize_url = confidential_client.oauth2_get_authorize_url()
    print(f'Please go to this URL and login: {authorize_url}')
    auth_code = input('Please enter the code you get after login here: ').strip()
    token_response = confidential_client.oauth2_exchange_code_for_tokens(auth_code)

    globus_auth_token = token_response.by_resource_server['auth.globus.org']['access_token']
    globus_transfer_token = token_response.by_resource_server['transfer.api.globus.org']['access_token']
    return {'transfer_token':globus_transfer_token, 'auth_token':globus_auth_token}

def create_shared_endpoint(globus_dict, host_endpoint, host_path, 
                           display_name='Globus endpoint', description='description'):
    globus_transfer_token = globus_dict['transfer_token']
    scopes = "urn:globus:auth:scopes:transfer.api.globus.org:all"
    authorizer = globus_sdk.AccessTokenAuthorizer(globus_transfer_token)
    tc = TransferClient(authorizer=authorizer)
    # high level interface; provides iterators for list responses
    shared_ep_data = {
      "DATA_TYPE": "shared_endpoint",
      "host_endpoint": host_endpoint,
      "host_path": host_path,
      "display_name": display_name,
      # optionally specify additional endpoint fields
      "description": description
    }
    #r = tc.operation_mkdir(host_id, path=share_path) #TODO create the directory directly from here instead of at local level?

    tc.endpoint_autoactivate(host_endpoint, if_expires_in=3600) #necessary for real use?
    create_result = tc.create_shared_endpoint(shared_ep_data) #not the app's end point, so should fail
    endpoint_id = create_result['id']
    globus_dict['endpoint_id'] = endpoint_id
    globus_dict['transfer_client'] = tc
    return globus_dict

def add_users_to_shared_endpoint(globus_dict, user_emails, dir_name):
    auth_token = globus_dict['auth_token']
    tc = globus_dict['transfer_client']
    share_id = globus_dict['endpoint_id']

    #https://github.com/slateci/slate-portal/blob/0ee1df2b40e813702338bf989a19c12a8eb066d1/notebook/mrdp-notebook.ipynb
    ac = globus_sdk.AuthClient(authorizer=globus_sdk.AccessTokenAuthorizer(auth_token))
    r = ac.get_identities(usernames=user_emails)
    for user in r['identities']:
        user_id = user['id']
        user_email = user['username']
        rule_data = {
            'DATA_TYPE': 'access',
            'principal_type': 'identity', # Grantee is
            'principal': user_id, # a user.
            'path': '/', # Path is /
            'permissions': 'r', # Read-only
            'notify_email': user_email, # Email invite
            'notify_message': # Invite msg
            f'Data collected at the NSLS-II beamlines is now available at endpoint {dir_name} for the next two weeks.'
        }
        r = tc.add_endpoint_acl_rule(share_id, rule_data)
        print('added %s' % user_email)

def share_dir(path, emails):
    if not os.path.isdir(path):
        print(f"{path} does not exist.")
        return 
    globus_dict = native_app_authenticate()
    host_endpoint = '92212f64-44f2-11e9-9e69-0266b1fe9f9e' # NSLS-II
    globus_dict = create_shared_endpoint(globus_dict, host_endpoint=host_endpoint, 
                                         host_path=path.replace("/nsls2", "/~/nsls2/direct"))
    add_users_to_shared_endpoint(globus_dict, emails, path)

