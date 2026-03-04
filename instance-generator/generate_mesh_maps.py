#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import heapq
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np


@dataclass(frozen=True)
class Params:
    # origin cluster (cluster_id=0)
    r1: float
    m1: int

    # cluster growth: new center on circumference with radius r ~ U[rmin,rmax]
    rmin: float
    rmax: float
    origin_bound_factor: float  # constraint: ||center|| <= rmax * origin_bound_factor

    # points inside each non-origin cluster
    r2: float
    m2min: int
    m2max: int

    # placement retry
    max_tries_per_cluster: int


# ---------- sampling ----------
def sample_uniform_in_disk(
    rng: np.random.Generator, radius: float, center: np.ndarray
) -> np.ndarray:
    theta = rng.uniform(0.0, 2.0 * math.pi)
    rad = radius * math.sqrt(rng.uniform(0.0, 1.0))
    return center + np.array(
        [rad * math.cos(theta), rad * math.sin(theta)], dtype=float
    )


def sample_points_in_disk(
    rng: np.random.Generator, radius: float, center: np.ndarray, m: int
) -> np.ndarray:
    if m <= 0:
        return np.empty((0, 2), dtype=float)
    return np.vstack([sample_uniform_in_disk(rng, radius, center) for _ in range(m)])


def propose_on_circumference(
    rng: np.random.Generator, parent: np.ndarray, r: float
) -> np.ndarray:
    theta = rng.uniform(0.0, 2.0 * math.pi)
    return parent + np.array([r * math.cos(theta), r * math.sin(theta)], dtype=float)


def ceil_euclid(a: np.ndarray, b: np.ndarray) -> int:
    return int(
        math.ceil(math.dist((float(a[0]), float(a[1])), (float(b[0]), float(b[1]))))
    )


# ---------- KNN graph + shortest paths ----------
def center_knn_edges(
    centers: np.ndarray, k: int
) -> Tuple[List[Tuple[int, int, int]], List[List[Tuple[int, int]]]]:
    """
    returns:
      edges: list of (u,v,w) with u < v
      adj: adjacency list adj[u] = [(v,w), ...]
    w = ceil(euclid(center_u, center_v))
    """
    C = centers.shape[0]
    k = max(1, min(k, C - 1)) if C > 1 else 0

    edges_set: Dict[Tuple[int, int], int] = {}
    adj: List[List[Tuple[int, int]]] = [[] for _ in range(C)]
    if C <= 1:
        return [], adj

    d = np.sqrt(((centers[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2))
    for i in range(C):
        nn = np.argsort(d[i])[1 : k + 1]
        for j in nn:
            j = int(j)
            w = int(math.ceil(d[i, j]))
            a, b = (i, j) if i < j else (j, i)
            if (a, b) not in edges_set or w < edges_set[(a, b)]:
                edges_set[(a, b)] = w

    # build adj from edges_set
    for (u, v), w in edges_set.items():
        adj[u].append((v, w))
        adj[v].append((u, w))

    edges = [(u, v, w) for (u, v), w in sorted(edges_set.items())]
    return edges, adj


def is_connected(adj: List[List[Tuple[int, int]]]) -> bool:
    C = len(adj)
    if C == 0:
        return True
    seen = [False] * C
    stack = [0]
    seen[0] = True
    while stack:
        u = stack.pop()
        for v, _ in adj[u]:
            if not seen[v]:
                seen[v] = True
                stack.append(v)
    return all(seen)


def all_pairs_shortest_paths(adj: List[List[Tuple[int, int]]]) -> np.ndarray:
    C = len(adj)
    INF = 10**15
    distmat = np.full((C, C), INF, dtype=np.int64)
    for s in range(C):
        dist = [INF] * C
        dist[s] = 0
        pq = [(0, s)]
        while pq:
            du, u = heapq.heappop(pq)
            if du != dist[u]:
                continue
            for v, w in adj[u]:
                nd = du + w
                if nd < dist[v]:
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))
        distmat[s, :] = dist
    return distmat


# ---------- generation ----------
def generate_instance(
    params: Params,
    n_clusters: int,
    seed: int,
    knn_k: int,
    ensure_connected: bool,
) -> Dict[str, Any]:
    if n_clusters <= 0:
        raise ValueError("n_clusters must be >= 1 (includes origin cluster).")
    if params.rmin <= 0 or params.rmax <= 0 or params.rmin > params.rmax:
        raise ValueError("Require 0 < rmin <= rmax.")
    if params.origin_bound_factor <= 0:
        raise ValueError("origin_bound_factor must be > 0.")
    if params.m2min <= 0 or params.m2max < params.m2min:
        raise ValueError("Require m2min >= 1 and m2max >= m2min.")
    if params.max_tries_per_cluster <= 0:
        raise ValueError("max_tries_per_cluster must be >= 1.")

    rng = np.random.default_rng(seed)
    origin = np.array([0.0, 0.0], dtype=float)

    centers: List[np.ndarray] = [origin.copy()]  # cluster_id=0
    bound = params.rmax * params.origin_bound_factor

    # grow cluster centers
    while len(centers) < n_clusters:
        ok = False
        for _ in range(params.max_tries_per_cluster):
            parent_idx = int(rng.integers(0, len(centers)))
            parent = centers[parent_idx]
            r = float(rng.uniform(params.rmin, params.rmax))
            cand = propose_on_circumference(rng, parent, r)

            # not within rmin of ANY existing center
            min_dist = min(
                math.dist((float(cand[0]), float(cand[1])), (float(c[0]), float(c[1])))
                for c in centers
            )
            if min_dist < params.rmin - 1e-12:
                continue

            # bounded from origin
            if float(np.linalg.norm(cand)) > bound + 1e-12:
                continue

            centers.append(cand)
            ok = True
            break

        if not ok:
            raise RuntimeError(
                f"Failed to place cluster {len(centers)} after {params.max_tries_per_cluster} tries. "
                f"Relax constraints (increase origin_bound_factor, decrease rmin, etc.)."
            )

    centers_arr = np.vstack(centers)  # (C,2)
    C = centers_arr.shape[0]

    # build KNN graph on centers, possibly increase k to ensure connectivity
    k_used = max(1, min(knn_k, C - 1)) if C > 1 else 0
    edges, adj = center_knn_edges(centers_arr, k_used)
    if ensure_connected and C > 1:
        while not is_connected(adj) and k_used < C - 1:
            k_used += 1
            edges, adj = center_knn_edges(centers_arr, k_used)

    sp = all_pairs_shortest_paths(adj)  # (C,C) int64, INF for disconnected

    # build locations
    locations: List[Dict[str, Any]] = []
    # origin center location
    locations.append({"id": 0, "x": 0.0, "y": 0.0, "type": "origin", "cluster_id": 0})

    # origin cluster points
    for p in sample_points_in_disk(rng, params.r1, origin, params.m1):
        locations.append(
            {
                "id": len(locations),
                "x": float(p[0]),
                "y": float(p[1]),
                "type": "center",
                "cluster_id": 0,
            }
        )

    # other clusters
    for cid in range(1, C):
        c = centers_arr[cid]
        locations.append(
            {
                "id": len(locations),
                "x": float(c[0]),
                "y": float(c[1]),
                "type": "rural-origin",
                "cluster_id": cid,
            }
        )
        m2 = int(rng.integers(params.m2min, params.m2max + 1))
        pts = sample_points_in_disk(rng, params.r2, c, m2)
        for p in pts:
            locations.append(
                {
                    "id": len(locations),
                    "x": float(p[0]),
                    "y": float(p[1]),
                    "type": "rural",
                    "cluster_id": cid,
                }
            )

    # distance matrix using KNN shortest paths
    dmat = build_distance_matrix_knn(locations, centers_arr, sp)

    inst: Dict[str, Any] = {
        "locations": locations,
        "distance_matrix": dmat,
        "meta": {
            "seed": seed,
            "n_clusters": C,
            "centers": [
                {
                    "cluster_id": i,
                    "x": float(centers_arr[i, 0]),
                    "y": float(centers_arr[i, 1]),
                }
                for i in range(C)
            ],
            "knn": {
                "k_requested": knn_k,
                "k_used": k_used,
                "ensure_connected": bool(ensure_connected),
                # edges are exactly the graph used for shortest paths + viz
                "edges": [{"u": u, "v": v, "w": w} for (u, v, w) in edges],
            },
            "params": {
                "r1": params.r1,
                "m1": params.m1,
                "rmin": params.rmin,
                "rmax": params.rmax,
                "origin_bound_factor": params.origin_bound_factor,
                "r2": params.r2,
                "m2min": params.m2min,
                "m2max": params.m2max,
                "max_tries_per_cluster": params.max_tries_per_cluster,
            },
        },
    }
    return inst


def build_distance_matrix_knn(
    locations: List[Dict[str, Any]],
    centers_arr: np.ndarray,
    sp: np.ndarray,
) -> List[List[int]]:
    """
    - same cluster: ceil(Euclid)
    - different clusters: ceil(i->ci) + sp(ci,cj) + ceil(cj->j)
    sp is shortest path distance on KNN center graph (edge weights are ceil(center distances)).
    """
    N = len(locations)
    pts = np.array([[loc["x"], loc["y"]] for loc in locations], dtype=float)
    clus = np.array([int(loc["cluster_id"]) for loc in locations], dtype=int)

    # ceil distance point->its center
    pt2c = np.empty(N, dtype=np.int64)
    for i in range(N):
        ci = centers_arr[clus[i]]
        pt2c[i] = ceil_euclid(pts[i], ci)

    INF = 10**15
    dmat = [[0] * N for _ in range(N)]
    for i in range(N):
        for j in range(i + 1, N):
            if clus[i] == clus[j]:
                dij = ceil_euclid(pts[i], pts[j])
            else:
                ci = int(clus[i])
                cj = int(clus[j])
                spij = int(sp[ci, cj])
                if spij >= INF // 2:
                    # disconnected: fallback to direct center distance
                    spij = ceil_euclid(centers_arr[ci], centers_arr[cj])
                dij = int(pt2c[i] + spij + pt2c[j])

            dmat[i][j] = dij
            dmat[j][i] = dij
    return dmat


# ---------- CLI ----------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="Generate circumference-growth clusters + KNN shortest-path distances"
    )

    ap.add_argument("--r1", type=float, default=60)
    ap.add_argument("--m1", type=int, default=4)

    ap.add_argument("--rmin", type=float, default=120)
    ap.add_argument("--rmax", type=float, default=240)
    ap.add_argument("--origin-bound-factor", type=float, default=3)

    ap.add_argument("--r2", type=float, default=60)
    ap.add_argument("--m2min", type=int, default=5)
    ap.add_argument("--m2max", type=int, default=15)

    ap.add_argument("--max-tries-per-cluster", type=int, default=5000)

    ap.add_argument("--knn-k", type=int, default=2)
    ap.add_argument("--ensure-connected", action="store_true")

    ap.add_argument("--n-values", type=int, nargs="+", default=[4, 8, 12, 16])
    ap.add_argument("--num-instances-per-n", type=int, default=5)

    ap.add_argument("--base-seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default=".")
    ap.add_argument("--prefix", type=str, default="mesh")

    args = ap.parse_args()

    params = Params(
        r1=args.r1,
        m1=args.m1,
        rmin=args.rmin,
        rmax=args.rmax,
        origin_bound_factor=args.origin_bound_factor,
        r2=args.r2,
        m2min=args.m2min,
        m2max=args.m2max,
        max_tries_per_cluster=args.max_tries_per_cluster,
    )

    ss = np.random.SeedSequence(args.base_seed)
    child_seeds = ss.spawn(len(args.n_values) * args.num_instances_per_n)

    t = 0
    for n in args.n_values:
        for k in range(args.num_instances_per_n):
            seed_int = int(child_seeds[t].generate_state(1, dtype=np.uint64)[0])
            t += 1

            inst = generate_instance(
                params=params,
                n_clusters=n,
                seed=seed_int,
                knn_k=args.knn_k,
                ensure_connected=args.ensure_connected,
            )

            path = f"{args.out_dir.rstrip('/')}/{args.prefix}_n{n}_{k}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(inst, f, ensure_ascii=False, indent=2)
            print(f"saved: {path}")


if __name__ == "__main__":
    main()
