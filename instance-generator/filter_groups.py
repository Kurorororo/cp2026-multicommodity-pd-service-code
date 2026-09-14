import argparse
import os
import json

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=str)
    parser.add_argument("output_dir", type=str)
    parser.add_argument("--groups", type=str, nargs="+", default=["depot", "lunch"])
    args = parser.parse_args()

    for fname in os.listdir(args.input_dir):
        if not fname.endswith(".json"):
            continue

        input_path = os.path.join(args.input_dir, fname)
        output_path = os.path.join(args.output_dir, fname)

        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        filtered_locations = [
            loc for loc in data["locations"] if loc["group"] in args.groups
        ]
        data["locations"] = filtered_locations

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
