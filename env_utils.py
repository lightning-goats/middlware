# env_utils.py

import os
from dotenv import load_dotenv

def validate_env_vars(required_vars):
    missing_vars = [var for var in required_vars if os.getenv(var) is None]
    if missing_vars:
        missing_vars_str = ', '.join(missing_vars)
        raise ValueError(f"The following environment variables are missing: {missing_vars_str}")

def load_environment_variables():
    # Load the environment variables
    load_dotenv()

    # List all the environment variables that your application depends on
    required_env_vars = ['OH_AUTH_1', 'API_KEY', 'HERD_KEY', 'SAT_KEY', 'API_URL', 'GOOGLE_API_KEY', 'NOS_SEC']
    validate_env_vars(required_env_vars)

    # Retrieve and return the environment variables
    return {
        'ohauth1': os.getenv('OH_AUTH_1'),
        'api_key': os.getenv('API_KEY'),
        'herd_key': os.getenv('HERD_KEY'),
        'sat_key': os.getenv('SAT_KEY'),
        'api_url': os.getenv('API_URL'),
        'google_api_key': os.getenv('GOOGLE_API_KEY'),
        'nos_sec': os.getenv('NOS_SEC')
    }
