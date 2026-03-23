import csv
import json
import os

input_file = 'Image Assets.csv'
output_file = 'Image Assets.csv.tmp'

with open(input_file, mode='r', encoding='utf-8') as infile:
    reader = csv.reader(infile)
    header = next(reader)
    
    # Identify indices
    try:
        id_idx = header.index("ID")
        title_idx = header.index("Needed image or icon, etc")
        desc_idx = header.index("Description")
        dims_idx = header.index("Dimensions")
    except ValueError as e:
        print(f"Error identifying columns: {e}")
        # Fallback to defaults if names differ slightly
        id_idx, title_idx, desc_idx, dims_idx = 0, 1, 2, 3

    new_header = header + ['JSON prompt']
    
    rows = []
    for row in reader:
        # Construct JSON from the row data
        # We handle cases where row might be shorter or longer than header
        json_data = {
            "id": row[id_idx] if len(row) > id_idx else "",
            "title": row[title_idx] if len(row) > title_idx else "",
            "prompt": row[desc_idx] if len(row) > desc_idx else "",
            "dimensions": row[dims_idx] if len(row) > dims_idx else ""
        }
        new_row = row + [json.dumps(json_data)]
        rows.append(new_row)

with open(output_file, mode='w', encoding='utf-8', newline='') as outfile:
    writer = csv.writer(outfile)
    writer.writerow(new_header)
    writer.writerows(rows)

os.replace(output_file, input_file)
print("Successfully added 'JSON prompt' column to Image Assets.csv")
