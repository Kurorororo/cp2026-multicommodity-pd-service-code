import argparse
import json

import gurobipy as gp

import lib


def add_hint(variable, value, fix=False, as_hint=False):
    if fix:
        variable.LB = value
        variable.UB = value
    elif as_hint:
        variable.VarHintVal = value
    else:
        variable.Start = value


def create_vehicle_tour_mip_model(
    data, fixed=None, hints=None, initial_solution_as_hint=False
):
    depots, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        lib.classify_locations(data)
    )
    centers = pickup_centers + delivery_centers
    customers = delivery_customers + pickup_customers
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

    time_groups = set(
        c["group"]
        for c in data["locations"]
        if c["type"] == "delivery-customer"
        and "transportation_time_limit" in c
        and c["transportation_time_limit"] is not None
    )

    model = gp.Model()

    max_capacity = max(v["capacity"] for v in data["vehicles"])
    start_vars = model.addVars(
        [c["id"] for c in customers],
        vtype=gp.GRB.CONTINUOUS,
        lb=[c["start"] for c in customers],
        ub=[c["end"] for c in customers],
        name="start_vars",
    )
    load_vars = model.addVars(
        [(c["id"], g) for c in customers for g in demand_groups],
        vtype=gp.GRB.CONTINUOUS,
        lb={
            (c["id"], g): (
                c["demand"]
                if c["group"] == g and c["type"] == "delivery-customer"
                else 0
            )
            for c in customers
            for g in demand_groups
        },
        ub={
            (c["id"], g): (
                max_capacity - c["demand"]
                if c["group"] == g and c["type"] == "pickup-customer"
                else max_capacity
            )
            for c in customers
            for g in demand_groups
        },
        name="load_vars",
    )
    elapsed_time_ub = {
        (c["id"], g): (
            c["transportation_time_limit"]
            if c["type"] == "delivery-customer"
            and "transportation_time_limit" in c
            and c["transportation_time_limit"] is not None
            and g == c["group"]
            else c["end"] - min(v["start"] for v in data["vehicles"])
        )
        for c in customers
        for g in time_groups
    }
    elapsed_time_vars = model.addVars(
        [(c["id"], g) for c in customers for g in time_groups],
        vtype=gp.GRB.CONTINUOUS,
        lb=0,
        ub=elapsed_time_ub,
        name="elapsed_time_vars",
    )

    if fixed:
        for c in customers:
            if c["id"] in fixed["customer"]:
                if "start" in fixed["customer"][c["id"]]:
                    add_hint(
                        start_vars[c["id"]],
                        fixed["customer"][c["id"]]["start"],
                        fix=True,
                    )

                if "load" in fixed["customer"][c["id"]]:
                    for g in demand_groups:
                        add_hint(
                            load_vars[c["id"], g],
                            fixed["customer"][c["id"]]["load"][g],
                            fix=True,
                        )

                if "elapsed_time" in fixed["customer"][c["id"]]:
                    for g in time_groups:
                        add_hint(
                            elapsed_time_vars[c["id"], g],
                            fixed["customer"][c["id"]]["elapsed_time"][g],
                            fix=True,
                        )

    if hints:
        for c in customers:
            if c["id"] in hints["customer"]:
                add_hint(
                    start_vars[c["id"]],
                    hints["customer"][c["id"]]["start"],
                    as_hint=initial_solution_as_hint,
                )

                for g in demand_groups:
                    add_hint(
                        load_vars[c["id"], g],
                        (
                            hints["customer"][c["id"]]["load"][g]
                            if g in hints["customer"][c["id"]]["load"]
                            else 0
                        ),
                        as_hint=initial_solution_as_hint,
                    )

                for g in time_groups:
                    add_hint(
                        elapsed_time_vars[c["id"], g],
                        (
                            hints["customer"][c["id"]]["elapsed_time"][g]
                            if g in hints["customer"][c["id"]]["elapsed_time"]
                            else 0
                        ),
                        as_hint=initial_solution_as_hint,
                    )
            else:
                add_hint(
                    start_vars[c["id"]],
                    c["start"],
                    as_hint=initial_solution_as_hint,
                )

                for g in demand_groups:
                    add_hint(
                        load_vars[c["id"], g],
                        (
                            c["demand"]
                            if g == c["group"] and c["type"] == "delivery-customer"
                            else 0
                        ),
                        as_hint=initial_solution_as_hint,
                    )

                for g in time_groups:
                    add_hint(
                        elapsed_time_vars[c["id"], g],
                        0,
                        as_hint=initial_solution_as_hint,
                    )

    vehicle_start_vars = model.addVars(
        [v["id"] for v in data["vehicles"]],
        vtype=gp.GRB.CONTINUOUS,
        lb=[v["start"] for v in data["vehicles"]],
        ub=[v["end"] for v in data["vehicles"]],
        name="vehicle_start_vars",
    )
    vehicle_end_vars = model.addVars(
        [v["id"] for v in data["vehicles"]],
        vtype=gp.GRB.CONTINUOUS,
        lb=[v["start"] for v in data["vehicles"]],
        ub=[v["end"] for v in data["vehicles"]],
        name="vehicle_end_vars",
    )

    if fixed:
        for v in data["vehicles"]:
            if v["id"] in fixed["vehicle"]:
                add_hint(
                    vehicle_start_vars[v["id"]],
                    fixed["vehicle"][v["id"]]["start"],
                    fix=True,
                )

                if "end" in fixed["vehicle"][v["id"]]:
                    add_hint(
                        vehicle_end_vars[v["id"]],
                        fixed["vehicle"][v["id"]]["end"],
                        fix=True,
                    )

    if hints:
        for v in data["vehicles"]:
            if v["id"] in hints["vehicle"]:
                add_hint(
                    vehicle_start_vars[v["id"]],
                    hints["vehicle"][v["id"]]["start"],
                    as_hint=initial_solution_as_hint,
                )
                add_hint(
                    vehicle_end_vars[v["id"]],
                    hints["vehicle"][v["id"]]["end"],
                    as_hint=initial_solution_as_hint,
                )
            else:
                add_hint(
                    vehicle_start_vars[v["id"]],
                    v["start"],
                    as_hint=initial_solution_as_hint,
                )
                add_hint(
                    vehicle_end_vars[v["id"]],
                    v["end"],
                    as_hint=initial_solution_as_hint,
                )

    id_to_depot = {d["id"]: d for d in depots}

    vehicle_visit_vars = model.addVars(
        [
            (v["id"], c["id"])
            for v in data["vehicles"]
            for c in customers
            if v["start"]
            + id_to_depot[v["start_location"]]["service_time"]
            + data["distance_matrix"][v["start_location"]][c["id"]]
            <= c["end"]
            and c["start"]
            + c["service_time"]
            + data["distance_matrix"][c["id"]][v["end_location"]]
            <= v["end"]
        ],
        vtype=gp.GRB.BINARY,
        name="vehicle_visit_vars",
    )

    if fixed:
        for c in customers:
            if c["id"] in fixed["customer"] and "vehicle" in fixed["customer"][c["id"]]:
                add_hint(
                    vehicle_visit_vars[fixed["customer"][c["id"]]["vehicle"], c["id"]],
                    1,
                    fix=True,
                )

    if hints:
        for v_id, c_id in vehicle_visit_vars.keys():
            add_hint(
                vehicle_visit_vars[v_id, c_id],
                (
                    1
                    if c_id in hints["customer"]
                    and v_id == hints["customer"][c_id]["vehicle"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

    distance_matrix = data["distance_matrix"]
    max_visits_dict = lib.compute_max_visits(data)
    vehicle_center_pairs = []
    vehicle_center_bounds = {}

    for v in data["vehicles"]:
        for c in centers:
            start_lb = max(
                c["start"],
                v["start"]
                + id_to_depot[v["start_location"]]["service_time"]
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

            center_elapsed_time_ub = {
                g: (0 if g == c["group"] else min(c["end"], v["end"]) - v["start"])
                for g in time_groups
            }
            max_visits = max_visits_dict[v["id"], c["id"]]

            for k in range(max_visits):
                vehicle_center_pairs.append((v["id"], c["id"], k))
                vehicle_center_bounds[v["id"], c["id"], k] = {
                    "start_lb": start_lb,
                    "start_ub": start_ub,
                    "elapsed_time_ub": center_elapsed_time_ub,
                }

    id_to_vehicle = {v["id"]: v for v in data["vehicles"]}
    vehicle_center_start_vars = model.addVars(
        vehicle_center_pairs,
        vtype=gp.GRB.CONTINUOUS,
        lb={
            (v_id, c_id, k): vehicle_center_bounds[v_id, c_id, k]["start_lb"]
            for (v_id, c_id, k) in vehicle_center_pairs
        },
        ub={
            (v_id, c_id, k): vehicle_center_bounds[v_id, c_id, k]["start_ub"]
            for (v_id, c_id, k) in vehicle_center_pairs
        },
        name="vehicle_center_start_vars",
    )
    vehicle_center_load_vars = model.addVars(
        [
            (v_id, c_id, k, g)
            for (v_id, c_id, k) in vehicle_center_pairs
            for g in demand_groups
        ],
        vtype=gp.GRB.CONTINUOUS,
        lb=0,
        ub=[
            id_to_vehicle[v_id]["capacity"]
            for (v_id, _, _) in vehicle_center_pairs
            for _ in demand_groups
        ],
        name="vehicle_center_load_vars",
    )
    vehicle_center_elapsed_time_vars = model.addVars(
        [
            (v_id, c_id, k, g)
            for (v_id, c_id, k) in vehicle_center_pairs
            for g in time_groups
        ],
        vtype=gp.GRB.CONTINUOUS,
        lb=0,
        ub=[
            vehicle_center_bounds[v_id, c_id, k]["elapsed_time_ub"][g]
            for (v_id, c_id, k) in vehicle_center_pairs
            for g in time_groups
        ],
        name="vehicle_center_elapsed_time_vars",
    )

    if fixed:
        for v_id, c_id, k in vehicle_center_pairs:
            if (v_id, c_id, k) in fixed["center"]:
                if "start" in fixed["center"][v_id, c_id, k]:
                    add_hint(
                        vehicle_center_start_vars[v_id, c_id, k],
                        fixed["center"][v_id, c_id, k]["start"],
                        fix=True,
                    )

                if "load" in fixed["center"][v_id, c_id, k]:
                    for g in demand_groups:
                        add_hint(
                            vehicle_center_load_vars[v_id, c_id, k, g],
                            fixed["center"][v_id, c_id, k]["load"][g],
                            fix=True,
                        )

                if "elapsed_time" in fixed["center"][v_id, c_id, k]:
                    for g in time_groups:
                        if g in fixed["center"][v_id, c_id, k]["elapsed_time"]:
                            add_hint(
                                vehicle_center_elapsed_time_vars[v_id, c_id, k, g],
                                fixed["center"][v_id, c_id, k]["elapsed_time"][g],
                                fix=True,
                            )

    if hints:
        for v_id, c_id, k in vehicle_center_pairs:
            if (v_id, c_id, k) in hints["center"]:
                add_hint(
                    vehicle_center_start_vars[v_id, c_id, k],
                    hints["center"][v_id, c_id, k]["start"],
                    as_hint=initial_solution_as_hint,
                )

                for g in demand_groups:
                    add_hint(
                        vehicle_center_load_vars[v_id, c_id, k, g],
                        (
                            hints["center"][v_id, c_id, k]["load"][g]
                            if g in hints["center"][v_id, c_id, k]["load"]
                            else 0
                        ),
                        as_hint=initial_solution_as_hint,
                    )

                for g in time_groups:
                    add_hint(
                        vehicle_center_elapsed_time_vars[v_id, c_id, k, g],
                        (
                            hints["center"][v_id, c_id, k]["elapsed_time"][g]
                            if g in hints["center"][v_id, c_id, k]["elapsed_time"]
                            else 0
                        ),
                        as_hint=initial_solution_as_hint,
                    )
            else:
                add_hint(
                    vehicle_center_start_vars[v_id, c_id, k],
                    vehicle_center_bounds[v_id, c_id, k]["start_lb"],
                    as_hint=initial_solution_as_hint,
                )

                for g in demand_groups:
                    add_hint(
                        vehicle_center_load_vars[v_id, c_id, k, g],
                        0,
                        as_hint=initial_solution_as_hint,
                    )

                for g in time_groups:
                    add_hint(
                        vehicle_center_elapsed_time_vars[v_id, c_id, k, g],
                        0,
                        as_hint=initial_solution_as_hint,
                    )

    driver_vehicle_vars = model.addVars(
        [(d["id"], v_id) for d in data["drivers"] for v_id in d["allowed_vehicles"]],
        vtype=gp.GRB.BINARY,
        name="driver_vehicle_vars",
    )

    if fixed:
        for d_id, v_id in driver_vehicle_vars.keys():
            if d_id in fixed["driver"]:
                add_hint(
                    driver_vehicle_vars[d_id, v_id],
                    1 if fixed["driver"][d_id]["vehicle"] == v_id else 0,
                    fix=True,
                )

    if hints:
        for d_id, v_id in driver_vehicle_vars.keys():
            add_hint(
                driver_vehicle_vars[d_id, v_id],
                (
                    1
                    if d_id in hints["driver"]
                    and hints["driver"][d_id]["vehicle"] == v_id
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

    edges = lib.extract_edges(data)

    x = model.addVars(
        [
            (ci["id"], cj["id"])
            for ci in customers
            for cj in customers
            if (ci["id"], cj["id"]) in edges
        ],
        vtype=gp.GRB.BINARY,
        obj={
            (ci["id"], cj["id"]): cj["score"]
            for ci in customers
            for cj in customers
            if (ci["id"], cj["id"]) in edges
        },
        name="x",
    )
    first_x = model.addVars(
        [
            (v["id"], ci["id"])
            for v in data["vehicles"]
            for ci in customers
            if ci["type"] == "pickup-customer"
            and (v["id"], ci["id"]) in vehicle_visit_vars
        ],
        vtype=gp.GRB.BINARY,
        obj={
            (v["id"], ci["id"]): ci["score"]
            for v in data["vehicles"]
            for ci in customers
            if ci["type"] == "pickup-customer"
            and (v["id"], ci["id"]) in vehicle_visit_vars
        },
        name="first_x",
    )
    last_x = model.addVars(
        [
            (ci["id"], v["id"])
            for v in data["vehicles"]
            for ci in customers
            if ci["type"] == "delivery-customer"
            and (v["id"], ci["id"]) in vehicle_visit_vars
        ],
        vtype=gp.GRB.BINARY,
        name="last_x",
    )

    id_to_vehicle = {v["id"]: v for v in data["vehicles"]}

    if fixed:
        for ci_id, cj_id in x.keys():
            if (("customer", ci_id), ("customer", cj_id)) in fixed["precedence"]:
                add_hint(x[ci_id, cj_id], 1, fix=True)

        for v_id, c_id in first_x.keys():
            if (
                (("vehicle_start", v_id), ("customer", c_id)) in fixed["precedence"]
                and "vehicle" in fixed["customer"][c_id]
                and fixed["customer"][c_id]["vehicle"] == v_id
            ):
                add_hint(first_x[v_id, c_id], 1, fix=True)

        for c_id, v_id in last_x.keys():
            if (
                (("customer", c_id), ("vehicle_end", v_id)) in fixed["precedence"]
                and "vehicle" in fixed["customer"][c_id]
                and fixed["customer"][c_id]["vehicle"] == v_id
            ):
                add_hint(last_x[c_id, v_id], 1, fix=True)

    if hints:
        for ci_id, cj_id in x.keys():
            add_hint(
                x[ci_id, cj_id],
                (
                    1
                    if (("customer", ci_id), ("customer", cj_id)) in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for v_id, c_id in first_x.keys():
            add_hint(
                first_x[v_id, c_id],
                (
                    1
                    if (("vehicle_start", v_id), ("customer", c_id))
                    in hints["precedence"]
                    and hints["customer"][c_id]["vehicle"] == v_id
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for c_id, v_id in last_x.keys():
            add_hint(
                last_x[c_id, v_id],
                (
                    1
                    if (("customer", c_id), ("vehicle_end", v_id))
                    in hints["precedence"]
                    and "vehicle" in hints["customer"][c_id]
                    and hints["customer"][c_id]["vehicle"] == v_id
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

    id_to_center = {c["id"]: c for c in centers}
    vehicle_center_customer_x = model.addVars(
        [
            (v_id, c_id, k, cj["id"])
            for (v_id, c_id, k) in vehicle_center_pairs
            for cj in customers
            if (v_id, cj["id"]) in vehicle_visit_vars and (c_id, cj["id"]) in edges
        ],
        vtype=gp.GRB.BINARY,
        obj={
            (v_id, c_id, k, cj["id"]): cj["score"]
            for (v_id, c_id, k) in vehicle_center_pairs
            for cj in customers
            if (v_id, cj["id"]) in vehicle_visit_vars and (c_id, cj["id"]) in edges
        },
        name="vehicle_center_customer_x",
    )
    customer_vehicle_center_x = model.addVars(
        [
            (ci["id"], v_id, c_id, k)
            for ci in customers
            for (v_id, c_id, k) in vehicle_center_pairs
            if (
                id_to_center[c_id]["type"] != "pickup-center"
                or k != 0
                or id_to_center[c_id]["group"] != ci["group"]
            )
            and (ci["id"], c_id) in edges
            and (v_id, ci["id"]) in vehicle_visit_vars
        ],
        vtype=gp.GRB.BINARY,
        name="customer_vehicle_center_x",
    )
    vehicle_center_center_x = model.addVars(
        [
            (v["id"], ci["id"], ki, cj["id"], kj)
            for v in data["vehicles"]
            for ci in centers
            for cj in centers
            for ki in range(max_visits_dict[v["id"], ci["id"]])
            for kj in range(max_visits_dict[v["id"], cj["id"]])
            if (v["id"], ci["id"], ki) in vehicle_center_start_vars
            and (v["id"], cj["id"], kj) in vehicle_center_start_vars
            and (ci["id"], cj["id"]) in edges
        ],
        vtype=gp.GRB.BINARY,
        name="vehicle_center_center_x",
    )
    vehicle_center_first_x = model.addVars(
        [
            (v_id, c_id, k)
            for (v_id, c_id, k) in vehicle_center_pairs
            if id_to_center[c_id]["type"] == "pickup-center" and k == 0
        ],
        vtype=gp.GRB.BINARY,
        name="vehicle_center_first_x",
    )
    vehicle_center_last_x = model.addVars(
        [
            (v_id, c_id, k)
            for (v_id, c_id, k) in vehicle_center_pairs
            if id_to_center[c_id]["type"] == "delivery-center" and k == 0
        ],
        vtype=gp.GRB.BINARY,
        name="vehicle_center_last_x",
    )

    if fixed:
        for v_id, ci_id, k, cj in vehicle_center_customer_x.keys():
            if (("center", (v_id, ci_id, k)), ("customer", cj)) in fixed["precedence"]:
                add_hint(vehicle_center_customer_x[v_id, ci_id, k, cj], 1, fix=True)

        for ci, v_id, cj_id, k in customer_vehicle_center_x.keys():
            if (("customer", ci), ("center", (v_id, cj_id, k))) in fixed["precedence"]:
                add_hint(customer_vehicle_center_x[ci, v_id, cj_id, k], 1, fix=True)

        for v_id, ci_id, ki, cj_id, kj in vehicle_center_center_x.keys():
            if (("center", (v_id, ci_id, ki)), ("center", (v_id, cj_id, kj))) in fixed[
                "precedence"
            ]:
                add_hint(
                    vehicle_center_center_x[v_id, ci_id, ki, cj_id, kj], 1, fix=True
                )

        for v_id, c_id, k in vehicle_center_first_x.keys():
            if (("vehicle_start", v_id), ("center", (v_id, c_id, k))) in fixed[
                "precedence"
            ]:
                add_hint(vehicle_center_first_x[v_id, c_id, k], 1, fix=True)

        for v_id, c_id, k in vehicle_center_last_x.keys():
            if (("center", (v_id, c_id, k)), ("vehicle_end", v_id)) in fixed[
                "precedence"
            ]:
                add_hint(vehicle_center_last_x[v_id, c_id, k], 1, fix=True)

    if hints:
        for v_id, ci_id, k, cj in vehicle_center_customer_x.keys():
            add_hint(
                vehicle_center_customer_x[v_id, ci_id, k, cj],
                (
                    1
                    if (("center", (v_id, ci_id, k)), ("customer", cj))
                    in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for ci, v_id, cj_id, k in customer_vehicle_center_x.keys():
            add_hint(
                customer_vehicle_center_x[ci, v_id, cj_id, k],
                (
                    1
                    if (("customer", ci), ("center", (v_id, cj_id, k)))
                    in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for v_id, ci_id, ki, cj_id, kj in vehicle_center_center_x.keys():
            add_hint(
                vehicle_center_center_x[v_id, ci_id, ki, cj_id, kj],
                (
                    1
                    if (("center", (v_id, ci_id, ki)), ("center", (v_id, cj_id, kj)))
                    in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for v_id, c_id, k in vehicle_center_first_x.keys():
            add_hint(
                vehicle_center_first_x[v_id, c_id, k],
                (
                    1
                    if (("vehicle_start", v_id), ("center", (v_id, c_id, k)))
                    in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

        for v_id, c_id, k in vehicle_center_last_x.keys():
            add_hint(
                vehicle_center_last_x[v_id, c_id, k],
                (
                    1
                    if (("center", (v_id, c_id, k)), ("vehicle_end", v_id))
                    in hints["precedence"]
                    else 0
                ),
                as_hint=initial_solution_as_hint,
            )

    # Driver assignment constraints
    id_to_customer = {c["id"]: c for c in customers}
    id_to_driver = {d["id"]: d for d in data["drivers"]}
    model.addConstrs(
        (
            gp.quicksum(
                driver_vehicle_vars[d_id, v_id]
                for v_id in id_to_driver[d_id]["allowed_vehicles"]
            )
            <= 1
            for d_id in id_to_driver.keys()
        ),
        name="vehicle_per_driver_assignment",
    )
    model.addConstrs(
        (
            gp.quicksum(
                driver_vehicle_vars[d["id"], v_id]
                for d in data["drivers"]
                if (d["id"], v_id) in driver_vehicle_vars
            )
            <= 1
            for v_id in [v["id"] for v in data["vehicles"]]
        ),
        name="driver_per_vehicle_assignment",
    )
    model.addConstrs(
        (
            vehicle_start_vars[v_id]
            >= id_to_driver[d_id]["start"] * driver_vehicle_vars[d_id, v_id]
            for d_id in id_to_driver.keys()
            for v_id in id_to_driver[d_id]["allowed_vehicles"]
        ),
        name="vehicle_start_time_driver",
    )
    model.addConstrs(
        (
            vehicle_end_vars[v_id]
            <= id_to_driver[d_id]["end"]
            + (id_to_vehicle[v_id]["end"] - id_to_driver[d_id]["end"])
            * (1 - driver_vehicle_vars[d_id, v_id])
            for d_id in id_to_driver.keys()
            for v_id in id_to_driver[d_id]["allowed_vehicles"]
        ),
        name="vehicle_end_time_driver",
    )
    model.addConstrs(
        (
            vehicle_end_vars[v_id] - vehicle_start_vars[v_id]
            <= id_to_driver[d_id]["max_working_time"]
            + (
                id_to_vehicle[v_id]["end"]
                - id_to_vehicle[v_id]["start"]
                - id_to_driver[d_id]["max_working_time"]
            )
            * (1 - driver_vehicle_vars[d_id, v_id])
            for d_id in id_to_driver.keys()
            for v_id in id_to_driver[d_id]["allowed_vehicles"]
        ),
        name="vehicle_working_time_driver",
    )

    # Capacity constraints
    model.addConstrs(
        (
            gp.quicksum(load_vars[c_id, g] for g in demand_groups)
            <= (
                id_to_vehicle[v_id]["capacity"]
                - (
                    id_to_customer[c_id]["demand"]
                    if id_to_customer[c_id]["type"] == "pickup-customer"
                    else 0
                )
            )
            * vehicle_visit_vars[v_id, c_id]
            + (
                max_capacity
                - (
                    id_to_customer[c_id]["demand"]
                    if id_to_customer[c_id]["type"] == "pickup-customer"
                    else 0
                )
            )
            * (1 - vehicle_visit_vars[v_id, c_id])
            for v_id in id_to_vehicle.keys()
            for c_id in id_to_customer.keys()
        ),
        name="customer_capacity",
    )
    model.addConstrs(
        (
            gp.quicksum(
                vehicle_center_load_vars[v_id, c_id, k, g] for g in demand_groups
            )
            <= id_to_vehicle[v_id]["capacity"]
            for (v_id, c_id, k) in vehicle_center_pairs
        ),
        name="center_capacity",
    )

    # Flow conservation constraints
    model.addConstrs(
        (
            gp.quicksum(
                driver_vehicle_vars[d["id"], v_id]
                for d in data["drivers"]
                if (d["id"], v_id) in driver_vehicle_vars
            )
            == gp.quicksum(
                first_x[v_id, c["id"]] for c in customers if (v_id, c["id"]) in first_x
            )
            + gp.quicksum(
                vehicle_center_first_x[v_id, c["id"], k]
                for c in centers
                for k in range(max_visits_dict[v_id, c["id"]])
                if (v_id, c["id"], k) in vehicle_center_first_x
            )
            for v_id in id_to_vehicle.keys()
        ),
        name="vehicle_first",
    )
    model.addConstrs(
        (
            gp.quicksum(
                first_x[v["id"], ci_id]
                for v in data["vehicles"]
                if (v["id"], ci_id) in first_x
            )
            + gp.quicksum(
                x[cj["id"], ci_id] for cj in customers if (cj["id"], ci_id) in x
            )
            + gp.quicksum(
                vehicle_center_customer_x[v_id, c_id, k, ci_id]
                for (v_id, c_id, k) in vehicle_center_pairs
                if (v_id, c_id, k, ci_id) in vehicle_center_customer_x
            )
            == gp.quicksum(
                x[ci_id, cj["id"]] for cj in customers if (ci_id, cj["id"]) in x
            )
            + gp.quicksum(
                customer_vehicle_center_x[ci_id, v_id, c_id, k]
                for (v_id, c_id, k) in vehicle_center_pairs
                if (ci_id, v_id, c_id, k) in customer_vehicle_center_x
            )
            + gp.quicksum(
                last_x[ci_id, v["id"]]
                for v in data["vehicles"]
                if (ci_id, v["id"]) in last_x
            )
            for ci_id in id_to_customer.keys()
        ),
        name="customer_flow_conservation",
    )
    model.addConstrs(
        (
            gp.quicksum(
                first_x[v["id"], ci_id]
                for v in data["vehicles"]
                if (v["id"], ci_id) in first_x
            )
            + gp.quicksum(
                x[cj["id"], ci_id] for cj in customers if (cj["id"], ci_id) in x
            )
            + gp.quicksum(
                vehicle_center_customer_x[v_id, c_id, k, ci_id]
                for (v_id, c_id, k) in vehicle_center_pairs
                if (v_id, c_id, k, ci_id) in vehicle_center_customer_x
            )
            == 1
            for ci_id in id_to_customer.keys()
            if id_to_customer[ci_id]["mandatory"]
        ),
        name="customer_flow_exact",
    )
    model.addConstrs(
        (
            gp.quicksum(
                first_x[v["id"], ci_id]
                for v in data["vehicles"]
                if (v["id"], ci_id) in first_x
            )
            + gp.quicksum(
                x[cj["id"], ci_id] for cj in customers if (cj["id"], ci_id) in x
            )
            + gp.quicksum(
                vehicle_center_customer_x[v_id, c_id, k, ci_id]
                for (v_id, c_id, k) in vehicle_center_pairs
                if (v_id, c_id, k, ci_id) in vehicle_center_customer_x
            )
            <= 1
            for ci_id in id_to_customer.keys()
            if not id_to_customer[ci_id]["mandatory"]
        ),
        name="customer_flow_ub",
    )
    model.addConstrs(
        (
            (
                vehicle_center_first_x[v_id, ci_id, ki]
                if (v_id, ci_id, ki) in vehicle_center_first_x
                else 0
            )
            + gp.quicksum(
                customer_vehicle_center_x[cj["id"], v_id, ci_id, ki]
                for cj in customers
                if (cj["id"], v_id, ci_id, ki) in customer_vehicle_center_x
            )
            + gp.quicksum(
                vehicle_center_center_x[v_id, cj["id"], kj, ci_id, ki]
                for cj in centers
                for kj in range(max_visits_dict[v_id, cj["id"]])
                if (v_id, cj["id"], kj, ci_id, ki) in vehicle_center_center_x
            )
            == gp.quicksum(
                vehicle_center_customer_x[v_id, ci_id, ki, cj["id"]]
                for cj in customers
                if (v_id, ci_id, ki, cj["id"]) in vehicle_center_customer_x
            )
            + gp.quicksum(
                vehicle_center_center_x[v_id, ci_id, ki, cj["id"], kj]
                for cj in centers
                for kj in range(max_visits_dict[v_id, cj["id"]])
                if (v_id, ci_id, ki, cj["id"], kj) in vehicle_center_center_x
            )
            + (
                vehicle_center_last_x[v_id, ci_id, ki]
                if (v_id, ci_id, ki) in vehicle_center_last_x
                else 0
            )
            for (v_id, ci_id, ki) in vehicle_center_pairs
        ),
        name="center_flow_conservation",
    )
    model.addConstrs(
        (
            (
                vehicle_center_first_x[v_id, ci_id, ki]
                if (v_id, ci_id, ki) in vehicle_center_first_x
                else 0
            )
            + gp.quicksum(
                customer_vehicle_center_x[cj["id"], v_id, ci_id, ki]
                for cj in customers
                if (cj["id"], v_id, ci_id, ki) in customer_vehicle_center_x
            )
            + gp.quicksum(
                vehicle_center_center_x[v_id, cj["id"], kj, ci_id, ki]
                for cj in centers
                for kj in range(max_visits_dict[v_id, cj["id"]])
                if (v_id, cj["id"], kj, ci_id, ki) in vehicle_center_center_x
            )
            <= 1
            for (v_id, ci_id, ki) in vehicle_center_pairs
        ),
        name="center_flow_ub",
    )
    model.addConstrs(
        (
            gp.quicksum(
                driver_vehicle_vars[d["id"], v_id]
                for d in data["drivers"]
                if (d["id"], v_id) in driver_vehicle_vars
            )
            == gp.quicksum(
                last_x[c["id"], v_id] for c in customers if (c["id"], v_id) in last_x
            )
            + gp.quicksum(
                vehicle_center_last_x[v_id, c["id"], k]
                for c in centers
                for k in range(max_visits_dict[v_id, c["id"]])
                if (v_id, c["id"], k) in vehicle_center_last_x
            )
            for v_id in id_to_vehicle.keys()
        ),
        name="vehicle_last",
    )

    # Vehicle consistency constraints
    model.addConstrs(
        (
            gp.quicksum(vehicle_visit_vars[v["id"], cj_id] for v in data["vehicles"])
            == gp.quicksum(
                first_x[v["id"], cj_id]
                for v in data["vehicles"]
                if (v["id"], cj_id) in first_x
            )
            + gp.quicksum(
                x[ci["id"], cj_id] for ci in customers if (ci["id"], cj_id) in x
            )
            + gp.quicksum(
                vehicle_center_customer_x[v_id, ci_id, k, cj_id]
                for (v_id, ci_id, k) in vehicle_center_pairs
                if (v_id, ci_id, k, cj_id) in vehicle_center_customer_x
            )
            for cj_id in id_to_customer.keys()
        )
    )
    model.addConstrs(
        (
            vehicle_visit_vars[v_id, c_id] >= first_x[v_id, c_id]
            for v_id in id_to_vehicle.keys()
            for c_id in id_to_customer.keys()
            if (v_id, c_id) in first_x
        ),
        name="first_implies_visit",
    )
    model.addConstrs(
        (
            vehicle_visit_vars[v_id, c_id] >= last_x[c_id, v_id]
            for c_id in id_to_customer.keys()
            for v_id in id_to_vehicle.keys()
            if (c_id, v_id) in last_x
        ),
        name="last_implies_visit",
    )
    model.addConstrs(
        (
            vehicle_visit_vars[v_id, cj_id]
            >= vehicle_visit_vars[v_id, ci_id] + x[ci_id, cj_id] - 1
            for v_id in id_to_vehicle.keys()
            for ci_id in id_to_customer.keys()
            for cj_id in id_to_customer.keys()
            if (ci_id, cj_id) in x
        ),
        name="flow_implies_visit",
    )
    model.addConstrs(
        (
            vehicle_visit_vars[v_id, cj_id]
            >= vehicle_center_customer_x[v_id, ci_id, k, cj_id]
            for cj_id in id_to_customer.keys()
            for (v_id, ci_id, k) in vehicle_center_pairs
            if (v_id, ci_id, k, cj_id) in vehicle_center_customer_x
        ),
        name="center_to_customer_implies_visit",
    )
    model.addConstrs(
        (
            vehicle_visit_vars[v_id, ci_id]
            >= customer_vehicle_center_x[ci_id, v_id, cj_id, k]
            for ci_id in id_to_customer.keys()
            for (v_id, cj_id, k) in vehicle_center_pairs
            if (ci_id, v_id, cj_id, k) in customer_vehicle_center_x
        ),
        name="customer_to_center_implies_visit",
    )

    # Time consistency constraints for customers
    model.addConstrs(
        (
            start_vars[c_id]
            >= vehicle_start_vars[v_id]
            + id_to_depot[id_to_vehicle[v_id]["start_location"]]["service_time"]
            + distance_matrix[id_to_vehicle[v_id]["start_location"]][c_id]
            - (
                id_to_vehicle[v_id]["end"]
                + id_to_depot[id_to_vehicle[v_id]["start_location"]]["service_time"]
                + distance_matrix[id_to_vehicle[v_id]["start_location"]][c_id]
                - id_to_customer[c_id]["start"]
            )
            * (1 - first_x[v_id, c_id])
            for v_id in id_to_vehicle.keys()
            for c_id in id_to_customer.keys()
            if (v_id, c_id) in first_x
        ),
        name="first_time_consistency",
    )
    model.addConstrs(
        (
            start_vars[cj_id]
            >= start_vars[ci_id]
            + id_to_customer[ci_id]["service_time"]
            + distance_matrix[ci_id][cj_id]
            - (
                id_to_customer[ci_id]["end"]
                - id_to_customer[cj_id]["start"]
                + id_to_customer[ci_id]["service_time"]
                + distance_matrix[ci_id][cj_id]
            )
            * (1 - x[ci_id, cj_id])
            for ci_id in id_to_customer.keys()
            for cj_id in id_to_customer.keys()
            if (ci_id, cj_id) in x
        ),
        name="flow_time_consistency",
    )
    model.addConstrs(
        (
            vehicle_end_vars[v_id]
            >= start_vars[c_id]
            + id_to_customer[c_id]["service_time"]
            + distance_matrix[c_id][id_to_vehicle[v_id]["end_location"]]
            - (
                id_to_customer[c_id]["end"]
                - id_to_vehicle[v_id]["start"]
                + id_to_customer[c_id]["service_time"]
                + distance_matrix[c_id][id_to_vehicle[v_id]["end_location"]]
            )
            * (1 - last_x[c_id, v_id])
            for c_id in id_to_customer.keys()
            for v_id in id_to_vehicle.keys()
            if (c_id, v_id) in last_x
        ),
        name="last_time_consistency",
    )
    # Time consistency constraints for centers
    model.addConstrs(
        (
            vehicle_center_start_vars[v_id, c_id, k]
            >= vehicle_start_vars[v_id]
            + id_to_depot[id_to_vehicle[v_id]["start_location"]]["service_time"]
            + distance_matrix[id_to_vehicle[v_id]["start_location"]][c_id]
            - (
                id_to_vehicle[v_id]["end"]
                - id_to_center[c_id]["start"]
                + distance_matrix[id_to_vehicle[v_id]["start_location"]][c_id]
            )
            * (1 - vehicle_center_first_x[v_id, c_id, k])
            for (v_id, c_id, k) in vehicle_center_pairs
            if (v_id, c_id, k) in vehicle_center_first_x
        ),
        name="center_first_time_consistency",
    )
    model.addConstrs(
        (
            start_vars[cj_id]
            >= vehicle_center_start_vars[v_id, ci_id, k]
            + id_to_center[ci_id]["service_time"]
            + distance_matrix[ci_id][cj_id]
            - (
                id_to_center[ci_id]["end"]
                - id_to_customer[cj_id]["start"]
                + id_to_center[ci_id]["service_time"]
                + distance_matrix[ci_id][cj_id]
            )
            * (1 - vehicle_center_customer_x[v_id, ci_id, k, cj_id])
            for (v_id, ci_id, k) in vehicle_center_pairs
            for cj_id in id_to_customer.keys()
            if (v_id, ci_id, k, cj_id) in vehicle_center_customer_x
        ),
        name="center_to_customer_time_consistency",
    )
    model.addConstrs(
        (
            vehicle_center_start_vars[v_id, cj_id, kj]
            >= start_vars[ci_id]
            + id_to_customer[ci_id]["service_time"]
            + distance_matrix[ci_id][cj_id]
            - (
                id_to_customer[ci_id]["end"]
                - id_to_center[cj_id]["start"]
                + id_to_customer[ci_id]["service_time"]
                + distance_matrix[ci_id][cj_id]
            )
            * (1 - customer_vehicle_center_x[ci_id, v_id, cj_id, kj])
            for ci_id in id_to_customer.keys()
            for (v_id, cj_id, kj) in vehicle_center_pairs
            if (ci_id, v_id, cj_id, kj) in customer_vehicle_center_x
        ),
        name="customer_to_center_time_consistency",
    )
    model.addConstrs(
        (
            vehicle_center_start_vars[v_id, cj_id, k_j]
            >= vehicle_center_start_vars[v_id, ci_id, k_i]
            + id_to_center[ci_id]["service_time"]
            + distance_matrix[ci_id][cj_id]
            - (
                id_to_center[ci_id]["end"]
                - id_to_center[cj_id]["start"]
                + id_to_center[ci_id]["service_time"]
                + distance_matrix[ci_id][cj_id]
            )
            * (1 - vehicle_center_center_x[v_id, ci_id, k_i, cj_id, k_j])
            for (v_id, ci_id, k_i, cj_id, k_j) in vehicle_center_center_x.keys()
        ),
        name="center_to_center_time_consistency",
    )
    model.addConstrs(
        (
            vehicle_end_vars[v_id]
            >= vehicle_center_start_vars[v_id, c_id, k]
            + id_to_center[c_id]["service_time"]
            + distance_matrix[c_id][id_to_vehicle[v_id]["end_location"]]
            - (
                id_to_center[c_id]["end"]
                - id_to_vehicle[v_id]["start"]
                + id_to_center[c_id]["service_time"]
                + distance_matrix[c_id][id_to_vehicle[v_id]["end_location"]]
            )
            * (1 - vehicle_center_last_x[v_id, c_id, k])
            for (v_id, c_id, k) in vehicle_center_pairs
            if (v_id, c_id, k) in vehicle_center_last_x
        ),
        name="center_last_time_consistency",
    )

    # Load consistency constraints for customers
    demand_change = {
        (c_id, g): (
            -id_to_customer[c_id]["demand"]
            if id_to_customer[c_id]["type"] == "delivery-customer"
            and id_to_customer[c_id]["group"] == g
            else (
                id_to_customer[c_id]["demand"]
                if id_to_customer[c_id]["type"] == "pickup-customer"
                and id_to_customer[c_id]["group"] == g
                else 0
            )
        )
        for c_id in id_to_customer.keys()
        for g in demand_groups
    }
    lb_groups = [
        g
        for g in demand_groups
        if any(c["type"] == "pickup-customer" for c in customers)
    ]
    ub_groups = [
        g
        for g in demand_groups
        if any(c["type"] == "delivery-customer" for c in customers)
    ]

    model.addConstrs(
        (
            load_vars[c_id, g] <= (1 - first_x[v_id, c_id]) * max_capacity
            for v_id in id_to_vehicle.keys()
            for c_id in id_to_customer.keys()
            for g in ub_groups
            if (v_id, c_id) in first_x
        ),
        name="first_load_0",
    )
    model.addConstrs(
        (
            load_vars[c_id, g] <= max_capacity * (1 - last_x[c_id, v_id])
            for c_id in id_to_customer.keys()
            for v_id in id_to_vehicle.keys()
            for g in lb_groups
            if (c_id, v_id) in last_x and g != id_to_customer[c_id]["group"]
        ),
        name="last_load_0",
    )
    model.addConstrs(
        (
            load_vars[cj_id, g]
            >= load_vars[ci_id, g]
            + demand_change[ci_id, g]
            - (max_capacity - demand_change[ci_id, g]) * (1 - x[ci_id, cj_id])
            for ci_id in id_to_customer.keys()
            for cj_id in id_to_customer.keys()
            if (ci_id, cj_id) in x
            for g in lb_groups
        ),
        name="flow_load_lb",
    )
    model.addConstrs(
        (
            load_vars[cj_id, g]
            <= load_vars[ci_id, g]
            + demand_change[ci_id, g]
            + (max_capacity - demand_change[ci_id, g]) * (1 - x[ci_id, cj_id])
            for ci_id in id_to_customer.keys()
            for cj_id in id_to_customer.keys()
            if (ci_id, cj_id) in x
            for g in ub_groups
        ),
        name="flow_load_ub",
    )
    # Load consistency constraints for centers
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, c_id, k, g]
            <= id_to_vehicle[v_id]["capacity"]
            * (1 - vehicle_center_first_x[v_id, c_id, k])
            for (v_id, c_id, k) in vehicle_center_pairs
            for g in ub_groups
            if (v_id, c_id, k) in vehicle_center_first_x
            and id_to_center[c_id]["group"] != g
        ),
        name="center_first_load_0",
    )
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, c_id, k, g]
            <= id_to_vehicle[v_id]["capacity"]
            * (1 - vehicle_center_last_x[v_id, c_id, k])
            for (v_id, c_id, k) in vehicle_center_pairs
            for g in lb_groups
            if (v_id, c_id, k) in vehicle_center_last_x
            and id_to_center[c_id]["group"] != g
        ),
        name="center_last_load_0",
    )
    model.addConstrs(
        (
            load_vars[cj_id, g]
            >= vehicle_center_load_vars[v_id, c_id, k, g]
            - (id_to_vehicle[v_id]["capacity"])
            * (1 - vehicle_center_customer_x[v_id, c_id, k, cj_id])
            for (v_id, c_id, k) in vehicle_center_pairs
            for cj_id in id_to_customer.keys()
            if (v_id, c_id, k, cj_id) in vehicle_center_customer_x
            for g in lb_groups
            if g != id_to_center[c_id]["group"]
        ),
        name="center_to_customer_load_lb",
    )
    model.addConstrs(
        (
            load_vars[cj_id, g]
            <= vehicle_center_load_vars[v_id, c_id, k, g]
            + max_capacity * (1 - vehicle_center_customer_x[v_id, c_id, k, cj_id])
            for (v_id, c_id, k) in vehicle_center_pairs
            for cj_id in id_to_customer.keys()
            if (v_id, c_id, k, cj_id) in vehicle_center_customer_x
            for g in ub_groups
            if g != id_to_center[c_id]["group"]
        ),
        name="center_to_customer_load_ub",
    )
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, c_id, k, g]
            >= load_vars[ci_id, g]
            + demand_change[ci_id, g]
            - (max_capacity + demand_change[ci_id, g])
            * (1 - customer_vehicle_center_x[ci_id, v_id, c_id, k])
            for ci_id in id_to_customer.keys()
            for (v_id, c_id, k) in vehicle_center_pairs
            if (ci_id, v_id, c_id, k) in customer_vehicle_center_x
            for g in lb_groups
        ),
        name="customer_to_center_load_lb",
    )
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, c_id, k, g]
            <= load_vars[ci_id, g]
            + demand_change[ci_id, g]
            + (id_to_vehicle[v_id]["capacity"] + demand_change[ci_id, g])
            * (1 - customer_vehicle_center_x[ci_id, v_id, c_id, k])
            for ci_id in id_to_customer.keys()
            for (v_id, c_id, k) in vehicle_center_pairs
            if (ci_id, v_id, c_id, k) in customer_vehicle_center_x
            for g in ub_groups
        ),
        name="customer_to_center_load_ub",
    )
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, cj_id, k_j, g]
            >= vehicle_center_load_vars[v_id, ci_id, k_i, g]
            - id_to_vehicle[v_id]["capacity"]
            * (1 - vehicle_center_center_x[v_id, ci_id, k_i, cj_id, k_j])
            for (v_id, ci_id, k_i, cj_id, k_j) in vehicle_center_center_x.keys()
            for g in lb_groups
            if g != id_to_center[ci_id]["group"]
        ),
        name="center_to_center_load_lb",
    )
    model.addConstrs(
        (
            vehicle_center_load_vars[v_id, cj_id, k_j, g]
            <= vehicle_center_load_vars[v_id, ci_id, k_i, g]
            + id_to_vehicle[v_id]["capacity"]
            * (1 - vehicle_center_center_x[v_id, ci_id, k_i, cj_id, k_j])
            for (v_id, ci_id, k_i, cj_id, k_j) in vehicle_center_center_x.keys()
            for g in ub_groups
            if g != id_to_center[ci_id]["group"]
        ),
        name="center_to_center_load_ub",
    )

    # Elapsed time consistency constraints for customers
    model.addConstrs(
        (
            elapsed_time_vars[cj_id, g]
            >= elapsed_time_vars[ci_id, g]
            + start_vars[cj_id]
            - start_vars[ci_id]
            - (
                elapsed_time_ub[ci_id, g]
                + id_to_customer[cj_id]["end"]
                - id_to_customer[ci_id]["start"]
            )
            * (1 - x[ci_id, cj_id])
            for ci_id in id_to_customer.keys()
            for cj_id in id_to_customer.keys()
            for g in time_groups
            if (ci_id, cj_id) in x
        ),
        name="customer_elapsed_time_lb",
    )
    # Elapsed time consistency constraints for centers
    model.addConstrs(
        (
            elapsed_time_vars[cj_id, g]
            >= vehicle_center_elapsed_time_vars[v_id, ci_id, k, g]
            + start_vars[cj_id]
            - vehicle_center_start_vars[v_id, ci_id, k]
            - (
                vehicle_center_bounds[v_id, ci_id, k]["elapsed_time_ub"][g]
                + id_to_customer[cj_id]["end"]
                - id_to_center[ci_id]["start"]
            )
            * (1 - vehicle_center_customer_x[v_id, ci_id, k, cj_id])
            for (v_id, ci_id, k) in vehicle_center_pairs
            for cj_id in id_to_customer.keys()
            for g in time_groups
            if (v_id, ci_id, k, cj_id) in vehicle_center_customer_x
            and g in vehicle_center_bounds[v_id, ci_id, k]["elapsed_time_ub"]
        ),
        name="center_to_customer_elapsed_time_lb",
    )
    model.addConstrs(
        (
            vehicle_center_elapsed_time_vars[v_id, cj_id, k, g]
            >= elapsed_time_vars[ci_id, g]
            + vehicle_center_start_vars[v_id, cj_id, k]
            - start_vars[ci_id]
            - (
                elapsed_time_ub[ci_id, g]
                + id_to_center[cj_id]["end"]
                - id_to_customer[ci_id]["start"]
            )
            * (1 - customer_vehicle_center_x[ci_id, v_id, cj_id, k])
            for ci_id in id_to_customer.keys()
            for (v_id, cj_id, k) in vehicle_center_pairs
            for g in time_groups
            if (ci_id, v_id, cj_id, k) in customer_vehicle_center_x
            and g != id_to_center[cj_id]["group"]
        ),
        name="customer_to_center_elapsed_time_lb",
    )
    model.addConstrs(
        (
            vehicle_center_elapsed_time_vars[v_id, cj_id, kj, g]
            >= vehicle_center_elapsed_time_vars[v_id, ci_id, ki, g]
            + vehicle_center_start_vars[v_id, cj_id, kj]
            - vehicle_center_start_vars[v_id, ci_id, ki]
            - (
                vehicle_center_bounds[v_id, ci_id, ki]["elapsed_time_ub"][g]
                + id_to_center[cj_id]["end"]
                - id_to_center[ci_id]["start"]
            )
            * (1 - vehicle_center_center_x[v_id, ci_id, ki, cj_id, kj])
            for (v_id, ci_id, ki, cj_id, kj) in vehicle_center_center_x.keys()
            for g in time_groups
            if g != id_to_center[cj_id]["group"]
        ),
        name="center_to_center_elapsed_time_lb",
    )

    model.modelSense = gp.GRB.MAXIMIZE

    return (
        model,
        vehicle_start_vars,
        vehicle_end_vars,
        start_vars,
        vehicle_visit_vars,
        vehicle_center_start_vars,
        vehicle_center_first_x,
        customer_vehicle_center_x,
        vehicle_center_center_x,
        driver_vehicle_vars,
    )


def extract_vehicle_tour_solution(
    data,
    vehicle_start_vars,
    vehicle_end_vars,
    start_vars,
    vehicle_visit_vars,
    vehicle_center_start_vars,
    vehicle_center_first_x,
    customer_vehicle_center_x,
    vehicle_center_center_x,
    driver_vehicle_vars,
):
    _, pickup_centers, delivery_customers, delivery_centers, pickup_customers = (
        lib.classify_locations(data)
    )
    centers = delivery_centers + pickup_centers
    customers = delivery_customers + pickup_customers
    max_visits_dict = lib.compute_max_visits(data)
    solution = []

    for v in data["vehicles"]:
        plan = [
            {
                "pos": v["start_location"],
                "time": vehicle_start_vars[v["id"]].x,
            }
        ]

        for c in customers:
            if (v["id"], c["id"]) in vehicle_visit_vars and vehicle_visit_vars[
                v["id"], c["id"]
            ].x >= 0.5:
                plan.append(
                    {
                        "pos": c["id"],
                        "time": start_vars[c["id"]].x,
                    }
                )

        for c in centers:
            for k in range(max_visits_dict[v["id"], c["id"]]):
                if (
                    (
                        (
                            v["id"],
                            c["id"],
                            k,
                        )
                        in vehicle_center_first_x
                        and vehicle_center_first_x[v["id"], c["id"], k].x >= 0.5
                    )
                    or any(
                        (ci["id"], v["id"], c["id"], k) in customer_vehicle_center_x
                        and customer_vehicle_center_x[ci["id"], v["id"], c["id"], k].x
                        >= 0.5
                        for ci in customers
                    )
                    or any(
                        (v["id"], ci["id"], ki, c["id"], k) in vehicle_center_center_x
                        and vehicle_center_center_x[v["id"], ci["id"], ki, c["id"], k].x
                        >= 0.5
                        for ci in centers
                        for ki in range(max_visits_dict[v["id"], ci["id"]])
                    )
                ):
                    plan.append(
                        {
                            "pos": c["id"],
                            "time": vehicle_center_start_vars[v["id"], c["id"], k].x,
                        }
                    )

        if len(plan) > 1:
            plan = sorted(plan, key=lambda x: x["time"])
            plan.append({"pos": v["end_location"], "time": vehicle_end_vars[v["id"]].x})

            for d in data["drivers"]:
                if (d["id"], v["id"]) in driver_vehicle_vars and driver_vehicle_vars[
                    d["id"], v["id"]
                ].x >= 0.5:
                    solution.append(
                        {
                            "vehicle": v["id"],
                            "driver": d["id"],
                            "plan": plan,
                        }
                    )
                    break

    return solution


def solve_model(
    data,
    time_limit=None,
    threads=None,
    verbose=None,
    fixed=None,
    hints=None,
    initial_solution_as_hint=False,
):
    (
        model,
        vehicle_start_vars,
        vehicle_end_vars,
        start_vars,
        vehicle_visit_vars,
        vehicle_center_start_vars,
        vehicle_center_first_x,
        customer_vehicle_center_x,
        vehicle_center_center_x,
        driver_vehicle_vars,
    ) = create_vehicle_tour_mip_model(
        data,
        fixed=fixed,
        hints=hints,
        initial_solution_as_hint=initial_solution_as_hint,
    )

    if time_limit is not None:
        model.setParam("TimeLimit", time_limit)
    if threads is not None:
        model.setParam("Threads", threads)
    if verbose is not None:
        model.setParam("OutputFlag", 1 if verbose else 0)

    model.optimize()

    status = model.getAttr("Status")
    sol_count = model.getAttr("SolCount")
    best_bound = None if status == gp.GRB.INFEASIBLE else model.ObjBound
    elapsed_time = model.Runtime

    if sol_count > 0:
        solution = extract_vehicle_tour_solution(
            data,
            vehicle_start_vars,
            vehicle_end_vars,
            start_vars,
            vehicle_visit_vars,
            vehicle_center_start_vars,
            vehicle_center_first_x,
            customer_vehicle_center_x,
            vehicle_center_center_x,
            driver_vehicle_vars,
        )
        objective_value = model.ObjVal

        return model, solution, objective_value, best_bound, elapsed_time, status
    else:

        return model, None, None, best_bound, elapsed_time, status


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
    parser.add_argument("--initial-solution-as-hint", action="store_true")
    parser.add_argument("--verbose", action="store_true")

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

    model, solution, objective_value, best_bound, elapsed_time, status = solve_model(
        preprocessed_data,
        time_limit=args.time_limit,
        threads=args.threads,
        verbose=args.verbose,
        fixed=fixed,
        hints=hints,
        initial_solution_as_hint=args.initial_solution_as_hint,
    )

    if status == gp.GRB.INFEASIBLE:
        print("Problem is infeasible")

        if args.verbose and status == gp.GRB.INFEASIBLE:
            model.computeIIS()
            print("\nThe following constraints and variables are in the IIS:")

            for c in model.getConstrs():
                if c.IISConstr:
                    print(f"\t{c.constrname}: {model.getRow(c)} {c.Sense} {c.RHS}")

            for v in model.getVars():
                if v.IISLB:
                    print(f"\t{v.varname} ≥ {v.LB}")
                if v.IISUB:
                    print(f"\t{v.varname} ≤ {v.UB}")
    elif solution is None:
        print("No solution found within the time limit")
    else:
        if status == gp.GRB.OPTIMAL:
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

            if args.verbose:
                for v in model.getVars():
                    if v.getAttr(gp.GRB.Attr.VType) != "B" or v.X > 0.5:
                        print(f"{v.VarName}: {v.X}")
