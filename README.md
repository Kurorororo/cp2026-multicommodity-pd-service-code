# Multi-Commodity Home-Delivery and Pickup Routing

Code and synthetic instances accompanying **[“Optimizing a Multi-Commodity Home-Delivery and Pickup Service in Depopulated Rural Areas with Constraint Programming”](https://doi.org/10.4230/LIPIcs.CP.2026.36)** (CP 2026).

The solvers plan vehicle routes and assign drivers for lunch delivery, package delivery, and package pickup in rural areas. They maximize the total score of served optional requests while respecting mandatory visits, time windows, vehicle capacities, driver availability and working-time limits, and commodity-specific pickup and delivery requirements. Lunch deliveries can also have a transportation-time limit.

Two implementations are provided: a constraint programming model using OR-Tools CP-SAT and a mixed-integer programming model using Gurobi.

## Repository contents

| Path | Contents |
| --- | --- |
| [solvers/cp_solver.py](solvers/cp_solver.py) | CP-SAT solver, with an optional circuit-constraint formulation. |
| [solvers/gurobi_solver.py](solvers/gurobi_solver.py) | Gurobi mixed-integer programming solver. |
| [solvers/lib.py](solvers/lib.py) | Shared preprocessing, solution validation, postprocessing, and initial-solution handling. |
| [instances/](instances/) | Solver-ready JSON instances for three commodity variants and two road-network topologies, together with their intermediate map and request data. |
| [instances/maps/](instances/maps/) | Synthetic maps in `mesh-maps/` and `star-maps/`, used to generate requests. |
| [instances/requests/](instances/requests/) | Request data in `mesh-requests/` and `star-requests/`, containing locations and travel-time matrices before vehicles and drivers are added. |
| [instance-generator/](instance-generator/) | Scripts for generating maps, requests, vehicles, and drivers, and filtering commodity groups. |

## Setup

Run the commands below from the repository root using Python 3. A virtual environment is recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ortools
```

For map generation, install NumPy:

```bash
python -m pip install numpy
```

To use the Gurobi solver, install its Python package and configure a Gurobi license suitable for the instance size:

```bash
python -m pip install gurobipy
```

Gurobi is optional; the CP-SAT solver does not require it.

## Run a solver

Both solvers require two positional arguments: the input instance and the output solution file.

For a small lunch-delivery instance:

```bash
mkdir -p results
python solvers/cp_solver.py \
  instances/lunch-instances/mesh-instances/mesh_n4_0_1units.json \
  results/lunch-cp.json \
  --time-limit 30 --threads 1
```

Use `--use-circuit` to enable the CP-SAT circuit-constraint formulation. It is disabled by default.

To solve the same instance with Gurobi:

```bash
python solvers/gurobi_solver.py \
  instances/lunch-instances/mesh-instances/mesh_n4_0_1units.json \
  results/lunch-mip.json \
  --time-limit 30 --threads 1
```

| Option | Description |
| --- | --- |
| `--time-limit SECONDS` | Solver time limit in seconds; default: `300`. |
| `--threads N` | Number of solver workers/threads; omitted by default to use the solver's automatic setting. |
| `--initial-solution PATH` | Read a previous solution to guide the search, including any explicitly fixed decisions. |
| `--verbose` | Enable detailed solver logging. |
| `--use-circuit` | CP-SAT only: use circuit constraints. |
| `--initial-solution-as-hint` | Gurobi only: use variable hints instead of a MIP start for the initial solution. |

The solvers print the routes, objective value, best bound, and elapsed solve time when a solution is found. They write the output JSON only after validating the solution. Check the console output if no file is produced: the instance may be infeasible, the time limit may expire without a solution, or validation may fail. A feasible solution is not necessarily proven optimal.

### Reuse a solution

A saved solution can guide a subsequent solve. The corresponding bundled commodity variants retain location IDs, so a lunch-only solution can be used when adding package deliveries:

```bash
python solvers/cp_solver.py \
  instances/lunch-package-instances/mesh-instances/mesh_n4_0_1units.json \
  results/lunch-package-cp.json \
  --initial-solution results/lunch-cp.json \
  --time-limit 300 --threads 1
```

The resulting solution can similarly seed the matching file under `instances/all-commodity-instances/`. For custom inputs, keep the location, vehicle, and driver IDs consistent between the initial solution and the target instance.

Initial solutions can also fix decisions: a tour's `fixed_up_to` fixes its prefix through the specified zero-based plan index; `fixed_pos` lists customer IDs whose vehicle assignment is fixed; and a plan entry's `fixed: true` fixes that visit's time. Omit these fields to leave decisions free to change.

## Benchmark instances

| Directory | Customer requests included |
| --- | --- |
| [instances/lunch-instances/](instances/lunch-instances/) | Lunch delivery (`lunch`). |
| [instances/lunch-package-instances/](instances/lunch-package-instances/) | Lunch and package delivery (`lunch`, `package`). |
| [instances/all-commodity-instances/](instances/all-commodity-instances/) | Lunch delivery, package delivery, and package pickup (`lunch`, `package`, `collection`). |

Each variant contains `mesh-instances/` and `star-instances/`, with 60 JSON files per topology (360 solver instances in total). Mesh maps connect cluster centers through a nearest-neighbor graph; star maps arrange rural clusters along branches connected through a central origin.

The intermediate data are also included: [instances/maps/](instances/maps/) and [instances/requests/](instances/requests/) each contain 20 mesh and 20 star JSON files. Request files include all three commodities. Maps and request files are not complete solver inputs; use the commodity-specific instance directories above to run a solver.

Filenames follow `<topology>_n<N>_<K>_<U>units.json`:

- `N` is the map size parameter: `4`, `8`, `12`, or `16`. For mesh maps it counts all clusters, including the central cluster; for star maps it counts rural clusters.
- `K` is the instance index: `0` through `4`.
- `U` is the number of resource units: `N/4`, `N/2`, or `N`. Each unit provides three vehicles and three drivers, so `1units` means three vehicles and three drivers.

The bundled requests are optional and use scores to prioritize lunch deliveries, then package deliveries, then package pickups. Serving one additional lunch request outweighs all lower-priority requests combined; serving one additional package delivery outweighs all package pickups combined.

## JSON formats

### Input

See [mesh_n4_0_1units.json](instances/all-commodity-instances/mesh-instances/mesh_n4_0_1units.json) for a complete example. Each instance has four top-level fields:

| Field | Required contents |
| --- | --- |
| `vehicles` | Objects with `id`, `capacity`, availability `start`/`end`, and depot IDs `start_location`/`end_location`. |
| `drivers` | Objects with `id`, availability `start`/`end`, `max_working_time`, and a list of `allowed_vehicles` IDs. |
| `locations` | Objects with `id`, `type`, `group`, `mandatory`, `score`, `demand`, time window `start`/`end`, and `service_time`. Delivery customers may also have `transportation_time_limit`. |
| `distance_matrix` | A matrix of travel times: entry `[i][j]` is the time from location ID `i` to location ID `j`. |

Vehicle and driver IDs should match their zero-based positions in their respective arrays. Location IDs must be unique nonnegative integers with matching matrix rows and columns; they need not be consecutive in `locations`. The reduced commodity variants retain the original location IDs and matrix indexing.

Location types are `depot`, `pickup-center`, `delivery-center`, `delivery-customer`, and `pickup-customer`. A `group` identifies a commodity: delivery customers receive goods from pickup locations of the same group, and pickup customers send goods to delivery locations of the same group. Centers can be visited repeatedly. Use separate groups for package delivery and package pickup, as in the bundled instances.

Customer `demand` is positive for both pickup and delivery. `mandatory: true` requires the customer to be served; otherwise, serving it contributes its `score` to the objective. A delivery customer's `transportation_time_limit`, when present and non-null, limits the elapsed time from the corresponding pickup-center visit to its delivery visit.

Use consistent integer time units for all input times, durations, and travel times. Output visit times use the same units. The command-line `--time-limit` is always in seconds, independently of the instance's time scale.

### Output

The output is a JSON array of tours. Each tour contains a `vehicle` ID, a `driver` ID, and a `plan` array of visits from the starting depot to the ending depot. Each visit contains:

- `pos`: the location ID.
- `time`: the scheduled visit time.
- `load_change`: the change in vehicle load; positive for loading, negative for unloading, and zero when the load is unchanged.

This is also the format accepted by `--initial-solution`.

## Generate new instances

Generation has three stages: create maps, add requests, then add vehicles and drivers. The scripts expect their output directories to exist. This example creates a small mesh map and three resource configurations under `generated/`:

```bash
mkdir -p generated/mesh-maps generated/mesh-requests generated/mesh-instances

python instance-generator/generate_mesh_maps.py \
  --n-values 4 --num-instances-per-n 1 --base-seed 0 \
  --out-dir generated/mesh-maps

python instance-generator/generate_requests.py \
  generated/mesh-maps generated/mesh-requests

python instance-generator/generate_driver_data.py \
  generated/mesh-requests generated/mesh-instances
```

For star maps, use `generate_star_maps.py` with `--prefix star` and separate directories. Both map generators default to sizes `4 8 12 16` and five maps per size when the size/count options are omitted. Keep the `_n<N>_<K>.json` filename pattern because the driver-data generator reads `N` from it.

To start from the bundled maps, pass `instances/maps/mesh-maps` or `instances/maps/star-maps` as the input directory to `generate_requests.py`. To reuse the bundled requests, skip map and request generation and add vehicles and drivers directly:

```bash
mkdir -p generated/all-commodity-mesh-instances
python instance-generator/generate_driver_data.py \
  instances/requests/mesh-requests generated/all-commodity-mesh-instances
```

For the star requests, use `instances/requests/star-requests` and a separate output directory.

The request generator includes all three commodities by default. Set `--collection-request-probability 0` to omit package pickup requests; also set `--package-request-probability 0` for lunch-only requests. The driver-data generator produces `N/4`, `N/2`, and `N` resource-unit variants for each input map.

Map generation accepts `--base-seed`, but request generation uses unseeded randomness and has no seed option. Use the bundled instance files for repeatable solver comparisons; the generation example creates new requests rather than reproducing the bundled JSON exactly.

### Remove commodities from existing instances

Use [filter_groups.py](instance-generator/filter_groups.py) to create reduced commodity variants from existing request files or complete solver instances. The `--groups` option lists the groups to **keep**, and all other locations are removed. It defaults to `depot lunch`; include `depot` to retain the vehicle base.

For example, create lunch-only and lunch-plus-package-delivery variants from the bundled mesh instances:

```bash
mkdir -p generated/lunch-instances/mesh-instances \
  generated/lunch-package-instances/mesh-instances

python instance-generator/filter_groups.py \
  instances/all-commodity-instances/mesh-instances \
  generated/lunch-instances/mesh-instances \
  --groups depot lunch

python instance-generator/filter_groups.py \
  instances/all-commodity-instances/mesh-instances \
  generated/lunch-package-instances/mesh-instances \
  --groups depot lunch package
```

Use the corresponding `star-instances` directories for star instances. The script processes JSON files directly inside the input directory and requires the output directory to exist. It preserves filenames, retained location IDs and scores, the distance matrix, and any vehicles and drivers. Filtering request files under `instances/requests/` still requires adding vehicles and drivers before solving.

Run any script with `--help` to see its full set of options.

## Citation

If you use this code or these instances in your research, please cite:

Ryo Kuroiwa, Tomoki Hasegawa, Eiji Ueda, Naoki Akiyama, and Akira Yoshioka. **[Optimizing a Multi-Commodity Home-Delivery and Pickup Service in Depopulated Rural Areas with Constraint Programming](https://doi.org/10.4230/LIPIcs.CP.2026.36)**. In *32nd International Conference on Principles and Practice of Constraint Programming (CP 2026)*, LIPIcs, volume 379, pages 36:1–36:22. Schloss Dagstuhl – Leibniz-Zentrum für Informatik, 2026.

```bibtex
@InProceedings{kuroiwa_et_al:LIPIcs.CP.2026.36,
  author    = {Kuroiwa, Ryo and Hasegawa, Tomoki and Ueda, Eiji and Akiyama, Naoki and Yoshioka, Akira},
  title     = {{Optimizing a Multi-Commodity Home-Delivery and Pickup Service in Depopulated Rural Areas with Constraint Programming}},
  booktitle = {32nd International Conference on Principles and Practice of Constraint Programming (CP 2026)},
  pages     = {36:1--36:22},
  series    = {Leibniz International Proceedings in Informatics (LIPIcs)},
  year      = {2026},
  volume    = {379},
  editor    = {Beldiceanu, Nicolas},
  publisher = {Schloss Dagstuhl -- Leibniz-Zentrum f{\"u}r Informatik},
  address   = {Dagstuhl, Germany},
  doi       = {10.4230/LIPIcs.CP.2026.36},
  url       = {https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CP.2026.36}
}
```

## License

This repository is licensed under the [Apache License, Version 2.0](LICENSE) (`Apache-2.0`). Third-party dependencies, including Gurobi, are distributed under their own licenses.
