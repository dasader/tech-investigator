def _reconstruct_abstract(inv_idx: dict[str, list[int]] | None) -> str:
    if not inv_idx:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inv_idx.items():
        for idx in idxs:
            positions[idx] = word
    if not positions:
        return ""
    return " ".join(positions[i] for i in sorted(positions.keys()))
