"""Instrumentation registry and reset helpers."""

import fnmatch
import logging
import time as _time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from peeka.core.instrumentation.target import (
    inspect_descriptor,
    read_target_binding,
    replace_function,
    restore_aliases_matching,
    restore_target_attribute_from_root,
)
from peeka.core.probes import ProbeContext

logger = logging.getLogger(__name__)


def wrapper_call_target(wrapper: Any) -> Any:
    """Return the callable a Peeka wrapper delegates to, or None.

    Peeka wrappers (watch/stack/trace/monitor) capture their target either in a
    closure cell named ``func``, on a factory object held in a ``self`` cell, or
    via a ``*wrapper_ref`` single-element list cell holding ``wrapper``.
    Only call this on wrappers known to be Peeka-owned.
    """
    closure = getattr(wrapper, "__closure__", None)
    code = getattr(wrapper, "__code__", None)
    if closure is None or code is None:
        return None
    factory_func = None
    ref_func = None
    for name, cell in zip(code.co_freevars, closure):
        try:
            cell_value = cell.cell_contents
        except ValueError:
            continue
        if name == "func":
            return cell_value
        if name == "self":
            factory_func = getattr(cell_value, "func", None)
        elif (
            name.endswith("wrapper_ref")
            and isinstance(cell_value, list)
            and len(cell_value) == 1
            and cell_value[0] is wrapper
        ):
            ref_func = getattr(wrapper, "__wrapped__", None)
    if factory_func is not None:
        return factory_func
    return ref_func


def retarget_wrapper_call(wrapper: Any, old_target: Any, new_target: Any) -> None:
    """Make a live Peeka wrapper call new_target where it called old_target.

    Updates both the real call path (closure cell / factory attribute) and
    ``__wrapped__`` so introspection and execution stay consistent.
    """
    if getattr(wrapper, "__wrapped__", None) is old_target:
        try:
            wrapper.__wrapped__ = new_target
        except Exception:
            pass

    closure = getattr(wrapper, "__closure__", None)
    code = getattr(wrapper, "__code__", None)
    if closure is None or code is None:
        return

    for name, cell in zip(code.co_freevars, closure):
        try:
            cell_value = cell.cell_contents
        except ValueError:
            continue

        if name == "func" and cell_value is old_target:
            try:
                cell.cell_contents = new_target
            except Exception:
                pass
        elif name == "self":
            factory_func = getattr(cell_value, "func", None)
            if factory_func is old_target:
                try:
                    cell_value.func = new_target
                except Exception:
                    pass


def get_slot_chains(owner: Any) -> Dict[Tuple[int, str], Dict[str, Any]]:
    """Return the shared slot-chain map stored on ``owner``."""
    return owner.__dict__.setdefault("_slot_chains", {})


def _merge_aliases(
    target_entry: Dict[str, Any], extra_aliases: List[Dict[str, Any]]
) -> None:
    """Merge alias bindings into ``target_entry`` without duplicating slots."""
    existing = target_entry.setdefault("aliases", [])
    seen = {(id(alias["parent"]), alias["attr_name"]) for alias in existing}
    for alias in extra_aliases:
        key = (id(alias["parent"]), alias["attr_name"])
        if key not in seen:
            seen.add(key)
            existing.append(alias)


def prepare_slot_chain(
    owner: Any, parent_obj: Any, attr_name: str, current_func: Any
) -> Dict[str, Any]:
    """Return the live chain for ``(parent_obj, attr_name)`` or start a new one."""
    slot_key = (id(parent_obj), str(attr_name))
    chains = get_slot_chains(owner)
    existing = chains.get(slot_key)
    if (
        existing is not None
        and existing["entries"]
        and existing["entries"][-1]["wrapper"] is current_func
    ):
        return existing

    descriptor_kind, raw_descriptor, defined_in_dict = inspect_descriptor(
        parent_obj, attr_name
    )
    return {
        "slot_key": slot_key,
        "parent": parent_obj,
        "attr_name": attr_name,
        "root_original": current_func,
        "root_descriptor_kind": descriptor_kind,
        "root_raw_descriptor": raw_descriptor,
        "root_defined_in_dict": defined_in_dict,
        "entries": [],
    }


def commit_slot_chain_entry(
    owner: Any,
    chain: Dict[str, Any],
    probe_id: str,
    probe_owner: str,
    wrapper: Any,
    aliases: List[Dict[str, Any]],
) -> None:
    """Append a newly installed wrapper entry to ``chain``."""
    get_slot_chains(owner)[chain["slot_key"]] = chain
    chain["entries"].append(
        {
            "probe_id": probe_id,
            "owner": probe_owner,
            "wrapper": wrapper,
            "aliases": list(aliases),
        }
    )


def remove_chain_entry(
    owner: Any,
    chain: Dict[str, Any],
    probe_id: str,
    on_retarget: Optional[Callable[[Dict[str, Any], Any, Any], None]] = None,
) -> Tuple[Any, Any]:
    """Remove ``probe_id`` from ``chain`` and restore canonical/alias bindings.

    Canonical attribute restoration runs before mutating ``chain["entries"]`` so
    any failure leaves the chain intact for a subsequent retry.
    """
    entries: List[Dict[str, Any]] = chain["entries"]
    idx = next(
        (i for i, entry in enumerate(entries) if entry["probe_id"] == probe_id),
        None,
    )
    if idx is None:
        raise ValueError(f"Probe not found in wrapper chain: {probe_id}")

    entry = entries[idx]
    removed_wrapper = entry["wrapper"]
    below = entries[idx - 1]["wrapper"] if idx > 0 else chain["root_original"]

    if idx < len(entries) - 1:
        above_entry = entries[idx + 1]
        retarget_wrapper_call(above_entry["wrapper"], removed_wrapper, below)
        if on_retarget is not None:
            on_retarget(above_entry, removed_wrapper, below)
        top_wrapper = entries[-1]["wrapper"]
        restore_aliases_matching(entry["aliases"], (removed_wrapper,), top_wrapper)
        _merge_aliases(entries[-1], entry["aliases"])
        entries.pop(idx)
        return removed_wrapper, below

    if len(entries) > 1:
        current_raw = read_target_binding(chain["parent"], chain["attr_name"])
        if current_raw is removed_wrapper:
            replace_function(
                chain["parent"],
                chain["attr_name"],
                below,
                descriptor_kind=chain["root_descriptor_kind"],
            )
        restore_aliases_matching(entry["aliases"], (removed_wrapper,), below)
        _merge_aliases(entries[idx - 1], entry["aliases"])
        entries.pop(idx)
        return removed_wrapper, below

    current_raw = read_target_binding(chain["parent"], chain["attr_name"])
    if current_raw is removed_wrapper:
        restore_target_attribute_from_root(
            chain["parent"],
            chain["attr_name"],
            chain["root_original"],
            chain["root_descriptor_kind"],
            chain["root_raw_descriptor"],
            chain["root_defined_in_dict"],
        )
    restore_aliases_matching(
        entry["aliases"], (removed_wrapper,), chain["root_original"]
    )
    entries.pop(idx)
    chains = get_slot_chains(owner)
    if chains.get(chain["slot_key"]) is chain:
        chains.pop(chain["slot_key"], None)
    return removed_wrapper, chain["root_original"]


class InjectorRegistryMixin:
    agent: Any = None
    instrumented: Dict[str, Dict[str, Any]] = {}
    _lock: Any = None

    if TYPE_CHECKING:
        def _replace_function(
            self, parent: Any, attr_name: str, new_func: Callable[..., Any],
            descriptor_kind: Optional[str] = None,
        ) -> None: ...

        def _restore_target_attribute(self, info: Dict[str, Any]) -> None: ...

        def _restore_aliases(self, info: Dict[str, Any]) -> None: ...

    def _prepare_slot_chain(
        self, parent_obj: Any, attr_name: str, current_func: Any
    ) -> Dict[str, Any]:
        return prepare_slot_chain(self, parent_obj, attr_name, current_func)

    def _commit_slot_chain_entry(
        self,
        chain: Dict[str, Any],
        probe_id: str,
        probe_owner: str,
        wrapper: Any,
        aliases: List[Dict[str, Any]],
    ) -> None:
        commit_slot_chain_entry(self, chain, probe_id, probe_owner, wrapper, aliases)

    def _retarget_injector_metadata(
        self, above_entry: Dict[str, Any], old_wrapper: Any, new_target: Any
    ) -> None:
        if above_entry.get("owner") != "injector":
            return
        above_info = self.instrumented.get(above_entry["probe_id"])
        if above_info is None:
            return
        for key in ("original", "previous_wrapper"):
            if above_info.get(key) is old_wrapper:
                above_info[key] = new_target

    def uninject(self, watch_id: str) -> Dict[str, Any]:
        """
        Remove observation and restore original function.

        Args:
            watch_id: The watch ID returned by inject()

        Returns:
            Dict with observation statistics

        Raises:
            ValueError: If watch_id not found
        """
        with self._lock:
            if watch_id not in self.instrumented:
                raise ValueError(f"Watch not found: {watch_id}")

            info = self.instrumented[watch_id]
            chain = info.get("_chain")
            if chain is not None:
                removed_wrapper, bypass_target = remove_chain_entry(
                    self,
                    chain,
                    watch_id,
                    on_retarget=self._retarget_injector_metadata,
                )
                self.instrumented.pop(watch_id, None)
            else:
                if "wrapper_group_key" in info:
                    self._restore_wrapper_stack(info, exclude_watch_id=watch_id)
                else:
                    current_raw = read_target_binding(
                        info["parent"], info["attr_name"]
                    )
                    if current_raw is info.get("wrapper"):
                        self._restore_target_attribute(info)
                    self._restore_aliases(info)

                self.instrumented.pop(watch_id, None)
                removed_wrapper = info.get("wrapper")
                bypass_target = self._bypass_removed_wrapper(info)

        self._notify_wrapper_removed(removed_wrapper, bypass_target)
        return {
            "watch_id": watch_id,
            "pattern": info["pattern"],
            "count": info["count"],
        }

    def uninject_all(self) -> int:
        """
        Remove all observations and restore all original functions.

        Returns:
            Number of observations removed

        Raises:
            Exception: If restoring one or more canonical attributes fails
                (failed entries remain tracked in ``self.instrumented``).
        """
        removed_notifications: List[Tuple[Any, Any]] = []
        errors: List[Exception] = []
        removed_count = 0

        with self._lock:
            chain_groups: Dict[int, Tuple[Dict[str, Any], List[Tuple[str, Dict[str, Any]]]]] = {}
            legacy_items: List[Tuple[str, Dict[str, Any]]] = []

            for watch_id, info in list(self.instrumented.items()):
                chain = info.get("_chain")
                if chain is not None:
                    cid = id(chain)
                    if cid not in chain_groups:
                        chain_groups[cid] = (chain, [])
                    chain_groups[cid][1].append((watch_id, info))
                else:
                    legacy_items.append((watch_id, info))

            for chain, group_items in chain_groups.values():
                injector_ids = {wid for wid, _ in group_items}
                entries = chain["entries"]
                remaining_entries = [
                    e for e in entries if e["probe_id"] not in injector_ids
                ]
                removed_entries = [
                    e for e in entries if e["probe_id"] in injector_ids
                ]
                removed_wrappers = [e["wrapper"] for e in removed_entries]
                all_chain_wrappers = [e["wrapper"] for e in entries]
                all_removed_aliases = [
                    a for e in removed_entries for a in e.get("aliases", [])
                ]

                if not remaining_entries:
                    current_raw = read_target_binding(
                        chain["parent"], chain["attr_name"]
                    )
                    if any(current_raw is w for w in all_chain_wrappers):
                        try:
                            restore_target_attribute_from_root(
                                chain["parent"],
                                chain["attr_name"],
                                chain["root_original"],
                                chain["root_descriptor_kind"],
                                chain["root_raw_descriptor"],
                                chain["root_defined_in_dict"],
                            )
                        except Exception as exc:
                            errors.append(exc)
                            continue
                    restore_aliases_matching(
                        all_removed_aliases,
                        all_chain_wrappers,
                        chain["root_original"],
                    )
                    chain["entries"] = []
                    chains = get_slot_chains(self)
                    if chains.get(chain["slot_key"]) is chain:
                        chains.pop(chain["slot_key"], None)
                    for wid, info in group_items:
                        self.instrumented.pop(wid, None)
                        removed_count += 1
                        removed_notifications.append(
                            (info.get("wrapper"), chain["root_original"])
                        )
                    continue

                old_top = entries[-1]["wrapper"]
                new_top = remaining_entries[-1]["wrapper"]
                if new_top is not old_top:
                    current_raw = read_target_binding(
                        chain["parent"], chain["attr_name"]
                    )
                    if any(current_raw is w for w in removed_wrappers):
                        try:
                            replace_function(
                                chain["parent"],
                                chain["attr_name"],
                                new_top,
                                descriptor_kind=chain["root_descriptor_kind"],
                            )
                        except Exception as exc:
                            errors.append(exc)
                            continue
                    restore_aliases_matching(
                        all_removed_aliases, removed_wrappers, new_top
                    )
                _merge_aliases(remaining_entries[-1], all_removed_aliases)

                for rem_idx, rem_entry in enumerate(remaining_entries):
                    desired_target = (
                        remaining_entries[rem_idx - 1]["wrapper"]
                        if rem_idx > 0
                        else chain["root_original"]
                    )
                    curr_target = wrapper_call_target(rem_entry["wrapper"])
                    if curr_target is not None and curr_target is not desired_target:
                        retarget_wrapper_call(
                            rem_entry["wrapper"], curr_target, desired_target
                        )

                chain["entries"] = remaining_entries
                for wid, info in group_items:
                    idx_in_old = next(
                        (i for i, e in enumerate(entries) if e["probe_id"] == wid),
                        -1,
                    )
                    bypass = (
                        entries[idx_in_old - 1]["wrapper"]
                        if idx_in_old > 0
                        else chain["root_original"]
                    )
                    self.instrumented.pop(wid, None)
                    removed_count += 1
                    removed_notifications.append((info.get("wrapper"), bypass))

            legacy_groups: Dict[Any, List[Tuple[str, Dict[str, Any]]]] = {}
            legacy_singles: List[Tuple[str, Dict[str, Any]]] = []
            for wid, info in legacy_items:
                if "wrapper_group_key" in info:
                    legacy_groups.setdefault(info["wrapper_group_key"], []).append(
                        (wid, info)
                    )
                else:
                    legacy_singles.append((wid, info))

            for group_items in legacy_groups.values():
                first_info = group_items[0][1]
                group_wrappers = [info.get("wrapper") for _, info in group_items]
                root_original = first_info.get("root_original", first_info["original"])
                current_raw = read_target_binding(
                    first_info["parent"], first_info["attr_name"]
                )
                if any(current_raw is w for w in group_wrappers):
                    try:
                        self._restore_target_attribute(
                            dict(first_info, original=root_original)
                        )
                    except Exception as exc:
                        errors.append(exc)
                        continue
                group_aliases = [
                    a for _, info in group_items for a in info.get("aliases", [])
                ]
                restore_aliases_matching(group_aliases, group_wrappers, root_original)
                for wid, info in group_items:
                    bypass = self._bypass_target_for(info)
                    self.instrumented.pop(wid, None)
                    removed_count += 1
                    removed_notifications.append((info.get("wrapper"), bypass))

            for wid, info in legacy_singles:
                current_raw = read_target_binding(info["parent"], info["attr_name"])
                if current_raw is info.get("wrapper"):
                    try:
                        self._restore_target_attribute(info)
                    except Exception as exc:
                        errors.append(exc)
                        continue
                self._restore_aliases(info)
                bypass = self._bypass_target_for(info)
                self.instrumented.pop(wid, None)
                removed_count += 1
                removed_notifications.append((info.get("wrapper"), bypass))

        for removed_wrapper, bypass_target in removed_notifications:
            self._notify_wrapper_removed(removed_wrapper, bypass_target)

        if errors:
            if len(errors) == 1:
                raise errors[0]
            raise RuntimeError("; ".join(str(e) for e in errors))

        return removed_count

    def cleanup_orphan_watches(self, now: Optional[float] = None) -> int:
        """Remove watch probes whose owner session stayed dead past grace.

        Args:
            now: Optional monotonic timestamp for deterministic tests.

        Returns:
            Number of orphaned watch probes removed.
        """
        if now is None:
            now = _time.monotonic()

        to_remove = []
        with self._lock:
            for watch_id, info in list(self.instrumented.items()):
                if not watch_id.startswith("watch_"):
                    continue

                grace = info.get("config", {}).get("watch_orphan_grace_seconds")
                if grace is None:
                    grace = getattr(self.agent, "watch_orphan_grace_seconds", 3600.0)
                try:
                    grace_seconds = float(grace)
                except (TypeError, ValueError):
                    grace_seconds = 3600.0

                session_id = info.get("client_session_id")
                is_live = False
                liveness_hook = getattr(self.agent, "is_client_session_live", None)
                if callable(liveness_hook):
                    try:
                        is_live = bool(liveness_hook(session_id))
                    except Exception:
                        is_live = True  # Fail-open: hook error must not trigger orphan cleanup.

                if is_live:
                    info.pop("_orphan_start", None)
                    continue

                orphan_start = info.get("_orphan_start")
                if orphan_start is None:
                    info["_orphan_start"] = now
                    orphan_start = now

                if now - float(orphan_start) >= grace_seconds:
                    to_remove.append(watch_id)

        removed_count = 0
        for watch_id in to_remove:
            try:
                self.uninject(watch_id)
                removed_count += 1
            except ValueError:
                continue
        return removed_count

    def get_watch_info(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an active watch.

        Args:
            watch_id: The watch ID

        Returns:
            Dict with watch info or None if not found
        """
        with self._lock:
            info = self.instrumented.get(watch_id)
            if info:
                return {
                    "watch_id": watch_id,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                    "config": info["config"],
                    "client_session_id": info.get("client_session_id"),
                    "is_coroutine_function": info.get(
                        "is_coroutine_function", False
                    ),
                    "alias_count": len(info.get("aliases", [])),
                    "aliases": [
                        alias["label"] for alias in info.get("aliases", [])
                    ],
                }
            return None

    def list_watches(self) -> List[Dict[str, Any]]:
        """
        List all active watches.

        Returns:
            List of watch info dicts
        """
        with self._lock:
            return [
                {
                    "watch_id": wid,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                    "client_session_id": info.get("client_session_id"),
                    "alias_count": len(info.get("aliases", [])),
                }
                for wid, info in self.instrumented.items()
            ]

    def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """
        Reset (uninject) enhancements, optionally filtered by pattern.

        Args:
            pattern: Optional pattern to match against stored patterns. If None, resets all.
                    Supports Unix shell-style wildcards (* and ?).

        Returns:
            Dict with status, action, affected watches, and count of successful resets
        """
        affected = []

        # Collect watch_ids to reset
        watch_ids_to_reset = []
        with self._lock:
            for watch_id, info in list(self.instrumented.items()):
                if pattern is None or self._match_pattern(
                    info.get("pattern", ""), pattern
                ):
                    watch_ids_to_reset.append(watch_id)

        # Reset each
        for watch_id in watch_ids_to_reset:
            try:
                result = self.uninject(watch_id)
                affected.append(
                    {"watch_id": watch_id, "pattern": result.get("pattern", "")}
                )
            except Exception as e:
                affected.append({"watch_id": watch_id, "error": str(e)})

        return {
            "status": "success",
            "action": "reset",
            "affected": affected,
            "count": len([a for a in affected if "error" not in a]),
        }

    def list_enhanced(self) -> Dict[str, Any]:
        """
        List all current enhancements.

        Returns:
            Dict with status, action, list of enhanced watches, and total count
        """
        enhanced = []
        with self._lock:
            for watch_id, info in self.instrumented.items():
                enhanced.append(
                    {
                        "watch_id": watch_id,
                        "pattern": info.get("pattern", "unknown"),
                        "command": info.get("config", {}).get("command", "watch"),
                        "count": info.get("count", 0),
                        "client_session_id": info.get("client_session_id"),
                        "alias_count": len(info.get("aliases", [])),
                    }
                )
        return {
            "status": "success",
            "action": "list",
            "enhanced": enhanced,
            "total": len(enhanced),
        }

    def _match_pattern(self, stored_pattern: str, filter_pattern: str) -> bool:
        """
        Match stored pattern against filter using fnmatch wildcards.

        Args:
            stored_pattern: The pattern stored in instrumented data
            filter_pattern: The pattern to filter by (supports * and ?)

        Returns:
            True if patterns match, False otherwise
        """
        return fnmatch.fnmatch(stored_pattern, filter_pattern)

    def _generate_watch_id(self) -> str:
        """Generate unique watch ID."""
        return f"watch_{uuid.uuid4().hex[:8]}"

    def _active_probe_infos_in_group(
        self,
        group_key: Tuple[int, str],
        exclude_watch_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return active probe infos that share one wrapped function slot."""
        return [
            info
            for wid, info in self.instrumented.items()
            if wid != exclude_watch_id and info.get("wrapper_group_key") == group_key
        ]

    def _restore_watch_wrapper(self, _watch_id: str, info: Dict[str, Any]) -> None:
        """Restore a watch wrapper only when its shared group permits it."""
        self._restore_wrapper_stack(info)

    def _restore_wrapper_stack(
        self,
        info: Dict[str, Any],
        exclude_watch_id: Optional[str] = None,
    ) -> None:
        """Restore a probe wrapper only when its shared group permits it."""
        group_key = info["wrapper_group_key"]
        remaining = self._active_probe_infos_in_group(
            group_key, exclude_watch_id=exclude_watch_id
        )
        current = read_target_binding(info["parent"], info["attr_name"])
        removed_wrapper = info.get("wrapper")

        if remaining:
            if current is removed_wrapper:
                replacement = self._live_previous_probe_wrapper(info, remaining)
                self._replace_function(
                    info["parent"],
                    info["attr_name"],
                    replacement,
                    descriptor_kind=info.get(
                        "root_descriptor_kind", info.get("descriptor_kind")
                    ),
                )
                self._restore_watch_aliases(info, replacement)
            return

        replacement = info.get("root_original", info["original"])
        if current is removed_wrapper:
            self._restore_target_attribute(dict(info, original=replacement))
            self._restore_watch_aliases(info, replacement)

    def add_wrapper_removed_listener(
        self, listener: Callable[[Any, Any], None]
    ) -> None:
        """Register a callback run after an injector wrapper is removed.

        The callback receives ``(removed_wrapper, bypass_target)`` outside the
        injector lock, so other wrapper owners (e.g. monitor) can stop calling
        the removed wrapper.
        """
        listeners = self.__dict__.setdefault("_wrapper_removed_listeners", [])
        listeners.append(listener)

    def _notify_wrapper_removed(self, removed_wrapper: Any, bypass_target: Any) -> None:
        if removed_wrapper is None:
            return
        for listener in list(self.__dict__.get("_wrapper_removed_listeners", [])):
            try:
                listener(removed_wrapper, bypass_target)
            except Exception:
                logger.debug("Wrapper-removed listener failed", exc_info=True)

    def _bypass_target_for(self, removed_info: Dict[str, Any]) -> Any:
        """Return what callers of a removed wrapper should call instead."""
        target = wrapper_call_target(removed_info.get("wrapper"))
        if target is None:
            target = removed_info.get("root_original", removed_info["original"])
        return target

    def _bypass_removed_wrapper(self, removed_info: Dict[str, Any]) -> Any:
        """Splice a removed wrapper out of every remaining probe's call path.

        Any live injector wrapper that called the removed wrapper now calls
        whatever the removed wrapper called, so no inactive Peeka wrapper stays
        on the execution path (it would otherwise keep running as a
        pass-through). Must be called with ``self._lock`` held.

        Returns:
            The bypass target used.
        """
        removed_wrapper = removed_info.get("wrapper")
        target = self._bypass_target_for(removed_info)
        if removed_wrapper is None:
            return target

        for active_info in self.instrumented.values():
            active_wrapper = active_info.get("wrapper")
            if active_wrapper is None or active_wrapper is removed_wrapper:
                continue
            if (
                wrapper_call_target(active_wrapper) is removed_wrapper
                or getattr(active_wrapper, "__wrapped__", None) is removed_wrapper
            ):
                retarget_wrapper_call(active_wrapper, removed_wrapper, target)
            for key in ("original", "previous_wrapper"):
                if active_info.get(key) is removed_wrapper:
                    active_info[key] = target
            if active_info.get("root_original") is removed_wrapper:
                active_info["root_original"] = removed_info.get(
                    "root_original", removed_info["original"]
                )
        return target

    def _live_previous_probe_wrapper(
        self,
        removed_info: Dict[str, Any],
        remaining: List[Dict[str, Any]],
    ) -> Callable[..., Any]:
        """Return the nearest still-registered Peeka wrapper below a removed probe."""
        live_wrappers = [active_info["wrapper"] for active_info in remaining]
        candidate = getattr(removed_info.get("wrapper"), "__wrapped__", None)
        visited = set()

        for _ in range(32):
            if candidate is None:
                break
            candidate_id = id(candidate)
            if candidate_id in visited:
                break
            visited.add(candidate_id)
            if any(candidate is w for w in live_wrappers):
                return candidate
            candidate = getattr(candidate, "__wrapped__", None)

        return removed_info.get("root_original", removed_info["original"])

    def _restore_watch_aliases(
        self,
        info: Dict[str, Any],
        replacement: Callable[..., Any],
        force: bool = False,
    ) -> None:
        """Restore aliases for a shared watch wrapper group."""
        wrapper = info.get("wrapper")
        for alias in info.get("aliases", []):
            try:
                parent = alias["parent"]
                attr_name = alias["attr_name"]
                if force or getattr(parent, attr_name, None) is wrapper:
                    setattr(parent, attr_name, replacement)
            except Exception:
                logger.debug(
                    "Best-effort watch alias restoration failed for %s",
                    alias.get("label", "<unknown>"),
                    exc_info=True,
                )

    def _record_probe_event(
        self,
        config: Dict[str, Any],
        observation: Dict[str, Any],
    ) -> bool:
        """Record a probe event and enrich the outgoing observation payload."""
        probe_context = config.get("_probe_context")
        if not isinstance(probe_context, ProbeContext):
            return True

        if probe_context.should_stop():
            return False

        event = probe_context.record_event(observation)
        if event is None:
            return probe_context.probe is None
        observation["event_id"] = event.event_id
        observation["probe_id"] = event.probe_id
        return True
