#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass(frozen=True)
class GeneratorParams:
    # origin cluster
    r1: float
    m1: int

    # step length / first radius range (used per-cluster)
    rmin: float
    rmax: float

    # rural cluster radius
    r2: float

    # rural cluster size
    m2min: int
    m2max: int

    # max clusters per line (chain)
    n_cluster_max: int


def sample_uniform_in_disk(
    rng: np.random.Generator, radius: float, center: np.ndarray
) -> np.ndarray:
    """Area-uniform sampling inside a disk."""
    theta = rng.uniform(0.0, 2.0 * np.pi)
    rad = radius * np.sqrt(rng.uniform(0.0, 1.0))
    return center + np.array([rad * np.cos(theta), rad * np.sin(theta)], dtype=float)


def sample_points_in_disk(
    rng: np.random.Generator, radius: float, center: np.ndarray, m: int
) -> np.ndarray:
    if m <= 0:
        return np.empty((0, 2), dtype=float)
    return np.vstack([sample_uniform_in_disk(rng, radius, center) for _ in range(m)])


def ceil_euclid(a: np.ndarray, b: np.ndarray) -> int:
    return int(
        math.ceil(math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    )


def chain_direction(chain_id: int, n_total_clusters: int) -> np.ndarray:
    """
    theta=0 means 'up' (0,1). We use (sin, cos) so:
      theta=0 -> (0,1)
      theta=pi/2 -> (1,0)
    We fix denominator to n (requested) to avoid re-rotating when #chains changes.
    """
    theta = chain_id * 2.0 * np.pi / n_total_clusters
    return np.array([math.sin(theta), math.cos(theta)], dtype=float)


def generate_instance(
    params: GeneratorParams, n: int, seed: Optional[int]
) -> Dict[str, Any]:
    """
    Output JSON:
      - locations: [{x,y,type,chain_id,cluster_id,chain_order}, ...]
      - distance_matrix: NxN ints
      - meta: chain_sizes, num_chains, n
    Types:
      origin, center (origin cluster points), rural-origin (cluster centers), rural (cluster points)
    """
    # ---- validate ----
    if n <= 0:
        raise ValueError("n must be >= 1 (total number of rural clusters).")
    if params.m1 < 0:
        raise ValueError("m1 must be >= 0.")
    if params.rmin < 0 or params.rmax <= 0 or params.rmin > params.rmax:
        raise ValueError("Require 0 <= rmin <= rmax and rmax > 0.")
    if params.m2min <= 0 or params.m2max < params.m2min:
        raise ValueError("Require m2min >= 1 and m2max >= m2min.")
    if params.n_cluster_max <= 0:
        raise ValueError("n_cluster_max must be >= 1.")

    rng = np.random.default_rng(seed)
    origin = np.array([0.0, 0.0], dtype=float)

    locations: List[Dict[str, Any]] = []

    # Origin
    locations.append(
        {
            "id": 0,
            "x": 0.0,
            "y": 0.0,
            "type": "origin",
            "chain_id": -1,
            "cluster_id": -1,
            "chain_order": -1,
        }
    )

    # Origin cluster points
    for p in sample_points_in_disk(rng, params.r1, origin, params.m1):
        locations.append(
            {
                "id": len(locations),
                "x": float(p[0]),
                "y": float(p[1]),
                "type": "center",
                "chain_id": -1,
                "cluster_id": -1,
                "chain_order": -1,
            }
        )

    # --- rural chains built incrementally ---
    # For each chain, maintain:
    #   - chain_id
    #   - current cluster count
    #   - last center position (for extending)
    chain_sizes: List[int] = []
    chain_last_center: List[np.ndarray] = []

    rural_centers: List[np.ndarray] = []  # indexed by cluster_id (0..n-1)
    rural_center_chain: List[int] = []  # chain_id per cluster_id
    rural_center_order: List[int] = []  # order within chain per cluster_id
    rural_points_by_cluster: List[np.ndarray] = []

    def add_new_chain_with_one_cluster(cluster_id: int) -> None:
        ch = len(chain_sizes)
        direction = chain_direction(ch, n_total_clusters=n)
        r0 = float(rng.uniform(params.rmin, params.rmax))
        cpos = origin + r0 * direction

        chain_sizes.append(1)
        chain_last_center.append(cpos.copy())

        rural_centers.append(cpos.copy())
        rural_center_chain.append(ch)
        rural_center_order.append(0)

        m2 = int(rng.integers(params.m2min, params.m2max + 1))
        rural_points_by_cluster.append(sample_points_in_disk(rng, params.r2, cpos, m2))

    def add_cluster_to_existing_chain(chain_id: int, cluster_id: int) -> None:
        direction = chain_direction(chain_id, n_total_clusters=n)
        r_step = float(rng.uniform(params.rmin, params.rmax))
        cpos = chain_last_center[chain_id] + r_step * direction

        order = chain_sizes[chain_id]
        chain_sizes[chain_id] += 1
        chain_last_center[chain_id] = cpos.copy()

        rural_centers.append(cpos.copy())
        rural_center_chain.append(chain_id)
        rural_center_order.append(order)

        m2 = int(rng.integers(params.m2min, params.m2max + 1))
        rural_points_by_cluster.append(sample_points_in_disk(rng, params.r2, cpos, m2))

    # Step 1: start with one chain and one cluster
    add_new_chain_with_one_cluster(cluster_id=0)

    # Step 2: repeat until total clusters == n
    for cid in range(1, n):
        eligible_chains = [
            ch for ch, sz in enumerate(chain_sizes) if sz < params.n_cluster_max
        ]
        # Candidates: eligible chains + "new chain"
        # If no eligible chains, must create a new chain.
        if not eligible_chains:
            choice_new = True
            chosen_chain = None
        else:
            # uniform among (eligible chains + new)
            # represent "new" as -1
            candidates = eligible_chains + [-1]
            pick = int(rng.integers(0, len(candidates)))
            chosen = candidates[pick]
            if chosen == -1:
                choice_new = True
                chosen_chain = None
            else:
                choice_new = False
                chosen_chain = chosen

        if choice_new:
            add_new_chain_with_one_cluster(cluster_id=cid)
        else:
            add_cluster_to_existing_chain(chosen_chain, cluster_id=cid)

    # Append rural locations (centers + points)
    for cluster_id, (cpos, ch, ord_, pts) in enumerate(
        zip(
            rural_centers,
            rural_center_chain,
            rural_center_order,
            rural_points_by_cluster,
        )
    ):
        locations.append(
            {
                "id": len(locations),
                "x": float(cpos[0]),
                "y": float(cpos[1]),
                "type": "rural-origin",
                "chain_id": int(ch),
                "cluster_id": int(cluster_id),
                "chain_order": int(ord_),
            }
        )
        for p in pts:
            locations.append(
                {
                    "id": len(locations),
                    "x": float(p[0]),
                    "y": float(p[1]),
                    "type": "rural",
                    "chain_id": int(ch),
                    "cluster_id": int(cluster_id),
                    "chain_order": int(ord_),
                }
            )

    instance = {
        "locations": locations,
        "meta": {
            "n": n,
            "num_chains": len(chain_sizes),
            "chain_sizes": chain_sizes,
            "params": {
                "r1": params.r1,
                "m1": params.m1,
                "rmin": params.rmin,
                "rmax": params.rmax,
                "r2": params.r2,
                "m2min": params.m2min,
                "m2max": params.m2max,
                "n_cluster_max": params.n_cluster_max,
            },
            "seed": seed,
        },
    }

    instance["distance_matrix"] = build_distance_matrix(instance)
    return instance


def build_distance_matrix(instance: Dict[str, Any]) -> List[List[int]]:
    locs = instance["locations"]
    N = len(locs)

    pts = np.array([[loc["x"], loc["y"]] for loc in locs], dtype=float)
    chain = np.array([int(loc.get("chain_id", -1)) for loc in locs], dtype=int)
    cluster = np.array([int(loc.get("cluster_id", -1)) for loc in locs], dtype=int)

    origin = np.array([0.0, 0.0], dtype=float)

    # cluster center lookup (cluster_id -> point)
    cluster_center: Dict[int, np.ndarray] = {}
    for loc in locs:
        if loc["type"] == "rural-origin":
            cid = int(loc["cluster_id"])
            cluster_center[cid] = np.array([loc["x"], loc["y"]], dtype=float)

    # Precompute ceil distance to origin for all points (used only for origin-side points now)
    ceil_to_origin = np.ceil(np.linalg.norm(pts - origin, axis=1)).astype(int)

    # Precompute ceil distance from each rural cluster center to origin
    ceil_center_to_origin: Dict[int, int] = {}
    for cid, cpt in cluster_center.items():
        ceil_center_to_origin[cid] = int(
            math.ceil(math.dist((float(cpt[0]), float(cpt[1])), (0.0, 0.0)))
        )

    dmat = [[0] * N for _ in range(N)]
    for i in range(N):
        for j in range(i + 1, N):
            # origin-side (origin+center) among themselves: Euclidean
            if chain[i] == -1 and chain[j] == -1:
                dij = ceil_euclid(pts[i], pts[j])

            # same rural cluster: Euclidean
            elif cluster[i] >= 0 and cluster[i] == cluster[j]:
                dij = ceil_euclid(pts[i], pts[j])

            # both are rural-side points (each belongs to some rural cluster)
            elif cluster[i] >= 0 and cluster[j] >= 0:
                ci = int(cluster[i])
                cj = int(cluster[j])
                cpi = cluster_center[ci]
                cpj = cluster_center[cj]

                if chain[i] == chain[j]:
                    # same chain but different clusters: via the two cluster centers
                    dij = (
                        ceil_euclid(pts[i], cpi)
                        + ceil_euclid(cpi, cpj)
                        + ceil_euclid(cpj, pts[j])
                    )
                else:
                    # different chains: via cluster centers and origin
                    dij = (
                        ceil_euclid(pts[i], cpi)
                        + ceil_center_to_origin[ci]
                        + ceil_center_to_origin[cj]
                        + ceil_euclid(cpj, pts[j])
                    )

            # mixed (origin-side vs rural-side):
            # enforce rural access via its cluster center + origin
            else:
                # ensure i is rural, j is origin-side (swap if needed)
                ii, jj = i, j
                if cluster[ii] < 0 and cluster[jj] >= 0:
                    ii, jj = jj, ii

                # now: cluster[ii] >= 0 (rural), cluster[jj] < 0 (origin-side)
                ci = int(cluster[ii])
                cpi = cluster_center[ci]

                dij = (
                    ceil_euclid(pts[ii], cpi)  # rural point -> its cluster center
                    + ceil_center_to_origin[ci]  # center -> origin
                    + ceil_to_origin[jj]  # origin -> origin-side point
                )

            dmat[i][j] = int(dij)
            dmat[j][i] = int(dij)

    return dmat


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic 2D instances (JSON + distance matrix)"
    )

    # Defaults as requested
    parser.add_argument("--r1", type=float, default=60)
    parser.add_argument("--m1", type=int, default=4)
    parser.add_argument("--rmin", type=float, default=120)
    parser.add_argument("--rmax", type=float, default=240)
    parser.add_argument("--r2", type=float, default=60)
    parser.add_argument("--m2min", type=int, default=5)
    parser.add_argument("--m2max", type=int, default=15)

    parser.add_argument(
        "--n-cluster-max",
        type=int,
        default=3,
        help="max rural clusters per line (chain)",
    )

    parser.add_argument("--n-values", type=int, nargs="+", default=[4, 8, 12, 16])
    parser.add_argument("--num-instances-per-n", type=int, default=5)

    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--out-dir", type=str, default=".")
    parser.add_argument("--prefix", type=str, default="instance")

    args = parser.parse_args()

    params = GeneratorParams(
        r1=args.r1,
        m1=args.m1,
        rmin=args.rmin,
        rmax=args.rmax,
        r2=args.r2,
        m2min=args.m2min,
        m2max=args.m2max,
        n_cluster_max=args.n_cluster_max,
    )

    ss = np.random.SeedSequence(args.base_seed)
    child_seeds = ss.spawn(len(args.n_values) * args.num_instances_per_n)

    t = 0
    for n in args.n_values:
        for k in range(args.num_instances_per_n):
            seed_int = int(child_seeds[t].generate_state(1, dtype=np.uint64)[0])
            t += 1

            inst = generate_instance(params, n=n, seed=seed_int)

            path = f"{args.out_dir.rstrip('/')}/{args.prefix}_n{n}_{k}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(inst, f, ensure_ascii=False, indent=2)

            print(f"saved: {path}")


if __name__ == "__main__":
    main()
