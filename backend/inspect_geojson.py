import json
import os

# WSL path
file_path = "./input/higashihie-matsushima_1_20241113.geojson"

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if 'features' in data and len(data['features']) > 0:
        first_feature = data['features'][0]
        properties = first_feature.get('properties', {})

        print("Keys in properties:")
        for key in properties.keys():
            print(f"- {key}")

        print("\nSample values:")
        for key, value in properties.items():
            str_val = str(value)
            if len(str_val) > 100:
                str_val = str_val[:100] + "..."
            print(f"{key}: {str_val}")

    else:
        print("No features found in GeoJSON.")

except Exception as e:
    print(f"Error: {e}")
