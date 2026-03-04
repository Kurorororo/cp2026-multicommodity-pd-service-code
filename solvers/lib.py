import copy
import math


def ceil_round(x, n_decimal_places):
    """
    Round a number to the nearest integer with n_decimal_places decimal places.
    """
    factor = 10**n_decimal_places
    return int(math.ceil(x * factor))


def floor_round(x, n_decimal_places):
    """
    Round a number to the nearest integer with n_decimal_places decimal places.
    """
    factor = 10**n_decimal_places
    return int(math.floor(x * factor))


def round_to_nearest(x, n_decimal_places):
    """
    Round a number to the nearest integer with n_decimal_places decimal places.
    """
    factor = 10**n_decimal_places
    return int(round(x * factor))


def round_instance(data, n_decimal_places):
    rounded_data = copy.deepcopy(data)

    rounded_data["distance_matrix"] = [
        [ceil_round(d, n_decimal_places) for d in row]
        for row in data["distance_matrix"]
    ]

    for i in range(len(data["locations"])):
        rounded_data["locations"][i]["start"] = ceil_round(
            data["locations"][i]["start"], n_decimal_places
        )
        rounded_data["locations"][i]["end"] = floor_round(
            data["locations"][i]["end"], n_decimal_places
        )
        rounded_data["locations"][i]["service_time"] = ceil_round(
            data["locations"][i]["service_time"], n_decimal_places
        )

        if (
            "transportation_time_limit" in data["locations"][i]
            and data["locations"][i]["transportation_time_limit"] is not None
        ):
            rounded_data["locations"][i]["transportation_time_limit"] = floor_round(
                data["locations"][i]["transportation_time_limit"],
                n_decimal_places,
            )

    for i in range(len(data["drivers"])):
        rounded_data["drivers"][i]["start"] = ceil_round(
            data["drivers"][i]["start"], n_decimal_places
        )
        rounded_data["drivers"][i]["end"] = floor_round(
            data["drivers"][i]["end"], n_decimal_places
        )
        rounded_data["drivers"][i]["max_working_time"] = floor_round(
            data["drivers"][i]["max_working_time"], n_decimal_places
        )

    for i in range(len(data["vehicles"])):
        rounded_data["vehicles"][i]["start"] = ceil_round(
            data["vehicles"][i]["start"], n_decimal_places
        )
        rounded_data["vehicles"][i]["end"] = floor_round(
            data["vehicles"][i]["end"], n_decimal_places
        )

    return rounded_data


def round_solution(solution, n_decimal_places):
    rounded_solution = copy.deepcopy(solution)

    for i, tour in enumerate(rounded_solution):
        for j in range(len(tour["plan"])):
            rounded_solution[i]["plan"][j]["time"] = round_to_nearest(
                tour["plan"][j]["time"], n_decimal_places
            )

    return rounded_solution


def deround_solution(solution, n_decimal_places):
    derounded_solution = copy.deepcopy(solution)

    for i, tour in enumerate(derounded_solution):
        for j in range(len(tour["plan"])):
            derounded_solution[i]["plan"][j]["time"] /= 10**n_decimal_places

    return derounded_solution


def validate_plan(data, vehicle, driver, id_to_location, plan, epsilon):
    visited = set()
    pos = plan[0]["pos"]

    if pos != vehicle["start_location"]:
        print(
            "Tour {} starts at customer {}, but it should start at {}".format(
                plan,
                pos,
                vehicle["start_location"],
            )
        )

        return None

    previous = None
    time = None
    score = 0

    groups = {
        c["group"]
        for c in data["locations"]
        if c["type"] in ["pickup-customer", "delivery-customer"]
    }
    load = {g: 0 for g in groups}
    last_pickup_started = {g: 0 for g in groups}

    for c in plan:
        location = id_to_location[c["pos"]]

        if location["id"] in visited:
            print(
                "Customer {} is visited more than once by the same tour".format(
                    pos,
                )
            )

            return None

        if previous is None:
            if c["time"] + epsilon < vehicle["start"]:
                print(
                    "Tour starts at time {}, but vehicle {} is unavailable until {}".format(
                        c["time"], vehicle["id"], vehicle["start"]
                    )
                )

                return None

            if c["time"] + epsilon < driver["start"]:
                print(
                    "Tour starts at time {}, but driver {} is unavailable until {}".format(
                        time, driver["id"], driver["start"]
                    )
                )

                return None

            start = c["time"]
        else:
            if (
                time
                + previous["service_time"]
                + data["distance_matrix"][previous["id"]][location["id"]]
                > c["time"] + epsilon
            ):
                print(
                    "Arriving at location {} at time {}, but time {} is required".format(
                        location["id"],
                        time
                        + previous["service_time"]
                        + data["distance_matrix"][previous["id"]][location["id"]],
                        c["time"],
                    )
                )

                return None

        if c["time"] + epsilon < location["start"]:
            print(
                "Arriving at location {} at time {}, but the earliest time is {}".format(
                    location["id"],
                    c["time"],
                    location["start"],
                )
            )

            return None

        if c["time"] > location["end"] + epsilon:
            print(
                "Arriving at location {} at time {}, but the latest time is {}".format(
                    location["id"],
                    c["time"],
                    location["end"],
                )
            )

            return None

        if location["type"] == "pickup-center":
            if c["load_change"] < 0:
                print(
                    "Pickup center {} has load change {}, but it should be nonnegative".format(
                        location["id"], c["load_change"]
                    )
                )

                return None

            last_pickup_started[location["group"]] = c["time"]

        if location["type"] == "delivery-customer":
            if c["load_change"] != -location["demand"]:
                print(
                    "Customer {} has load change {}, but it should be -{}".format(
                        location["id"], c["load_change"], location["demand"]
                    )
                )

                return None

            if (
                "transportation_time_limit" in location
                and location["transportation_time_limit"] is not None
                and c["time"] - last_pickup_started[location["group"]]
                > location["transportation_time_limit"]
            ):
                print(
                    "Customer {} exceeds transportation time limit {}".format(
                        location["id"], location["transportation_time_limit"]
                    )
                )

                return None

            visited.add(c["pos"])
            score += location["score"]

        if location["type"] == "pickup-customer":
            if c["load_change"] != location["demand"]:
                print(
                    "Pickup customer {} has load change {}, but it should be {}".format(
                        location["id"], c["load_change"], location["demand"]
                    )
                )

                return None

            visited.add(c["pos"])
            score += location["score"]

        if location["type"] == "delivery-center":
            if c["load_change"] > 0:
                print(
                    "Delivery center {} has load change {}, but it should be non-positive".format(
                        location["id"], c["load_change"]
                    )
                )

                return None

        if location["group"] in load:
            load[location["group"]] = load[location["group"]] + c["load_change"]

            if load[location["group"]] < 0:
                print(
                    "Tour {} has a negative load {} for group {}".format(
                        plan, load[location["group"]], location["group"]
                    )
                )

                return None

        total_load = sum(load.values())

        if total_load > vehicle["capacity"]:
            print(
                "Tour {} has a total load {} exceeding the vehicle capacity {}".format(
                    plan, total_load, vehicle["capacity"]
                )
            )

            return None

        previous = location
        time = c["time"]

    if sum(load.values()) != 0:
        print("Tour {} ends with a non-zero load {}".format(plan, sum(load.values())))

        return None

    if pos != vehicle["end_location"]:
        print(
            "Tour {} ends at customer {}, but it should end at {}".format(
                plan, pos, vehicle["end_location"]
            )
        )

        return None

    if time > vehicle["end"] + epsilon:
        print(
            "Tour ends at time {}, but vehicle {} is unavailable after {}".format(
                time, vehicle["id"], vehicle["end"]
            )
        )

        return None

    if time > driver["end"] + epsilon:
        print(
            "Tour ends at time {}, but driver {} is unavailable after {}".format(
                time, driver["id"], driver["end"]
            )
        )

        return None

    if time - start > driver["max_working_time"] + epsilon:
        print(
            "Tour requires working time {} while the maximum working time for driver {} is {}",
            time - start,
            driver["id"],
            driver["max_working_time"],
        )

    return visited, score


def validate(data, solution, epsilon=1e-6):
    id_to_vehicle = {v["id"]: v for v in data["vehicles"]}
    id_to_driver = {d["id"]: d for d in data["drivers"]}
    id_to_location = {c["id"]: c for c in data["locations"]}
    used_vehicles = set()
    used_drivers = set()
    visited = set()
    score = 0

    for tour in solution:
        if tour["driver"] not in id_to_driver:
            print(
                "Tour {} uses driver {}, but this driver is not in the data".format(
                    tour, tour["driver"]
                )
            )

            return False

        if tour["driver"] in used_drivers:
            print("Driver {} is used in more than one tour".format(tour["driver"]))

            return False

        used_drivers.add(tour["driver"])

        if tour["vehicle"] not in id_to_vehicle:
            print(
                "Tour {} uses vehicle {}, but this vehicle is not in the data".format(
                    tour, tour["vehicle"]
                )
            )

            return False

        if tour["vehicle"] in used_vehicles:
            print("Vehicle {} is used in more than one tour".format(tour["vehicle"]))

            return False

        used_vehicles.add(tour["vehicle"])

        vehicle = id_to_vehicle[tour["vehicle"]]
        driver = id_to_driver[tour["driver"]]

        if tour["vehicle"] not in driver["allowed_vehicles"]:
            print(
                "Tour {} uses vehicle {}, but this vehicle is not allowed for driver {}".format(
                    tour, tour["vehicle"], tour["driver"]
                )
            )

            return False

        result = validate_plan(
            data, vehicle, driver, id_to_location, tour["plan"], epsilon=epsilon
        )

        if result is None:
            print("Tour {} is invalid".format(tour))
            return False

        tour_visited, plan_score = result

        intersection = visited.intersection(tour_visited)

        if intersection:
            print(
                "Tour {} visits the same customers {} as another tour".format(
                    tour, intersection
                )
            )

            return False

        visited.update(tour_visited)

        score += plan_score

    mandatory_ids = set(
        c["id"]
        for c in data["locations"]
        if c["type"] == "delivery-customer" and c["mandatory"]
    )

    if not mandatory_ids.issubset(visited):
        print(
            "The solution does not visit mandatory customers {}".format(
                mandatory_ids - visited,
            )
        )

        return False

    return True


def classify_locations(data):
    depots = []
    pickup_centers = []
    delivery_customers = []
    delivery_centers = []
    pickup_customers = []

    for loc in data["locations"]:
        if loc["type"] == "depot":
            depots.append(loc)

        if loc["type"] == "pickup-center":
            pickup_centers.append(loc)

        if loc["type"] == "delivery-customer":
            delivery_customers.append(loc)

        if loc["type"] == "delivery-center":
            delivery_centers.append(loc)

        if loc["type"] == "pickup-customer":
            pickup_customers.append(loc)

    return (
        depots,
        pickup_centers,
        delivery_customers,
        delivery_centers,
        pickup_customers,
    )


def tighten_time_windows(
    vehicles,
    depots,
    pickup_centers,
    delivery_customers,
    delivery_centers,
    pickup_customers,
    distance_matrix,
):
    id_to_depot = {depot["id"]: depot for depot in depots}
    new_vehicles = []

    for v in vehicles:
        result_v = copy.deepcopy(v)
        result_v["start"] = max(v["start"], id_to_depot[v["start_location"]]["start"])
        result_v["end"] = min(v["end"], id_to_depot[v["end_location"]]["end"])
        new_vehicles.append(result_v)

    result_pickup_centers = []
    groups_with_pickup_centers = set()

    for p in pickup_centers:
        min_pickup_start = min(
            c["start"] - distance_matrix[p["id"]][c["id"]] - p["service_time"]
            for c in pickup_centers + delivery_customers + pickup_customers
            if c["id"] != p["id"]
            and (c["type"] != "delivery-customer" or c["group"] == p["group"])
        )
        min_pickup_start = max(
            min_pickup_start,
            min(
                v["start"]
                + id_to_depot[v["start_location"]]["service_time"]
                + distance_matrix[v["start_location"]][p["id"]]
                for v in new_vehicles
            ),
        )
        max_pickup_end = max(
            c["end"] - distance_matrix[p["id"]][c["id"]] - p["service_time"]
            for c in delivery_customers
            if c["group"] == p["group"]
        )
        result_p = copy.deepcopy(p)
        result_p["start"] = max(result_p["start"], min_pickup_start)
        result_p["end"] = min(result_p["end"], max_pickup_end)

        if result_p["start"] <= result_p["end"]:
            groups_with_pickup_centers.add(p["group"])
            result_pickup_centers.append(result_p)

    result_delivery_customers = []
    groups_with_delivery_customers = set()
    groups_without_pickup_centers = set()

    for c in delivery_customers:
        if c["group"] not in groups_with_pickup_centers:
            groups_without_pickup_centers.add(c["group"])
            continue

        min_customer_start = min(
            p["start"] + p["service_time"] + distance_matrix[p["id"]][c["id"]]
            for p in result_pickup_centers
            if p["group"] == c["group"]
        )
        max_customer_end = max(
            v["end"] - distance_matrix[c["id"]][v["end_location"]] - c["service_time"]
            for v in new_vehicles
        )
        result_c = copy.deepcopy(c)
        result_c["start"] = max(result_c["start"], min_customer_start)
        result_c["end"] = min(result_c["end"], max_customer_end)

        if result_c["start"] <= result_c["end"]:
            groups_with_delivery_customers.add(c["group"])
            result_delivery_customers.append(result_c)

    result_delivery_centers = []
    groups_with_delivery_centers = set()

    for d in delivery_centers:
        min_delivery_start = min(
            c["start"] + c["service_time"] + distance_matrix[c["id"]][d["id"]]
            for c in pickup_customers
            if c["group"] == d["group"]
        )
        max_delivery_end = max(
            c["end"] + c["service_time"] + distance_matrix[c["id"]][d["id"]]
            for c in delivery_centers + pickup_customers + delivery_customers
            if c["id"] != d["id"]
            and (c["type"] != "pickup-customer" or c["group"] == d["group"])
        )
        max_delivery_end = min(
            max_delivery_end,
            max(
                v["end"]
                - distance_matrix[d["id"]][v["end_location"]]
                - d["service_time"]
                for v in new_vehicles
            ),
        )
        result_d = copy.deepcopy(d)
        result_d["start"] = max(result_d["start"], min_delivery_start)
        result_d["end"] = min(result_d["end"], max_delivery_end)

        if result_d["start"] <= result_d["end"]:
            groups_with_delivery_centers.add(d["group"])
            result_delivery_centers.append(result_d)

    result_pickup_customers = []
    groups_with_pickup_customers = set()
    groups_without_delivery_centers = set()

    for c in pickup_customers:
        if c["group"] not in groups_with_delivery_centers:
            groups_without_delivery_centers.add(c["group"])
            continue

        min_customer_start = min(
            v["start"]
            + id_to_depot[v["start_location"]]["service_time"]
            + distance_matrix[v["start_location"]][c["id"]]
            for v in new_vehicles
        )
        max_customer_end = max(
            d["end"] + d["service_time"] + distance_matrix[d["id"]][c["id"]]
            for d in result_delivery_centers
            if d["group"] == c["group"]
        )
        result_c = copy.deepcopy(c)
        result_c["start"] = max(result_c["start"], min_customer_start)
        result_c["end"] = min(result_c["end"], max_customer_end)

        if result_c["start"] <= result_c["end"]:
            groups_with_pickup_customers.add(c["group"])
            result_pickup_customers.append(result_c)

    result_pickup_centers = [
        p for p in result_pickup_centers if p["group"] in groups_with_delivery_customers
    ]
    result_delivery_centers = [
        d for d in result_delivery_centers if d["group"] in groups_with_pickup_customers
    ]

    groups_with_only_customers = (
        groups_without_pickup_centers & groups_without_delivery_centers
    )

    for c in pickup_customers:
        group = c["group"]

        if group not in groups_with_only_customers:
            continue

        min_customer_start = min(
            v["start"]
            + id_to_depot[v["start_location"]]["service_time"]
            + distance_matrix[v["start_location"]][c["id"]]
            for v in new_vehicles
        )
        max_customer_end = max(
            d["end"] - distance_matrix[c["id"]][d["id"]] - c["service_time"]
            for d in delivery_customers
            if d["group"] == c["group"]
        )
        result_c = copy.deepcopy(c)
        result_c["start"] = max(result_c["start"], min_customer_start)
        result_c["end"] = min(result_c["end"], max_customer_end)

        if result_c["start"] <= result_c["end"]:
            result_pickup_customers.append(result_c)

    for c in delivery_customers:
        group = c["group"]

        if group not in groups_with_only_customers:
            continue

        min_customer_start = min(
            p["start"] + p["service_time"] + distance_matrix[p["id"]][c["id"]]
            for p in pickup_customers
            if p["group"] == c["group"]
        )
        max_customer_end = max(
            v["end"] - distance_matrix[c["id"]][v["end_location"]] - c["service_time"]
            for v in new_vehicles
        )
        result_c = copy.deepcopy(c)
        result_c["start"] = max(result_c["start"], min_customer_start)
        result_c["end"] = min(result_c["end"], max_customer_end)

        if result_c["start"] <= result_c["end"]:
            result_delivery_customers.append(result_c)

    result_vehicles = []

    for v in new_vehicles:
        result_v = copy.deepcopy(v)

        if len(result_delivery_customers) > 0 or len(result_pickup_customers) > 0:
            min_vehicle_start = min(
                p["start"]
                - distance_matrix[result_v["start_location"]][p["id"]]
                - id_to_depot[result_v["start_location"]]["service_time"]
                for p in result_pickup_centers + result_pickup_customers
            )
            max_vehicle_end = max(
                c["end"]
                + c["service_time"]
                + distance_matrix[c["id"]][result_v["end_location"]]
                for c in result_delivery_customers + result_delivery_centers
            )
            result_v["start"] = max(result_v["start"], min_vehicle_start)
            result_v["end"] = min(result_v["end"], max_vehicle_end)
            result_vehicles.append(result_v)

    result_depots = copy.deepcopy(depots)
    depot_id_to_start = {}
    depot_id_to_end = {}

    for v in result_vehicles:
        if (
            v["start_location"] not in depot_id_to_start
            or v["start"] < depot_id_to_start[v["start_location"]]
        ):
            depot_id_to_start[v["start_location"]] = v["start"]

        if (
            v["end_location"] not in depot_id_to_end
            or v["end"] > depot_id_to_end[v["end_location"]]
        ):
            depot_id_to_end[v["end_location"]] = v["end"]

    for d in result_depots:
        if d["id"] in depot_id_to_start:
            d["start"] = max(d["start"], depot_id_to_start[d["id"]])

        if d["id"] in depot_id_to_end:
            d["end"] = min(d["end"], depot_id_to_end[d["id"]])

    return (
        result_vehicles,
        result_depots,
        result_pickup_centers,
        result_delivery_customers,
        result_delivery_centers,
        result_pickup_customers,
    )


def driver_vehicle_filter_propagation(data):
    vehicles = data["vehicles"]
    drivers = data["drivers"]

    id_to_vehicle = {v["id"]: v for v in vehicles}
    new_drivers = []
    allowed_vehicle_set = set()

    for d in drivers:
        allowed_vehicles = [
            i
            for i in d["allowed_vehicles"]
            if i in id_to_vehicle
            if d["start"] <= id_to_vehicle[i]["end"]
            and d["end"] >= id_to_vehicle[i]["start"]
        ]

        if len(allowed_vehicles) > 0:
            new_d = copy.deepcopy(d)
            new_d["allowed_vehicles"] = allowed_vehicles
            new_d["max_working_time"] = min(
                new_d["max_working_time"],
                new_d["end"] - new_d["start"],
            )
            new_drivers.append(new_d)
            allowed_vehicle_set.update(allowed_vehicles)

    new_vehicles = []

    for v in vehicles:
        if v["id"] in allowed_vehicle_set:
            new_v = copy.deepcopy(v)
            new_vehicles.append(new_v)

    return new_vehicles, new_drivers


def preprocess_data(data):
    depots, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        classify_locations(data)
    )
    (
        vehicles,
        depots,
        pickup_centers,
        delivery_customers,
        delivery_centers,
        pickup_customers,
    ) = tighten_time_windows(
        data["vehicles"],
        depots,
        pickup_centers,
        delivery_customers,
        delivery_centers,
        pickup_customers,
        data["distance_matrix"],
    )
    vehicles, drivers = driver_vehicle_filter_propagation(data)

    if len(vehicles) == 0:
        print("No vehicles can be used.")
        return None

    if len(drivers) == 0:
        print("No drivers can be used.")
        return None

    if len(delivery_customers) == 0 and len(pickup_customers) == 0:
        print("No customers can be visited.")
        return None

    return {
        "vehicles": vehicles,
        "drivers": drivers,
        "locations": depots
        + pickup_centers
        + delivery_customers
        + delivery_centers
        + pickup_customers,
        "distance_matrix": data["distance_matrix"],
    }


def compute_max_visits(data):
    depots, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        classify_locations(data)
    )
    group_to_customers = {}

    for c in delivery_customers + pickup_customers:
        group = c["group"]

        if group not in group_to_customers:
            group_to_customers[group] = []

        group_to_customers[group].append(c)

    id_to_depot = {d["id"]: d for d in depots}
    result = {}

    for p in pickup_centers + delivery_centers:
        # Bound from time
        trip_times = sorted(
            [
                p["service_time"]
                + data["distance_matrix"][p["id"]][c["id"]]
                + c["service_time"]
                + data["distance_matrix"][c["id"]][p["id"]]
                for c in group_to_customers[p["group"]]
            ]
        )

        # Bound per vehicle
        for v in data["vehicles"]:
            if v["start"] > p["end"] or v["end"] < p["start"]:
                result[v["id"], p["id"]] = 0
                continue

            time_bound = 0
            time = max(
                p["start"],
                v["start"]
                + id_to_depot[v["start_location"]]["service_time"]
                + data["distance_matrix"][v["start_location"]][p["id"]],
            )
            end = min(
                p["end"],
                v["end"]
                - data["distance_matrix"][p["id"]][v["end_location"]]
                - p["service_time"],
            )

            for t in trip_times:
                time_bound += 1
                time += t

                if time > end:
                    break

            result[v["id"], p["id"]] = min(
                len(group_to_customers[p["group"]]), time_bound
            )

    return result


def extract_edges(data):
    edges = set()
    locations = data["locations"]

    for ci in locations:
        for cj in locations:
            if ci["id"] == cj["id"]:
                continue

            if ci["type"] == "depot" and cj["type"] == "depot":
                continue

            if ci["type"] == "depot" and cj["type"] not in (
                "pickup-customer",
                "pickup-center",
            ):
                continue

            if cj["type"] == "depot" and ci["type"] not in (
                "delivery-customer",
                "delivery-center",
            ):
                continue

            if (
                (ci["type"] == "pickup-center" and cj["type"] == "pickup-center")
                or (ci["type"] == "delivery-center" and cj["type"] == "delivery-center")
            ) and ci["group"] == cj["group"]:
                continue

            if (
                ci["start"]
                + ci["service_time"]
                + data["distance_matrix"][ci["id"]][cj["id"]]
                > cj["end"]
            ):
                continue

            edges.add((ci["id"], cj["id"]))

    return edges


def postprocess_solution(data, solution, initial_solution=None):
    vehicle_driver_to_fixed_plan = {}

    if initial_solution is not None:
        for tour in initial_solution:
            if "fixed_up_to" in tour:
                fixed_up_to = tour["fixed_up_to"]
                vehicle_driver_to_fixed_plan[tour["vehicle"], tour["driver"]] = tour[
                    "plan"
                ][: fixed_up_to + 1]

    result = []
    id_to_location = {c["id"]: c for c in data["locations"]}
    groups = {
        c["group"]
        for c in data["locations"]
        if c["type"] in ["pickup-customer", "delivery-customer"]
    }

    for tour in solution:
        load = {g: 0 for g in groups}
        load_change_sequence = []

        for c in tour["plan"]:
            location = id_to_location[c["pos"]]

            if location["type"] == "delivery-center":
                load_change = -load[location["group"]]
                load[location["group"]] = 0
            elif location["type"] == "pickup-customer":
                load_change = location["demand"]
                load[location["group"]] = load[location["group"]] + location["demand"]
            else:
                load_change = 0

            load_change_sequence.append(load_change)

        load = {g: 0 for g in groups}
        reverse_load_change_sequence = []

        for c in tour["plan"][::-1]:
            location = id_to_location[c["pos"]]

            if location["type"] == "pickup-center":
                load_change = load[location["group"]]
                load[location["group"]] = 0
            elif location["type"] == "delivery-customer":
                load_change = -location["demand"]
                load[location["group"]] = load[location["group"]] + location["demand"]
            else:
                load_change = 0

            reverse_load_change_sequence.append(load_change)

        reverse_load_change_sequence.reverse()

        load_change_sequence = [
            x + y for x, y in zip(load_change_sequence, reverse_load_change_sequence)
        ]

        vehicle_id = tour["vehicle"]
        driver_id = tour["driver"]

        if (vehicle_id, driver_id) in vehicle_driver_to_fixed_plan:
            fixed_plan = vehicle_driver_to_fixed_plan[vehicle_id, driver_id]
            carried_load = {}

            for i, c in enumerate(fixed_plan):
                location = id_to_location[c["pos"]]

                if load_change_sequence[i] != c["load_change"]:
                    group = location["group"]

                    if group not in carried_load:
                        carried_load[group] = 0

                    carried_load[group] += load_change_sequence[i] - c["load_change"]
                    load_change_sequence[i] = c["load_change"]

            fixed_plan_length = len(fixed_plan)

            for i, c in enumerate(tour["plan"][fixed_plan_length:]):
                location = id_to_location[c["pos"]]
                group = location["group"]

                if group in carried_load and (
                    (
                        location["type"] == "pickup-center"
                        and load_change_sequence[fixed_plan_length + i] > 0
                    )
                    or (
                        location["type"] == "delivery-center"
                        and load_change_sequence[fixed_plan_length + i] < 0
                    )
                ):
                    load_change_sequence[fixed_plan_length + i] += carried_load[group]
                    del carried_load[group]

            plan = fixed_plan.copy()
        else:
            plan = [
                {
                    "pos": tour["plan"][0]["pos"],
                    "time": tour["plan"][0]["time"],
                    "load_change": 0,
                }
            ]

        has_transportation_time_limit = {g: False for g in groups}

        for c in data["locations"]:
            if (
                c["type"] == "delivery-customer"
                and "transportation_time_limit" in c
                and c["transportation_time_limit"] is not None
            ):
                has_transportation_time_limit[c["group"]] = True

        previous = id_to_location[plan[-1]["pos"]]
        time = plan[-1]["time"] + previous["service_time"]
        fixed_plan_length = len(plan)

        for c, load_change in zip(
            tour["plan"][fixed_plan_length:], load_change_sequence[fixed_plan_length:]
        ):
            location = id_to_location[c["pos"]]

            if (
                location["type"] == "pickup-center"
                or location["type"] == "delivery-center"
            ):
                # skip unnecessary pickup or delivery centers
                if load_change == 0:
                    continue

            if (
                location["type"] == "pickup-center"
                and has_transportation_time_limit[location["group"]]
            ):
                time = c["time"]
            else:
                time = max(
                    time + data["distance_matrix"][previous["id"]][location["id"]],
                    location["start"],
                )

            plan.append(
                {
                    "pos": location["id"],
                    "time": time,
                    "load_change": load_change,
                }
            )

            time += location["service_time"]
            previous = location

        if (vehicle_id, driver_id) not in vehicle_driver_to_fixed_plan:
            depot = id_to_location[plan[0]["pos"]]
            first_location = id_to_location[plan[1]["pos"]]

            plan[0]["time"] = min(
                depot["end"],
                plan[1]["time"]
                - depot["service_time"]
                - data["distance_matrix"][depot["id"]][first_location["id"]],
            )

        result.append(
            {
                "vehicle": tour["vehicle"],
                "driver": tour["driver"],
                "plan": plan,
            }
        )

    return result


def extract_hints(data, initial_solution):
    delivery_demand_groups = set(
        c["group"] for c in data["locations"] if c["type"] == "pickup-center"
    )
    pickup_demand_groups = set(
        c["group"] for c in data["locations"] if c["type"] == "delivery-center"
    )
    customer_demand_groups = (
        set(
            c["group"]
            for c in data["locations"]
            if c["type"] == "delivery-customer" or c["type"] == "pickup-customer"
        )
        - delivery_demand_groups
        - pickup_demand_groups
    )

    assert delivery_demand_groups.isdisjoint(
        pickup_demand_groups
    ), "Delivery and pickup demand groups must be disjoint."

    assert customer_demand_groups.isdisjoint(
        delivery_demand_groups
    ), "Customer demand groups must be disjoint with delivery demand groups."

    assert customer_demand_groups.isdisjoint(
        pickup_demand_groups
    ), "Customer demand groups must be disjoint with pickup demand groups."

    demand_groups = (
        pickup_demand_groups | delivery_demand_groups | customer_demand_groups
    )

    time_groups = set(
        c["group"]
        for c in data["locations"]
        if c["type"] == "delivery-customer"
        and "transportation_time_limit" in c
        and c["transportation_time_limit"] is not None
    )

    assert time_groups.isdisjoint(
        pickup_demand_groups
    ), "Time groups must not overlap with pickup demand groups."

    assert time_groups.isdisjoint(
        customer_demand_groups
    ), "Time groups must not overlap with customer demand groups."

    id_to_location = {c["id"]: c for c in data["locations"]}

    vehicle_to_fixed = {}
    driver_to_fixed = {}
    center_to_fixed = {}
    customer_to_fixed = {}
    precedence_fixed = set()

    vehicle_to_hints = {}
    driver_to_hints = {}
    center_to_hints = {}
    customer_to_hints = {}
    precedence_hint = set()

    for tour in initial_solution:
        start = tour["plan"][0]["time"]
        end = tour["plan"][-1]["time"]
        size = end - start
        driver = tour["driver"]
        vehicle = tour["vehicle"]

        fixed_up_to = tour["fixed_up_to"] if "fixed_up_to" in tour else -1

        if fixed_up_to >= 0:
            vehicle_to_fixed[vehicle] = {
                "start": start,
                "driver": driver,
            }
            driver_to_fixed[driver] = {
                "start": start,
                "vehicle": vehicle,
            }

        if fixed_up_to >= len(tour["plan"]) - 1:
            vehicle_to_fixed[vehicle]["end"] = end
            vehicle_to_fixed[vehicle]["size"] = size
            driver_to_fixed[driver]["end"] = end
            driver_to_fixed[driver]["size"] = size

        fixed_pos = set(tour["fixed_pos"]) if "fixed_pos" in tour else set()

        vehicle_to_hints[vehicle] = {
            "start": start,
            "end": end,
            "size": size,
            "driver": driver,
        }
        driver_to_hints[driver] = {
            "start": start,
            "end": end,
            "size": size,
            "vehicle": vehicle,
        }

        n_delivery_centers = {}

        for c in tour["plan"]:
            if id_to_location[c["pos"]]["type"] == "delivery-center":
                if c["pos"] not in n_delivery_centers:
                    n_delivery_centers[c["pos"]] = 0

                n_delivery_centers[c["pos"]] += 1

        previous = ("vehicle_start", vehicle)
        previous_time = start
        load = {g: 0 for g in demand_groups}
        elapsed_time = {g: 0 for g in time_groups}
        pickup_center_counter = {}
        delivery_center_counter = {}

        for i, c in enumerate(tour["plan"][1:-1]):
            location = id_to_location[c["pos"]]
            fixed = "fixed" in c and c["fixed"]

            if location["type"] == "pickup-center":
                if c["pos"] not in pickup_center_counter:
                    pickup_center_counter[c["pos"]] = 0

                k = pickup_center_counter[c["pos"]]
                pickup_center_counter[c["pos"]] += 1

                for g in time_groups:
                    if g == location["group"]:
                        elapsed_time[g] = 0
                    else:
                        elapsed_time[g] += c["time"] - previous_time

                hint = {
                    "start": c["time"],
                    "load": copy.deepcopy(load),
                    "elapsed_time": copy.deepcopy(elapsed_time),
                }

                current = ("center", (vehicle, location["id"], k))

                if fixed_up_to >= i + 1:
                    center_to_fixed[vehicle, c["pos"], k] = hint
                    precedence_fixed.add(
                        (previous, ("center", (vehicle, location["id"], k)))
                    )
                elif fixed:
                    center_to_fixed[vehicle, c["pos"], k] = {"start": c["time"]}

                center_to_hints[vehicle, c["pos"], k] = hint
                precedence_hint.add((previous, current))
                load[location["group"]] += c["load_change"]
                previous = current
                previous_time = c["time"]
            elif location["type"] == "delivery-center":
                if c["pos"] not in delivery_center_counter:
                    delivery_center_counter[c["pos"]] = n_delivery_centers[c["pos"]] - 1

                k = delivery_center_counter[c["pos"]]
                delivery_center_counter[c["pos"]] -= 1

                for g in time_groups:
                    if g == location["group"]:
                        elapsed_time[g] = 0
                    else:
                        elapsed_time[g] += c["time"] - previous_time

                hint = {
                    "start": c["time"],
                    "load": copy.deepcopy(load),
                    "elapsed_time": copy.deepcopy(elapsed_time),
                }

                current = ("center", (vehicle, location["id"], k))

                if fixed_up_to >= i + 1:
                    center_to_fixed[vehicle, c["pos"], k] = hint
                    precedence_fixed.add((previous, current))
                elif fixed:
                    center_to_fixed[vehicle, c["pos"], k] = {"start": c["time"]}

                center_to_hints[vehicle, c["pos"], k] = hint
                precedence_hint.add((previous, current))

                load[location["group"]] += c["load_change"]
                previous = current
                previous_time = c["time"]
            else:
                for g in time_groups:
                    elapsed_time[g] += c["time"] - previous_time

                hint = {
                    "start": c["time"],
                    "load": copy.deepcopy(load),
                    "elapsed_time": copy.deepcopy(elapsed_time),
                    "vehicle": vehicle,
                    "driver": driver,
                }

                current = ("customer", location["id"])

                if fixed_up_to >= i + 1:
                    customer_to_fixed[c["pos"]] = hint
                    precedence_fixed.add((previous, current))
                else:
                    fixed_hint = {}

                    if fixed:
                        fixed_hint["start"] = c["time"]

                    if c["pos"] in fixed_pos:
                        fixed_hint["vehicle"] = vehicle
                        fixed_hint["driver"] = driver

                    if len(fixed_hint.keys()) > 0:
                        customer_to_fixed[c["pos"]] = fixed_hint

                customer_to_hints[c["pos"]] = hint
                precedence_hint.add((previous, current))

                load[location["group"]] += c["load_change"]
                previous = current
                previous_time = c["time"]

        if fixed_up_to >= len(tour["plan"]) - 1:
            precedence_fixed.add((previous, ("vehicle_end", vehicle)))

        precedence_hint.add((previous, ("vehicle_end", vehicle)))

    fixed = {
        "vehicle": vehicle_to_fixed,
        "driver": driver_to_fixed,
        "center": center_to_fixed,
        "customer": customer_to_fixed,
        "precedence": precedence_fixed,
    }

    hints = {
        "vehicle": vehicle_to_hints,
        "driver": driver_to_hints,
        "center": center_to_hints,
        "customer": customer_to_hints,
        "precedence": precedence_hint,
    }

    return fixed, hints
