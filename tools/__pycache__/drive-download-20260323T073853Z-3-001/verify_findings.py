import os
import sys
import json

_tools_dir = os.path.dirname(os.path.abspath(__file__))
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

import notion_client_wrapper as api

def verify_findings():
    with open('db_ids.json') as f:
        db_ids = json.load(f)
    
    client = api.get_client()
    
    # Check Quests Status
    quests_props = api.get_database_properties(client, db_ids['Quests'])
    print('QUESTS STATUS OPTIONS:')
    if 'Status' in quests_props:
        print(json.dumps(quests_props['Status']['status']['options'], indent=2))
    else:
        print("Status property not found in Quests DB")
    
    # Check Settings Rows
    settings_rows = api.query_database(client, db_ids['Settings'])
    print('\nSETTINGS ROWS:')
    names = [row['properties']['Name']['title'][0]['plain_text'] for row in settings_rows if row['properties']['Name']['title']]
    for name in sorted(names):
        print(f"- {name}")
    
    # Check Set Log
    set_log_props = api.get_database_properties(client, db_ids['Set Log'])
    print('\nSET LOG PROPERTIES:')
    print(sorted(set_log_props.keys()))
    
    # Check Budget Categories
    budget_props = api.get_database_properties(client, db_ids['Budget Categories'])
    print('\nBUDGET CATEGORIES PROPERTIES:')
    print(sorted(budget_props.keys()))

if __name__ == "__main__":
    verify_findings()
