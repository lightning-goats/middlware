# db_utils.py

import shelve
from typing import List

def set_trigger_amount(amount):
    with shelve.open('mydata.db') as shelf:
        shelf['trigger_amount'] = amount

def get_trigger_amount():
    with shelve.open('mydata.db') as shelf:
        return shelf.get('trigger_amount')

def get_cyber_herd_list():
    with shelve.open('cyber_herd_data.db') as shelf:
        return shelf.get('cyber_herd_list', [])

def update_cyber_herd_list(new_data: List[dict], reset=False):  
    db_path = 'cyber_herd_data.db'
    
    if reset:
        # Close and delete the database file
        with shelve.open(db_path) as shelf:
            shelf.close()  # Explicitly close the shelf before deleting the file
        os.remove(db_path)
        print("Database has been completely deleted.")
        return

    with shelve.open(db_path, writeback=True) as shelf:
        cyber_herd_dict = {item['pubkey']: item for item in shelf.get('cyber_herd_list', [])}

        for new_item_dict in new_data:  # new_item_dict is already a dictionary
            pubkey = new_item_dict['pubkey']
            cyber_herd_dict[pubkey] = new_item_dict  # Update or add the new item

        updated_cyber_herd_list = list(cyber_herd_dict.values())[-10:]
        shelf['cyber_herd_list'] = updated_cyber_herd_list
