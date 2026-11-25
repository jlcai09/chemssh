from __future__ import annotations

import threading
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from ase.data import covalent_radii
from ase.neighborlist import primitive_neighbor_list
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from backend.app.models.structure import AtomDisplayModeStr, DynamicDisplayRule

DEFAULT_COVALENT_RADIUS = 0.78
MIN_BOND_DISTANCE = 0.4  # d^2 >= 0.16, matches frontend isBonded()
MIN_BOND_CUTOFF = 0.45
BOND_CUTOFF_OFFSET = 0.18
MAX_FRAGMENT_CACHE_SIZE = 32

DISPLAY_MODE_CODES: dict[AtomDisplayModeStr, int] = {
    "stick": 0,
    "sphere": 1,
    "line": 2,
    "dim": 3,
    "hidden": 4,
}


@dataclass(frozen=True)
class FragmentGraph:
    n_atoms: int
    n_components: int
    component_ids: np.ndarray  # int32[n_atoms]
    component_atoms: tuple[tuple[int, ...], ...]
    component_formulas: tuple[str, ...]
    formula_to_components: dict[str, tuple[int, ...]]
    edge_i: np.ndarray  # int32[n_edges]
    edge_j: np.ndarray  # int32[n_edges]
    edge_shifts: np.ndarray  # int32[n_edges, 3]


_fragment_cache: OrderedDict[tuple[str, int, int, int, int, bool], FragmentGraph] = OrderedDict()
_fragment_cache_lock = threading.Lock()


def _atom_radii(numbers: np.ndarray) -> np.ndarray:
    radii = np.full(len(numbers), DEFAULT_COVALENT_RADIUS, dtype=np.float64)
    max_num = len(covalent_radii) - 1
    for idx, num in enumerate(numbers):
        n = int(num)
        if 0 < n <= max_num:
            r = float(covalent_radii[n])
            if np.isfinite(r) and r > 0:
                radii[idx] = r
    return radii


def _has_valid_pbc_cell(cell: np.ndarray | None, pbc: Sequence[bool] | None) -> bool:
    if cell is None or pbc is None:
        return False
    arr = np.asarray(cell, dtype=np.float64)
    if arr.shape != (3, 3):
        return False
    if not any(bool(flag) for flag in pbc):
        return False
    return abs(float(np.linalg.det(arr))) > 1e-8


def hill_formula(symbols: Sequence[str], indices: Sequence[int]) -> str:
    counts = Counter(symbols[i] for i in indices)
    if not counts:
        return ""

    def fmt(sym: str, cnt: int) -> str:
        return sym if cnt == 1 else f"{sym}{cnt}"

    parts: list[str] = []
    if "C" in counts:
        parts.append(fmt("C", counts.pop("C")))
        if "H" in counts:
            parts.append(fmt("H", counts.pop("H")))
    for sym in sorted(counts.keys()):
        parts.append(fmt(sym, counts[sym]))
    return "".join(parts)


def compute_fragment_graph(
    positions: np.ndarray,
    numbers: np.ndarray,
    symbols: Sequence[str],
    cell: np.ndarray | None,
    pbc: Sequence[bool] | None,
    bond_scale: float = 1.25,
    use_pbc: bool = True,
) -> FragmentGraph:
    pos = np.asarray(positions, dtype=np.float64)
    n_atoms = int(pos.shape[0])
    if n_atoms == 0:
        return FragmentGraph(
            n_atoms=0,
            n_components=0,
            component_ids=np.empty(0, dtype=np.int32),
            component_atoms=(),
            component_formulas=(),
            formula_to_components={},
            edge_i=np.empty(0, dtype=np.int32),
            edge_j=np.empty(0, dtype=np.int32),
            edge_shifts=np.empty((0, 3), dtype=np.int32),
        )

    radii = _atom_radii(numbers)
    pbc_active = use_pbc and _has_valid_pbc_cell(cell, pbc)

    if n_atoms == 1:
        edge_i = np.empty(0, dtype=np.int32)
        edge_j = np.empty(0, dtype=np.int32)
        edge_shifts = np.empty((0, 3), dtype=np.int32)
    elif pbc_active:
        cell_arr = np.asarray(cell, dtype=np.float64)
        pbc_arr = np.asarray([bool(x) for x in pbc], dtype=bool)  # type: ignore[union-attr]
        # primitive_neighbor_list uses cutoff[i] + cutoff[j] for pair (i, j)
        atom_cutoffs = np.maximum(MIN_BOND_CUTOFF * 0.5, radii * bond_scale + BOND_CUTOFF_OFFSET * 0.5)
        raw_i, raw_j, raw_d, raw_s = primitive_neighbor_list(
            "ijdS",
            pbc_arr,
            cell_arr,
            pos,
            cutoff=atom_cutoffs,
            self_interaction=False,
        )
        if len(raw_i) > 0:
            pair_cutoffs = np.maximum(MIN_BOND_CUTOFF, (radii[raw_i] + radii[raw_j]) * bond_scale + BOND_CUTOFF_OFFSET)
            mask = (raw_d >= MIN_BOND_DISTANCE) & (raw_d <= pair_cutoffs)
            edge_i = raw_i[mask].astype(np.int32, copy=False)
            edge_j = raw_j[mask].astype(np.int32, copy=False)
            edge_shifts = raw_s[mask].astype(np.int32, copy=False)
        else:
            edge_i = np.empty(0, dtype=np.int32)
            edge_j = np.empty(0, dtype=np.int32)
            edge_shifts = np.empty((0, 3), dtype=np.int32)
    else:
        max_cutoff = float(np.max(radii) * 2.0 * bond_scale + BOND_CUTOFF_OFFSET)
        max_cutoff = max(MIN_BOND_CUTOFF, max_cutoff)
        tree = cKDTree(pos)
        pairs = tree.query_pairs(r=max_cutoff, output_type="ndarray")
        if len(pairs) > 0:
            pi = pairs[:, 0]
            pj = pairs[:, 1]
            diff = pos[pi] - pos[pj]
            dist_sq = np.einsum("ij,ij->i", diff, diff)
            pair_cutoffs = np.maximum(MIN_BOND_CUTOFF, (radii[pi] + radii[pj]) * bond_scale + BOND_CUTOFF_OFFSET)
            mask = (dist_sq >= MIN_BOND_DISTANCE * MIN_BOND_DISTANCE) & (dist_sq <= pair_cutoffs * pair_cutoffs)
            pi = pi[mask].astype(np.int32, copy=False)
            pj = pj[mask].astype(np.int32, copy=False)
            # Store symmetric directed edges for fast adjacency lookup
            edge_i = np.concatenate([pi, pj])
            edge_j = np.concatenate([pj, pi])
            edge_shifts = np.zeros((len(edge_i), 3), dtype=np.int32)
        else:
            edge_i = np.empty(0, dtype=np.int32)
            edge_j = np.empty(0, dtype=np.int32)
            edge_shifts = np.empty((0, 3), dtype=np.int32)

    if len(edge_i) > 0:
        data = np.ones(len(edge_i), dtype=np.int8)
        graph = csr_matrix((data, (edge_i, edge_j)), shape=(n_atoms, n_atoms))
        n_components, labels = connected_components(csgraph=graph, directed=False, return_labels=True)
        component_ids = labels.astype(np.int32, copy=False)
    else:
        n_components = n_atoms
        component_ids = np.arange(n_atoms, dtype=np.int32)

    # Group atoms by component id in O(N)
    buckets: list[list[int]] = [[] for _ in range(n_components)]
    for atom_idx, comp_id in enumerate(component_ids.tolist()):
        buckets[comp_id].append(atom_idx)

    component_atoms = tuple(tuple(b) for b in buckets)
    component_formulas = tuple(hill_formula(symbols, b) for b in component_atoms)

    formula_map: dict[str, list[int]] = {}
    for comp_id, formula in enumerate(component_formulas):
        formula_map.setdefault(formula, []).append(comp_id)
    formula_to_components = {k: tuple(v) for k, v in formula_map.items()}

    return FragmentGraph(
        n_atoms=n_atoms,
        n_components=n_components,
        component_ids=component_ids,
        component_atoms=component_atoms,
        component_formulas=component_formulas,
        formula_to_components=formula_to_components,
        edge_i=edge_i,
        edge_j=edge_j,
        edge_shifts=edge_shifts,
    )


def get_cached_fragment_graph(
    cache_key: tuple[str, int, int, int, int, bool],
    positions: np.ndarray,
    numbers: np.ndarray,
    symbols: Sequence[str],
    cell: np.ndarray | None,
    pbc: Sequence[bool] | None,
    bond_scale: float,
    use_pbc: bool,
) -> FragmentGraph:
    with _fragment_cache_lock:
        cached = _fragment_cache.get(cache_key)
        if cached is not None:
            _fragment_cache.move_to_end(cache_key)
            return cached

    graph = compute_fragment_graph(
        positions=positions,
        numbers=numbers,
        symbols=symbols,
        cell=cell,
        pbc=pbc,
        bond_scale=bond_scale,
        use_pbc=use_pbc,
    )

    with _fragment_cache_lock:
        _fragment_cache[cache_key] = graph
        _fragment_cache.move_to_end(cache_key)
        while len(_fragment_cache) > MAX_FRAGMENT_CACHE_SIZE:
            _fragment_cache.popitem(last=False)

    return graph


def select_connected_fragments(graph: FragmentGraph, seed_atoms: Sequence[int]) -> tuple[list[int], int, list[str]]:
    comp_ids: list[int] = []
    seen_comp: set[int] = set()
    for idx in seed_atoms:
        if 0 <= idx < graph.n_atoms:
            cid = int(graph.component_ids[idx])
            if cid not in seen_comp:
                seen_comp.add(cid)
                comp_ids.append(cid)

    if not comp_ids:
        return [], 0, []

    atoms: list[int] = []
    formulas: list[str] = []
    seen_formulas: set[str] = set()
    for cid in comp_ids:
        atoms.extend(graph.component_atoms[cid])
        formula = graph.component_formulas[cid]
        if formula and formula not in seen_formulas:
            seen_formulas.add(formula)
            formulas.append(formula)

    atoms.sort()
    return atoms, len(comp_ids), formulas


def select_same_formula_fragments(graph: FragmentGraph, seed_atoms: Sequence[int]) -> tuple[list[int], int, list[str]]:
    target_formulas: list[str] = []
    seen_formulas: set[str] = set()
    for idx in seed_atoms:
        if 0 <= idx < graph.n_atoms:
            cid = int(graph.component_ids[idx])
            formula = graph.component_formulas[cid]
            if formula and formula not in seen_formulas:
                seen_formulas.add(formula)
                target_formulas.append(formula)

    if not target_formulas:
        return [], 0, []

    atoms: list[int] = []
    fragment_count = 0
    for formula in target_formulas:
        matching_comps = graph.formula_to_components.get(formula, ())
        fragment_count += len(matching_comps)
        for cid in matching_comps:
            atoms.extend(graph.component_atoms[cid])

    atoms.sort()
    return atoms, fragment_count, target_formulas


def select_within_radius(
    graph: FragmentGraph,
    positions: np.ndarray,
    cell: np.ndarray | None,
    pbc: Sequence[bool] | None,
    seed_atoms: Sequence[int],
    radius: float,
    *,
    use_pbc: bool = True,
    expand_fragments: bool = True,
) -> tuple[list[int], int, list[str]]:
    pos = np.asarray(positions, dtype=np.float64)
    n_atoms = int(pos.shape[0])
    valid_seeds = sorted({int(i) for i in seed_atoms if 0 <= int(i) < n_atoms})
    if not valid_seeds or radius <= 0:
        return [], 0, []

    pbc_active = use_pbc and _has_valid_pbc_cell(cell, pbc)
    hit_atoms: set[int] = set(valid_seeds)

    if pbc_active:
        cell_arr = np.asarray(cell, dtype=np.float64)
        pbc_arr = np.asarray([bool(x) for x in pbc], dtype=bool)  # type: ignore[union-attr]
        raw_i, raw_j = primitive_neighbor_list(
            "ij",
            pbc_arr,
            cell_arr,
            pos,
            cutoff=float(radius),
            self_interaction=False,
        )
        if len(raw_i) > 0:
            seed_mask = np.isin(raw_i, valid_seeds)
            hit_atoms.update(int(x) for x in raw_j[seed_mask].tolist())
    else:
        tree = cKDTree(pos)
        seed_tree = cKDTree(pos[valid_seeds])
        neighbors = seed_tree.query_ball_tree(tree, r=float(radius))
        for group in neighbors:
            hit_atoms.update(group)

    if expand_fragments:
        return select_connected_fragments(graph, sorted(hit_atoms))

    sorted_atoms = sorted(hit_atoms)
    comp_ids = {int(graph.component_ids[i]) for i in sorted_atoms}
    formulas = sorted({graph.component_formulas[cid] for cid in comp_ids if graph.component_formulas[cid]})
    return sorted_atoms, len(comp_ids), formulas


def compute_whole_molecule_wrapped_positions(
    graph: FragmentGraph,
    positions: np.ndarray,
    cell: np.ndarray | None,
    pbc: Sequence[bool] | None,
) -> list[list[float]]:
    pos = np.asarray(positions, dtype=np.float64)
    n_atoms = int(pos.shape[0])
    if n_atoms == 0:
        return []
    if not _has_valid_pbc_cell(cell, pbc):
        return pos.tolist()

    cell_arr = np.asarray(cell, dtype=np.float64)
    inv_cell = np.linalg.inv(cell_arr)
    pbc_arr = np.asarray([bool(x) for x in pbc], dtype=bool)  # type: ignore[union-attr]

    # Build adjacency list with PBC integer shift vectors S_ij
    # In primitive_neighbor_list: r_j + S_ij @ cell - r_i = D_ij
    adj: list[list[tuple[int, np.ndarray]]] = [[] for _ in range(n_atoms)]
    for i_idx, j_idx, shift in zip(graph.edge_i.tolist(), graph.edge_j.tolist(), graph.edge_shifts):
        adj[i_idx].append((j_idx, shift))

    unwrapped = pos.copy()
    visited = np.zeros(n_atoms, dtype=bool)

    for comp_atoms in graph.component_atoms:
        if not comp_atoms:
            continue
        root = comp_atoms[0]
        visited[root] = True
        atom_shifts: dict[int, np.ndarray] = {root: np.zeros(3, dtype=np.int32)}
        queue: deque[int] = deque([root])

        while queue:
            u = queue.popleft()
            u_shift = atom_shifts[u]
            for v, edge_shift in adj[u]:
                if not visited[v]:
                    visited[v] = True
                    v_shift = u_shift + edge_shift
                    atom_shifts[v] = v_shift
                    unwrapped[v] = pos[v] + v_shift @ cell_arr
                    queue.append(v)

        # Wrap the whole component by its geometric center fractional coordinates
        comp_idx = np.asarray(comp_atoms, dtype=np.int32)
        com = unwrapped[comp_idx].mean(axis=0)
        frac_com = com @ inv_cell
        cell_shift = np.zeros(3, dtype=np.float64)
        for axis in range(3):
            if pbc_arr[axis]:
                cell_shift[axis] = -np.floor(frac_com[axis])
        if np.any(cell_shift != 0):
            unwrapped[comp_idx] += cell_shift @ cell_arr

    return np.round(unwrapped, 6).tolist()


def _expand_mask_to_fragments(graph: FragmentGraph, mask: np.ndarray) -> np.ndarray:
    if not np.any(mask):
        return mask
    hit_comps = np.unique(graph.component_ids[mask])
    return np.isin(graph.component_ids, hit_comps)


def _compare_counts(values: np.ndarray, operator: str, target: int) -> np.ndarray:
    if operator == "eq":
        return values == target
    if operator == "ne":
        return values != target
    if operator == "lt":
        return values < target
    if operator == "le":
        return values <= target
    if operator == "gt":
        return values > target
    if operator == "ge":
        return values >= target
    return np.zeros(len(values), dtype=bool)


def evaluate_dynamic_display_rules(
    graph: FragmentGraph,
    positions: np.ndarray,
    symbols: Sequence[str],
    cell: np.ndarray | None,
    pbc: Sequence[bool] | None,
    fixed_indices: Sequence[int],
    rules: Sequence[DynamicDisplayRule],
    *,
    default_style: AtomDisplayModeStr = "stick",
    use_pbc: bool = True,
) -> tuple[list[int], dict[str, int], list[str]]:
    n_atoms = graph.n_atoms
    default_code = DISPLAY_MODE_CODES.get(default_style, 0)
    if n_atoms == 0:
        return [], {r.id: 0 for r in rules}, []

    modes = np.full(n_atoms, default_code, dtype=np.int32)
    rule_match_counts: dict[str, int] = {}

    # Lazy-computed arrays shared across rules
    coord_numbers: np.ndarray | None = None
    frac_positions: np.ndarray | None = None
    fixed_mask: np.ndarray | None = None
    pos = np.asarray(positions, dtype=np.float64)
    symbol_arr = np.asarray(symbols)

    for rule in rules:
        if not rule.enabled:
            rule_match_counts[rule.id] = 0
            continue

        mask = np.zeros(n_atoms, dtype=bool)
        style_code = DISPLAY_MODE_CODES.get(rule.style, default_code)

        if rule.type == "formula":
            targets = {f.strip() for f in rule.formulas if f and f.strip()}
            if targets:
                comp_ids: list[int] = []
                for f in targets:
                    comp_ids.extend(graph.formula_to_components.get(f, ()))
                if comp_ids:
                    mask = np.isin(graph.component_ids, np.asarray(comp_ids, dtype=np.int32))

        elif rule.type == "shell":
            seeds: list[int] = []
            if rule.anchor_type == "atoms":
                seeds = [idx for idx in rule.anchor_atoms if 0 <= idx < n_atoms]
            else:
                el_set = {e.strip() for e in rule.anchor_elements if e and e.strip()}
                if el_set:
                    seeds = [i for i, sym in enumerate(symbols) if sym in el_set]
            if seeds:
                hit_atoms, _, _ = select_within_radius(
                    graph=graph,
                    positions=pos,
                    cell=cell,
                    pbc=pbc,
                    seed_atoms=seeds,
                    radius=rule.radius,
                    use_pbc=use_pbc,
                    expand_fragments=rule.expand_fragments,
                )
                if hit_atoms:
                    mask[np.asarray(hit_atoms, dtype=np.int32)] = True
                if rule.outside:
                    mask = ~mask

        elif rule.type == "coordination":
            if coord_numbers is None:
                if len(graph.edge_i) > 0:
                    coord_numbers = np.bincount(graph.edge_i, minlength=n_atoms)
                else:
                    coord_numbers = np.zeros(n_atoms, dtype=np.int64)
            mask = _compare_counts(coord_numbers, rule.operator, rule.count)
            el_set = {e.strip() for e in rule.elements if e and e.strip()}
            if el_set:
                mask &= np.isin(symbol_arr, list(el_set))
            if rule.expand_fragments:
                mask = _expand_mask_to_fragments(graph, mask)

        elif rule.type == "slice":
            axis_idx = 0 if rule.axis == "x" else (1 if rule.axis == "y" else 2)
            coords = pos[:, axis_idx]
            if rule.fractional and _has_valid_pbc_cell(cell, (True, True, True)):
                if frac_positions is None:
                    frac_positions = pos @ np.linalg.inv(np.asarray(cell, dtype=np.float64))
                coords = frac_positions[:, axis_idx]
            in_range = np.ones(n_atoms, dtype=bool)
            if rule.min_val is not None:
                in_range &= coords >= rule.min_val
            if rule.max_val is not None:
                in_range &= coords <= rule.max_val
            if rule.expand_fragments:
                in_range = _expand_mask_to_fragments(graph, in_range)
            mask = ~in_range if rule.outside else in_range

        elif rule.type == "minority":
            matched_comps: list[int] = []
            for formula, comp_ids in graph.formula_to_components.items():
                atom_count = sum(len(graph.component_atoms[cid]) for cid in comp_ids)
                fraction = atom_count / n_atoms
                is_minority = fraction <= rule.max_fraction
                if (is_minority and not rule.invert) or ((not is_minority) and rule.invert):
                    matched_comps.extend(comp_ids)
            if matched_comps:
                mask = np.isin(graph.component_ids, np.asarray(matched_comps, dtype=np.int32))

        elif rule.type == "element_fixed":
            el_set = {e.strip() for e in rule.elements if e and e.strip()}
            if el_set:
                mask = np.isin(symbol_arr, list(el_set))
            elif rule.fixed_only:
                mask = np.ones(n_atoms, dtype=bool)
            if rule.fixed_only:
                if fixed_mask is None:
                    fixed_mask = np.zeros(n_atoms, dtype=bool)
                    for idx in fixed_indices:
                        if 0 <= idx < n_atoms:
                            fixed_mask[idx] = True
                mask &= fixed_mask

        matched_count = int(np.count_nonzero(mask))
        rule_match_counts[rule.id] = matched_count
        if matched_count > 0:
            modes[mask] = style_code

    available_formulas = sorted(
        graph.formula_to_components.keys(),
        key=lambda f: (-len(graph.formula_to_components[f]), f),
    )
    return modes.tolist(), rule_match_counts, available_formulas
