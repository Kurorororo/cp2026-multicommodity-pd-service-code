import argparse
import os
import random
import json
from typing import List


class RequestParameters:
    def __init__(
        self,
        start_choices: List[int],
        duration: int,
        demand_choices: List[int],
        service_time: int,
    ):
        self.start_choices = start_choices
        self.duration = duration
        self.demand_choices = demand_choices
        self.service_time = service_time


def create_request(
    request_params: RequestParameters,
):
    start = random.choice(request_params.start_choices)
    end = start + request_params.duration

    req = {
        "start": start,
        "end": end,
        "service_time": request_params.service_time,
        "demand": random.choice(request_params.demand_choices),
    }

    return req


def create_requests(
    locations,
    id_prefix,
    p,
    request_params: RequestParameters,
    location_type,
    group,
):
    results = []
    location_indices = []
    current_id = id_prefix

    for loc in locations:
        if random.random() < p:
            req = create_request(request_params)
            req["id"] = current_id
            req["type"] = location_type
            req["group"] = group
            req["mandatory"] = False
            location_indices.append(loc["id"])

            current_id += 1
            results.append(req)

    return results, location_indices


def create_center(
    group,
    location_type,
    start,
    end,
    service_time,
):
    return {
        "group": group,
        "type": location_type,
        "start": start,
        "end": end,
        "service_time": service_time,
        "demand": 0,
        "mandatory": False,
    }


def add_transportation_time_limits(
    requests,
    transportation_time_limit,
    center_location,
    location_indices,
    distance_matrix,
):
    for req, loc_index in zip(requests, location_indices):
        distance = distance_matrix[loc_index][center_location["id"]]
        req["transportation_time_limit"] = transportation_time_limit + distance


def add_scores(
    requests,
    location_types,
    location_groups,
    score,
):
    for req in requests:
        if req["type"] in location_types and req["group"] in location_groups:
            req["score"] = score


def adjust_distance_matrix(distance_matrix, location_indices):
    n = len(location_indices)
    new_distance_matrix = [[0 for _ in range(n)] for _ in range(n)]

    for i in range(n):
        for j in range(n):
            old_i = location_indices[i]
            old_j = location_indices[j]
            new_distance_matrix[i][j] = distance_matrix[old_i][old_j]

    return new_distance_matrix


def generate_instance(locations, distance_matrix, args):
    centers = [(i, loc) for i, loc in enumerate(locations) if loc["type"] == "center"]
    depot = create_center(
        group="depot",
        location_type="depot",
        start=args.depot_start,
        end=args.depot_end,
        service_time=args.depot_service_time,
    )
    depot["id"] = 0
    location_indices = [centers[0][0]]

    lunch_center = create_center(
        group="lunch",
        location_type="pickup-center",
        start=args.lunch_pickup_start,
        end=args.lunch_pickup_end,
        service_time=args.lunch_pickup_service,
    )
    lunch_center["id"] = 1
    location_indices.append(centers[1][0])

    package_center = create_center(
        group="package",
        location_type="pickup-center",
        start=args.package_pickup_start,
        end=args.package_pickup_end,
        service_time=args.package_pickup_service,
    )
    package_center["id"] = 2
    location_indices.append(centers[2][0])

    collection_center = create_center(
        group="collection",
        location_type="delivery-center",
        start=args.collection_delivery_start,
        end=args.collection_delivery_end,
        service_time=args.collection_delivery_service,
    )
    collection_center["id"] = 3
    location_indices.append(centers[3][0])

    locations = [loc for loc in locations if loc["type"] == "rural"]
    id_prefix = 4

    lunch_params = RequestParameters(
        start_choices=args.lunch_delivery_start_choices,
        duration=args.lunch_delivery_duration,
        demand_choices=args.lunch_demand_choices,
        service_time=args.lunch_delivery_service,
    )
    lunch_requests, lunch_location_indices = create_requests(
        locations,
        id_prefix,
        args.lunch_request_probability,
        lunch_params,
        location_type="delivery-customer",
        group="lunch",
    )
    add_transportation_time_limits(
        lunch_requests,
        args.transportation_time_limit,
        lunch_center,
        lunch_location_indices,
        distance_matrix,
    )
    location_indices.extend(lunch_location_indices)
    id_prefix += len(lunch_requests)

    package_params = RequestParameters(
        start_choices=args.package_delivery_start_choices,
        duration=args.package_delivery_duration,
        demand_choices=args.package_demand_choices,
        service_time=args.package_delivery_service,
    )
    package_requests, package_location_indices = create_requests(
        locations,
        id_prefix,
        args.package_request_probability,
        package_params,
        location_type="delivery-customer",
        group="package",
    )
    n_package_locations = len(package_location_indices)
    location_indices.extend(package_location_indices)
    id_prefix += len(package_requests)

    collection_params = RequestParameters(
        start_choices=args.collection_pickup_start_choices,
        duration=args.collection_pickup_duration,
        demand_choices=args.collection_demand_choices,
        service_time=args.collection_pickup_service,
    )
    collection_requests, collection_location_indices = create_requests(
        locations,
        id_prefix,
        args.collection_request_probability,
        collection_params,
        location_type="pickup-customer",
        group="collection",
    )
    location_indices.extend(collection_location_indices)
    n_collection_locations = len(collection_location_indices)

    requests = (
        [depot, lunch_center, package_center, collection_center]
        + lunch_requests
        + package_requests
        + collection_requests
    )
    add_scores(
        requests,
        ["depot", "pickup-center", "delivery-center"],
        ["depot", "lunch", "package", "collection"],
        0,
    )
    add_scores(requests, ["pickup-customer"], ["collection"], 1)
    add_scores(requests, ["delivery-customer"], ["package"], n_collection_locations + 1)
    add_scores(
        requests,
        ["delivery-customer"],
        ["lunch"],
        n_package_locations * (n_collection_locations + 1) + n_collection_locations + 1,
    )
    new_distance_matrix = adjust_distance_matrix(distance_matrix, location_indices)

    data = {
        "locations": requests,
        "distance_matrix": new_distance_matrix,
    }

    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_dir", type=str, help="Input directory containing instance JSON files"
    )
    parser.add_argument(
        "output_dir", type=str, help="Output directory for modified instance JSON files"
    )

    parser.add_argument("--depot-start", type=int, default=0)
    parser.add_argument("--depot-end", type=int, default=4320)
    parser.add_argument("--depot-service-time", type=int, default=0)

    parser.add_argument("--lunch-request-probability", type=float, default=0.5)
    parser.add_argument("--lunch-pickup-start", type=int, default=720)
    parser.add_argument("--lunch-pickup-end", type=int, default=2160)
    parser.add_argument("--lunch-pickup-service", type=int, default=60)
    parser.add_argument(
        "--lunch-delivery-start-choices", type=int, nargs="+", default=[1440]
    )
    parser.add_argument("--lunch-delivery-duration", type=int, default=1440)
    parser.add_argument("--lunch-delivery-service", type=int, default=24)
    parser.add_argument("--lunch-demand-choices", type=int, nargs="+", default=[2, 4])
    parser.add_argument("--transportation-time-limit", type=int, default=360)

    parser.add_argument("--package-request-probability", type=float, default=0.5)
    parser.add_argument("--package-pickup-start", type=int, default=0)
    parser.add_argument("--package-pickup-end", type=int, default=4320)
    parser.add_argument("--package-pickup-service", type=int, default=60)
    parser.add_argument(
        "--package-delivery-start-choices",
        type=int,
        nargs="+",
        default=[
            0,
            360,
            720,
            1080,
            1440,
            1800,
            2160,
            2520,
            2880,
        ],
    )
    parser.add_argument("--package-delivery-duration", type=int, default=1440)
    parser.add_argument("--package-delivery-service", type=int, default=24)
    parser.add_argument("--package-demand-choices", type=int, nargs="+", default=[5])

    parser.add_argument("--collection-request-probability", type=float, default=0.1)
    parser.add_argument("--collection-delivery-start", type=int, default=0)
    parser.add_argument("--collection-delivery-end", type=int, default=4320)
    parser.add_argument("--collection-delivery-service", type=int, default=60)
    parser.add_argument(
        "--collection-pickup-start-choices",
        type=int,
        nargs="+",
        default=[
            0,
            360,
            720,
            1080,
            1440,
            1800,
            2160,
            2520,
            2880,
        ],
    )
    parser.add_argument("--collection-pickup-duration", type=int, default=1440)
    parser.add_argument("--collection-pickup-service", type=int, default=24)
    parser.add_argument("--collection-demand-choices", type=int, nargs="+", default=[5])

    args = parser.parse_args()

    # List all JSON files in the input directory
    input_files = [f for f in os.listdir(args.input_dir) if f.endswith(".json")]

    for filename in input_files:
        input_path = os.path.join(args.input_dir, filename)
        output_path = os.path.join(args.output_dir, filename)

        with open(input_path, "r") as f:
            instance_data = json.load(f)

        locations = instance_data["locations"]
        distance_matrix = instance_data["distance_matrix"]

        new_instance_data = generate_instance(locations, distance_matrix, args)

        with open(output_path, "w") as f:
            json.dump(new_instance_data, f, indent=2)
