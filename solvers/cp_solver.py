#!/usr/bin/env python3

import argparse
import json

from ortools.sat.python import cp_model

import lib


def create_model(data, use_circuit, fixed=None, hints=None):
    _, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        lib.classify_locations(data)
    )
    centers = pickup_centers + delivery_centers
    customers = delivery_customers + pickup_customers
    id_to_location = {loc["id"]: loc for loc in data["locations"]}

    model = cp_model.CpModel()

    # Customer visit variables
    customer_visit_vars = {}

    for c in customers:
        start_var = model.new_int_var(
            c["start"], c["end"], name=f"customer{c['id']}_visit_start"
        )

        if c["mandatory"]:
            customer_visit_vars[c["id"]] = {
                "start": start_var,
                "interval": model.new_fixed_size_interval_var(
                    start=start_var,
                    size=c["service_time"],
                    name=f"customer{c['id']}_visit_interval",
                ),
            }
        else:
            is_present = model.new_bool_var(f"customer{c['id']}_is_present")
            customer_visit_vars[c["id"]] = {
                "start": start_var,
                "interval": model.new_optional_fixed_size_interval_var(
                    start=start_var,
                    size=c["service_time"],
                    is_present=is_present,
                    name=f"customer{c['id']}_visit_interval",
                ),
                "is_present": is_present,
            }

    if fixed:
        for c_id, var in customer_visit_vars.items():
            if c_id in fixed["customer"]:
                if "start" in fixed["customer"][c_id]:
                    model.add(var["start"] == fixed["customer"][c_id]["start"])

                if not id_to_location[c_id]["mandatory"]:
                    model.add(var["is_present"] == 1)

    if hints:
        for c_id, var in customer_visit_vars.items():
            c = id_to_location[c_id]

            if c_id in hints["customer"]:
                if not c["mandatory"]:
                    model.add_hint(var["is_present"], 1)

                model.add_hint(var["start"], hints["customer"][c_id]["start"])
            else:
                if not c["mandatory"]:
                    model.add_hint(var["is_present"], 0)

                model.add_hint(var["start"], c["start"])

    # Vehicle interval variable
    id_to_vehicle = {v["id"]: v for v in data["vehicles"]}

    vehicle_tour_vars = {}

    for v in data["vehicles"]:
        start_var = model.new_int_var(
            v["start"], v["end"], name=f"vehicle{v['id']}_tour_start"
        )
        end_var = model.new_int_var(
            v["start"], v["end"], name=f"vehicle{v['id']}_tour_end"
        )
        size_var = model.new_int_var(
            0, v["end"] - v["start"], name=f"vehicle{v['id']}_tour_size"
        )
        is_present = model.new_bool_var(f"vehicle{v['id']}_tour_is_present")
        interval_var = model.new_optional_interval_var(
            start=start_var,
            end=end_var,
            size=size_var,
            is_present=is_present,
            name=f"vehicle{v['id']}_tour_interval",
        )
        vehicle_tour_vars[v["id"]] = {
            "start": start_var,
            "end": end_var,
            "size": size_var,
            "interval": interval_var,
            "is_present": is_present,
        }

    if fixed:
        for v_id, var in vehicle_tour_vars.items():
            if v_id in fixed["vehicle"]:
                if "start" in fixed["vehicle"][v_id]:
                    model.add(var["start"] == fixed["vehicle"][v_id]["start"])

                if "end" in fixed["vehicle"][v_id]:
                    model.add(var["end"] == fixed["vehicle"][v_id]["end"])

                if "size" in fixed["vehicle"][v_id]:
                    model.add(var["size"] == fixed["vehicle"][v_id]["size"])

                model.add(var["is_present"] == 1)

    if hints:
        for v_id, var in vehicle_tour_vars.items():
            if v_id in hints["vehicle"]:
                model.add_hint(var["is_present"], 1)
                model.add_hint(var["start"], hints["vehicle"][v_id]["start"])
                model.add_hint(var["end"], hints["vehicle"][v_id]["end"])
                model.add_hint(var["size"], hints["vehicle"][v_id]["size"])
            else:
                v = id_to_vehicle[v_id]
                model.add_hint(var["is_present"], 0)
                model.add_hint(var["start"], v["start"])
                model.add_hint(var["end"], v["start"])
                model.add_hint(var["size"], 0)

    # Vehicle customer interval variables
    vehicle_customer_visit_literals = {
        (v["id"], c["id"]): model.new_bool_var(
            f"vehicle{v['id']}_visit_customer{c['id']}_literal"
        )
        for c in customers
        for v in data["vehicles"]
        if (
            v["start"]
            + id_to_location[v["start_location"]]["service_time"]
            + data["distance_matrix"][v["start_location"]][c["id"]]
            <= c["end"]
        )
        and c["start"]
        + c["service_time"]
        + data["distance_matrix"][c["id"]][v["end_location"]]
        <= v["end"]
    }

    if fixed:
        for c in customers:
            if c["id"] in fixed["customer"] and "vehicle" in fixed["customer"][c["id"]]:
                v_id = fixed["customer"][c["id"]]["vehicle"]
                model.add(vehicle_customer_visit_literals[v_id, c["id"]] == 1)

    if hints:
        for (v_id, c_id), literal in vehicle_customer_visit_literals.items():
            if c_id in hints["customer"] and v_id == hints["customer"][c_id]["vehicle"]:
                model.add_hint(literal, 1)
            else:
                model.add_hint(literal, 0)

    # Vehicle center interval variables
    distance_matrix = data["distance_matrix"]
    max_visits_dict = lib.compute_max_visits(data)
    vehicle_center_visit_vars = {}

    for v in data["vehicles"]:
        for c in centers:
            start_lb = max(
                c["start"],
                v["start"]
                + id_to_location[v["start_location"]]["service_time"]
                + distance_matrix[v["start_location"]][c["id"]],
            )
            start_ub = min(
                c["end"],
                v["end"]
                - distance_matrix[c["id"]][v["end_location"]]
                - c["service_time"],
            )

            if start_lb > start_ub:
                continue

            for k in range(max_visits_dict[v["id"], c["id"]]):
                start_var = model.new_int_var(
                    start_lb,
                    start_ub,
                    name=f"vehicle{v['id']}_center{c['id']}_{k}_start",
                )
                visit_literal = model.new_bool_var(
                    f"vehicle{v['id']}_visit_center{c['id']}_{k}"
                )
                interval_var = model.new_optional_fixed_size_interval_var(
                    start=start_var,
                    size=c["service_time"],
                    is_present=visit_literal,
                    name=f"vehicle{v['id']}_center{c['id']}_{k}_interval",
                )
                vehicle_center_visit_vars[v["id"], c["id"], k] = {
                    "start": start_var,
                    "interval": interval_var,
                    "is_present": visit_literal,
                    "start_lb": start_lb,
                    "start_ub": start_ub,
                }

    if fixed:
        for (v_id, c_id, k), var in vehicle_center_visit_vars.items():
            if (v_id, c_id, k) in fixed["center"]:
                if "start" in fixed["center"][(v_id, c_id, k)]:
                    model.add(var["start"] == fixed["center"][v_id, c_id, k]["start"])

                model.add(var["is_present"] == 1)

    if hints:
        for (v_id, c_id, k), var in vehicle_center_visit_vars.items():
            if (v_id, c_id, k) in hints["center"]:
                model.add_hint(var["start"], hints["center"][v_id, c_id, k]["start"])
                model.add_hint(var["is_present"], 1)
            else:
                model.add_hint(
                    var["start"],
                    vehicle_center_visit_vars[v_id, c_id, k]["start_lb"],
                )
                model.add_hint(var["is_present"], 0)

    # Arcs
    edges = lib.extract_edges(data)
    optional_customers = [c for c in customers if not c["mandatory"]]
    arc_literals = {}

    # Arcs between customers
    for ci in customers:
        for cj in customers:
            if (ci["id"], cj["id"]) in edges:
                precedence_ij = model.new_bool_var(
                    name=f"precedence_{ci['id']}_{cj['id']}"
                )
                arc_literals[("customer", ci["id"]), ("customer", cj["id"])] = (
                    precedence_ij
                )

    # Arcs between centers
    for ci in centers:
        for cj in centers:
            if (ci["id"], cj["id"]) not in edges:
                continue

            for v in data["vehicles"]:
                for ki in range(max_visits_dict[v["id"], ci["id"]]):
                    if (v["id"], ci["id"], ki) not in vehicle_center_visit_vars:
                        continue

                    for kj in range(max_visits_dict[v["id"], cj["id"]]):
                        if (v["id"], cj["id"], kj) not in vehicle_center_visit_vars:
                            continue

                        precedence_ij = model.new_bool_var(
                            name=f"precedence_vehicle{v['id']}_center{ci['id']}_{ki}"
                            f"_center{cj['id']}_{kj}"
                        )
                        arc_literals[
                            ("center", (v["id"], ci["id"], ki)),
                            ("center", (v["id"], cj["id"], kj)),
                        ] = precedence_ij

    # Arcs from centers to customers
    for ci in centers:
        for cj in customers:
            if (ci["id"], cj["id"]) not in edges:
                continue

            for v in data["vehicles"]:
                if (v["id"], cj["id"]) not in vehicle_customer_visit_literals:
                    continue

                for k in range(max_visits_dict[v["id"], ci["id"]]):
                    if (v["id"], ci["id"], k) not in vehicle_center_visit_vars:
                        continue

                    if (
                        ci["type"] == "delivery-center"
                        and k == 0
                        and cj["type"] == "pickup-customer"
                        and ci["group"] == cj["group"]
                    ):
                        continue

                    precedence_ij = model.new_bool_var(
                        name=f"precedence_vehicle{v['id']}_center{ci['id']}_{k}_customer{cj['id']}"
                    )
                    arc_literals[
                        ("center", (v["id"], ci["id"], k)),
                        ("customer", cj["id"]),
                    ] = precedence_ij

    # Arcs from customers to centers
    for ci in customers:
        for cj in centers:
            if (ci["id"], cj["id"]) not in edges:
                continue

            for v in data["vehicles"]:
                if (v["id"], ci["id"]) not in vehicle_customer_visit_literals:
                    continue

                for k in range(max_visits_dict[v["id"], cj["id"]]):
                    if (v["id"], cj["id"], k) not in vehicle_center_visit_vars:
                        continue

                    if (
                        cj["type"] == "pickup-center"
                        and k == 0
                        and ci["type"] == "delivery-customer"
                        and cj["group"] == ci["group"]
                    ):
                        continue

                    precedence_ij = model.new_bool_var(
                        name=f"precedence_vehicle{v['id']}_customer{ci['id']}_center{cj['id']}_{k}"
                    )
                    arc_literals[
                        ("customer", ci["id"]),
                        ("center", (v["id"], cj["id"], k)),
                    ] = precedence_ij

    # Arcs from depots and customers
    for v in data["vehicles"]:
        depot = id_to_location[v["start_location"]]

        for c in pickup_customers:
            arrival_time = (
                v["start"]
                + depot["service_time"]
                + distance_matrix[v["start_location"]][c["id"]]
            )

            if (
                v["id"],
                c["id"],
            ) in vehicle_customer_visit_literals and arrival_time <= c["end"]:
                precedence_depot_c = model.new_bool_var(
                    name=f"precedence_depot_vehicle{v['id']}_{c['id']}"
                )
                arc_literals[("vehicle_start", v["id"]), ("customer", c["id"])] = (
                    precedence_depot_c
                )

    # Arcs from depots to centers
    for v in data["vehicles"]:
        depot = id_to_location[v["start_location"]]

        for c in pickup_centers:
            arrival_time = (
                v["start"]
                + depot["service_time"]
                + distance_matrix[v["start_location"]][c["id"]]
            )

            if (v["id"], c["id"], 0) in vehicle_center_visit_vars and arrival_time <= c[
                "end"
            ]:
                precedence_depot_c = model.new_bool_var(
                    name=f"precedence_depot_vehicle{v['id']}_center{c['id']}"
                )
                arc_literals[
                    ("vehicle_start", v["id"]), ("center", (v["id"], c["id"], 0))
                ] = precedence_depot_c

    # Arcs from customers to depots
    for c in delivery_customers:
        for v in data["vehicles"]:
            arrival_time = (
                c["start"]
                + c["service_time"]
                + data["distance_matrix"][c["id"]][v["end_location"]]
            )

            if (
                v["id"],
                c["id"],
            ) in vehicle_customer_visit_literals and arrival_time <= v["end"]:
                precedence_c_depot = model.new_bool_var(
                    name=f"precedence_vehicle{v['id']}_{c['id']}_depot"
                )
                arc_literals[("customer", c["id"]), ("vehicle_end", v["id"])] = (
                    precedence_c_depot
                )

    # Arcs from centers to depots
    for c in delivery_centers:
        for v in data["vehicles"]:
            arrival_time = (
                c["start"]
                + c["service_time"]
                + data["distance_matrix"][c["id"]][v["end_location"]]
            )

            if (
                v["id"],
                c["id"],
                0,
            ) in vehicle_center_visit_vars and arrival_time <= v["end"]:
                precedence_c_depot = model.new_bool_var(
                    name=f"precedence_vehicle{v['id']}_center{c['id']}_depot"
                )
                arc_literals[
                    ("center", (v["id"], c["id"], 0)), ("vehicle_end", v["id"])
                ] = precedence_c_depot

    if fixed:
        for from_node, to_node in fixed["precedence"]:
            model.add(arc_literals[from_node, to_node] == 1)

    if hints:
        for from_node, to_node in arc_literals.keys():
            if (from_node, to_node) in hints["precedence"]:
                model.add_hint(arc_literals[from_node, to_node], 1)
            else:
                model.add_hint(arc_literals[from_node, to_node], 0)

    # Objective
    if len(optional_customers) > 0:
        model.maximize(
            sum(
                c["score"] * customer_visit_vars[c["id"]]["is_present"]
                for c in optional_customers
            )
        )

    # Circuit
    nodes = (
        [("customer", c["id"]) for c in customers]
        + [
            ("center", (v["id"], c["id"], k))
            for v in data["vehicles"]
            for c in centers
            for k in range(max_visits_dict[v["id"], c["id"]])
            if (v["id"], c["id"], k) in vehicle_center_visit_vars
        ]
        + [("vehicle_start", v["id"]) for v in data["vehicles"]]
        + [("vehicle_end", v["id"]) for v in data["vehicles"]]
    )

    # Use global constraint
    if use_circuit:
        dummy_arc_literals = {}

        # Self arcs for customers
        for c in optional_customers:
            dummy_arc_literals[("customer", c["id"]), ("customer", c["id"])] = (
                ~customer_visit_vars[c["id"]]["is_present"]
            )

        # Self arcs for centers
        for (v_id, c_id, k), var in vehicle_center_visit_vars.items():
            dummy_arc_literals[
                ("center", (v_id, c_id, k)),
                ("center", (v_id, c_id, k)),
            ] = ~var["is_present"]

        # Self arcs for vehicles
        for v_id, var in vehicle_tour_vars.items():
            dummy_arc_literals[("vehicle_start", v_id), ("vehicle_end", v_id)] = ~var[
                "is_present"
            ]

        # Arcs between vehicles
        for v_i, v_j in zip(
            data["vehicles"], data["vehicles"][1:] + [data["vehicles"][0]]
        ):
            dummy_arc_literals[
                ("vehicle_end", v_i["id"]), ("vehicle_start", v_j["id"])
            ] = 1

        node_to_id = {}

        for i, n in enumerate(nodes):
            node_to_id[n] = i

        model.add_circuit(
            [
                (
                    node_to_id[from_node],
                    node_to_id[to_node],
                    literal,
                )
                for (from_node, to_node), literal in arc_literals.items()
            ]
            + [
                (node_to_id[from_node], node_to_id[to_node], literal)
                for (from_node, to_node), literal in dummy_arc_literals.items()
            ]
        )
    # Formulate flow constraints
    else:
        node_to_incoming_literals = {n: [] for n in nodes}
        node_to_outgoing_literals = {n: [] for n in nodes}

        for (from_node, to_node), arc_literal in arc_literals.items():
            node_to_outgoing_literals[from_node].append(arc_literal)
            node_to_incoming_literals[to_node].append(arc_literal)

        for n in nodes:
            if n[0] == "customer" and id_to_location[n[1]]["mandatory"]:
                model.add_exactly_one(node_to_incoming_literals[n])
                model.add_exactly_one(node_to_outgoing_literals[n])
                continue

            if n[0] == "vehicle_start":
                v_id = n[1]
                is_present_literal = vehicle_tour_vars[v_id]["is_present"]
                model.add_at_most_one(node_to_outgoing_literals[n])
                model.add_at_least_one(node_to_outgoing_literals[n]).only_enforce_if(
                    is_present_literal
                )

                for literal in node_to_outgoing_literals[n]:
                    model.add_implication(
                        literal,
                        is_present_literal,
                    )

                continue

            if n[0] == "vehicle_end":
                v_id = n[1]
                is_present_literal = vehicle_tour_vars[v_id]["is_present"]
                model.add_at_most_one(node_to_incoming_literals[n])
                model.add_at_least_one(node_to_incoming_literals[n]).only_enforce_if(
                    is_present_literal
                )

                for literal in node_to_incoming_literals[n]:
                    model.add_implication(
                        literal,
                        is_present_literal,
                    )

                continue

            if n[0] == "customer":
                is_present_literal = customer_visit_vars[n[1]]["is_present"]
            elif n[0] == "center":
                v_id, c_id, k = n[1]
                is_present_literal = vehicle_center_visit_vars[v_id, c_id, k][
                    "is_present"
                ]

            model.add_at_most_one(node_to_incoming_literals[n])
            model.add_at_least_one(node_to_incoming_literals[n]).only_enforce_if(
                is_present_literal
            )
            model.add_at_most_one(node_to_outgoing_literals[n])
            model.add_at_least_one(node_to_outgoing_literals[n]).only_enforce_if(
                is_present_literal
            )

            for literal in node_to_incoming_literals[n] + node_to_outgoing_literals[n]:
                model.add_implication(literal, is_present_literal)

    # Time constraints
    for (from_node, to_node), arc_literal in arc_literals.items():
        if from_node[0] == "customer":
            from_location = from_node[1]
            from_service_time = id_to_location[from_location]["service_time"]
            from_start_var = customer_visit_vars[from_location]["start"]
        elif from_node[0] == "center":
            v_id, c_id, k = from_node[1]
            from_service_time = id_to_location[c_id]["service_time"]
            from_start_var = vehicle_center_visit_vars[v_id, c_id, k]["start"]
            from_location = c_id
        elif from_node[0] == "vehicle_start":
            v_id = from_node[1]
            from_location = id_to_vehicle[v_id]["start_location"]
            from_service_time = id_to_location[from_location]["service_time"]
            from_start_var = vehicle_tour_vars[v_id]["start"]

        if to_node[0] == "customer":
            to_location = to_node[1]
            to_start_var = customer_visit_vars[to_location]["start"]
        elif to_node[0] == "center":
            v_id, c_id, k = to_node[1]
            to_start_var = vehicle_center_visit_vars[v_id, c_id, k]["start"]
            to_location = c_id
        elif to_node[0] == "vehicle_end":
            v_id = to_node[1]
            to_location = id_to_vehicle[v_id]["end_location"]
            to_start_var = vehicle_tour_vars[v_id]["end"]

        travel_time = data["distance_matrix"][from_location][to_location]

        model.add(
            to_start_var >= from_start_var + from_service_time + travel_time
        ).only_enforce_if(arc_literal)

    # A customer must be visited by exactly one vehicle if present
    for c in customers:
        if id_to_location[c["id"]]["mandatory"]:
            model.add_exactly_one(
                vehicle_customer_visit_literals[v["id"], c["id"]]
                for v in data["vehicles"]
                if (v["id"], c["id"]) in vehicle_customer_visit_literals
            )
        else:
            model.add_at_most_one(
                vehicle_customer_visit_literals[v["id"], c["id"]]
                for v in data["vehicles"]
                if (v["id"], c["id"]) in vehicle_customer_visit_literals
            )
            model.add_at_least_one(
                vehicle_customer_visit_literals[v["id"], c["id"]]
                for v in data["vehicles"]
                if (v["id"], c["id"]) in vehicle_customer_visit_literals
            ).only_enforce_if(customer_visit_vars[c["id"]]["is_present"])

    # Vehicle flow constraints
    for (from_node, to_node), arc_literal in arc_literals.items():
        if from_node[0] == "customer" and to_node[0] == "customer":
            ci_id = from_node[1]
            cj_id = to_node[1]

            for v in data["vehicles"]:
                if (v["id"], ci_id) not in vehicle_customer_visit_literals:
                    continue

                if (v["id"], cj_id) not in vehicle_customer_visit_literals:
                    continue

                model.add(
                    vehicle_customer_visit_literals[v["id"], ci_id]
                    == vehicle_customer_visit_literals[v["id"], cj_id],
                ).only_enforce_if(arc_literal)

            continue

        if from_node[0] == "center" and to_node[0] == "customer":
            v_id, _, _ = from_node[1]
            c_id = to_node[1]
        elif from_node[0] == "customer" and to_node[0] == "center":
            v_id, _, _ = to_node[1]
            c_id = from_node[1]
        elif from_node[0] == "vehicle_start" and to_node[0] == "customer":
            v_id = from_node[1]
            c_id = to_node[1]
        elif from_node[0] == "customer" and to_node[0] == "vehicle_end":
            v_id = to_node[1]
            c_id = from_node[1]
        else:
            continue

        model.add_implication(
            arc_literal,
            vehicle_customer_visit_literals[v_id, c_id],
        )

    # Driver assignment
    driver_vehicle_literals = {
        (d["id"], v_id): model.new_bool_var(f"driver{d['id']}_vehicle{v_id}")
        for d in data["drivers"]
        for v_id in d["allowed_vehicles"]
    }

    if fixed:
        for d in data["drivers"]:
            if d["id"] in fixed["driver"] and "vehicle" in fixed["driver"][d["id"]]:
                v_id = fixed["driver"][d["id"]]["vehicle"]
                model.add(driver_vehicle_literals[d["id"], v_id] == 1)

    if hints:
        for d in data["drivers"]:
            for v_id in d["allowed_vehicles"]:
                if (
                    d["id"] in hints["driver"]
                    and v_id == hints["driver"][d["id"]]["vehicle"]
                ):
                    model.add_hint(driver_vehicle_literals[d["id"], v_id], 1)
                else:
                    model.add_hint(driver_vehicle_literals[d["id"], v_id], 0)

    for d in data["drivers"]:
        model.add_at_most_one(
            driver_vehicle_literals[d["id"], v_id] for v_id in d["allowed_vehicles"]
        )

    for v in data["vehicles"]:
        model.add_at_most_one(
            driver_vehicle_literals[d["id"], v["id"]]
            for d in data["drivers"]
            if (d["id"], v["id"]) in driver_vehicle_literals
        )
        model.add_at_least_one(
            driver_vehicle_literals[d["id"], v["id"]]
            for d in data["drivers"]
            if (d["id"], v["id"]) in driver_vehicle_literals
        ).only_enforce_if(vehicle_tour_vars[v["id"]]["is_present"])

    for d in data["drivers"]:
        for v_id in d["allowed_vehicles"]:
            model.add(vehicle_tour_vars[v_id]["start"] >= d["start"]).only_enforce_if(
                driver_vehicle_literals[d["id"], v_id]
            )
            model.add(vehicle_tour_vars[v_id]["end"] <= d["end"]).only_enforce_if(
                driver_vehicle_literals[d["id"], v_id]
            )
            model.add(
                vehicle_tour_vars[v_id]["size"] <= d["max_working_time"]
            ).only_enforce_if(driver_vehicle_literals[d["id"], v_id])

    # Load variables and constraints
    delivery_demand_groups = set(c["group"] for c in pickup_centers)
    pickup_demand_groups = set(c["group"] for c in delivery_centers)
    customer_demand_groups = (
        set(c["group"] for c in customers)
        - delivery_demand_groups
        - pickup_demand_groups
    )

    assert delivery_demand_groups.isdisjoint(
        pickup_demand_groups
    ), "Delivery and pickup demand groups must be disjoint."

    demand_groups = (
        delivery_demand_groups | pickup_demand_groups | customer_demand_groups
    )
    max_capacity = max(v["capacity"] for v in data["vehicles"])

    customer_load_lb = {
        (c["id"], g): (
            c["demand"] if c["type"] == "delivery-customer" and c["group"] == g else 0
        )
        for c in customers
        for g in demand_groups
    }
    customer_load_ub = {
        (c["id"], g): (
            max_capacity - c["demand"]
            if c["type"] == "pickup-customer" and c["group"] == g
            else max_capacity
        )
        for c in customers
        for g in demand_groups
    }

    customer_load_vars = {
        (c["id"], g): model.new_int_var(
            customer_load_lb[c["id"], g],
            customer_load_ub[c["id"], g],
            name=f"customer{c['id']}_load_group{g}",
        )
        for c in customers
        for g in demand_groups
    }

    if fixed:
        for c in customers:
            if c["id"] in fixed["customer"] and "load" in fixed["customer"][c["id"]]:
                for g in demand_groups:
                    model.add(
                        customer_load_vars[c["id"], g]
                        == fixed["customer"][c["id"]]["load"][g]
                    )

    if hints:
        for c in customers:
            for g in demand_groups:
                if (
                    c["id"] in hints["customer"]
                    and "load" in hints["customer"][c["id"]]
                    and g in hints["customer"][c["id"]]["load"]
                ):
                    model.add_hint(
                        customer_load_vars[c["id"], g],
                        hints["customer"][c["id"]]["load"][g],
                    )
                else:
                    model.add_hint(
                        customer_load_vars[c["id"], g], customer_load_lb[c["id"], g]
                    )

    vehicle_center_load_vars = {
        (v_id, c_id, k, g): model.new_int_var(
            0,
            id_to_vehicle[v_id]["capacity"],
            name=f"vehicle{v_id}_center{c_id}_{k}_load_group{g}",
        )
        for (v_id, c_id, k) in vehicle_center_visit_vars.keys()
        for g in demand_groups
    }

    if fixed:
        for v_id, c_id, k in vehicle_center_visit_vars.keys():
            for g in demand_groups:
                if (
                    (v_id, c_id, k) in fixed["center"]
                    and "load" in fixed["center"][v_id, c_id, k]
                    and g in fixed["center"][v_id, c_id, k]["load"]
                ):
                    model.add(
                        vehicle_center_load_vars[v_id, c_id, k, g]
                        == fixed["center"][v_id, c_id, k]["load"][g]
                    )

    if hints:
        for v_id, c_id, k in vehicle_center_visit_vars.keys():
            for g in demand_groups:
                if (
                    (v_id, c_id, k) in hints["center"]
                    and "load" in hints["center"][v_id, c_id, k]
                    and g in hints["center"][v_id, c_id, k]["load"]
                ):
                    model.add_hint(
                        vehicle_center_load_vars[v_id, c_id, k, g],
                        hints["center"][v_id, c_id, k]["load"][g],
                    )
                else:
                    model.add_hint(vehicle_center_load_vars[v_id, c_id, k, g], 0)

    for (v_id, c_id), literal in vehicle_customer_visit_literals.items():
        model.add(
            sum(customer_load_vars[c_id, g] for g in demand_groups)
            <= id_to_vehicle[v_id]["capacity"]
        ).only_enforce_if(literal)

    for (v_id, c_id, k), var in vehicle_center_visit_vars.items():
        model.add(
            sum(vehicle_center_load_vars[v_id, c_id, k, g] for g in demand_groups)
            <= id_to_vehicle[v_id]["capacity"]
        ).only_enforce_if(var["is_present"])

    for (from_node, to_node), arc_literal in arc_literals.items():
        for g in demand_groups:
            if from_node[0] == "vehicle_start":
                if g in pickup_demand_groups:
                    continue

                from_var = 0
                demand_change = 0
            elif from_node[0] == "customer":
                c_id = from_node[1]
                from_var = customer_load_vars[c_id, g]
                c = id_to_location[c_id]
                demand_change = (
                    c["demand"]
                    if c["type"] == "pickup-customer" and c["group"] == g
                    else (
                        -c["demand"]
                        if c["type"] == "delivery-customer" and c["group"] == g
                        else 0
                    )
                )
            elif from_node[0] == "center":
                v_id, c_id, k = from_node[1]

                if id_to_location[c_id]["group"] == g:
                    continue

                from_var = vehicle_center_load_vars[v_id, c_id, k, g]
                demand_change = 0

            if to_node[0] == "vehicle_end":
                if g in delivery_demand_groups:
                    continue

                to_var = 0
            elif to_node[0] == "customer":
                to_var = customer_load_vars[to_node[1], g]
            elif to_node[0] == "center":
                v_id, c_id, k = to_node[1]
                c = id_to_location[c_id]

                if from_node[0] == "vehicle_start" and c["group"] == g:
                    continue

                to_var = vehicle_center_load_vars[v_id, c_id, k, g]

            model.add(to_var == from_var + demand_change).only_enforce_if(arc_literal)

    # Transportation time variables and constraints
    time_groups = set(
        c["group"]
        for c in data["locations"]
        if c["type"] == "delivery-customer"
        and "transportation_time_limit" in c
        and c["transportation_time_limit"] is not None
    )

    customer_elapsed_time_ub = {
        (c["id"], g): (
            c["transportation_time_limit"]
            if c["type"] == "delivery-customer"
            and c["group"] == g
            and "transportation_time_limit" in c
            and c["transportation_time_limit"] is not None
            else c["end"] - min(v["start"] for v in data["vehicles"])
        )
        for c in customers
        for g in time_groups
    }
    customer_elapsed_time_vars = {
        (c["id"], g): model.new_int_var(
            0,
            customer_elapsed_time_ub[c["id"], g],
            name=f"customer{c['id']}_elapsed_time_group{g}",
        )
        for c in customers
        for g in time_groups
        if (c["id"], g) in customer_elapsed_time_ub
    }

    if fixed:
        for c in customers:
            for g in time_groups:
                if (
                    c["id"] in fixed["customer"]
                    and "elapsed_time" in fixed["customer"][c["id"]]
                    and g in fixed["customer"][c["id"]]["elapsed_time"]
                ):
                    model.add(
                        customer_elapsed_time_vars[c["id"], g]
                        == fixed["customer"][c["id"]]["elapsed_time"][g]
                    )

    if hints:
        for c in customers:
            for g in time_groups:
                if (
                    c["id"] in hints["customer"]
                    and "elapsed_time" in hints["customer"][c["id"]]
                    and g in hints["customer"][c["id"]]["elapsed_time"]
                ):
                    model.add_hint(
                        customer_elapsed_time_vars[c["id"], g],
                        hints["customer"][c["id"]]["elapsed_time"][g],
                    )
                else:
                    model.add_hint(customer_elapsed_time_vars[c["id"], g], 0)

    vehicle_center_elapsed_time_vars = {
        (v_id, c_id, k, g): model.new_int_var(
            0,
            min(id_to_location[c_id]["end"], id_to_vehicle[v_id]["end"])
            - id_to_vehicle[v_id]["start"],
            name=f"vehicle{v_id}_center{c_id}_{k}_elapsed_time_group{g}",
        )
        for (v_id, c_id, k) in vehicle_center_visit_vars.keys()
        for g in time_groups
        if id_to_location[c_id]["type"] != "pickup-center"
        or id_to_location[c_id]["group"] != g
    }

    if fixed:
        for (v_id, c_id, k, g), var in vehicle_center_elapsed_time_vars.items():
            if (
                (v_id, c_id, k) in fixed["center"]
                and "elapsed_time" in fixed["center"][v_id, c_id, k]
                and g in fixed["center"][v_id, c_id, k]["elapsed_time"]
            ):
                model.add(
                    vehicle_center_elapsed_time_vars[v_id, c_id, k, g]
                    == fixed["center"][v_id, c_id, k]["elapsed_time"][g]
                )

    if hints:
        for (v_id, c_id, k, g), var in vehicle_center_elapsed_time_vars.items():
            if (
                (v_id, c_id, k) in hints["center"]
                and "elapsed_time" in hints["center"][v_id, c_id, k]
                and g in hints["center"][v_id, c_id, k]["elapsed_time"]
            ):
                model.add_hint(
                    vehicle_center_elapsed_time_vars[v_id, c_id, k, g],
                    hints["center"][v_id, c_id, k]["elapsed_time"][g],
                )
            else:
                model.add_hint(vehicle_center_elapsed_time_vars[v_id, c_id, k, g], 0)

    for (from_node, to_node), arc_literal in arc_literals.items():
        for g in time_groups:
            if from_node[0] == "customer":
                from_location = from_node[1]
                from_var = customer_elapsed_time_vars[from_location, g]
                from_start_var = customer_visit_vars[from_location]["start"]
            elif from_node[0] == "center":
                v_id, c_id, k = from_node[1]

                if (v_id, c_id, k, g) in vehicle_center_elapsed_time_vars:
                    from_var = vehicle_center_elapsed_time_vars[v_id, c_id, k, g]
                else:
                    from_var = 0

                from_start_var = vehicle_center_visit_vars[v_id, c_id, k]["start"]
            else:
                continue

            if to_node[0] == "customer":
                to_location = to_node[1]
                to_var = customer_elapsed_time_vars[to_location, g]
                to_start_var = customer_visit_vars[to_location]["start"]
            elif to_node[0] == "center":
                v_id, c_id, k = to_node[1]
                c = id_to_location[c_id]

                if (v_id, c_id, k, g) not in vehicle_center_elapsed_time_vars:
                    continue

                to_var = vehicle_center_elapsed_time_vars[v_id, c_id, k, g]
                to_start_var = vehicle_center_visit_vars[v_id, c_id, k]["start"]
            else:
                continue

            model.add(
                to_var == from_var + to_start_var - from_start_var
            ).only_enforce_if(arc_literal)

    return (
        model,
        customer_visit_vars,
        vehicle_center_visit_vars,
        vehicle_tour_vars,
        vehicle_customer_visit_literals,
        driver_vehicle_literals,
        arc_literals,
    )


def extract_solution(
    data,
    solver,
    customer_visit_vars,
    vehicle_center_visit_vars,
    vehicle_tour_vars,
    vehicle_customer_visit_literals,
    driver_vehicle_literals,
):
    _, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        lib.classify_locations(data)
    )
    centers = delivery_centers + pickup_centers
    customers = delivery_customers + pickup_customers
    max_visits_dict = lib.compute_max_visits(data)
    solution = []

    for v in data["vehicles"]:
        if solver.value(vehicle_tour_vars[v["id"]]["is_present"]):
            plan = [
                {
                    "pos": v["start_location"],
                    "time": solver.value(vehicle_tour_vars[v["id"]]["start"]),
                }
            ]

            for c in customers:
                if (
                    (v["id"], c["id"]) in vehicle_customer_visit_literals
                    and solver.value(vehicle_customer_visit_literals[v["id"], c["id"]])
                    and (
                        c["mandatory"]
                        or solver.value(customer_visit_vars[c["id"]]["is_present"])
                    )
                ):
                    plan.append(
                        {
                            "pos": c["id"],
                            "time": solver.value(customer_visit_vars[c["id"]]["start"]),
                        }
                    )

            if len(plan) == 1:
                continue

            for c in centers:
                for k in range(max_visits_dict[v["id"], c["id"]]):
                    if (
                        v["id"],
                        c["id"],
                        k,
                    ) in vehicle_center_visit_vars and solver.value(
                        vehicle_center_visit_vars[v["id"], c["id"], k]["is_present"]
                    ):
                        plan.append(
                            {
                                "pos": c["id"],
                                "time": solver.value(
                                    vehicle_center_visit_vars[v["id"], c["id"], k][
                                        "start"
                                    ]
                                ),
                            }
                        )

            plan = sorted(plan, key=lambda x: x["time"])
            plan.append(
                {
                    "pos": v["end_location"],
                    "time": solver.value(vehicle_tour_vars[v["id"]]["end"]),
                }
            )

            d_id = None

            for d in data["drivers"]:
                if (d["id"], v["id"]) in driver_vehicle_literals and solver.value(
                    driver_vehicle_literals[d["id"], v["id"]]
                ):
                    d_id = d["id"]
                    break

            solution.append(
                {
                    "vehicle": v["id"],
                    "driver": d_id,
                    "plan": plan,
                }
            )

    return solution


def solve_model(
    data,
    use_circuit,
    time_limit=None,
    threads=None,
    verbose=None,
    fixed=None,
    hints=None,
):
    (
        model,
        customer_visit_vars,
        vehicle_center_visit_vars,
        vehicle_tour_vars,
        vehicle_customer_visit_vars,
        driver_vehicle_literals,
        arc_literals,
    ) = create_model(data, use_circuit, fixed=fixed, hints=hints)

    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = verbose

    if time_limit is not None:
        solver.parameters.max_time_in_seconds = time_limit

    if threads is not None:
        solver.parameters.num_search_workers = threads

    status = solver.Solve(model)
    elapsed_time = solver.WallTime()
    best_bound = solver.BestObjectiveBound()

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # for (from_node, to_node), arc_literal in arc_literals.items():
        #     if solver.value(arc_literal):
        #         print(f"Arc from {from_node} to {to_node} is used.")

        # for (v_id, c_id), literal in vehicle_customer_visit_vars.items():
        #     if solver.value(literal):
        #         print(f"Vehicle {v_id} visits customer {c_id}.")

        solution = extract_solution(
            data,
            solver,
            customer_visit_vars,
            vehicle_center_visit_vars,
            vehicle_tour_vars,
            vehicle_customer_visit_vars,
            driver_vehicle_literals,
        )
        objective_value = solver.ObjectiveValue()

        return solution, objective_value, best_bound, elapsed_time, status
    else:
        return None, None, best_bound, elapsed_time, status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input",
        type=str,
        help="Path to the JSON file containing the data",
    )
    parser.add_argument(
        "output",
        type=str,
        help="Path to the JSON file where the solution will be saved",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=300,
        help="Time limit for the solver in seconds",
    )
    parser.add_argument("--threads", type=int, help="Number of threads to use")
    parser.add_argument(
        "--initial-solution",
        type=str,
        help="Path to a JSON file with an initial solution",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--use-circuit",
        action="store_true",
        help="Use circuit constraints in the model",
    )
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    preprocessed_data = lib.preprocess_data(data)

    if preprocessed_data is None:
        exit(0)

    if args.initial_solution:
        with open(args.initial_solution, "r", encoding="utf-8") as f:
            initial_solution = json.load(f)

        if not lib.validate(preprocessed_data, initial_solution):
            print("WARNING: The initial solution is infeasible")

        fixed, hints = lib.extract_hints(preprocessed_data, initial_solution)
    else:
        fixed, hints, initial_solution = None, None, None

    solution, objective_value, best_bound, elapsed_time, status = solve_model(
        preprocessed_data,
        use_circuit=args.use_circuit,
        time_limit=args.time_limit,
        threads=args.threads,
        verbose=args.verbose,
        fixed=fixed,
        hints=hints,
    )

    if status == cp_model.INFEASIBLE:
        print("Problem is infeasible")
    elif solution is None:
        print("No solution found within the time limit")
    else:
        if status == cp_model.OPTIMAL:
            print("Optimal solution found")

        solution = lib.postprocess_solution(
            preprocessed_data, solution, initial_solution=initial_solution
        )

        for tour in solution:
            print(tour)

        print("Objective value:", objective_value)
        print("Best bound:", best_bound)
        print("Elapsed time (s):", elapsed_time)

        if lib.validate(data, solution):
            with open(args.output, "w") as f:
                json.dump(solution, f, indent=4)
        else:
            print("The final solution is invalid")
