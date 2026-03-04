import json
import argparse
import re
import os


def generate_vehicles(n_units, capacity1, capacity2, start, end):
    results = []
    current_id = 0

    for _ in range(n_units):
        results += [
            {
                "id": current_id,
                "capacity": capacity1,
                "start": start,
                "end": end,
                "start_location": 0,
                "end_location": 0,
            },
            {
                "id": current_id + 1,
                "capacity": capacity2,
                "start": start,
                "end": end,
                "start_location": 0,
                "end_location": 0,
            },
            {
                "id": current_id + 2,
                "capacity": capacity2,
                "start": start,
                "end": end,
                "start_location": 0,
                "end_location": 0,
            },
        ]
        current_id += 3

    return results


def generate_drivers(
    n_units, start1, end1, start2, end2, start3, end3, max_working_time, vehicle_ids
):
    results = []
    current_id = 0

    for _ in range(n_units):
        results += [
            {
                "id": current_id,
                "start": start1,
                "end": end1,
                "max_working_time": max_working_time,
                "allowed_vehicles": vehicle_ids,
            },
            {
                "id": current_id + 1,
                "start": start2,
                "end": end2,
                "max_working_time": max_working_time,
                "allowed_vehicles": vehicle_ids,
            },
            {
                "id": current_id + 2,
                "start": start3,
                "end": end3,
                "max_working_time": max_working_time,
                "allowed_vehicles": vehicle_ids,
            },
        ]
        current_id += 3

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("--vehicle-start", type=int, default=0)
    parser.add_argument("--vehicle-end", type=int, default=4320)
    parser.add_argument("--vehicle-capacity1", type=int, default=70)
    parser.add_argument("--vehicle-capacity2", type=int, default=40)
    parser.add_argument("--driver-start1", type=int, default=0)
    parser.add_argument("--driver-end1", type=int, default=4320)
    parser.add_argument("--driver-start2", type=int, default=0)
    parser.add_argument("--driver-end2", type=int, default=2160)
    parser.add_argument("--driver-start3", type=int, default=2160)
    parser.add_argument("--driver-end3", type=int, default=4320)
    parser.add_argument("--driver-max-working-time", type=int, default=2880)
    args = parser.parse_args()

    # List all instance files
    instance_files = [
        os.path.join(args.input_dir, fname) for fname in os.listdir(args.input_dir)
    ]

    for instance_file in instance_files:
        with open(instance_file, "r") as f:
            instance_data = json.load(f)

        n_clusters = re.match(r".+_n(\d+)_.*\.json", os.path.basename(instance_file))

        for i in [4, 2, 1]:
            n_units = int(n_clusters.group(1)) // i

            vehicles = generate_vehicles(
                n_units=n_units,
                capacity1=args.vehicle_capacity1,
                capacity2=args.vehicle_capacity2,
                start=args.vehicle_start,
                end=args.vehicle_end,
            )

            vehicle_ids = [v["id"] for v in vehicles]

            drivers = generate_drivers(
                n_units=n_units,
                start1=args.driver_start1,
                end1=args.driver_end1,
                start2=args.driver_start2,
                end2=args.driver_end2,
                start3=args.driver_start3,
                end3=args.driver_end3,
                max_working_time=args.driver_max_working_time,
                vehicle_ids=vehicle_ids,
            )

            output_data = {
                "vehicles": vehicles,
                "drivers": drivers,
                "locations": instance_data["locations"],
                "distance_matrix": instance_data["distance_matrix"],
            }

            output_file = os.path.join(
                args.output_dir,
                os.path.basename(instance_file).replace(
                    ".json", f"_{n_units}units.json"
                ),
            )

            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=4)
