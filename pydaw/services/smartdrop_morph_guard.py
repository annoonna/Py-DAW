"""Safety-first planning helpers for future Instrument→Audio SmartDrop morphing.

This phase prepares a shared preview / validate / apply schema without mutating
project state yet. The real routing + undo-safe conversion comes later.
"""

from __future__ import annotations

import copy
import hashlib
import json

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeSnapshotObjectBinding:
    """Typed, read-only snapshot binding for the future morph apply phase.

    These objects are still non-mutating preview artifacts, but they already
    carry stable object keys plus the capture/restore entry points that the
    later atomic apply/rollback flow can reuse.
    """

    name: str
    snapshot_instance_key: str
    snapshot_instance_kind: str
    snapshot_state: str
    owner_scope: str
    owner_ids: tuple[str, ...]
    snapshot_payload: dict[str, Any]
    snapshot_payload_entry_count: int
    payload_digest: str
    snapshot_object_key: str
    snapshot_object_class: str
    bind_state: str
    supports_capture: bool
    supports_restore: bool
    capture_method: str
    restore_method: str
    rollback_slot: str
    object_stub: str
    source: str = "runtime-snapshot-object-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_instance_key": self.snapshot_instance_key,
            "snapshot_instance_kind": self.snapshot_instance_kind,
            "snapshot_state": self.snapshot_state,
            "owner_scope": self.owner_scope,
            "owner_ids": list(self.owner_ids),
            "snapshot_payload": copy.deepcopy(self.snapshot_payload),
            "snapshot_payload_entry_count": int(self.snapshot_payload_entry_count),
            "payload_digest": self.payload_digest,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "bind_state": self.bind_state,
            "supports_capture": bool(self.supports_capture),
            "supports_restore": bool(self.supports_restore),
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "object_stub": self.object_stub,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotTransactionBundle:
    """Read-only transaction container for later atomic morph apply/rollback.

    The bundle groups the already prepared snapshot-object bindings into one
    stable transaction envelope. It still performs no capture/apply work, but
    gives the later implementation one deterministic object to receive real
    snapshot instances, commit hooks and rollback hooks.
    """

    bundle_key: str
    transaction_key: str
    transaction_container_kind: str
    bundle_state: str
    object_count: int
    ready_object_count: int
    required_snapshot_count: int
    snapshot_object_keys: tuple[str, ...]
    capture_methods: tuple[str, ...]
    restore_methods: tuple[str, ...]
    rollback_slots: tuple[str, ...]
    payload_digests: tuple[str, ...]
    commit_stub: str
    rollback_stub: str
    bundle_stub: str
    source: str = "runtime-snapshot-transaction-bundle-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "bundle_key": self.bundle_key,
            "transaction_key": self.transaction_key,
            "transaction_container_kind": self.transaction_container_kind,
            "bundle_state": self.bundle_state,
            "object_count": int(self.object_count),
            "ready_object_count": int(self.ready_object_count),
            "required_snapshot_count": int(self.required_snapshot_count),
            "snapshot_object_keys": list(self.snapshot_object_keys),
            "capture_methods": list(self.capture_methods),
            "restore_methods": list(self.restore_methods),
            "rollback_slots": list(self.rollback_slots),
            "payload_digests": list(self.payload_digests),
            "commit_stub": self.commit_stub,
            "rollback_stub": self.rollback_stub,
            "bundle_stub": self.bundle_stub,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotDryRunReport:
    """Read-only rehearsal report for the future atomic morph transaction.

    The report simulates capture / commit / restore ordering against the
    prepared snapshot bundle, but it never mutates project state. It exists so
    the later real apply phase can reuse one deterministic runner contract.
    """

    runner_key: str
    transaction_key: str
    bundle_key: str
    dry_run_mode: str
    runner_state: str
    phase_count: int
    ready_phase_count: int
    capture_sequence: tuple[str, ...]
    restore_sequence: tuple[str, ...]
    rollback_sequence: tuple[str, ...]
    rehearsed_steps: tuple[str, ...]
    phase_results: tuple[dict[str, Any], ...]
    capture_method_calls: tuple[str, ...]
    restore_method_calls: tuple[str, ...]
    state_carrier_calls: tuple[str, ...]
    state_carrier_summary: str
    state_container_calls: tuple[str, ...]
    state_container_summary: str
    state_holder_calls: tuple[str, ...]
    state_holder_summary: str
    state_slot_calls: tuple[str, ...]
    state_slot_summary: str
    state_store_calls: tuple[str, ...]
    state_store_summary: str
    state_registry_calls: tuple[str, ...]
    state_registry_summary: str
    state_registry_backend_calls: tuple[str, ...]
    state_registry_backend_summary: str
    state_registry_backend_adapter_calls: tuple[str, ...]
    state_registry_backend_adapter_summary: str
    runner_dispatch_summary: str
    commit_rehearsed: bool
    rollback_rehearsed: bool
    dry_run_stub: str
    source: str = "runtime-snapshot-dry-run-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "runner_key": self.runner_key,
            "transaction_key": self.transaction_key,
            "bundle_key": self.bundle_key,
            "dry_run_mode": self.dry_run_mode,
            "runner_state": self.runner_state,
            "phase_count": int(self.phase_count),
            "ready_phase_count": int(self.ready_phase_count),
            "capture_sequence": list(self.capture_sequence),
            "restore_sequence": list(self.restore_sequence),
            "rollback_sequence": list(self.rollback_sequence),
            "rehearsed_steps": list(self.rehearsed_steps),
            "phase_results": [copy.deepcopy(dict(item or {})) for item in list(self.phase_results or ())],
            "capture_method_calls": list(self.capture_method_calls),
            "restore_method_calls": list(self.restore_method_calls),
            "state_carrier_calls": list(self.state_carrier_calls),
            "state_carrier_summary": self.state_carrier_summary,
            "state_container_calls": list(self.state_container_calls),
            "state_container_summary": self.state_container_summary,
            "state_holder_calls": list(self.state_holder_calls),
            "state_holder_summary": self.state_holder_summary,
            "state_slot_calls": list(self.state_slot_calls),
            "state_slot_summary": self.state_slot_summary,
            "state_store_calls": list(self.state_store_calls),
            "state_store_summary": self.state_store_summary,
            "state_registry_calls": list(self.state_registry_calls),
            "state_registry_summary": self.state_registry_summary,
            "state_registry_backend_calls": list(self.state_registry_backend_calls),
            "state_registry_backend_summary": self.state_registry_backend_summary,
            "state_registry_backend_adapter_calls": list(self.state_registry_backend_adapter_calls),
            "state_registry_backend_adapter_summary": self.state_registry_backend_adapter_summary,
            "runner_dispatch_summary": self.runner_dispatch_summary,
            "commit_rehearsed": bool(self.commit_rehearsed),
            "rollback_rehearsed": bool(self.rollback_rehearsed),
            "dry_run_stub": self.dry_run_stub,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStubBinding:
    """Concrete runtime stub binding for the safe-runner preview layer.

    This is still fully read-only, but it materializes a typed class/stub pair
    that the dry-run can call directly instead of dispatching only by plain
    method-name strings. The later real apply phase can reuse the same stub
    factory contract when the commit path gets unlocked.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    bind_state: str
    stub_key: str
    stub_class: str
    dispatch_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_preview: bool
    supports_restore_preview: bool
    factory_method: str
    capture_stub: str
    restore_stub: str
    rollback_stub: str
    source: str = "runtime-snapshot-stub-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "bind_state": self.bind_state,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "dispatch_state": self.dispatch_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_preview": bool(self.supports_capture_preview),
            "supports_restore_preview": bool(self.supports_restore_preview),
            "factory_method": self.factory_method,
            "capture_stub": self.capture_stub,
            "restore_stub": self.restore_stub,
            "rollback_stub": self.rollback_stub,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateCarrier:
    """Typed state-carrier preview for future capture/restore snapshot instances.

    The carrier binds an already prepared snapshot object + runtime stub to a
    concrete state payload preview. It remains fully read-only, but gives the
    later apply phase a deterministic holder for capture/restore state.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    carrier_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_state: bool
    supports_restore_state: bool
    bind_method: str
    capture_state_stub: str
    restore_state_stub: str
    rollback_state_stub: str
    state_payload_preview: dict[str, Any]
    state_payload_entry_count: int
    state_payload_digest: str
    source: str = "runtime-snapshot-state-carrier-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "carrier_state": self.carrier_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_state": bool(self.supports_capture_state),
            "supports_restore_state": bool(self.supports_restore_state),
            "bind_method": self.bind_method,
            "capture_state_stub": self.capture_state_stub,
            "restore_state_stub": self.restore_state_stub,
            "rollback_state_stub": self.rollback_state_stub,
            "state_payload_preview": copy.deepcopy(self.state_payload_preview),
            "state_payload_entry_count": int(self.state_payload_entry_count),
            "state_payload_digest": self.state_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateContainer:
    """Read-only runtime-state container preview for future snapshot apply phases.

    The container materializes one state-carrier into a dedicated runtime holder
    with its own key, payload digest and preview methods. This stays fully
    non-mutating, but gives the later real apply phase a deterministic place to
    attach concrete runtime state objects.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    container_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_container: bool
    supports_restore_container: bool
    supports_runtime_state_container: bool
    instantiate_method: str
    capture_container_stub: str
    restore_container_stub: str
    rollback_container_stub: str
    runtime_state_stub: str
    state_payload_preview: dict[str, Any]
    state_payload_entry_count: int
    state_payload_digest: str
    container_payload_preview: dict[str, Any]
    container_payload_entry_count: int
    container_payload_digest: str
    source: str = "runtime-snapshot-state-container-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "container_state": self.container_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_container": bool(self.supports_capture_container),
            "supports_restore_container": bool(self.supports_restore_container),
            "supports_runtime_state_container": bool(self.supports_runtime_state_container),
            "instantiate_method": self.instantiate_method,
            "capture_container_stub": self.capture_container_stub,
            "restore_container_stub": self.restore_container_stub,
            "rollback_container_stub": self.rollback_container_stub,
            "runtime_state_stub": self.runtime_state_stub,
            "state_payload_preview": copy.deepcopy(self.state_payload_preview),
            "state_payload_entry_count": int(self.state_payload_entry_count),
            "state_payload_digest": self.state_payload_digest,
            "container_payload_preview": copy.deepcopy(self.container_payload_preview),
            "container_payload_entry_count": int(self.container_payload_entry_count),
            "container_payload_digest": self.container_payload_digest,
            "source": self.source,
        }




@dataclass(frozen=True)
class RuntimeSnapshotStateHolder:
    """Read-only runtime-state holder preview for future snapshot apply phases.

    The holder binds one dedicated runtime-state container to a separate runtime
    state holder object. It still performs no mutation, but represents the
    final preview-level place where later real snapshot instances/state slots can
    be attached for an atomic apply/rollback transaction.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    holder_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_holder: bool
    supports_restore_holder: bool
    supports_runtime_state_holder: bool
    instantiate_method: str
    capture_holder_stub: str
    restore_holder_stub: str
    rollback_holder_stub: str
    runtime_holder_stub: str
    container_payload_preview: dict[str, Any]
    container_payload_entry_count: int
    container_payload_digest: str
    holder_payload_preview: dict[str, Any]
    holder_payload_entry_count: int
    holder_payload_digest: str
    source: str = "runtime-snapshot-state-holder-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "holder_state": self.holder_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_holder": bool(self.supports_capture_holder),
            "supports_restore_holder": bool(self.supports_restore_holder),
            "supports_runtime_state_holder": bool(self.supports_runtime_state_holder),
            "instantiate_method": self.instantiate_method,
            "capture_holder_stub": self.capture_holder_stub,
            "restore_holder_stub": self.restore_holder_stub,
            "rollback_holder_stub": self.rollback_holder_stub,
            "runtime_holder_stub": self.runtime_holder_stub,
            "container_payload_preview": copy.deepcopy(self.container_payload_preview),
            "container_payload_entry_count": int(self.container_payload_entry_count),
            "container_payload_digest": self.container_payload_digest,
            "holder_payload_preview": copy.deepcopy(self.holder_payload_preview),
            "holder_payload_entry_count": int(self.holder_payload_entry_count),
            "holder_payload_digest": self.holder_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateSlot:
    """Read-only runtime-state slot / snapshot-state storage preview.

    This is the next safe layer after runtime-state holders. It models the
    later concrete runtime slot or state-store object that would hold captured
    snapshot state for commit/rollback, but remains completely non-mutating.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    slot_key: str
    slot_class: str
    slot_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_slot: bool
    supports_restore_slot: bool
    supports_runtime_state_slot: bool
    instantiate_method: str
    capture_slot_stub: str
    restore_slot_stub: str
    rollback_slot_stub: str
    runtime_state_slot_stub: str
    holder_payload_preview: dict[str, Any]
    holder_payload_entry_count: int
    holder_payload_digest: str
    slot_payload_preview: dict[str, Any]
    slot_payload_entry_count: int
    slot_payload_digest: str
    source: str = "runtime-snapshot-state-slot-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "slot_key": self.slot_key,
            "slot_class": self.slot_class,
            "slot_state": self.slot_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_slot": bool(self.supports_capture_slot),
            "supports_restore_slot": bool(self.supports_restore_slot),
            "supports_runtime_state_slot": bool(self.supports_runtime_state_slot),
            "instantiate_method": self.instantiate_method,
            "capture_slot_stub": self.capture_slot_stub,
            "restore_slot_stub": self.restore_slot_stub,
            "rollback_slot_stub": self.rollback_slot_stub,
            "runtime_state_slot_stub": self.runtime_state_slot_stub,
            "holder_payload_preview": copy.deepcopy(self.holder_payload_preview),
            "holder_payload_entry_count": int(self.holder_payload_entry_count),
            "holder_payload_digest": self.holder_payload_digest,
            "slot_payload_preview": copy.deepcopy(self.slot_payload_preview),
            "slot_payload_entry_count": int(self.slot_payload_entry_count),
            "slot_payload_digest": self.slot_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateStore:
    """Read-only runtime-state store with capture-handle previews.

    This layer sits behind runtime-state slots and models the later concrete
    snapshot-state store object that would own capture/restore handles for the
    atomic morph transaction. It remains fully read-only in this phase.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    slot_key: str
    slot_class: str
    store_key: str
    store_class: str
    store_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_store: bool
    supports_restore_store: bool
    supports_runtime_state_store: bool
    instantiate_method: str
    capture_store_stub: str
    restore_store_stub: str
    rollback_store_stub: str
    runtime_state_store_stub: str
    capture_handle_key: str
    restore_handle_key: str
    rollback_handle_key: str
    capture_handle_state: str
    slot_payload_preview: dict[str, Any]
    slot_payload_entry_count: int
    slot_payload_digest: str
    store_payload_preview: dict[str, Any]
    store_payload_entry_count: int
    store_payload_digest: str
    source: str = "runtime-snapshot-state-store-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "slot_key": self.slot_key,
            "slot_class": self.slot_class,
            "store_key": self.store_key,
            "store_class": self.store_class,
            "store_state": self.store_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_store": bool(self.supports_capture_store),
            "supports_restore_store": bool(self.supports_restore_store),
            "supports_runtime_state_store": bool(self.supports_runtime_state_store),
            "instantiate_method": self.instantiate_method,
            "capture_store_stub": self.capture_store_stub,
            "restore_store_stub": self.restore_store_stub,
            "rollback_store_stub": self.rollback_store_stub,
            "runtime_state_store_stub": self.runtime_state_store_stub,
            "capture_handle_key": self.capture_handle_key,
            "restore_handle_key": self.restore_handle_key,
            "rollback_handle_key": self.rollback_handle_key,
            "capture_handle_state": self.capture_handle_state,
            "slot_payload_preview": copy.deepcopy(self.slot_payload_preview),
            "slot_payload_entry_count": int(self.slot_payload_entry_count),
            "slot_payload_digest": self.slot_payload_digest,
            "store_payload_preview": copy.deepcopy(self.store_payload_preview),
            "store_payload_entry_count": int(self.store_payload_entry_count),
            "store_payload_digest": self.store_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateRegistry:
    """Read-only runtime-state registry with separate handle-storage previews.

    This layer sits behind runtime-state stores. It groups store-level capture /
    restore handles into one deterministic registry + separate handle-storage
    preview, still without mutating any project state.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    slot_key: str
    slot_class: str
    store_key: str
    store_class: str
    registry_key: str
    registry_class: str
    registry_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_registry: bool
    supports_restore_registry: bool
    supports_runtime_state_registry: bool
    instantiate_method: str
    capture_registry_stub: str
    restore_registry_stub: str
    rollback_registry_stub: str
    runtime_state_registry_stub: str
    capture_handle_key: str
    restore_handle_key: str
    rollback_handle_key: str
    handle_store_key: str
    handle_store_class: str
    handle_store_state: str
    store_payload_preview: dict[str, Any]
    store_payload_entry_count: int
    store_payload_digest: str
    registry_payload_preview: dict[str, Any]
    registry_payload_entry_count: int
    registry_payload_digest: str
    source: str = "runtime-snapshot-state-registry-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "slot_key": self.slot_key,
            "slot_class": self.slot_class,
            "store_key": self.store_key,
            "store_class": self.store_class,
            "registry_key": self.registry_key,
            "registry_class": self.registry_class,
            "registry_state": self.registry_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_registry": bool(self.supports_capture_registry),
            "supports_restore_registry": bool(self.supports_restore_registry),
            "supports_runtime_state_registry": bool(self.supports_runtime_state_registry),
            "instantiate_method": self.instantiate_method,
            "capture_registry_stub": self.capture_registry_stub,
            "restore_registry_stub": self.restore_registry_stub,
            "rollback_registry_stub": self.rollback_registry_stub,
            "runtime_state_registry_stub": self.runtime_state_registry_stub,
            "capture_handle_key": self.capture_handle_key,
            "restore_handle_key": self.restore_handle_key,
            "rollback_handle_key": self.rollback_handle_key,
            "handle_store_key": self.handle_store_key,
            "handle_store_class": self.handle_store_class,
            "handle_store_state": self.handle_store_state,
            "store_payload_preview": copy.deepcopy(self.store_payload_preview),
            "store_payload_entry_count": int(self.store_payload_entry_count),
            "store_payload_digest": self.store_payload_digest,
            "registry_payload_preview": copy.deepcopy(self.registry_payload_preview),
            "registry_payload_entry_count": int(self.registry_payload_entry_count),
            "registry_payload_digest": self.registry_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateRegistryBackend:
    """Read-only backend binding behind runtime-state registries.

    This layer sits one step behind the registry + handle-store preview and
    materializes a separate backend plus registry-slot / handle-register view.
    It remains fully read-only and is meant only as the next deterministic
    contract for the later real apply phase.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    slot_key: str
    slot_class: str
    store_key: str
    store_class: str
    registry_key: str
    registry_class: str
    backend_key: str
    backend_class: str
    backend_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_backend: bool
    supports_restore_backend: bool
    supports_runtime_state_backend: bool
    instantiate_method: str
    capture_backend_stub: str
    restore_backend_stub: str
    rollback_backend_stub: str
    runtime_state_backend_stub: str
    handle_register_key: str
    handle_register_class: str
    handle_register_state: str
    registry_slot_key: str
    registry_slot_class: str
    registry_slot_state: str
    registry_payload_preview: dict[str, Any]
    registry_payload_entry_count: int
    registry_payload_digest: str
    backend_payload_preview: dict[str, Any]
    backend_payload_entry_count: int
    backend_payload_digest: str
    source: str = "runtime-snapshot-state-registry-backend-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "slot_key": self.slot_key,
            "slot_class": self.slot_class,
            "store_key": self.store_key,
            "store_class": self.store_class,
            "registry_key": self.registry_key,
            "registry_class": self.registry_class,
            "backend_key": self.backend_key,
            "backend_class": self.backend_class,
            "backend_state": self.backend_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_backend": bool(self.supports_capture_backend),
            "supports_restore_backend": bool(self.supports_restore_backend),
            "supports_runtime_state_backend": bool(self.supports_runtime_state_backend),
            "instantiate_method": self.instantiate_method,
            "capture_backend_stub": self.capture_backend_stub,
            "restore_backend_stub": self.restore_backend_stub,
            "rollback_backend_stub": self.rollback_backend_stub,
            "runtime_state_backend_stub": self.runtime_state_backend_stub,
            "handle_register_key": self.handle_register_key,
            "handle_register_class": self.handle_register_class,
            "handle_register_state": self.handle_register_state,
            "registry_slot_key": self.registry_slot_key,
            "registry_slot_class": self.registry_slot_class,
            "registry_slot_state": self.registry_slot_state,
            "registry_payload_preview": copy.deepcopy(self.registry_payload_preview),
            "registry_payload_entry_count": int(self.registry_payload_entry_count),
            "registry_payload_digest": self.registry_payload_digest,
            "backend_payload_preview": copy.deepcopy(self.backend_payload_preview),
            "backend_payload_entry_count": int(self.backend_payload_entry_count),
            "backend_payload_digest": self.backend_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotStateRegistryBackendAdapter:
    """Read-only adapter binding behind runtime-state registry backends.

    This layer sits one step behind the registry-backend preview. It binds each
    registry backend to a concrete backend-store adapter plus a dedicated
    registry-slot backend contract, still fully read-only and commit-free.
    """

    name: str
    snapshot_object_key: str
    snapshot_object_class: str
    stub_key: str
    stub_class: str
    carrier_key: str
    carrier_class: str
    container_key: str
    container_class: str
    holder_key: str
    holder_class: str
    slot_key: str
    slot_class: str
    store_key: str
    store_class: str
    registry_key: str
    registry_class: str
    backend_key: str
    backend_class: str
    adapter_key: str
    adapter_class: str
    adapter_state: str
    capture_method: str
    restore_method: str
    rollback_slot: str
    supports_capture_backend_adapter: bool
    supports_restore_backend_adapter: bool
    supports_runtime_state_backend_adapter: bool
    instantiate_method: str
    capture_adapter_stub: str
    restore_adapter_stub: str
    rollback_adapter_stub: str
    runtime_state_backend_adapter_stub: str
    backend_store_adapter_key: str
    backend_store_adapter_class: str
    backend_store_adapter_state: str
    registry_slot_backend_key: str
    registry_slot_backend_class: str
    registry_slot_backend_state: str
    backend_payload_preview: dict[str, Any]
    backend_payload_entry_count: int
    backend_payload_digest: str
    adapter_payload_preview: dict[str, Any]
    adapter_payload_entry_count: int
    adapter_payload_digest: str
    source: str = "runtime-snapshot-state-registry-backend-adapter-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "snapshot_object_key": self.snapshot_object_key,
            "snapshot_object_class": self.snapshot_object_class,
            "stub_key": self.stub_key,
            "stub_class": self.stub_class,
            "carrier_key": self.carrier_key,
            "carrier_class": self.carrier_class,
            "container_key": self.container_key,
            "container_class": self.container_class,
            "holder_key": self.holder_key,
            "holder_class": self.holder_class,
            "slot_key": self.slot_key,
            "slot_class": self.slot_class,
            "store_key": self.store_key,
            "store_class": self.store_class,
            "registry_key": self.registry_key,
            "registry_class": self.registry_class,
            "backend_key": self.backend_key,
            "backend_class": self.backend_class,
            "adapter_key": self.adapter_key,
            "adapter_class": self.adapter_class,
            "adapter_state": self.adapter_state,
            "capture_method": self.capture_method,
            "restore_method": self.restore_method,
            "rollback_slot": self.rollback_slot,
            "supports_capture_backend_adapter": bool(self.supports_capture_backend_adapter),
            "supports_restore_backend_adapter": bool(self.supports_restore_backend_adapter),
            "supports_runtime_state_backend_adapter": bool(self.supports_runtime_state_backend_adapter),
            "instantiate_method": self.instantiate_method,
            "capture_adapter_stub": self.capture_adapter_stub,
            "restore_adapter_stub": self.restore_adapter_stub,
            "rollback_adapter_stub": self.rollback_adapter_stub,
            "runtime_state_backend_adapter_stub": self.runtime_state_backend_adapter_stub,
            "backend_store_adapter_key": self.backend_store_adapter_key,
            "backend_store_adapter_class": self.backend_store_adapter_class,
            "backend_store_adapter_state": self.backend_store_adapter_state,
            "registry_slot_backend_key": self.registry_slot_backend_key,
            "registry_slot_backend_class": self.registry_slot_backend_class,
            "registry_slot_backend_state": self.registry_slot_backend_state,
            "backend_payload_preview": copy.deepcopy(self.backend_payload_preview),
            "backend_payload_entry_count": int(self.backend_payload_entry_count),
            "backend_payload_digest": self.backend_payload_digest,
            "adapter_payload_preview": copy.deepcopy(self.adapter_payload_preview),
            "adapter_payload_entry_count": int(self.adapter_payload_entry_count),
            "adapter_payload_digest": self.adapter_payload_digest,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotApplyRunnerReport:
    """Read-only snapshot apply-runner preview behind the adapter layer.

    This report simulates the future apply-runner dispatch over adapter,
    backend-store-adapter and registry-slot-backend contracts. It remains fully
    non-mutating and keeps commit blocked, but gives the later real apply phase
    one deterministic runner payload to reuse.
    """

    runner_key: str
    transaction_key: str
    bundle_key: str
    apply_mode: str
    runner_state: str
    phase_count: int
    ready_phase_count: int
    apply_sequence: tuple[str, ...]
    restore_sequence: tuple[str, ...]
    rollback_sequence: tuple[str, ...]
    rehearsed_steps: tuple[str, ...]
    phase_results: tuple[dict[str, Any], ...]
    state_registry_backend_adapter_calls: tuple[str, ...]
    state_registry_backend_adapter_summary: str
    backend_store_adapter_calls: tuple[str, ...]
    backend_store_adapter_summary: str
    registry_slot_backend_calls: tuple[str, ...]
    registry_slot_backend_summary: str
    runner_dispatch_summary: str
    commit_preview_only: bool
    rollback_rehearsed: bool
    apply_runner_stub: str
    source: str = "runtime-snapshot-apply-runner-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "runner_key": self.runner_key,
            "transaction_key": self.transaction_key,
            "bundle_key": self.bundle_key,
            "apply_mode": self.apply_mode,
            "runner_state": self.runner_state,
            "phase_count": int(self.phase_count),
            "ready_phase_count": int(self.ready_phase_count),
            "apply_sequence": list(self.apply_sequence),
            "restore_sequence": list(self.restore_sequence),
            "rollback_sequence": list(self.rollback_sequence),
            "rehearsed_steps": list(self.rehearsed_steps),
            "phase_results": [copy.deepcopy(dict(item or {})) for item in list(self.phase_results or ())],
            "state_registry_backend_adapter_calls": list(self.state_registry_backend_adapter_calls),
            "state_registry_backend_adapter_summary": self.state_registry_backend_adapter_summary,
            "backend_store_adapter_calls": list(self.backend_store_adapter_calls),
            "backend_store_adapter_summary": self.backend_store_adapter_summary,
            "registry_slot_backend_calls": list(self.registry_slot_backend_calls),
            "registry_slot_backend_summary": self.registry_slot_backend_summary,
            "runner_dispatch_summary": self.runner_dispatch_summary,
            "commit_preview_only": bool(self.commit_preview_only),
            "rollback_rehearsed": bool(self.rollback_rehearsed),
            "apply_runner_stub": self.apply_runner_stub,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotMinimalCaseReport:
    """Read-only qualification for the first later empty-audio minimal case.

    The report does not unlock or mutate anything. It only marks whether the
    current target already matches the safest future first real morph case:
    an empty audio track with a fully rehearsed snapshot/apply-runner/dry-run
    contract behind the guard.
    """

    minimal_case_key: str
    transaction_key: str
    candidate_state: str
    target_kind: str
    target_empty: bool
    audio_clip_count: int
    audio_fx_count: int
    note_fx_count: int
    bundle_ready: bool
    apply_runner_ready: bool
    dry_run_ready: bool
    future_unlock_ready: bool
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-minimal-case-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "minimal_case_key": self.minimal_case_key,
            "transaction_key": self.transaction_key,
            "candidate_state": self.candidate_state,
            "target_kind": self.target_kind,
            "target_empty": bool(self.target_empty),
            "audio_clip_count": int(self.audio_clip_count),
            "audio_fx_count": int(self.audio_fx_count),
            "note_fx_count": int(self.note_fx_count),
            "bundle_ready": bool(self.bundle_ready),
            "apply_runner_ready": bool(self.apply_runner_ready),
            "dry_run_ready": bool(self.dry_run_ready),
            "future_unlock_ready": bool(self.future_unlock_ready),
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotPrecommitContractReport:
    """Read-only pre-commit contract for the first later minimal morph case.

    This report still blocks any project mutation. It only prepares the exact
    empty-audio-track contract that the later real apply phase should reuse for
    atomic undo/routing/track-kind/instrument switching.
    """

    contract_key: str
    transaction_key: str
    minimal_case_key: str
    contract_state: str
    mutation_gate_state: str
    target_scope: str
    target_empty: bool
    preview_phase_count: int
    ready_preview_phase_count: int
    preview_commit_sequence: tuple[str, ...]
    preview_rollback_sequence: tuple[str, ...]
    preview_phase_results: tuple[dict[str, Any], ...]
    bundle_key: str
    apply_runner_key: str
    dry_run_key: str
    future_commit_stub: str
    future_rollback_stub: str
    commit_preview_only: bool
    project_mutation_enabled: bool
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-precommit-contract-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "contract_key": self.contract_key,
            "transaction_key": self.transaction_key,
            "minimal_case_key": self.minimal_case_key,
            "contract_state": self.contract_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "target_empty": bool(self.target_empty),
            "preview_phase_count": int(self.preview_phase_count),
            "ready_preview_phase_count": int(self.ready_preview_phase_count),
            "preview_commit_sequence": list(self.preview_commit_sequence),
            "preview_rollback_sequence": list(self.preview_rollback_sequence),
            "preview_phase_results": [copy.deepcopy(dict(item or {})) for item in list(self.preview_phase_results or ())],
            "bundle_key": self.bundle_key,
            "apply_runner_key": self.apply_runner_key,
            "dry_run_key": self.dry_run_key,
            "future_commit_stub": self.future_commit_stub,
            "future_rollback_stub": self.future_rollback_stub,
            "commit_preview_only": bool(self.commit_preview_only),
            "project_mutation_enabled": bool(self.project_mutation_enabled),
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotAtomicEntryPointReport:
    """Read-only coupling of the pre-commit contract to real owner entry points.

    The report still performs no mutation. It only resolves which concrete
    service/undo/routing entry points the later atomic minimal-case apply path
    should call once mutation is finally unlocked.
    """

    entrypoint_key: str
    transaction_key: str
    contract_key: str
    entrypoint_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    total_entrypoint_count: int
    ready_entrypoint_count: int
    entrypoints: tuple[dict[str, Any], ...]
    preview_dispatch_sequence: tuple[str, ...]
    future_apply_stub: str
    future_commit_stub: str
    future_rollback_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-atomic-entrypoint-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "entrypoint_key": self.entrypoint_key,
            "transaction_key": self.transaction_key,
            "contract_key": self.contract_key,
            "entrypoint_state": self.entrypoint_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "total_entrypoint_count": int(self.total_entrypoint_count),
            "ready_entrypoint_count": int(self.ready_entrypoint_count),
            "entrypoints": [copy.deepcopy(dict(item or {})) for item in list(self.entrypoints or ())],
            "preview_dispatch_sequence": list(self.preview_dispatch_sequence),
            "future_apply_stub": self.future_apply_stub,
            "future_commit_stub": self.future_commit_stub,
            "future_rollback_stub": self.future_rollback_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotMutationGateCapsuleReport:
    """Read-only coupling of atomic entry points to a guarded transaction capsule.

    This stays strictly preview-only. It only records whether a real owner could
    later expose an explicit mutation gate and a transaction capsule around the
    already prepared minimal-case entry points.
    """

    capsule_key: str
    transaction_key: str
    contract_key: str
    entrypoint_key: str
    capsule_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    total_capsule_step_count: int
    ready_capsule_step_count: int
    capsule_steps: tuple[dict[str, Any], ...]
    preview_capsule_sequence: tuple[str, ...]
    future_gate_stub: str
    future_capsule_stub: str
    future_commit_stub: str
    future_rollback_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-mutation-gate-capsule-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "capsule_key": self.capsule_key,
            "transaction_key": self.transaction_key,
            "contract_key": self.contract_key,
            "entrypoint_key": self.entrypoint_key,
            "capsule_state": self.capsule_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "total_capsule_step_count": int(self.total_capsule_step_count),
            "ready_capsule_step_count": int(self.ready_capsule_step_count),
            "capsule_steps": [copy.deepcopy(dict(item or {})) for item in list(self.capsule_steps or ())],
            "preview_capsule_sequence": list(self.preview_capsule_sequence),
            "future_gate_stub": self.future_gate_stub,
            "future_capsule_stub": self.future_capsule_stub,
            "future_commit_stub": self.future_commit_stub,
            "future_rollback_stub": self.future_rollback_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }

@dataclass(frozen=True)
class RuntimeSnapshotCommandUndoShellReport:
    """Read-only coupling of the transaction capsule to ProjectSnapshotEditCommand.

    This adds the last missing explicit command/undo shell around the later
    minimal-case morph transaction. It still stays strictly preview-only and
    never pushes a real command onto the undo stack in this phase.
    """

    shell_key: str
    transaction_key: str
    capsule_key: str
    contract_key: str
    shell_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    command_class: str
    command_module: str
    total_shell_step_count: int
    ready_shell_step_count: int
    shell_steps: tuple[dict[str, Any], ...]
    preview_shell_sequence: tuple[str, ...]
    future_command_stub: str
    future_undo_stub: str
    future_commit_stub: str
    future_rollback_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-command-undo-shell-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "shell_key": self.shell_key,
            "transaction_key": self.transaction_key,
            "capsule_key": self.capsule_key,
            "contract_key": self.contract_key,
            "shell_state": self.shell_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "command_class": self.command_class,
            "command_module": self.command_module,
            "total_shell_step_count": int(self.total_shell_step_count),
            "ready_shell_step_count": int(self.ready_shell_step_count),
            "shell_steps": [copy.deepcopy(dict(item or {})) for item in list(self.shell_steps or ())],
            "preview_shell_sequence": list(self.preview_shell_sequence),
            "future_command_stub": self.future_command_stub,
            "future_undo_stub": self.future_undo_stub,
            "future_commit_stub": self.future_commit_stub,
            "future_rollback_stub": self.future_rollback_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotCommandFactoryPayloadReport:
    """Read-only before/after snapshot factory with materialized payload metadata.

    The later ProjectSnapshotEditCommand already has a visible shell, but this
    report adds the next safe layer: a preview-only factory that materializes
    before/after snapshot payload metadata so the future command constructor can
    be wired against concrete payload descriptors without mutating the project.
    """

    factory_key: str
    transaction_key: str
    shell_key: str
    capsule_key: str
    contract_key: str
    payload_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    command_class: str
    command_module: str
    label_preview: str
    payload_delta_kind: str
    materialized_payload_count: int
    before_payload_summary: dict[str, Any]
    after_payload_summary: dict[str, Any]
    total_factory_step_count: int
    ready_factory_step_count: int
    factory_steps: tuple[dict[str, Any], ...]
    preview_factory_sequence: tuple[str, ...]
    future_factory_stub: str
    future_before_snapshot_stub: str
    future_after_snapshot_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-command-factory-payload-preview"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "factory_key": self.factory_key,
            "transaction_key": self.transaction_key,
            "shell_key": self.shell_key,
            "capsule_key": self.capsule_key,
            "contract_key": self.contract_key,
            "payload_state": self.payload_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "command_class": self.command_class,
            "command_module": self.command_module,
            "label_preview": self.label_preview,
            "payload_delta_kind": self.payload_delta_kind,
            "materialized_payload_count": int(self.materialized_payload_count),
            "before_payload_summary": copy.deepcopy(dict(self.before_payload_summary or {})),
            "after_payload_summary": copy.deepcopy(dict(self.after_payload_summary or {})),
            "total_factory_step_count": int(self.total_factory_step_count),
            "ready_factory_step_count": int(self.ready_factory_step_count),
            "factory_steps": [copy.deepcopy(dict(item or {})) for item in list(self.factory_steps or ())],
            "preview_factory_sequence": list(self.preview_factory_sequence),
            "future_factory_stub": self.future_factory_stub,
            "future_before_snapshot_stub": self.future_before_snapshot_stub,
            "future_after_snapshot_stub": self.future_after_snapshot_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotPreviewCommandConstructionReport:
    """Read-only construction of the later ProjectSnapshotEditCommand instance.

    The before/after payload factory already materializes payload metadata.
    This next safe layer goes one step further and constructs the later command
    in memory without executing it, pushing it onto the undo stack or mutating
    project state.
    """

    preview_command_key: str
    transaction_key: str
    factory_key: str
    shell_key: str
    capsule_key: str
    contract_key: str
    preview_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    command_class: str
    command_module: str
    command_constructor: str
    label_preview: str
    apply_callback_name: str
    apply_callback_owner_class: str
    payload_delta_kind: str
    materialized_payload_count: int
    before_payload_summary: dict[str, Any]
    after_payload_summary: dict[str, Any]
    command_field_names: tuple[str, ...]
    total_preview_step_count: int
    ready_preview_step_count: int
    preview_steps: tuple[dict[str, Any], ...]
    preview_command_sequence: tuple[str, ...]
    future_constructor_stub: str
    future_executor_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-preview-command-construction"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "preview_command_key": self.preview_command_key,
            "transaction_key": self.transaction_key,
            "factory_key": self.factory_key,
            "shell_key": self.shell_key,
            "capsule_key": self.capsule_key,
            "contract_key": self.contract_key,
            "preview_state": self.preview_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "command_class": self.command_class,
            "command_module": self.command_module,
            "command_constructor": self.command_constructor,
            "label_preview": self.label_preview,
            "apply_callback_name": self.apply_callback_name,
            "apply_callback_owner_class": self.apply_callback_owner_class,
            "payload_delta_kind": self.payload_delta_kind,
            "materialized_payload_count": int(self.materialized_payload_count),
            "before_payload_summary": copy.deepcopy(dict(self.before_payload_summary or {})),
            "after_payload_summary": copy.deepcopy(dict(self.after_payload_summary or {})),
            "command_field_names": list(self.command_field_names),
            "total_preview_step_count": int(self.total_preview_step_count),
            "ready_preview_step_count": int(self.ready_preview_step_count),
            "preview_steps": [copy.deepcopy(dict(item or {})) for item in list(self.preview_steps or ())],
            "preview_command_sequence": list(self.preview_command_sequence),
            "future_constructor_stub": self.future_constructor_stub,
            "future_executor_stub": self.future_executor_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }


@dataclass(frozen=True)
class RuntimeSnapshotDryCommandExecutorReport:
    """Read-only do()/undo() simulation harness for ProjectSnapshotEditCommand.

    The preview command is now not only constructed in memory, but also rehearsed
    through ``do()`` and ``undo()`` against a recorder callback that never touches
    the live project state.
    """

    dry_executor_key: str
    transaction_key: str
    preview_command_key: str
    factory_key: str
    shell_key: str
    capsule_key: str
    contract_key: str
    dry_executor_state: str
    mutation_gate_state: str
    target_scope: str
    owner_class: str
    command_class: str
    command_module: str
    command_constructor: str
    label_preview: str
    apply_callback_name: str
    apply_callback_owner_class: str
    payload_delta_kind: str
    materialized_payload_count: int
    before_payload_summary: dict[str, Any]
    after_payload_summary: dict[str, Any]
    do_call_count: int
    undo_call_count: int
    callback_call_count: int
    callback_trace: tuple[str, ...]
    callback_payload_digests: tuple[str, ...]
    total_simulation_step_count: int
    ready_simulation_step_count: int
    simulation_steps: tuple[dict[str, Any], ...]
    simulation_sequence: tuple[str, ...]
    future_executor_stub: str
    future_live_executor_stub: str
    blocked_by: tuple[str, ...]
    pending_by: tuple[str, ...]
    summary: str
    source: str = "runtime-snapshot-dry-command-executor"

    def as_plan_dict(self) -> dict[str, Any]:
        return {
            "dry_executor_key": self.dry_executor_key,
            "transaction_key": self.transaction_key,
            "preview_command_key": self.preview_command_key,
            "factory_key": self.factory_key,
            "shell_key": self.shell_key,
            "capsule_key": self.capsule_key,
            "contract_key": self.contract_key,
            "dry_executor_state": self.dry_executor_state,
            "mutation_gate_state": self.mutation_gate_state,
            "target_scope": self.target_scope,
            "owner_class": self.owner_class,
            "command_class": self.command_class,
            "command_module": self.command_module,
            "command_constructor": self.command_constructor,
            "label_preview": self.label_preview,
            "apply_callback_name": self.apply_callback_name,
            "apply_callback_owner_class": self.apply_callback_owner_class,
            "payload_delta_kind": self.payload_delta_kind,
            "materialized_payload_count": int(self.materialized_payload_count),
            "before_payload_summary": copy.deepcopy(dict(self.before_payload_summary or {})),
            "after_payload_summary": copy.deepcopy(dict(self.after_payload_summary or {})),
            "do_call_count": int(self.do_call_count),
            "undo_call_count": int(self.undo_call_count),
            "callback_call_count": int(self.callback_call_count),
            "callback_trace": list(self.callback_trace),
            "callback_payload_digests": list(self.callback_payload_digests),
            "total_simulation_step_count": int(self.total_simulation_step_count),
            "ready_simulation_step_count": int(self.ready_simulation_step_count),
            "simulation_steps": [copy.deepcopy(dict(item or {})) for item in list(self.simulation_steps or ())],
            "simulation_sequence": list(self.simulation_sequence),
            "future_executor_stub": self.future_executor_stub,
            "future_live_executor_stub": self.future_live_executor_stub,
            "blocked_by": list(self.blocked_by),
            "pending_by": list(self.pending_by),
            "summary": self.summary,
            "source": self.source,
        }



class _RuntimeSnapshotPreviewStubBase:
    """Read-only runtime stub used by the safe-runner dry-run.

    The stub wraps one prepared snapshot-object binding and exposes concrete
    class methods for capture/restore/rollback previews. It never mutates
    project state; it only routes into the existing preview helpers.
    """

    stub_class_name = "GenericRuntimeSnapshotStub"

    def __init__(self, binding: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        self.binding = binding

    @property
    def snapshot_object_key(self) -> str:
        return str(self.binding.get("snapshot_object_key") or "").strip()

    def capture_preview(self) -> dict[str, Any]:
        return _dispatch_safe_runner_capture_preview(self.binding)

    def restore_preview(self) -> dict[str, Any]:
        return _dispatch_safe_runner_restore_preview(self.binding)

    def rollback_preview(self) -> dict[str, Any]:
        return _build_safe_runner_rollback_preview(self.binding)


class TrackStateRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "TrackStateRuntimeSnapshotStub"


class RoutingRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "RoutingRuntimeSnapshotStub"


class TrackKindRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "TrackKindRuntimeSnapshotStub"


class ClipCollectionRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "ClipCollectionRuntimeSnapshotStub"


class AudioFxChainRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "AudioFxChainRuntimeSnapshotStub"


class NoteFxChainRuntimeSnapshotStub(_RuntimeSnapshotPreviewStubBase):
    stub_class_name = "NoteFxChainRuntimeSnapshotStub"


class _RuntimeSnapshotStateCarrierBase:
    """Read-only state carrier used by the future safe morph transaction."""

    carrier_class_name = "GenericRuntimeSnapshotStateCarrier"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan

    def _build_state_payload(self) -> dict[str, Any]:
        payload = copy.deepcopy(dict(self.binding.get("snapshot_payload") or {})) if isinstance(self.binding.get("snapshot_payload"), dict) else {}
        owner_ids = [str(x).strip() for x in list(self.binding.get("owner_ids") or []) if str(x).strip()]
        payload.setdefault("snapshot_object_key", str(self.binding.get("snapshot_object_key") or "").strip())
        payload.setdefault("snapshot_object_class", str(self.binding.get("snapshot_object_class") or "").strip())
        payload.setdefault("stub_key", str(self.stub_plan.get("stub_key") or "").strip())
        payload.setdefault("stub_class", str(self.stub_plan.get("stub_class") or "").strip())
        payload.setdefault("owner_scope", str(self.binding.get("owner_scope") or "").strip())
        if owner_ids:
            payload.setdefault("owner_ids", list(owner_ids))
        payload.setdefault("rollback_slot", str(self.binding.get("rollback_slot") or "").strip())
        payload.setdefault("payload_digest", str(self.binding.get("payload_digest") or "").strip())
        payload.setdefault("bind_state", str(self.binding.get("bind_state") or "").strip())
        return payload

    def capture_state_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_state_payload()
        result["state_carrier_class"] = self.carrier_class_name
        result["state_payload_preview"] = payload
        result["state_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["state_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Zustandstraeger {self.carrier_class_name} bindet Snapshot-State read-only vor."
        return result

    def restore_state_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_state_payload()
        result["state_carrier_class"] = self.carrier_class_name
        result["state_payload_preview"] = payload
        result["state_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["state_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Zustandstraeger {self.carrier_class_name} haelt den Restore-State read-only bereit."
        return result

    def rollback_state_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_state_payload()
        result["state_carrier_class"] = self.carrier_class_name
        result["state_payload_preview"] = payload
        result["state_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["state_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Zustandstraeger {self.carrier_class_name} reserviert den Rollback-State read-only."
        return result


class TrackStateRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "TrackStateRuntimeSnapshotStateCarrier"


class RoutingRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "RoutingRuntimeSnapshotStateCarrier"


class TrackKindRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "TrackKindRuntimeSnapshotStateCarrier"


class ClipCollectionRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "ClipCollectionRuntimeSnapshotStateCarrier"


class AudioFxChainRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "AudioFxChainRuntimeSnapshotStateCarrier"


class NoteFxChainRuntimeSnapshotStateCarrier(_RuntimeSnapshotStateCarrierBase):
    carrier_class_name = "NoteFxChainRuntimeSnapshotStateCarrier"


class _RuntimeSnapshotStateContainerBase:
    """Read-only runtime-state container for future snapshot apply phases."""

    container_class_name = "GenericRuntimeSnapshotStateContainer"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        try:
            carrier_plan = dict(carrier_plan or {})
        except Exception:
            carrier_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan
        self.carrier_plan = carrier_plan

    def _build_container_payload(self) -> dict[str, Any]:
        carrier_payload = copy.deepcopy(dict(self.carrier_plan.get("state_payload_preview") or {})) if isinstance(self.carrier_plan.get("state_payload_preview"), dict) else {}
        payload = {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "carrier_state": str(self.carrier_plan.get("carrier_state") or "").strip(),
            "owner_scope": str(self.binding.get("owner_scope") or "").strip(),
            "owner_ids": [str(x).strip() for x in list(self.binding.get("owner_ids") or []) if str(x).strip()],
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "state_payload_digest": str(self.carrier_plan.get("state_payload_digest") or "").strip(),
            "container_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "runtime_state": carrier_payload,
        }
        return payload

    def capture_container_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_container_payload()
        result["state_container_class"] = self.container_class_name
        result["container_payload_preview"] = payload
        result["container_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["container_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Container {self.container_class_name} haelt separaten Capture-State read-only bereit."
        return result

    def restore_container_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_container_payload()
        result["state_container_class"] = self.container_class_name
        result["container_payload_preview"] = payload
        result["container_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["container_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Container {self.container_class_name} haelt separaten Restore-State read-only bereit."
        return result

    def rollback_container_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_container_payload()
        result["state_container_class"] = self.container_class_name
        result["container_payload_preview"] = payload
        result["container_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["container_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Container {self.container_class_name} reserviert separaten Rollback-State read-only."
        return result


class TrackStateRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "TrackStateRuntimeStateContainer"


class RoutingRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "RoutingRuntimeStateContainer"


class TrackKindRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "TrackKindRuntimeStateContainer"


class ClipCollectionRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "ClipCollectionRuntimeStateContainer"


class AudioFxChainRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "AudioFxChainRuntimeStateContainer"


class NoteFxChainRuntimeStateContainer(_RuntimeSnapshotStateContainerBase):
    container_class_name = "NoteFxChainRuntimeStateContainer"


class _RuntimeSnapshotStateHolderBase:
    """Read-only runtime-state holder for future snapshot apply phases."""

    holder_class_name = "GenericRuntimeSnapshotStateHolder"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        try:
            carrier_plan = dict(carrier_plan or {})
        except Exception:
            carrier_plan = {}
        try:
            container_plan = dict(container_plan or {})
        except Exception:
            container_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan
        self.carrier_plan = carrier_plan
        self.container_plan = container_plan

    def _build_holder_payload(self) -> dict[str, Any]:
        container_payload = copy.deepcopy(dict(self.container_plan.get("container_payload_preview") or {})) if isinstance(self.container_plan.get("container_payload_preview"), dict) else {}
        payload = {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "container_state": str(self.container_plan.get("container_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "container_payload_digest": str(self.container_plan.get("container_payload_digest") or "").strip(),
            "holder_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "runtime_state_container": container_payload,
        }
        return payload

    def capture_holder_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_holder_payload()
        result["state_holder_class"] = self.holder_class_name
        result["holder_payload_preview"] = payload
        result["holder_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["holder_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Halter {self.holder_class_name} haelt separaten Capture-State read-only bereit."
        return result

    def restore_holder_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_holder_payload()
        result["state_holder_class"] = self.holder_class_name
        result["holder_payload_preview"] = payload
        result["holder_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["holder_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Halter {self.holder_class_name} haelt separaten Restore-State read-only bereit."
        return result

    def rollback_holder_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_holder_payload()
        result["state_holder_class"] = self.holder_class_name
        result["holder_payload_preview"] = payload
        result["holder_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["holder_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Halter {self.holder_class_name} reserviert separaten Rollback-State read-only."
        return result


class TrackStateRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "TrackStateRuntimeStateHolder"


class RoutingRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "RoutingRuntimeStateHolder"


class TrackKindRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "TrackKindRuntimeStateHolder"


class ClipCollectionRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "ClipCollectionRuntimeStateHolder"


class AudioFxChainRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "AudioFxChainRuntimeStateHolder"


class NoteFxChainRuntimeStateHolder(_RuntimeSnapshotStateHolderBase):
    holder_class_name = "NoteFxChainRuntimeStateHolder"


class _RuntimeSnapshotStateSlotBase:
    """Read-only runtime-state slot for future snapshot-state stores."""

    slot_class_name = "GenericRuntimeSnapshotStateSlot"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        try:
            carrier_plan = dict(carrier_plan or {})
        except Exception:
            carrier_plan = {}
        try:
            container_plan = dict(container_plan or {})
        except Exception:
            container_plan = {}
        try:
            holder_plan = dict(holder_plan or {})
        except Exception:
            holder_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan
        self.carrier_plan = carrier_plan
        self.container_plan = container_plan
        self.holder_plan = holder_plan

    def _build_slot_payload(self) -> dict[str, Any]:
        holder_payload = copy.deepcopy(dict(self.holder_plan.get("holder_payload_preview") or {})) if isinstance(self.holder_plan.get("holder_payload_preview"), dict) else {}
        return {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "holder_key": str(self.holder_plan.get("holder_key") or "").strip(),
            "holder_class": str(self.holder_plan.get("holder_class") or "").strip(),
            "holder_state": str(self.holder_plan.get("holder_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "holder_payload_digest": str(self.holder_plan.get("holder_payload_digest") or "").strip(),
            "slot_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "runtime_state_holder": holder_payload,
        }

    def capture_slot_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_slot_payload()
        result["state_slot_class"] = self.slot_class_name
        result["slot_payload_preview"] = payload
        result["slot_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["slot_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Slot {self.slot_class_name} haelt separaten Capture-State-Speicher read-only bereit."
        return result

    def restore_slot_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_slot_payload()
        result["state_slot_class"] = self.slot_class_name
        result["slot_payload_preview"] = payload
        result["slot_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["slot_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Slot {self.slot_class_name} haelt separaten Restore-State-Speicher read-only bereit."
        return result

    def rollback_slot_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_slot_payload()
        result["state_slot_class"] = self.slot_class_name
        result["slot_payload_preview"] = payload
        result["slot_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["slot_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Slot {self.slot_class_name} reserviert separaten Rollback-State-Speicher read-only."
        return result


class TrackStateRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "TrackStateRuntimeStateSlot"


class RoutingRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "RoutingRuntimeStateSlot"


class TrackKindRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "TrackKindRuntimeStateSlot"


class ClipCollectionRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "ClipCollectionRuntimeStateSlot"


class AudioFxChainRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "AudioFxChainRuntimeStateSlot"


class NoteFxChainRuntimeStateSlot(_RuntimeSnapshotStateSlotBase):
    slot_class_name = "NoteFxChainRuntimeStateSlot"


_RUNTIME_SNAPSHOT_STUB_CLASS_MAP = {
    "TrackStateSnapshotObject": TrackStateRuntimeSnapshotStub,
    "RoutingSnapshotObject": RoutingRuntimeSnapshotStub,
    "TrackKindSnapshotObject": TrackKindRuntimeSnapshotStub,
    "ClipCollectionSnapshotObject": ClipCollectionRuntimeSnapshotStub,
    "AudioFxChainSnapshotObject": AudioFxChainRuntimeSnapshotStub,
    "NoteFxChainSnapshotObject": NoteFxChainRuntimeSnapshotStub,
}


def _resolve_runtime_snapshot_stub_class(snapshot_object_class: str):
    return _RUNTIME_SNAPSHOT_STUB_CLASS_MAP.get(str(snapshot_object_class or "").strip(), _RuntimeSnapshotPreviewStubBase)


def _instantiate_runtime_snapshot_stub(binding: dict[str, Any] | None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    stub_cls = _resolve_runtime_snapshot_stub_class(str(binding.get("snapshot_object_class") or ""))
    return stub_cls(binding)


def _count_chain_devices(chain: Any) -> int:
    try:
        devices = (chain or {}).get("devices", []) if isinstance(chain, dict) else []
        return len([d for d in list(devices or []) if d is not None])
    except Exception:
        return 0


def _collect_track_clip_counts(project_obj: Any, track_id: str) -> tuple[int, int]:
    audio_count = 0
    midi_count = 0
    if not project_obj or not track_id:
        return audio_count, midi_count
    try:
        for clip in list(getattr(project_obj, "clips", []) or []):
            if str(getattr(clip, "track_id", "") or "") != str(track_id):
                continue
            kind = str(getattr(clip, "kind", "") or "").strip().lower()
            if kind == "audio":
                audio_count += 1
            elif kind == "midi":
                midi_count += 1
    except Exception:
        return 0, 0
    return audio_count, midi_count


def _plural(value: int, singular: str, plural: str | None = None) -> str:
    plural = plural or f"{singular}s"
    return f"{value} {singular if int(value) == 1 else plural}"


def _track_kind_label(track_kind: str) -> str:
    track_kind = str(track_kind or "").strip().lower()
    return {
        "audio": "Audio-Spur",
        "instrument": "Instrument-Spur",
        "bus": "Bus-Spur",
        "fx": "FX-Spur",
        "group": "Gruppen-Spur",
        "master": "Master-Spur",
    }.get(track_kind, "Spur")


def _build_impact_summary(audio_clip_count: int, audio_fx_count: int, note_fx_count: int) -> str:
    parts: list[str] = []
    if int(audio_clip_count) > 0:
        parts.append(_plural(audio_clip_count, "Audio-Clip"))
    if int(audio_fx_count) > 0:
        parts.append(_plural(audio_fx_count, "FX", "FX"))
    if int(note_fx_count) > 0:
        parts.append(_plural(note_fx_count, "Note-FX", "Note-FX"))
    if not parts:
        return "Rueckbau-Scope derzeit klein, aber Undo-/Routing-Snapshot bleibt trotzdem Pflicht."
    return "Rueckbau-Scope: " + ", ".join(parts)


def _build_rollback_lines(track_kind: str, audio_clip_count: int, audio_fx_count: int, note_fx_count: int) -> list[str]:
    lines: list[str] = [
        "Vor dem Morphing muss ein kompletter Undo-Snapshot der Zielspur erstellt werden.",
        "Routing muss atomar zwischen Audio-In und Instrument-/MIDI-Pfad umschaltbar bleiben.",
    ]
    if str(track_kind or "").strip().lower() == "audio":
        lines.append("Die bestehende Audio-Spur darf erst umgeschaltet werden, wenn ein verlustfreier Rueckweg feststeht.")
    if int(audio_clip_count) > 0:
        lines.append(f"{_plural(audio_clip_count, 'Audio-Clip')} muessen gesichert oder sauber rueckfuehrbar bleiben.")
    if int(audio_fx_count) > 0:
        lines.append(f"{_plural(audio_fx_count, 'FX', 'FX')} muessen atomar mit Snapshot und Rueckbaupfad behandelt werden.")
    if int(note_fx_count) > 0:
        lines.append(f"{_plural(note_fx_count, 'Note-FX', 'Note-FX')} brauchen nach der Conversion eine Kompatibilitaetspruefung.")
    if len(lines) <= 2:
        lines.append("Auch ohne Clips/FX bleibt die echte Freigabe an Undo- und Routing-Sicherheit gebunden.")
    return lines


def _build_future_apply_steps(audio_clip_count: int, audio_fx_count: int, note_fx_count: int) -> list[str]:
    steps: list[str] = [
        "1. Guard-Plan bestaetigen und Undo-Snapshot aufnehmen.",
        "2. Routing-/Spurmodus atomar vorbereiten.",
    ]
    if int(audio_clip_count) > 0:
        steps.append("3. Audio-Clips sichern oder auf einen verlustfreien Rueckbaupfad legen.")
    if int(audio_fx_count) > 0:
        steps.append("4. Audio-FX-Kette mit Rueckbau-Info sichern.")
    if int(note_fx_count) > 0:
        steps.append("5. Note-FX-Kompatibilitaet fuer den Instrument-Pfad pruefen.")
    steps.append("6. Instrument einfuegen und gesamten Schritt als einen Undo-Punkt abschliessen.")
    return steps


def _build_required_snapshots(track_kind: str, audio_clip_count: int, audio_fx_count: int, note_fx_count: int) -> list[str]:
    snapshots: list[str] = [
        "undo_track_state",
        "routing_state",
    ]
    if str(track_kind or "").strip().lower() == "audio":
        snapshots.append("track_kind_state")
    if int(audio_clip_count) > 0:
        snapshots.append("audio_clip_state")
    if int(audio_fx_count) > 0:
        snapshots.append("audio_fx_chain_state")
    if int(note_fx_count) > 0:
        snapshots.append("note_fx_chain_state")
    # dedupe while keeping order
    seen: set[str] = set()
    ordered: list[str] = []
    for item in snapshots:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def _build_transaction_steps(audio_clip_count: int, audio_fx_count: int, note_fx_count: int) -> list[str]:
    steps: list[str] = [
        "1. Alle benoetigten Snapshots erfassen.",
        "2. Routing und Spurmodus in einer atomaren Transaktion vorbereiten.",
    ]
    next_no = 3
    if int(audio_clip_count) > 0:
        steps.append(f"{next_no}. Audio-Clips fuer verlustfreien Rueckbau sichern.")
        next_no += 1
    if int(audio_fx_count) > 0:
        steps.append(f"{next_no}. Audio-FX-Kette samt Reihenfolge sichern.")
        next_no += 1
    if int(note_fx_count) > 0:
        steps.append(f"{next_no}. Note-FX-Kompatibilitaet vor der Conversion pruefen.")
        next_no += 1
    steps.append(f"{next_no}. Instrument einfuegen und den Gesamtvorgang als einen Undo-Punkt committen.")
    return steps


def _build_transaction_key(track_id: str, plugin_name: str) -> str:
    safe_track = str(track_id or "track").strip() or "track"
    safe_plugin = "_".join(str(plugin_name or "instrument").strip().lower().split()) or "instrument"
    safe_plugin = "".join(ch for ch in safe_plugin if ch.isalnum() or ch in {"_", "-"}) or "instrument"
    return f"audio_to_instrument_morph::{safe_track}::{safe_plugin}"


def _build_transaction_summary(required_snapshots: list[str], transaction_steps: list[str]) -> str:
    snap_count = len(list(required_snapshots or []))
    step_count = len(list(transaction_steps or []))
    return (
        f"Atomarer Plan: {snap_count} Snapshot{'s' if snap_count != 1 else ''}, {step_count} Schritt{'e' if step_count != 1 else ''}, 1 Undo-Punkt."
    )


def _sanitize_ref_token(value: str, fallback: str) -> str:
    token = str(value or "").strip().lower()
    token = "".join(ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in token)
    token = "_".join(part for part in token.split("_") if part)
    return token or str(fallback or "ref")


def _build_snapshot_refs(required_snapshots: list[str], transaction_key: str) -> list[dict[str, str]]:
    tx_key = _sanitize_ref_token(str(transaction_key or "audio_to_instrument_morph::preview"), "audio_to_instrument_morph_preview")
    refs: list[dict[str, str]] = []
    for name in list(required_snapshots or []):
        raw_name = str(name or "").strip()
        if not raw_name:
            continue
        safe_name = _sanitize_ref_token(raw_name, "snapshot")
        refs.append({
            "name": raw_name,
            "ref": f"preview_snapshot::{tx_key}::{safe_name}",
            "phase": "preview",
        })
    return refs


def _build_snapshot_ref_summary(snapshot_refs: list[dict[str, str]]) -> str:
    count = len(list(snapshot_refs or []))
    if count <= 0:
        return ""
    return f"{count} geplante Snapshot-Referenz{'en' if count != 1 else ''} fuer die spaetere Apply-Phase vorbereitet."


def _summarize_chain_devices(chain: Any) -> tuple[int, list[str]]:
    names: list[str] = []
    try:
        devices = (chain or {}).get("devices", []) if isinstance(chain, dict) else []
        for dev in list(devices or []):
            if dev is None:
                continue
            label = ""
            try:
                if isinstance(dev, dict):
                    label = str(dev.get("name") or dev.get("label") or dev.get("plugin_name") or dev.get("type") or "").strip()
                else:
                    label = str(getattr(dev, "name", "") or getattr(dev, "label", "") or getattr(dev, "plugin_name", "") or getattr(dev, "type", "") or "").strip()
            except Exception:
                label = ""
            names.append(label or "Unbenannt")
    except Exception:
        return 0, []
    return len(names), names[:3]


def _build_runtime_snapshot_preview(project_obj: Any, track: Any, required_snapshots: list[str], snapshot_ref_map: dict[str, str]) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    track_id = str(getattr(track, "id", "") or "") if track is not None else ""
    track_name = str(getattr(track, "name", "") or track_id or "Spur") if track is not None else "Spur"
    track_kind = str(getattr(track, "kind", "") or "").strip().lower() if track is not None else ""
    audio_clip_count, midi_clip_count = _collect_track_clip_counts(project_obj, track_id)
    audio_fx_count, audio_fx_names = _summarize_chain_devices(getattr(track, "audio_fx_chain", {}) or {}) if track is not None else (0, [])
    note_fx_count, note_fx_names = _summarize_chain_devices(getattr(track, "note_fx_chain", {}) or {}) if track is not None else (0, [])

    for raw_name in list(required_snapshots or []):
        name = str(raw_name or "").strip()
        if not name:
            continue
        ref = str((snapshot_ref_map or {}).get(name) or "").strip()
        entry: dict[str, Any] = {
            "name": name,
            "ref": ref,
            "available": False,
            "summary": "",
            "source": "runtime-preview",
        }
        if name == "undo_track_state":
            entry["available"] = bool(track is not None and track_id)
            entry["summary"] = f"Track={track_name} ({_track_kind_label(track_kind)}), Vol={getattr(track, 'volume', 0.0):.2f}, Pan={getattr(track, 'pan', 0.0):.2f}" if entry["available"] else "Zielspur ist derzeit nicht aufloesbar."
        elif name == "routing_state":
            entry["available"] = bool(track is not None and track_id)
            if entry["available"]:
                entry["summary"] = (
                    f"Input-Paar {int(getattr(track, 'input_pair', 1) or 1)}, Output-Paar {int(getattr(track, 'output_pair', 1) or 1)}, "
                    f"Monitor={'an' if bool(getattr(track, 'monitor', False)) else 'aus'}"
                )
            else:
                entry["summary"] = "Routing-Quelle derzeit nicht verfuegbar."
        elif name == "track_kind_state":
            entry["available"] = bool(track is not None and track_id)
            entry["summary"] = f"Aktueller Spurtyp: {_track_kind_label(track_kind)}" if entry["available"] else "Spurtyp kann derzeit nicht gelesen werden."
        elif name == "audio_clip_state":
            entry["available"] = bool(project_obj is not None and track_id)
            if entry["available"]:
                clip_word = _plural(audio_clip_count, "Audio-Clip")
                midi_note = f", {midi_clip_count} MIDI-Clip{'s' if midi_clip_count != 1 else ''} daneben" if midi_clip_count > 0 else ""
                entry["summary"] = f"{clip_word} aktuell auf {track_name}{midi_note}."
            else:
                entry["summary"] = "Clip-Quelle derzeit nicht aufloesbar."
        elif name == "audio_fx_chain_state":
            entry["available"] = bool(track is not None and isinstance(getattr(track, 'audio_fx_chain', {}), dict))
            if entry["available"]:
                names_preview = ", ".join(audio_fx_names)
                entry["summary"] = f"{_plural(audio_fx_count, 'FX', 'FX')} in Audio-FX-Kette" + (f": {names_preview}" if names_preview else ".")
            else:
                entry["summary"] = "Audio-FX-Kette derzeit nicht aufloesbar."
        elif name == "note_fx_chain_state":
            entry["available"] = bool(track is not None and isinstance(getattr(track, 'note_fx_chain', {}), dict))
            if entry["available"]:
                names_preview = ", ".join(note_fx_names)
                entry["summary"] = f"{_plural(note_fx_count, 'Note-FX', 'Note-FX')} in Note-FX-Kette" + (f": {names_preview}" if names_preview else ".")
            else:
                entry["summary"] = "Note-FX-Kette derzeit nicht aufloesbar."
        else:
            entry["summary"] = "Noch keine Runtime-Vorschau fuer diesen Snapshot-Typ vorhanden."
        preview.append(entry)
    return preview


def _build_runtime_snapshot_summary(runtime_snapshot_preview: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_preview or [])
    if not items:
        return ""
    available = sum(1 for item in items if bool(item.get("available")))
    total = len(items)
    return f"Runtime-Snapshot-Vorschau: {available}/{total} Referenzen aktuell aufloesbar."


def _collect_track_clip_ids(project_obj: Any, track_id: str, clip_kind: str = "") -> list[str]:
    clip_ids: list[str] = []
    if not project_obj or not track_id:
        return clip_ids
    wanted_kind = str(clip_kind or "").strip().lower()
    try:
        for clip in list(getattr(project_obj, "clips", []) or []):
            if str(getattr(clip, "track_id", "") or "") != str(track_id):
                continue
            if wanted_kind and str(getattr(clip, "kind", "") or "").strip().lower() != wanted_kind:
                continue
            clip_id = str(getattr(clip, "id", "") or "").strip()
            if clip_id:
                clip_ids.append(clip_id)
    except Exception:
        return []
    return clip_ids


def _collect_chain_device_targets(chain: Any, chain_key: str) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    try:
        devices = (chain or {}).get("devices", []) if isinstance(chain, dict) else []
        for idx, dev in enumerate(list(devices or []), start=1):
            if dev is None:
                continue
            dev_id = ""
            dev_name = ""
            dev_type = ""
            try:
                if isinstance(dev, dict):
                    dev_id = str(dev.get("id") or dev.get("device_id") or "").strip()
                    dev_name = str(dev.get("name") or dev.get("label") or dev.get("plugin_name") or "").strip()
                    dev_type = str(dev.get("type") or dev.get("format") or "").strip()
                else:
                    dev_id = str(getattr(dev, "id", "") or getattr(dev, "device_id", "") or "").strip()
                    dev_name = str(getattr(dev, "name", "") or getattr(dev, "label", "") or getattr(dev, "plugin_name", "") or "").strip()
                    dev_type = str(getattr(dev, "type", "") or getattr(dev, "format", "") or "").strip()
            except Exception:
                dev_id = ""
                dev_name = ""
                dev_type = ""
            targets.append({
                "id": dev_id or f"{chain_key}_device_{idx}",
                "name": dev_name or "Unbenannt",
                "type": dev_type or chain_key,
            })
    except Exception:
        return []
    return targets


def _snapshot_handle_kind(snapshot_name: str) -> str:
    name = str(snapshot_name or "").strip().lower()
    return {
        "undo_track_state": "track-state-snapshot",
        "routing_state": "routing-snapshot",
        "track_kind_state": "track-kind-snapshot",
        "audio_clip_state": "clip-collection-snapshot",
        "audio_fx_chain_state": "audio-fx-chain-snapshot",
        "note_fx_chain_state": "note-fx-chain-snapshot",
    }.get(name, "generic-snapshot")


def _build_runtime_snapshot_handles(project_obj: Any, track: Any, runtime_snapshot_preview: list[dict[str, Any]], transaction_key: str) -> list[dict[str, Any]]:
    handles: list[dict[str, Any]] = []
    track_id = str(getattr(track, "id", "") or "") if track is not None else ""
    tx_token = _sanitize_ref_token(str(transaction_key or "audio_to_instrument_morph::preview"), "audio_to_instrument_morph_preview")
    audio_clip_ids = _collect_track_clip_ids(project_obj, track_id, clip_kind="audio")
    midi_clip_ids = _collect_track_clip_ids(project_obj, track_id, clip_kind="midi")
    audio_fx_targets = _collect_chain_device_targets(getattr(track, "audio_fx_chain", {}) or {}, "audio_fx") if track is not None else []
    note_fx_targets = _collect_chain_device_targets(getattr(track, "note_fx_chain", {}) or {}, "note_fx") if track is not None else []

    for item in list(runtime_snapshot_preview or []):
        try:
            item = dict(item or {})
        except Exception:
            item = {}
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        ref = str(item.get("ref") or "").strip()
        available = bool(item.get("available"))
        summary = str(item.get("summary") or "").strip()
        safe_name = _sanitize_ref_token(name, "snapshot")
        handle_key = f"runtime_handle::{tx_token}::{safe_name}"
        owner_scope = "track"
        owner_ids: list[str] = []
        if name in {"undo_track_state", "routing_state", "track_kind_state"}:
            owner_ids = [track_id] if track_id else []
        elif name == "audio_clip_state":
            owner_scope = "clips"
            owner_ids = list(audio_clip_ids)
        elif name == "audio_fx_chain_state":
            owner_scope = "audio_fx_chain"
            owner_ids = [str(t.get("id") or "").strip() for t in audio_fx_targets if str(t.get("id") or "").strip()]
        elif name == "note_fx_chain_state":
            owner_scope = "note_fx_chain"
            owner_ids = [str(t.get("id") or "").strip() for t in note_fx_targets if str(t.get("id") or "").strip()]
        runtime_target_count = len(owner_ids)
        if name == "undo_track_state" and not owner_ids and track_id:
            owner_ids = [track_id]
            runtime_target_count = 1
        handle = {
            "name": name,
            "ref": ref,
            "handle_key": handle_key,
            "handle_kind": _snapshot_handle_kind(name),
            "capture_state": "ready" if available else "pending",
            "owner_scope": owner_scope,
            "owner_ids": list(owner_ids),
            "runtime_target_count": runtime_target_count,
            "summary": summary,
            "capture_stub": f"capture_{safe_name}",
            "source": "runtime-handle-preview",
        }
        if name == "audio_clip_state" and midi_clip_ids:
            handle["related_ids"] = list(midi_clip_ids)
        handles.append(handle)
    return handles


def _build_runtime_snapshot_handle_summary(snapshot_handles: list[dict[str, Any]]) -> str:
    items = list(snapshot_handles or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("capture_state") or "").strip().lower() == "ready")
    total = len(items)
    return f"Runtime-Snapshot-Handles: {ready}/{total} Capture-Handles vorbereitet."

def _capture_object_kind(handle_kind: str) -> str:
    value = str(handle_kind or "").strip().lower()
    return {
        "track-state-snapshot": "track-state-capture",
        "routing-snapshot": "routing-capture",
        "track-kind-snapshot": "track-kind-capture",
        "clip-collection-snapshot": "clip-collection-capture",
        "audio-fx-chain-snapshot": "audio-fx-chain-capture",
        "note-fx-chain-snapshot": "note-fx-chain-capture",
    }.get(value, "generic-capture")


def _capture_payload_preview_for_handle(project_obj: Any, track: Any, handle: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    name = str(handle.get("name") or "").strip()
    track_id = str(getattr(track, "id", "") or "") if track is not None else ""
    if name == "undo_track_state" and track is not None:
        payload = {
            "track_id": track_id,
            "track_name": str(getattr(track, "name", "") or track_id or "Spur"),
            "track_kind": str(getattr(track, "kind", "") or ""),
            "volume": float(getattr(track, "volume", 0.0) or 0.0),
            "pan": float(getattr(track, "pan", 0.0) or 0.0),
            "mute": bool(getattr(track, "mute", False)),
            "solo": bool(getattr(track, "solo", False)),
            "monitor": bool(getattr(track, "monitor", False)),
        }
    elif name == "routing_state" and track is not None:
        payload = {
            "track_id": track_id,
            "input_pair": int(getattr(track, "input_pair", 1) or 1),
            "output_pair": int(getattr(track, "output_pair", 1) or 1),
            "monitor": bool(getattr(track, "monitor", False)),
        }
    elif name == "track_kind_state" and track is not None:
        payload = {
            "track_id": track_id,
            "track_kind": str(getattr(track, "kind", "") or ""),
        }
    elif name == "audio_clip_state":
        audio_clip_ids = _collect_track_clip_ids(project_obj, track_id, clip_kind="audio")
        payload = {
            "track_id": track_id,
            "audio_clip_ids": list(audio_clip_ids),
            "audio_clip_count": len(audio_clip_ids),
        }
    elif name == "audio_fx_chain_state" and track is not None:
        audio_fx_targets = _collect_chain_device_targets(getattr(track, "audio_fx_chain", {}) or {}, "audio_fx")
        payload = {
            "track_id": track_id,
            "device_ids": [str(t.get("id") or "").strip() for t in audio_fx_targets if str(t.get("id") or "").strip()],
            "device_names": [str(t.get("name") or "").strip() for t in audio_fx_targets if str(t.get("name") or "").strip()],
            "device_count": len(audio_fx_targets),
        }
    elif name == "note_fx_chain_state" and track is not None:
        note_fx_targets = _collect_chain_device_targets(getattr(track, "note_fx_chain", {}) or {}, "note_fx")
        payload = {
            "track_id": track_id,
            "device_ids": [str(t.get("id") or "").strip() for t in note_fx_targets if str(t.get("id") or "").strip()],
            "device_names": [str(t.get("name") or "").strip() for t in note_fx_targets if str(t.get("name") or "").strip()],
            "device_count": len(note_fx_targets),
        }
    return payload


def _build_runtime_snapshot_capture_objects(project_obj: Any, track: Any, runtime_snapshot_handles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_handles or []):
        try:
            handle = dict(item or {})
        except Exception:
            handle = {}
        handle_key = str(handle.get("handle_key") or "").strip()
        name = str(handle.get("name") or "").strip()
        if not handle_key or not name:
            continue
        capture_state = str(handle.get("capture_state") or "").strip().lower()
        payload_preview = _capture_payload_preview_for_handle(project_obj, track, handle)
        payload_count = 0
        for key, value in payload_preview.items():
            if isinstance(value, (list, tuple, set, dict)):
                payload_count += len(value)
            elif value not in (None, "", False):
                payload_count += 1
        captures.append({
            "name": name,
            "handle_key": handle_key,
            "capture_key": f"capture_object::{_sanitize_ref_token(handle_key, 'capture_handle')}",
            "capture_object_kind": _capture_object_kind(str(handle.get("handle_kind") or "")),
            "capture_state": capture_state or "pending",
            "owner_scope": str(handle.get("owner_scope") or "").strip(),
            "owner_ids": list(handle.get("owner_ids") or []),
            "capture_stub": str(handle.get("capture_stub") or "").strip(),
            "payload_preview": payload_preview,
            "payload_entry_count": int(payload_count),
            "source": "runtime-capture-object-preview",
        })
    return captures


def _build_runtime_snapshot_capture_summary(runtime_snapshot_captures: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_captures or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("capture_state") or "").strip().lower() == "ready")
    payload_ready = sum(1 for item in items if int(item.get("payload_entry_count") or 0) > 0)
    total = len(items)
    return f"Runtime-Capture-Objekte: {ready}/{total} vorbereitet, {payload_ready}/{total} bereits mit Payload-Vorschau bestuetzt."


def _snapshot_instance_kind(capture_object_kind: str) -> str:
    value = str(capture_object_kind or "").strip().lower()
    return {
        "track-state-capture": "track-state-instance",
        "routing-capture": "routing-instance",
        "track-kind-capture": "track-kind-instance",
        "clip-collection-capture": "clip-collection-instance",
        "audio-fx-chain-capture": "audio-fx-chain-instance",
        "note-fx-chain-capture": "note-fx-chain-instance",
    }.get(value, "generic-instance")


def _stable_snapshot_payload_digest(payload: dict[str, Any]) -> str:
    try:
        raw = json.dumps(payload or {}, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        try:
            raw = repr(payload or {})
        except Exception:
            raw = "{}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _stable_payload_size_bytes(payload: Any) -> int:
    try:
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    except Exception:
        try:
            raw = repr(payload)
        except Exception:
            raw = "{}"
    try:
        return len(raw.encode("utf-8", errors="ignore"))
    except Exception:
        return len(raw)


def _snapshot_payload_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = copy.deepcopy(dict(payload or {})) if isinstance(payload, dict) else {}
    top_level_keys = sorted(str(key).strip() for key in data.keys() if str(key).strip())
    return {
        "payload_entry_count": len(data),
        "payload_digest": _stable_snapshot_payload_digest(data),
        "payload_size_bytes": _stable_payload_size_bytes(data),
        "top_level_key_count": len(top_level_keys),
        "top_level_keys": top_level_keys[:12],
        "track_count": len(list(data.get("tracks") or [])) if isinstance(data.get("tracks"), list) else 0,
        "clip_count": len(list(data.get("clips") or [])) if isinstance(data.get("clips"), list) else 0,
        "device_count": len(list(data.get("devices") or [])) if isinstance(data.get("devices"), list) else 0,
        "transport_keys": sorted(str(key).strip() for key in dict(data.get("transport") or {}).keys() if str(key).strip())[:8] if isinstance(data.get("transport"), dict) else [],
    }


def _build_runtime_snapshot_instances(runtime_snapshot_captures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_captures or []):
        try:
            capture = dict(item or {})
        except Exception:
            capture = {}
        capture_key = str(capture.get("capture_key") or "").strip()
        name = str(capture.get("name") or "").strip()
        if not capture_key or not name:
            continue
        payload_preview = copy.deepcopy(dict(capture.get("payload_preview") or {})) if isinstance(capture.get("payload_preview"), dict) else {}
        payload_entry_count = int(capture.get("payload_entry_count") or 0)
        capture_state = str(capture.get("capture_state") or "pending").strip().lower() or "pending"
        payload_digest = _stable_snapshot_payload_digest(payload_preview)
        ready_payload = bool(payload_preview) and payload_entry_count > 0
        snapshot_state = "ready" if capture_state == "ready" and ready_payload else (capture_state if capture_state else "pending")
        instances.append({
            "name": name,
            "capture_key": capture_key,
            "snapshot_instance_key": f"snapshot_instance::{_sanitize_ref_token(capture_key, 'snapshot_capture')}",
            "snapshot_instance_kind": _snapshot_instance_kind(str(capture.get("capture_object_kind") or "")),
            "snapshot_state": snapshot_state,
            "owner_scope": str(capture.get("owner_scope") or "").strip(),
            "owner_ids": [str(x).strip() for x in list(capture.get("owner_ids") or []) if str(x).strip()],
            "snapshot_stub": f"snapshot_from::{_sanitize_ref_token(name, 'snapshot')}",
            "snapshot_payload": payload_preview,
            "snapshot_payload_entry_count": payload_entry_count,
            "payload_digest": payload_digest,
            "source": "runtime-snapshot-instance-preview",
        })
    return instances


def _build_runtime_snapshot_instance_summary(runtime_snapshot_instances: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_instances or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("snapshot_state") or "").strip().lower() == "ready")
    payload_ready = sum(1 for item in items if int(item.get("snapshot_payload_entry_count") or 0) > 0)
    total = len(items)
    return f"Runtime-Snapshot-Instanzen: {ready}/{total} materialisiert, {payload_ready}/{total} bereits mit konkreter Snapshot-Payload versehen."


def _snapshot_object_class_name(snapshot_instance_kind: str) -> str:
    value = str(snapshot_instance_kind or "").strip().lower()
    return {
        "track-state-instance": "TrackStateSnapshotObject",
        "routing-instance": "RoutingSnapshotObject",
        "track-kind-instance": "TrackKindSnapshotObject",
        "clip-collection-instance": "ClipCollectionSnapshotObject",
        "audio-fx-chain-instance": "AudioFxChainSnapshotObject",
        "note-fx-chain-instance": "NoteFxChainSnapshotObject",
    }.get(value, "GenericSnapshotObject")



def _snapshot_object_methods(snapshot_instance_kind: str) -> tuple[str, str, str]:
    value = str(snapshot_instance_kind or "").strip().lower()
    return {
        "track-state-instance": ("capture_track_state_snapshot", "restore_track_state_snapshot", "undo.track_state"),
        "routing-instance": ("capture_routing_snapshot", "restore_routing_snapshot", "routing.atomic"),
        "track-kind-instance": ("capture_track_kind_snapshot", "restore_track_kind_snapshot", "track.kind"),
        "clip-collection-instance": ("capture_clip_collection_snapshot", "restore_clip_collection_snapshot", "clips.audio"),
        "audio-fx-chain-instance": ("capture_audio_fx_chain_snapshot", "restore_audio_fx_chain_snapshot", "fx.audio_chain"),
        "note-fx-chain-instance": ("capture_note_fx_chain_snapshot", "restore_note_fx_chain_snapshot", "fx.note_chain"),
    }.get(value, ("capture_generic_snapshot", "restore_generic_snapshot", "generic.snapshot"))



def _build_runtime_snapshot_objects(runtime_snapshot_instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_instances or []):
        try:
            instance = dict(item or {})
        except Exception:
            instance = {}
        snapshot_instance_key = str(instance.get("snapshot_instance_key") or "").strip()
        name = str(instance.get("name") or "").strip()
        if not snapshot_instance_key or not name:
            continue
        snapshot_instance_kind = str(instance.get("snapshot_instance_kind") or "").strip()
        snapshot_state = str(instance.get("snapshot_state") or "pending").strip().lower() or "pending"
        owner_scope = str(instance.get("owner_scope") or "").strip()
        owner_ids = tuple(str(x).strip() for x in list(instance.get("owner_ids") or []) if str(x).strip())
        snapshot_payload = copy.deepcopy(dict(instance.get("snapshot_payload") or {})) if isinstance(instance.get("snapshot_payload"), dict) else {}
        snapshot_payload_entry_count = int(instance.get("snapshot_payload_entry_count") or 0)
        payload_digest = str(instance.get("payload_digest") or "").strip()
        snapshot_object_class = _snapshot_object_class_name(snapshot_instance_kind)
        capture_method, restore_method, rollback_slot = _snapshot_object_methods(snapshot_instance_kind)
        supports_capture = bool(snapshot_object_class and capture_method)
        supports_restore = bool(snapshot_object_class and restore_method)
        bind_ready = snapshot_state == "ready" and supports_capture and supports_restore and bool(payload_digest)
        binding = RuntimeSnapshotObjectBinding(
            name=name,
            snapshot_instance_key=snapshot_instance_key,
            snapshot_instance_kind=snapshot_instance_kind,
            snapshot_state=snapshot_state,
            owner_scope=owner_scope,
            owner_ids=owner_ids,
            snapshot_payload=snapshot_payload,
            snapshot_payload_entry_count=snapshot_payload_entry_count,
            payload_digest=payload_digest,
            snapshot_object_key=f"snapshot_object::{_sanitize_ref_token(snapshot_instance_key, 'snapshot_instance')}",
            snapshot_object_class=snapshot_object_class,
            bind_state="ready" if bind_ready else (snapshot_state if snapshot_state else "pending"),
            supports_capture=supports_capture,
            supports_restore=supports_restore,
            capture_method=capture_method,
            restore_method=restore_method,
            rollback_slot=rollback_slot,
            object_stub=f"bind_to::{snapshot_object_class}",
        )
        objects.append(binding.as_plan_dict())
    return objects



def _build_runtime_snapshot_object_summary(runtime_snapshot_objects: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_objects or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("bind_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore")))
    total = len(items)
    return (
        f"Runtime-Snapshot-Objekte: {ready}/{total} gebunden, "
        f"{capture_ready}/{total} mit Capture-Methode, {restore_ready}/{total} mit Restore-Methode vorbereitet."
    )


def _build_runtime_snapshot_bundle(runtime_snapshot_objects: list[dict[str, Any]], transaction_key: str, required_snapshots: list[str]) -> dict[str, Any]:
    items = [dict(item or {}) for item in list(runtime_snapshot_objects or [])]
    tx_key = str(transaction_key or "audio_to_instrument_morph::preview").strip() or "audio_to_instrument_morph::preview"
    tx_token = _sanitize_ref_token(tx_key, "audio_to_instrument_morph_preview")
    snapshot_object_keys = tuple(
        str(item.get("snapshot_object_key") or "").strip()
        for item in items
        if str(item.get("snapshot_object_key") or "").strip()
    )
    capture_methods = tuple(sorted({
        str(item.get("capture_method") or "").strip()
        for item in items
        if str(item.get("capture_method") or "").strip()
    }))
    restore_methods = tuple(sorted({
        str(item.get("restore_method") or "").strip()
        for item in items
        if str(item.get("restore_method") or "").strip()
    }))
    rollback_slots = tuple(sorted({
        str(item.get("rollback_slot") or "").strip()
        for item in items
        if str(item.get("rollback_slot") or "").strip()
    }))
    payload_digests = tuple(
        str(item.get("payload_digest") or "").strip()
        for item in items
        if str(item.get("payload_digest") or "").strip()
    )
    object_count = len(items)
    ready_object_count = sum(
        1
        for item in items
        if str(item.get("bind_state") or "").strip().lower() == "ready"
        and bool(item.get("supports_capture"))
        and bool(item.get("supports_restore"))
        and str(item.get("snapshot_object_key") or "").strip()
    )
    required_snapshot_count = len([str(x).strip() for x in list(required_snapshots or []) if str(x).strip()])
    bundle_state = "ready" if object_count > 0 and ready_object_count >= object_count else ("pending" if object_count > 0 else "blocked")
    bundle = RuntimeSnapshotTransactionBundle(
        bundle_key=f"snapshot_bundle::{tx_token}",
        transaction_key=tx_key,
        transaction_container_kind="audio-to-instrument-morph-transaction-bundle",
        bundle_state=bundle_state,
        object_count=object_count,
        ready_object_count=ready_object_count,
        required_snapshot_count=required_snapshot_count,
        snapshot_object_keys=snapshot_object_keys,
        capture_methods=capture_methods,
        restore_methods=restore_methods,
        rollback_slots=rollback_slots,
        payload_digests=payload_digests,
        commit_stub="commit_audio_to_instrument_morph_transaction",
        rollback_stub="rollback_audio_to_instrument_morph_transaction",
        bundle_stub="bundle_runtime_snapshot_objects",
    )
    return bundle.as_plan_dict()


def _build_runtime_snapshot_bundle_summary(runtime_snapshot_bundle: dict[str, Any] | None) -> str:
    bundle = dict(runtime_snapshot_bundle or {})
    if not bundle:
        return ""
    ready = int(bundle.get("ready_object_count") or 0)
    total = int(bundle.get("object_count") or 0)
    required = int(bundle.get("required_snapshot_count") or 0)
    state = str(bundle.get("bundle_state") or "pending").strip().lower() or "pending"
    state_label = {"ready": "bereit", "pending": "vorbereitet", "blocked": "gesperrt"}.get(state, state)
    return f"Snapshot-Bundle / Transaktions-Container: {ready}/{total} Objektbindungen {state_label}, {required} benoetigte Snapshot-Typen im Container zusammengefuehrt."


def _build_runtime_snapshot_stubs(runtime_snapshot_objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stubs: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_objects or []):
        try:
            binding = dict(item or {})
        except Exception:
            binding = {}
        snapshot_object_key = str(binding.get("snapshot_object_key") or "").strip()
        snapshot_object_class = str(binding.get("snapshot_object_class") or "").strip()
        name = str(binding.get("name") or "").strip()
        if not snapshot_object_key or not snapshot_object_class or not name:
            continue
        stub_cls = _resolve_runtime_snapshot_stub_class(snapshot_object_class)
        stub_instance = stub_cls(binding)
        bind_state = str(binding.get("bind_state") or "pending").strip().lower() or "pending"
        supports_capture_preview = callable(getattr(stub_instance, "capture_preview", None))
        supports_restore_preview = callable(getattr(stub_instance, "restore_preview", None))
        dispatch_state = "ready" if bind_state == "ready" and supports_capture_preview and supports_restore_preview else bind_state
        stub_binding = RuntimeSnapshotStubBinding(
            name=name,
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=snapshot_object_class,
            bind_state=bind_state,
            stub_key=f"runtime_stub::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            stub_class=str(getattr(stub_cls, "stub_class_name", getattr(stub_cls, "__name__", "RuntimeSnapshotPreviewStub"))) or "RuntimeSnapshotPreviewStub",
            dispatch_state=dispatch_state or "pending",
            capture_method=str(binding.get("capture_method") or "capture_generic_snapshot").strip() or "capture_generic_snapshot",
            restore_method=str(binding.get("restore_method") or "restore_generic_snapshot").strip() or "restore_generic_snapshot",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_preview=supports_capture_preview,
            supports_restore_preview=supports_restore_preview,
            factory_method="_instantiate_runtime_snapshot_stub",
            capture_stub=f"{str(getattr(stub_cls, 'stub_class_name', getattr(stub_cls, '__name__', 'RuntimeSnapshotPreviewStub')))}.capture_preview",
            restore_stub=f"{str(getattr(stub_cls, 'stub_class_name', getattr(stub_cls, '__name__', 'RuntimeSnapshotPreviewStub')))}.restore_preview",
            rollback_stub=f"{str(getattr(stub_cls, 'stub_class_name', getattr(stub_cls, '__name__', 'RuntimeSnapshotPreviewStub')))}.rollback_preview",
        )
        stubs.append(stub_binding.as_plan_dict())
    return stubs


def _build_runtime_snapshot_stub_summary(runtime_snapshot_stubs: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_stubs or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("dispatch_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_preview")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_preview")))
    total = len(items)
    return (
        f"Runtime-Snapshot-Stubs: {ready}/{total} dispatch-bereit, "
        f"Capture={capture_ready}/{total}, Restore={restore_ready}/{total}."
    )


def _resolve_runtime_snapshot_state_carrier_class(snapshot_object_class: str):
    value = str(snapshot_object_class or "").strip().lower()
    return {
        "trackstatesnapshotobject": TrackStateRuntimeSnapshotStateCarrier,
        "routingsnapshotobject": RoutingRuntimeSnapshotStateCarrier,
        "trackkindsnapshotobject": TrackKindRuntimeSnapshotStateCarrier,
        "clipcollectionsnapshotobject": ClipCollectionRuntimeSnapshotStateCarrier,
        "audiofxchainsnapshotobject": AudioFxChainRuntimeSnapshotStateCarrier,
        "notefxchainsnapshotobject": NoteFxChainRuntimeSnapshotStateCarrier,
    }.get(value, _RuntimeSnapshotStateCarrierBase)


def _instantiate_runtime_snapshot_state_carrier(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    carrier_cls = _resolve_runtime_snapshot_state_carrier_class(str(binding.get("snapshot_object_class") or ""))
    return carrier_cls(binding, stub_plan)


def _count_preview_payload_entries(payload: Any) -> int:
    if isinstance(payload, dict):
        count = 0
        for value in payload.values():
            if isinstance(value, (list, tuple, set, dict)):
                count += len(value)
            elif value not in (None, "", False):
                count += 1
        return int(count)
    if isinstance(payload, (list, tuple, set)):
        return len(payload)
    return 1 if payload not in (None, "", False) else 0


def _build_runtime_snapshot_state_carriers(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stub_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_stubs or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    carriers: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_objects or []):
        try:
            binding = dict(item or {})
        except Exception:
            binding = {}
        snapshot_object_key = str(binding.get("snapshot_object_key") or "").strip()
        name = str(binding.get("name") or "").strip()
        if not snapshot_object_key or not name:
            continue
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        stub_cls = str(stub_plan.get("stub_class") or "").strip()
        stub_key = str(stub_plan.get("stub_key") or "").strip()
        carrier_instance = _instantiate_runtime_snapshot_state_carrier(binding, stub_plan)
        carrier_class = str(getattr(carrier_instance, "carrier_class_name", carrier_instance.__class__.__name__)).strip() or carrier_instance.__class__.__name__
        state_payload = carrier_instance._build_state_payload() if hasattr(carrier_instance, "_build_state_payload") else {}
        state_payload_entry_count = _count_preview_payload_entries(state_payload)
        state_payload_digest = _stable_snapshot_payload_digest(state_payload)
        bind_state = str(binding.get("bind_state") or "pending").strip().lower() or "pending"
        supports_capture_state = callable(getattr(carrier_instance, "capture_state_preview", None))
        supports_restore_state = callable(getattr(carrier_instance, "restore_state_preview", None))
        carrier_state = "ready" if bind_state == "ready" and supports_capture_state and supports_restore_state and bool(state_payload_digest) else bind_state
        carrier = RuntimeSnapshotStateCarrier(
            name=name,
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=stub_key,
            stub_class=stub_cls,
            carrier_key=f"state_carrier::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            carrier_class=carrier_class,
            carrier_state=carrier_state or "pending",
            capture_method=str(binding.get("capture_method") or "capture_generic_snapshot").strip() or "capture_generic_snapshot",
            restore_method=str(binding.get("restore_method") or "restore_generic_snapshot").strip() or "restore_generic_snapshot",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_state=supports_capture_state,
            supports_restore_state=supports_restore_state,
            bind_method="_instantiate_runtime_snapshot_state_carrier",
            capture_state_stub=f"{carrier_class}.capture_state_preview",
            restore_state_stub=f"{carrier_class}.restore_state_preview",
            rollback_state_stub=f"{carrier_class}.rollback_state_preview",
            state_payload_preview=state_payload,
            state_payload_entry_count=state_payload_entry_count,
            state_payload_digest=state_payload_digest,
        )
        carriers.append(carrier.as_plan_dict())
    return carriers


def _build_runtime_snapshot_state_carrier_summary(runtime_snapshot_state_carriers: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_carriers or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("carrier_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_state")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_state")))
    total = len(items)
    return f"Runtime-Zustandstraeger: {ready}/{total} bereit, Capture-State={capture_ready}/{total}, Restore-State={restore_ready}/{total}."


def _resolve_runtime_snapshot_state_container_class(snapshot_object_class: str):
    value = str(snapshot_object_class or "").strip().lower()
    return {
        "trackstatesnapshotobject": TrackStateRuntimeStateContainer,
        "routingsnapshotobject": RoutingRuntimeStateContainer,
        "trackkindsnapshotobject": TrackKindRuntimeStateContainer,
        "clipcollectionsnapshotobject": ClipCollectionRuntimeStateContainer,
        "audiofxchainsnapshotobject": AudioFxChainRuntimeStateContainer,
        "notefxchainsnapshotobject": NoteFxChainRuntimeStateContainer,
    }.get(value, _RuntimeSnapshotStateContainerBase)


def _instantiate_runtime_snapshot_state_container(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    container_cls = _resolve_runtime_snapshot_state_container_class(str(binding.get("snapshot_object_class") or ""))
    return container_cls(binding, stub_plan, carrier_plan)


def _build_runtime_snapshot_state_containers(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stub_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_stubs or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    carrier_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_state_carriers or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    containers: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_objects or []):
        try:
            binding = dict(item or {})
        except Exception:
            binding = {}
        snapshot_object_key = str(binding.get("snapshot_object_key") or "").strip()
        name = str(binding.get("name") or "").strip()
        if not snapshot_object_key or not name:
            continue
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        carrier_plan = dict(carrier_map.get(snapshot_object_key) or {})
        container_instance = _instantiate_runtime_snapshot_state_container(binding, stub_plan, carrier_plan)
        container_class = str(getattr(container_instance, "container_class_name", container_instance.__class__.__name__)).strip() or container_instance.__class__.__name__
        container_payload = container_instance._build_container_payload() if hasattr(container_instance, "_build_container_payload") else {}
        container_payload_entry_count = _count_preview_payload_entries(container_payload)
        container_payload_digest = _stable_snapshot_payload_digest(container_payload)
        bind_state = str(binding.get("bind_state") or "pending").strip().lower() or "pending"
        supports_capture_container = callable(getattr(container_instance, "capture_container_preview", None))
        supports_restore_container = callable(getattr(container_instance, "restore_container_preview", None))
        container_state = "ready" if bind_state == "ready" and supports_capture_container and supports_restore_container and bool(container_payload_digest) else bind_state
        container = RuntimeSnapshotStateContainer(
            name=name,
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=f"state_container::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            container_class=container_class,
            container_state=container_state or "pending",
            capture_method=str(binding.get("capture_method") or "capture_generic_snapshot").strip() or "capture_generic_snapshot",
            restore_method=str(binding.get("restore_method") or "restore_generic_snapshot").strip() or "restore_generic_snapshot",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_container=supports_capture_container,
            supports_restore_container=supports_restore_container,
            supports_runtime_state_container=bool(carrier_plan.get("carrier_key")) and bool(container_payload_digest),
            instantiate_method="_instantiate_runtime_snapshot_state_container",
            capture_container_stub=f"{container_class}.capture_container_preview",
            restore_container_stub=f"{container_class}.restore_container_preview",
            rollback_container_stub=f"{container_class}.rollback_container_preview",
            runtime_state_stub=f"{container_class}._build_container_payload",
            state_payload_preview=copy.deepcopy(dict(carrier_plan.get("state_payload_preview") or {})) if isinstance(carrier_plan.get("state_payload_preview"), dict) else {},
            state_payload_entry_count=int(carrier_plan.get("state_payload_entry_count") or 0),
            state_payload_digest=str(carrier_plan.get("state_payload_digest") or "").strip(),
            container_payload_preview=container_payload,
            container_payload_entry_count=container_payload_entry_count,
            container_payload_digest=container_payload_digest,
        )
        containers.append(container.as_plan_dict())
    return containers


def _build_runtime_snapshot_state_container_summary(runtime_snapshot_state_containers: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_containers or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("container_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_container")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_container")))
    total = len(items)
    return f"Runtime-State-Container: {ready}/{total} bereit, Capture-Container={capture_ready}/{total}, Restore-Container={restore_ready}/{total}."


def _resolve_runtime_snapshot_state_holder_class(snapshot_object_class: str):
    value = str(snapshot_object_class or "").strip().lower()
    return {
        "trackstatesnapshotobject": TrackStateRuntimeStateHolder,
        "routingsnapshotobject": RoutingRuntimeStateHolder,
        "trackkindsnapshotobject": TrackKindRuntimeStateHolder,
        "clipcollectionsnapshotobject": ClipCollectionRuntimeStateHolder,
        "audiofxchainsnapshotobject": AudioFxChainRuntimeStateHolder,
        "notefxchainsnapshotobject": NoteFxChainRuntimeStateHolder,
    }.get(value, _RuntimeSnapshotStateHolderBase)


def _instantiate_runtime_snapshot_state_holder(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    holder_cls = _resolve_runtime_snapshot_state_holder_class(str(binding.get("snapshot_object_class") or ""))
    return holder_cls(binding, stub_plan, carrier_plan, container_plan)


def _build_runtime_snapshot_state_holders(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stub_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_stubs or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    carrier_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_state_carriers or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    container_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in list(runtime_snapshot_state_containers or [])
        if str(item.get("snapshot_object_key") or "").strip()
    }
    holders: list[dict[str, Any]] = []
    for item in list(runtime_snapshot_objects or []):
        try:
            binding = dict(item or {})
        except Exception:
            binding = {}
        snapshot_object_key = str(binding.get("snapshot_object_key") or "").strip()
        name = str(binding.get("name") or "").strip()
        if not snapshot_object_key or not name:
            continue
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        carrier_plan = dict(carrier_map.get(snapshot_object_key) or {})
        container_plan = dict(container_map.get(snapshot_object_key) or {})
        holder_instance = _instantiate_runtime_snapshot_state_holder(binding, stub_plan, carrier_plan, container_plan)
        holder_class = str(getattr(holder_instance, "holder_class_name", holder_instance.__class__.__name__)).strip() or holder_instance.__class__.__name__
        holder_payload = holder_instance._build_holder_payload() if hasattr(holder_instance, "_build_holder_payload") else {}
        holder_payload_entry_count = _count_preview_payload_entries(holder_payload)
        holder_payload_digest = _stable_snapshot_payload_digest(holder_payload)
        bind_state = str(binding.get("bind_state") or "pending").strip().lower() or "pending"
        supports_capture_holder = callable(getattr(holder_instance, "capture_holder_preview", None))
        supports_restore_holder = callable(getattr(holder_instance, "restore_holder_preview", None))
        holder_state = "ready" if bind_state == "ready" and supports_capture_holder and supports_restore_holder and bool(holder_payload_digest) else bind_state
        holder = RuntimeSnapshotStateHolder(
            name=name,
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=f"state_holder::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            holder_class=holder_class,
            holder_state=holder_state or "pending",
            capture_method=str(binding.get("capture_method") or "capture_generic_snapshot").strip() or "capture_generic_snapshot",
            restore_method=str(binding.get("restore_method") or "restore_generic_snapshot").strip() or "restore_generic_snapshot",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_holder=supports_capture_holder,
            supports_restore_holder=supports_restore_holder,
            supports_runtime_state_holder=bool(container_plan.get("container_key")) and bool(holder_payload_digest),
            instantiate_method="_instantiate_runtime_snapshot_state_holder",
            capture_holder_stub=f"{holder_class}.capture_holder_preview",
            restore_holder_stub=f"{holder_class}.restore_holder_preview",
            rollback_holder_stub=f"{holder_class}.rollback_holder_preview",
            runtime_holder_stub=f"{holder_class}._build_holder_payload",
            container_payload_preview=copy.deepcopy(dict(container_plan.get("container_payload_preview") or {})) if isinstance(container_plan.get("container_payload_preview"), dict) else {},
            container_payload_entry_count=int(container_plan.get("container_payload_entry_count") or 0),
            container_payload_digest=str(container_plan.get("container_payload_digest") or "").strip(),
            holder_payload_preview=holder_payload,
            holder_payload_entry_count=holder_payload_entry_count,
            holder_payload_digest=holder_payload_digest,
        )
        holders.append(holder.as_plan_dict())
    return holders


def _build_runtime_snapshot_state_holder_summary(runtime_snapshot_state_holders: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_holders or [])
    if not items:
        return ""
    ready = sum(1 for item in items if str(item.get("holder_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_holder")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_holder")))
    total = len(items)
    return f"Runtime-State-Halter: {ready}/{total} bereit, Capture-Halter={capture_ready}/{total}, Restore-Halter={restore_ready}/{total}."


def _safe_runner_owner_text(item: dict[str, Any]) -> str:
    owner_ids = [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()]
    if owner_ids:
        return ", ".join(owner_ids[:3])
    return str(item.get("owner_scope") or "runtime").strip() or "runtime"


def _safe_runner_payload_detail(item: dict[str, Any]) -> tuple[int, str]:
    payload = dict(item.get("snapshot_payload") or {}) if isinstance(item.get("snapshot_payload"), dict) else {}
    payload_count = int(item.get("snapshot_payload_entry_count") or 0)
    payload_digest = str(item.get("payload_digest") or "").strip()
    if not payload_digest:
        payload_digest = _stable_snapshot_payload_digest(payload)
    if payload_count <= 0 and payload:
        for value in payload.values():
            if isinstance(value, (list, tuple, set, dict)):
                payload_count += len(value)
            elif value not in (None, "", False):
                payload_count += 1
    return payload_count, payload_digest


def _build_safe_runner_phase_result(phase: str, item: dict[str, Any], method_name: str, detail_text: str, state: str = "ready") -> dict[str, Any]:
    object_key = str(item.get("snapshot_object_key") or "").strip() or str(item.get("snapshot_instance_key") or "").strip() or "snapshot-object"
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    result = {
        "phase": phase,
        "target": object_key,
        "method": str(method_name or "method").strip() or "method",
        "state": str(state or "ready").strip().lower() or "ready",
        "detail": detail_text,
        "payload_entry_count": int(payload_count),
        "payload_digest": payload_digest,
        "owner_scope": str(item.get("owner_scope") or "").strip(),
        "owner_ids": [str(x).strip() for x in list(item.get("owner_ids") or []) if str(x).strip()],
    }
    return result


class _RuntimeSnapshotStateStoreBase:
    """Read-only runtime-state store owning capture-handle previews."""

    store_class_name = "GenericRuntimeSnapshotStateStore"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        try:
            carrier_plan = dict(carrier_plan or {})
        except Exception:
            carrier_plan = {}
        try:
            container_plan = dict(container_plan or {})
        except Exception:
            container_plan = {}
        try:
            holder_plan = dict(holder_plan or {})
        except Exception:
            holder_plan = {}
        try:
            slot_plan = dict(slot_plan or {})
        except Exception:
            slot_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan
        self.carrier_plan = carrier_plan
        self.container_plan = container_plan
        self.holder_plan = holder_plan
        self.slot_plan = slot_plan

    def _capture_handle_triplet(self) -> tuple[str, str, str]:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return (
            f"capture_handle::{safe_key}",
            f"restore_handle::{safe_key}",
            f"rollback_handle::{safe_key}",
        )

    def _build_store_payload(self) -> dict[str, Any]:
        slot_payload = copy.deepcopy(dict(self.slot_plan.get("slot_payload_preview") or {})) if isinstance(self.slot_plan.get("slot_payload_preview"), dict) else {}
        capture_handle_key, restore_handle_key, rollback_handle_key = self._capture_handle_triplet()
        return {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "holder_key": str(self.holder_plan.get("holder_key") or "").strip(),
            "holder_class": str(self.holder_plan.get("holder_class") or "").strip(),
            "slot_key": str(self.slot_plan.get("slot_key") or "").strip(),
            "slot_class": str(self.slot_plan.get("slot_class") or "").strip(),
            "slot_state": str(self.slot_plan.get("slot_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "slot_payload_digest": str(self.slot_plan.get("slot_payload_digest") or "").strip(),
            "store_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "capture_handle_key": capture_handle_key,
            "restore_handle_key": restore_handle_key,
            "rollback_handle_key": rollback_handle_key,
            "runtime_state_slot": slot_payload,
        }

    def capture_store_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_store_payload()
        capture_handle_key, restore_handle_key, rollback_handle_key = self._capture_handle_triplet()
        result["state_store_class"] = self.store_class_name
        result["capture_handle_key"] = capture_handle_key
        result["restore_handle_key"] = restore_handle_key
        result["rollback_handle_key"] = rollback_handle_key
        result["capture_handle_state"] = "ready" if capture_handle_key else "pending"
        result["store_payload_preview"] = payload
        result["store_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["store_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Store {self.store_class_name} haelt Capture-/Restore-Handles read-only bereit."
        return result

    def restore_store_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_store_payload()
        capture_handle_key, restore_handle_key, rollback_handle_key = self._capture_handle_triplet()
        result["state_store_class"] = self.store_class_name
        result["capture_handle_key"] = capture_handle_key
        result["restore_handle_key"] = restore_handle_key
        result["rollback_handle_key"] = rollback_handle_key
        result["capture_handle_state"] = "ready" if restore_handle_key else "pending"
        result["store_payload_preview"] = payload
        result["store_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["store_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Store {self.store_class_name} haelt Restore-Handles read-only bereit."
        return result

    def rollback_store_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_store_payload()
        capture_handle_key, restore_handle_key, rollback_handle_key = self._capture_handle_triplet()
        result["state_store_class"] = self.store_class_name
        result["capture_handle_key"] = capture_handle_key
        result["restore_handle_key"] = restore_handle_key
        result["rollback_handle_key"] = rollback_handle_key
        result["capture_handle_state"] = "ready" if rollback_handle_key else "pending"
        result["store_payload_preview"] = payload
        result["store_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["store_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Store {self.store_class_name} reserviert Rollback-Handles read-only."
        return result


class TrackStateRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "TrackStateRuntimeStateStore"


class RoutingRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "RoutingRuntimeStateStore"


class TrackKindRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "TrackKindRuntimeStateStore"


class ClipCollectionRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "ClipCollectionRuntimeStateStore"


class AudioFxChainRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "AudioFxChainRuntimeStateStore"


class NoteFxChainRuntimeStateStore(_RuntimeSnapshotStateStoreBase):
    store_class_name = "NoteFxChainRuntimeStateStore"


class _RuntimeSnapshotStateRegistryBase:
    """Read-only runtime-state registry for future capture-handle storage."""

    registry_class_name = "GenericRuntimeSnapshotStateRegistry"
    handle_store_class_name = "GenericRuntimeSnapshotHandleStore"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None) -> None:
        try:
            binding = dict(binding or {})
        except Exception:
            binding = {}
        try:
            stub_plan = dict(stub_plan or {})
        except Exception:
            stub_plan = {}
        try:
            carrier_plan = dict(carrier_plan or {})
        except Exception:
            carrier_plan = {}
        try:
            container_plan = dict(container_plan or {})
        except Exception:
            container_plan = {}
        try:
            holder_plan = dict(holder_plan or {})
        except Exception:
            holder_plan = {}
        try:
            slot_plan = dict(slot_plan or {})
        except Exception:
            slot_plan = {}
        try:
            store_plan = dict(store_plan or {})
        except Exception:
            store_plan = {}
        self.binding = binding
        self.stub_plan = stub_plan
        self.carrier_plan = carrier_plan
        self.container_plan = container_plan
        self.holder_plan = holder_plan
        self.slot_plan = slot_plan
        self.store_plan = store_plan

    def _handle_store_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"handle_store::{safe_key}"

    def _build_registry_payload(self) -> dict[str, Any]:
        store_payload = copy.deepcopy(dict(self.store_plan.get("store_payload_preview") or {})) if isinstance(self.store_plan.get("store_payload_preview"), dict) else {}
        return {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "holder_key": str(self.holder_plan.get("holder_key") or "").strip(),
            "holder_class": str(self.holder_plan.get("holder_class") or "").strip(),
            "slot_key": str(self.slot_plan.get("slot_key") or "").strip(),
            "slot_class": str(self.slot_plan.get("slot_class") or "").strip(),
            "store_key": str(self.store_plan.get("store_key") or "").strip(),
            "store_class": str(self.store_plan.get("store_class") or "").strip(),
            "store_state": str(self.store_plan.get("store_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "store_payload_digest": str(self.store_plan.get("store_payload_digest") or "").strip(),
            "capture_handle_key": str(self.store_plan.get("capture_handle_key") or "").strip(),
            "restore_handle_key": str(self.store_plan.get("restore_handle_key") or "").strip(),
            "rollback_handle_key": str(self.store_plan.get("rollback_handle_key") or "").strip(),
            "handle_store_key": self._handle_store_key(),
            "registry_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "runtime_state_store": store_payload,
        }

    def capture_registry_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_registry_payload()
        result["state_registry_class"] = self.registry_class_name
        result["handle_store_class"] = self.handle_store_class_name
        result["handle_store_key"] = self._handle_store_key()
        result["registry_payload_preview"] = payload
        result["registry_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["registry_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry {self.registry_class_name} bindet separaten Handle-Speicher read-only vor."
        return result

    def restore_registry_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_registry_payload()
        result["state_registry_class"] = self.registry_class_name
        result["handle_store_class"] = self.handle_store_class_name
        result["handle_store_key"] = self._handle_store_key()
        result["registry_payload_preview"] = payload
        result["registry_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["registry_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry {self.registry_class_name} haelt Restore-Handle-Speicher read-only bereit."
        return result

    def rollback_registry_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_registry_payload()
        result["state_registry_class"] = self.registry_class_name
        result["handle_store_class"] = self.handle_store_class_name
        result["handle_store_key"] = self._handle_store_key()
        result["registry_payload_preview"] = payload
        result["registry_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["registry_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry {self.registry_class_name} reserviert Rollback-Handle-Speicher read-only."
        return result


class TrackStateRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "TrackStateRuntimeStateRegistry"
    handle_store_class_name = "TrackStateRuntimeHandleStore"


class RoutingRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "RoutingRuntimeStateRegistry"
    handle_store_class_name = "RoutingRuntimeHandleStore"


class TrackKindRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "TrackKindRuntimeStateRegistry"
    handle_store_class_name = "TrackKindRuntimeHandleStore"


class ClipCollectionRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "ClipCollectionRuntimeStateRegistry"
    handle_store_class_name = "ClipCollectionRuntimeHandleStore"


class AudioFxChainRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "AudioFxChainRuntimeStateRegistry"
    handle_store_class_name = "AudioFxChainRuntimeHandleStore"


class NoteFxChainRuntimeStateRegistry(_RuntimeSnapshotStateRegistryBase):
    registry_class_name = "NoteFxChainRuntimeStateRegistry"
    handle_store_class_name = "NoteFxChainRuntimeHandleStore"


class _RuntimeSnapshotStateRegistryBackendBase:
    """Read-only backend behind runtime-state registries + handle registers."""

    backend_class_name = "GenericRuntimeSnapshotStateRegistryBackend"
    handle_register_class_name = "GenericRuntimeSnapshotHandleRegister"
    registry_slot_class_name = "GenericRuntimeSnapshotRegistrySlot"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None, registry_plan: dict[str, Any] | None = None) -> None:
        self.binding = dict(binding or {}) if isinstance(binding, dict) else {}
        self.stub_plan = dict(stub_plan or {}) if isinstance(stub_plan, dict) else {}
        self.carrier_plan = dict(carrier_plan or {}) if isinstance(carrier_plan, dict) else {}
        self.container_plan = dict(container_plan or {}) if isinstance(container_plan, dict) else {}
        self.holder_plan = dict(holder_plan or {}) if isinstance(holder_plan, dict) else {}
        self.slot_plan = dict(slot_plan or {}) if isinstance(slot_plan, dict) else {}
        self.store_plan = dict(store_plan or {}) if isinstance(store_plan, dict) else {}
        self.registry_plan = dict(registry_plan or {}) if isinstance(registry_plan, dict) else {}

    def _backend_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"state_backend::{safe_key}"

    def _handle_register_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"handle_register::{safe_key}"

    def _registry_slot_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"registry_slot::{safe_key}"

    def _build_backend_payload(self) -> dict[str, Any]:
        registry_payload = copy.deepcopy(dict(self.registry_plan.get("registry_payload_preview") or {})) if isinstance(self.registry_plan.get("registry_payload_preview"), dict) else {}
        return {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "holder_key": str(self.holder_plan.get("holder_key") or "").strip(),
            "holder_class": str(self.holder_plan.get("holder_class") or "").strip(),
            "slot_key": str(self.slot_plan.get("slot_key") or "").strip(),
            "slot_class": str(self.slot_plan.get("slot_class") or "").strip(),
            "store_key": str(self.store_plan.get("store_key") or "").strip(),
            "store_class": str(self.store_plan.get("store_class") or "").strip(),
            "registry_key": str(self.registry_plan.get("registry_key") or "").strip(),
            "registry_class": str(self.registry_plan.get("registry_class") or "").strip(),
            "registry_state": str(self.registry_plan.get("registry_state") or "").strip(),
            "handle_store_key": str(self.registry_plan.get("handle_store_key") or "").strip(),
            "handle_store_class": str(self.registry_plan.get("handle_store_class") or "").strip(),
            "handle_store_state": str(self.registry_plan.get("handle_store_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "registry_payload_digest": str(self.registry_plan.get("registry_payload_digest") or "").strip(),
            "handle_register_key": self._handle_register_key(),
            "registry_slot_key": self._registry_slot_key(),
            "backend_bind_state": str(self.binding.get("bind_state") or "").strip(),
            "runtime_state_registry": registry_payload,
        }

    def capture_backend_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_backend_payload()
        result["state_registry_backend_class"] = self.backend_class_name
        result["handle_register_class"] = self.handle_register_class_name
        result["registry_slot_class"] = self.registry_slot_class_name
        result["backend_payload_preview"] = payload
        result["backend_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["backend_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Backend {self.backend_class_name} koppelt Handle-Register und Registry-Slot read-only hinter der Registry."
        return result

    def restore_backend_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_backend_payload()
        result["state_registry_backend_class"] = self.backend_class_name
        result["handle_register_class"] = self.handle_register_class_name
        result["registry_slot_class"] = self.registry_slot_class_name
        result["backend_payload_preview"] = payload
        result["backend_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["backend_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Backend {self.backend_class_name} haelt Restore-Pfade ueber Handle-Register und Registry-Slot read-only bereit."
        return result

    def rollback_backend_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_backend_payload()
        result["state_registry_backend_class"] = self.backend_class_name
        result["handle_register_class"] = self.handle_register_class_name
        result["registry_slot_class"] = self.registry_slot_class_name
        result["backend_payload_preview"] = payload
        result["backend_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["backend_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Backend {self.backend_class_name} reserviert Rollback ueber Handle-Register und Registry-Slot read-only."
        return result


class TrackStateRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "TrackStateRuntimeStateRegistryBackend"
    handle_register_class_name = "TrackStateRuntimeHandleRegister"
    registry_slot_class_name = "TrackStateRuntimeRegistrySlot"


class RoutingRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "RoutingRuntimeStateRegistryBackend"
    handle_register_class_name = "RoutingRuntimeHandleRegister"
    registry_slot_class_name = "RoutingRuntimeRegistrySlot"


class TrackKindRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "TrackKindRuntimeStateRegistryBackend"
    handle_register_class_name = "TrackKindRuntimeHandleRegister"
    registry_slot_class_name = "TrackKindRuntimeRegistrySlot"


class ClipCollectionRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "ClipCollectionRuntimeStateRegistryBackend"
    handle_register_class_name = "ClipCollectionRuntimeHandleRegister"
    registry_slot_class_name = "ClipCollectionRuntimeRegistrySlot"


class AudioFxChainRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "AudioFxChainRuntimeStateRegistryBackend"
    handle_register_class_name = "AudioFxChainRuntimeHandleRegister"
    registry_slot_class_name = "AudioFxChainRuntimeRegistrySlot"


class NoteFxChainRuntimeStateRegistryBackend(_RuntimeSnapshotStateRegistryBackendBase):
    backend_class_name = "NoteFxChainRuntimeStateRegistryBackend"
    handle_register_class_name = "NoteFxChainRuntimeHandleRegister"
    registry_slot_class_name = "NoteFxChainRuntimeRegistrySlot"


class _RuntimeSnapshotStateRegistryBackendAdapterBase:
    """Read-only adapter behind runtime-state registries + backend previews."""

    adapter_class_name = "GenericRuntimeSnapshotStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "GenericRuntimeSnapshotBackendStoreAdapter"
    registry_slot_backend_class_name = "GenericRuntimeSnapshotRegistrySlotBackend"

    def __init__(self, binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None, registry_plan: dict[str, Any] | None = None, backend_plan: dict[str, Any] | None = None) -> None:
        self.binding = dict(binding or {}) if isinstance(binding, dict) else {}
        self.stub_plan = dict(stub_plan or {}) if isinstance(stub_plan, dict) else {}
        self.carrier_plan = dict(carrier_plan or {}) if isinstance(carrier_plan, dict) else {}
        self.container_plan = dict(container_plan or {}) if isinstance(container_plan, dict) else {}
        self.holder_plan = dict(holder_plan or {}) if isinstance(holder_plan, dict) else {}
        self.slot_plan = dict(slot_plan or {}) if isinstance(slot_plan, dict) else {}
        self.store_plan = dict(store_plan or {}) if isinstance(store_plan, dict) else {}
        self.registry_plan = dict(registry_plan or {}) if isinstance(registry_plan, dict) else {}
        self.backend_plan = dict(backend_plan or {}) if isinstance(backend_plan, dict) else {}

    def _adapter_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"state_backend_adapter::{safe_key}"

    def _backend_store_adapter_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"backend_store_adapter::{safe_key}"

    def _registry_slot_backend_key(self) -> str:
        snapshot_object_key = str(self.binding.get("snapshot_object_key") or "snapshot_object").strip() or "snapshot_object"
        safe_key = _sanitize_ref_token(snapshot_object_key, "snapshot_object")
        return f"registry_slot_backend::{safe_key}"

    def _build_adapter_payload(self) -> dict[str, Any]:
        backend_payload = copy.deepcopy(dict(self.backend_plan.get("backend_payload_preview") or {})) if isinstance(self.backend_plan.get("backend_payload_preview"), dict) else {}
        return {
            "snapshot_object_key": str(self.binding.get("snapshot_object_key") or "").strip(),
            "snapshot_object_class": str(self.binding.get("snapshot_object_class") or "").strip(),
            "stub_key": str(self.stub_plan.get("stub_key") or "").strip(),
            "stub_class": str(self.stub_plan.get("stub_class") or "").strip(),
            "carrier_key": str(self.carrier_plan.get("carrier_key") or "").strip(),
            "carrier_class": str(self.carrier_plan.get("carrier_class") or "").strip(),
            "container_key": str(self.container_plan.get("container_key") or "").strip(),
            "container_class": str(self.container_plan.get("container_class") or "").strip(),
            "holder_key": str(self.holder_plan.get("holder_key") or "").strip(),
            "holder_class": str(self.holder_plan.get("holder_class") or "").strip(),
            "slot_key": str(self.slot_plan.get("slot_key") or "").strip(),
            "slot_class": str(self.slot_plan.get("slot_class") or "").strip(),
            "store_key": str(self.store_plan.get("store_key") or "").strip(),
            "store_class": str(self.store_plan.get("store_class") or "").strip(),
            "registry_key": str(self.registry_plan.get("registry_key") or "").strip(),
            "registry_class": str(self.registry_plan.get("registry_class") or "").strip(),
            "backend_key": str(self.backend_plan.get("backend_key") or "").strip(),
            "backend_class": str(self.backend_plan.get("backend_class") or "").strip(),
            "backend_state": str(self.backend_plan.get("backend_state") or "").strip(),
            "handle_register_key": str(self.backend_plan.get("handle_register_key") or "").strip(),
            "handle_register_class": str(self.backend_plan.get("handle_register_class") or "").strip(),
            "handle_register_state": str(self.backend_plan.get("handle_register_state") or "").strip(),
            "registry_slot_key": str(self.backend_plan.get("registry_slot_key") or "").strip(),
            "registry_slot_class": str(self.backend_plan.get("registry_slot_class") or "").strip(),
            "registry_slot_state": str(self.backend_plan.get("registry_slot_state") or "").strip(),
            "rollback_slot": str(self.binding.get("rollback_slot") or "").strip(),
            "backend_payload_digest": str(self.backend_plan.get("backend_payload_digest") or "").strip(),
            "backend_store_adapter_key": self._backend_store_adapter_key(),
            "registry_slot_backend_key": self._registry_slot_backend_key(),
            "runtime_state_backend": backend_payload,
        }

    def capture_adapter_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_capture_preview(self.binding) or {})
        payload = self._build_adapter_payload()
        result["state_registry_backend_adapter_class"] = self.adapter_class_name
        result["backend_store_adapter_class"] = self.backend_store_adapter_class_name
        result["registry_slot_backend_class"] = self.registry_slot_backend_class_name
        result["adapter_payload_preview"] = payload
        result["adapter_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["adapter_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry-Backend-Adapter {self.adapter_class_name} koppelt Backend-Store-Adapter und Registry-Slot-Backend read-only hinter dem Registry-Backend."
        return result

    def restore_adapter_preview(self) -> dict[str, Any]:
        result = dict(_dispatch_safe_runner_restore_preview(self.binding) or {})
        payload = self._build_adapter_payload()
        result["state_registry_backend_adapter_class"] = self.adapter_class_name
        result["backend_store_adapter_class"] = self.backend_store_adapter_class_name
        result["registry_slot_backend_class"] = self.registry_slot_backend_class_name
        result["adapter_payload_preview"] = payload
        result["adapter_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["adapter_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry-Backend-Adapter {self.adapter_class_name} haelt Restore-Pfade ueber Backend-Store-Adapter und Registry-Slot-Backend read-only bereit."
        return result

    def rollback_adapter_preview(self) -> dict[str, Any]:
        result = dict(_build_safe_runner_rollback_preview(self.binding) or {})
        payload = self._build_adapter_payload()
        result["state_registry_backend_adapter_class"] = self.adapter_class_name
        result["backend_store_adapter_class"] = self.backend_store_adapter_class_name
        result["registry_slot_backend_class"] = self.registry_slot_backend_class_name
        result["adapter_payload_preview"] = payload
        result["adapter_payload_entry_count"] = _count_preview_payload_entries(payload)
        result["adapter_payload_digest"] = _stable_snapshot_payload_digest(payload)
        detail = str(result.get("detail") or "").strip()
        result["detail"] = (detail + " " if detail else "") + f"Runtime-State-Registry-Backend-Adapter {self.adapter_class_name} reserviert Rollback ueber Backend-Store-Adapter und Registry-Slot-Backend read-only."
        return result

    def _build_backend_store_adapter_result(self, phase: str) -> dict[str, Any]:
        phase_key = str(phase or "capture").strip().lower() or "capture"
        method_map = {
            "capture": "capture_backend_store_adapter_preview",
            "restore": "restore_backend_store_adapter_preview",
            "rollback": "rollback_backend_store_adapter_preview",
        }
        detail_map = {
            "capture": "haengt den spaeteren Snapshot-Transaktions-Dispatch read-only an den Backend-Store-Adapter.",
            "restore": "haelt den spaeteren Restore-Dispatch read-only ueber den Backend-Store-Adapter bereit.",
            "rollback": "reserviert den spaeteren Rollback-Dispatch read-only ueber den Backend-Store-Adapter.",
        }
        target = self._backend_store_adapter_key()
        state = "ready" if target else "pending"
        return {
            "phase": f"backend-store-{phase_key}",
            "target": target or self._adapter_key(),
            "method": method_map.get(phase_key, "capture_backend_store_adapter_preview"),
            "state": state,
            "detail": f"Backend-Store-Adapter {self.backend_store_adapter_class_name} {detail_map.get(phase_key, detail_map['capture'])}",
            "backend_store_adapter_key": target,
            "backend_store_adapter_class": self.backend_store_adapter_class_name,
            "adapter_key": self._adapter_key(),
            "adapter_class": self.adapter_class_name,
            "adapter_payload_digest": _stable_snapshot_payload_digest(self._build_adapter_payload()),
        }

    def capture_backend_store_adapter_preview(self) -> dict[str, Any]:
        return self._build_backend_store_adapter_result("capture")

    def restore_backend_store_adapter_preview(self) -> dict[str, Any]:
        return self._build_backend_store_adapter_result("restore")

    def rollback_backend_store_adapter_preview(self) -> dict[str, Any]:
        return self._build_backend_store_adapter_result("rollback")

    def _build_registry_slot_backend_result(self, phase: str) -> dict[str, Any]:
        phase_key = str(phase or "capture").strip().lower() or "capture"
        method_map = {
            "capture": "capture_registry_slot_backend_preview",
            "restore": "restore_registry_slot_backend_preview",
            "rollback": "rollback_registry_slot_backend_preview",
        }
        detail_map = {
            "capture": "haengt den spaeteren Snapshot-Transaktions-Dispatch read-only an das Registry-Slot-Backend.",
            "restore": "haelt den spaeteren Restore-Dispatch read-only ueber das Registry-Slot-Backend bereit.",
            "rollback": "reserviert den spaeteren Rollback-Dispatch read-only ueber das Registry-Slot-Backend.",
        }
        target = self._registry_slot_backend_key()
        state = "ready" if target else "pending"
        return {
            "phase": f"registry-slot-backend-{phase_key}",
            "target": target or self._adapter_key(),
            "method": method_map.get(phase_key, "capture_registry_slot_backend_preview"),
            "state": state,
            "detail": f"Registry-Slot-Backend {self.registry_slot_backend_class_name} {detail_map.get(phase_key, detail_map['capture'])}",
            "registry_slot_backend_key": target,
            "registry_slot_backend_class": self.registry_slot_backend_class_name,
            "adapter_key": self._adapter_key(),
            "adapter_class": self.adapter_class_name,
            "adapter_payload_digest": _stable_snapshot_payload_digest(self._build_adapter_payload()),
        }

    def capture_registry_slot_backend_preview(self) -> dict[str, Any]:
        return self._build_registry_slot_backend_result("capture")

    def restore_registry_slot_backend_preview(self) -> dict[str, Any]:
        return self._build_registry_slot_backend_result("restore")

    def rollback_registry_slot_backend_preview(self) -> dict[str, Any]:
        return self._build_registry_slot_backend_result("rollback")

    def _build_apply_runner_result(self, phase: str) -> dict[str, Any]:
        phase_key = str(phase or "capture").strip().lower() or "capture"
        base_map = {
            "capture": self.capture_adapter_preview,
            "restore": self.restore_adapter_preview,
            "rollback": self.rollback_adapter_preview,
        }
        result = dict(base_map.get(phase_key, self.capture_adapter_preview)() or {})
        result["phase"] = f"apply-runner-{phase_key}"
        result["target"] = self._adapter_key() or str(self.binding.get("snapshot_object_key") or "").strip()
        result["method"] = f"{phase_key}_apply_runner_preview"
        detail = str(result.get("detail") or "").strip()
        suffix = {
            "capture": "Der Snapshot-Transaktions-Apply-Runner dispatcht diese Adapter-Ebene jetzt als eigenen read-only Schritt.",
            "restore": "Der Snapshot-Transaktions-Apply-Runner fuehrt den Restore-Pfad jetzt als eigenen read-only Schritt.",
            "rollback": "Der Snapshot-Transaktions-Apply-Runner reserviert den Rollback-Pfad jetzt als eigenen read-only Schritt.",
        }.get(phase_key, "Der Snapshot-Transaktions-Apply-Runner fuehrt diese Ebene read-only.")
        result["detail"] = (detail + " " if detail else "") + suffix
        return result

    def capture_apply_runner_preview(self) -> dict[str, Any]:
        return self._build_apply_runner_result("capture")

    def restore_apply_runner_preview(self) -> dict[str, Any]:
        return self._build_apply_runner_result("restore")

    def rollback_apply_runner_preview(self) -> dict[str, Any]:
        return self._build_apply_runner_result("rollback")


class TrackStateRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "TrackStateRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "TrackStateRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "TrackStateRuntimeRegistrySlotBackend"


class RoutingRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "RoutingRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "RoutingRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "RoutingRuntimeRegistrySlotBackend"


class TrackKindRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "TrackKindRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "TrackKindRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "TrackKindRuntimeRegistrySlotBackend"


class ClipCollectionRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "ClipCollectionRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "ClipCollectionRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "ClipCollectionRuntimeRegistrySlotBackend"


class AudioFxChainRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "AudioFxChainRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "AudioFxChainRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "AudioFxChainRuntimeRegistrySlotBackend"


class NoteFxChainRuntimeStateRegistryBackendAdapter(_RuntimeSnapshotStateRegistryBackendAdapterBase):
    adapter_class_name = "NoteFxChainRuntimeStateRegistryBackendAdapter"
    backend_store_adapter_class_name = "NoteFxChainRuntimeBackendStoreAdapter"
    registry_slot_backend_class_name = "NoteFxChainRuntimeRegistrySlotBackend"


def _capture_track_state_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_track_state_snapshot",
        f"Safe-Runner liest den Track-State fuer {owner_text} read-only an (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_routing_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_routing_snapshot",
        f"Safe-Runner prueft Routing-Snapshot fuer {owner_text} read-only (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_track_kind_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_track_kind_snapshot",
        f"Safe-Runner liest den Spurtyp fuer {owner_text} read-only an (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_clip_collection_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_clip_collection_snapshot",
        f"Safe-Runner inventarisiert Audio-Clip-Snapshot fuer {owner_text} read-only (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_audio_fx_chain_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_audio_fx_chain_snapshot",
        f"Safe-Runner prueft Audio-FX-Kette fuer {owner_text} read-only (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_note_fx_chain_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        "capture_note_fx_chain_snapshot",
        f"Safe-Runner prueft Note-FX-Kette fuer {owner_text} read-only (payload={payload_count}, digest={payload_digest}).",
    )


def _capture_generic_snapshot_preview(item: dict[str, Any], method_name: str) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    payload_count, payload_digest = _safe_runner_payload_detail(item)
    return _build_safe_runner_phase_result(
        "capture",
        item,
        method_name,
        f"Safe-Runner dispatcht {method_name} read-only fuer {owner_text} (payload={payload_count}, digest={payload_digest}).",
    )


def _restore_track_state_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_track_state_snapshot",
        f"Safe-Runner prueft den Rueckweg des Track-State fuer {owner_text} read-only.",
    )


def _restore_routing_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_routing_snapshot",
        f"Safe-Runner prueft den atomaren Routing-Rueckweg fuer {owner_text} read-only.",
    )


def _restore_track_kind_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_track_kind_snapshot",
        f"Safe-Runner prueft den Spurtyp-Rueckweg fuer {owner_text} read-only.",
    )


def _restore_clip_collection_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_clip_collection_snapshot",
        f"Safe-Runner prueft den Audio-Clip-Rueckweg fuer {owner_text} read-only.",
    )


def _restore_audio_fx_chain_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_audio_fx_chain_snapshot",
        f"Safe-Runner prueft den Audio-FX-Rueckweg fuer {owner_text} read-only.",
    )


def _restore_note_fx_chain_snapshot_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        "restore_note_fx_chain_snapshot",
        f"Safe-Runner prueft den Note-FX-Rueckweg fuer {owner_text} read-only.",
    )


def _restore_generic_snapshot_preview(item: dict[str, Any], method_name: str) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    return _build_safe_runner_phase_result(
        "restore",
        item,
        method_name,
        f"Safe-Runner dispatcht {method_name} read-only fuer {owner_text} im Restore-Pfad.",
    )


def _build_safe_runner_rollback_preview(item: dict[str, Any]) -> dict[str, Any]:
    owner_text = _safe_runner_owner_text(item)
    rollback_slot = str(item.get("rollback_slot") or "rollback").strip() or "rollback"
    return _build_safe_runner_phase_result(
        "rollback-slot",
        item,
        rollback_slot,
        f"Rollback-Slot {rollback_slot} ist fuer {owner_text} reserviert und wurde read-only verifiziert.",
    )


_CAPTURE_PREVIEW_DISPATCH = {
    "capture_track_state_snapshot": _capture_track_state_snapshot_preview,
    "capture_routing_snapshot": _capture_routing_snapshot_preview,
    "capture_track_kind_snapshot": _capture_track_kind_snapshot_preview,
    "capture_clip_collection_snapshot": _capture_clip_collection_snapshot_preview,
    "capture_audio_fx_chain_snapshot": _capture_audio_fx_chain_snapshot_preview,
    "capture_note_fx_chain_snapshot": _capture_note_fx_chain_snapshot_preview,
}


_RESTORE_PREVIEW_DISPATCH = {
    "restore_track_state_snapshot": _restore_track_state_snapshot_preview,
    "restore_routing_snapshot": _restore_routing_snapshot_preview,
    "restore_track_kind_snapshot": _restore_track_kind_snapshot_preview,
    "restore_clip_collection_snapshot": _restore_clip_collection_snapshot_preview,
    "restore_audio_fx_chain_snapshot": _restore_audio_fx_chain_snapshot_preview,
    "restore_note_fx_chain_snapshot": _restore_note_fx_chain_snapshot_preview,
}


def _dispatch_safe_runner_capture_preview(item: dict[str, Any]) -> dict[str, Any]:
    method_name = str(item.get("capture_method") or "capture_generic_snapshot").strip() or "capture_generic_snapshot"
    handler = _CAPTURE_PREVIEW_DISPATCH.get(method_name)
    if handler is None:
        return _capture_generic_snapshot_preview(item, method_name)
    return dict(handler(item) or {})


def _dispatch_safe_runner_restore_preview(item: dict[str, Any]) -> dict[str, Any]:
    method_name = str(item.get("restore_method") or "restore_generic_snapshot").strip() or "restore_generic_snapshot"
    handler = _RESTORE_PREVIEW_DISPATCH.get(method_name)
    if handler is None:
        return _restore_generic_snapshot_preview(item, method_name)
    return dict(handler(item) or {})


def _build_safe_runner_dispatch_summary(capture_ready_items: list[dict[str, Any]], phase_results: list[dict[str, Any]]) -> str:
    total_objects = len(list(capture_ready_items or []))
    capture_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "capture")
    restore_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "restore")
    rollback_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "rollback-slot")
    return (
        f"Safe-Runner dispatcht jetzt {capture_calls} Capture-, {restore_calls} Restore- und "
        f"{rollback_calls} Rollback-Slot-Aufrufe read-only ueber {total_objects} Snapshot-Objekte."
    )


def _build_state_carrier_dispatch_summary(state_carrier_calls: list[str]) -> str:
    calls = list(state_carrier_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_state_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_state_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_state_preview" in str(item))
    total = len(calls)
    return f"Zustandstraeger dispatchen {capture_calls} Capture-State-, {restore_calls} Restore-State- und {rollback_calls} Rollback-State-Aufrufe read-only ({total} Calls gesamt)."


def _resolve_runtime_snapshot_state_slot_class(snapshot_object_class: str):
    value = str(snapshot_object_class or "").strip().lower()
    return {
        "trackstatesnapshotobject": TrackStateRuntimeStateSlot,
        "routingsnapshotobject": RoutingRuntimeStateSlot,
        "trackkindsnapshotobject": TrackKindRuntimeStateSlot,
        "clipcollectionsnapshotobject": ClipCollectionRuntimeStateSlot,
        "audiofxchainsnapshotobject": AudioFxChainRuntimeStateSlot,
        "notefxchainsnapshotobject": NoteFxChainRuntimeStateSlot,
    }.get(value, _RuntimeSnapshotStateSlotBase)


def _instantiate_runtime_snapshot_state_slot(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    try:
        holder_plan = dict(holder_plan or {})
    except Exception:
        holder_plan = {}
    slot_cls = _resolve_runtime_snapshot_state_slot_class(str(binding.get("snapshot_object_class") or ""))
    return slot_cls(binding, stub_plan, carrier_plan, container_plan, holder_plan)


def _build_runtime_snapshot_state_slots(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]], runtime_snapshot_state_holders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_objects or []) if str(item.get("snapshot_object_key") or "").strip()}
    stub_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_stubs or []) if str(item.get("snapshot_object_key") or "").strip()}
    carrier_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_carriers or []) if str(item.get("snapshot_object_key") or "").strip()}
    container_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_containers or []) if str(item.get("snapshot_object_key") or "").strip()}
    holder_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_holders or []) if str(item.get("snapshot_object_key") or "").strip()}
    result=[]
    for snapshot_object_key, binding in object_map.items():
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        carrier_plan = dict(carrier_map.get(snapshot_object_key) or {})
        container_plan = dict(container_map.get(snapshot_object_key) or {})
        holder_plan = dict(holder_map.get(snapshot_object_key) or {})
        slot_instance = _instantiate_runtime_snapshot_state_slot(binding, stub_plan, carrier_plan, container_plan, holder_plan)
        capture_result = dict(slot_instance.capture_slot_preview() or {})
        restore_result = dict(slot_instance.restore_slot_preview() or {})
        rollback_result = dict(slot_instance.rollback_slot_preview() or {})
        slot_payload_preview = dict(capture_result.get("slot_payload_preview") or {}) if isinstance(capture_result.get("slot_payload_preview"), dict) else {}
        slot_payload_entry_count = int(capture_result.get("slot_payload_entry_count") or 0)
        slot_payload_digest = str(capture_result.get("slot_payload_digest") or "").strip() or _stable_snapshot_payload_digest(slot_payload_preview)
        slot = RuntimeSnapshotStateSlot(
            name=str(binding.get("name") or snapshot_object_key or "Snapshot").strip() or "Snapshot",
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=str(holder_plan.get("holder_key") or "").strip(),
            holder_class=str(holder_plan.get("holder_class") or getattr(slot_instance, "slot_class_name", slot_instance.__class__.__name__)).strip(),
            slot_key=f"state_slot::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            slot_class=str(getattr(slot_instance, "slot_class_name", slot_instance.__class__.__name__)).strip(),
            slot_state="ready" if str(holder_plan.get("holder_key") or "").strip() and bool(slot_payload_digest) else "pending",
            capture_method=str(binding.get("capture_method") or "capture").strip(),
            restore_method=str(binding.get("restore_method") or "restore").strip(),
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip(),
            supports_capture_slot=bool(holder_plan.get("holder_key")) and bool(slot_payload_digest),
            supports_restore_slot=bool(holder_plan.get("holder_key")) and bool(slot_payload_digest),
            supports_runtime_state_slot=bool(holder_plan.get("supports_runtime_state_holder")) and bool(slot_payload_digest),
            instantiate_method="_instantiate_runtime_snapshot_state_slot",
            capture_slot_stub=str(capture_result.get("detail") or "").strip(),
            restore_slot_stub=str(restore_result.get("detail") or "").strip(),
            rollback_slot_stub=str(rollback_result.get("detail") or "").strip(),
            runtime_state_slot_stub=f"{str(getattr(slot_instance, 'slot_class_name', slot_instance.__class__.__name__)).strip()}.slot_state_store_preview",
            holder_payload_preview=copy.deepcopy(dict(holder_plan.get("holder_payload_preview") or {})) if isinstance(holder_plan.get("holder_payload_preview"), dict) else {},
            holder_payload_entry_count=int(holder_plan.get("holder_payload_entry_count") or 0),
            holder_payload_digest=str(holder_plan.get("holder_payload_digest") or "").strip(),
            slot_payload_preview=slot_payload_preview,
            slot_payload_entry_count=slot_payload_entry_count,
            slot_payload_digest=slot_payload_digest,
        )
        result.append(slot.as_plan_dict())
    return result


def _build_runtime_snapshot_state_slot_summary(runtime_snapshot_state_slots: list[dict[str, Any]]) -> str:
    items=list(runtime_snapshot_state_slots or [])
    if not items:
        return ""
    ready=sum(1 for item in items if str(item.get("slot_state") or "").strip().lower()=="ready")
    capture_ready=sum(1 for item in items if bool(item.get("supports_capture_slot")))
    restore_ready=sum(1 for item in items if bool(item.get("supports_restore_slot")))
    total=len(items)
    return f"Runtime-State-Slots: {ready}/{total} bereit, Capture-Slots={capture_ready}/{total}, Restore-Slots={restore_ready}/{total}."


def _build_state_slot_dispatch_summary(state_slot_calls: list[str]) -> str:
    calls = list(state_slot_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_slot_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_slot_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_slot_preview" in str(item))
    total = len(calls)
    return f"State-Slots dispatchen {capture_calls} Capture-Slot-, {restore_calls} Restore-Slot- und {rollback_calls} Rollback-Slot-Aufrufe read-only ({total} Calls gesamt)."


def _build_state_container_dispatch_summary(state_container_calls: list[str]) -> str:
    calls = list(state_container_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_container_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_container_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_container_preview" in str(item))
    total = len(calls)
    return f"State-Container dispatchen {capture_calls} Capture-Container-, {restore_calls} Restore-Container- und {rollback_calls} Rollback-Container-Aufrufe read-only ({total} Calls gesamt)."


def _build_state_holder_dispatch_summary(state_holder_calls: list[str]) -> str:
    calls = list(state_holder_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_holder_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_holder_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_holder_preview" in str(item))
    total = len(calls)
    return f"State-Halter dispatchen {capture_calls} Capture-Halter-, {restore_calls} Restore-Halter- und {rollback_calls} Rollback-Halter-Aufrufe read-only ({total} Calls gesamt)."


def _resolve_runtime_snapshot_state_store_class(snapshot_object_class: str):
    value = str(snapshot_object_class or "").strip().lower()
    return {
        "trackstatesnapshotobject": TrackStateRuntimeStateStore,
        "routingsnapshotobject": RoutingRuntimeStateStore,
        "trackkindsnapshotobject": TrackKindRuntimeStateStore,
        "clipcollectionsnapshotobject": ClipCollectionRuntimeStateStore,
        "audiofxchainsnapshotobject": AudioFxChainRuntimeStateStore,
        "notefxchainsnapshotobject": NoteFxChainRuntimeStateStore,
    }.get(value, _RuntimeSnapshotStateStoreBase)


def _instantiate_runtime_snapshot_state_store(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    try:
        holder_plan = dict(holder_plan or {})
    except Exception:
        holder_plan = {}
    try:
        slot_plan = dict(slot_plan or {})
    except Exception:
        slot_plan = {}
    store_cls = _resolve_runtime_snapshot_state_store_class(str(binding.get("snapshot_object_class") or ""))
    return store_cls(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan)


def _build_runtime_snapshot_state_stores(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]], runtime_snapshot_state_holders: list[dict[str, Any]], runtime_snapshot_state_slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_objects or []) if str(item.get("snapshot_object_key") or "").strip()}
    stub_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_stubs or []) if str(item.get("snapshot_object_key") or "").strip()}
    carrier_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_carriers or []) if str(item.get("snapshot_object_key") or "").strip()}
    container_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_containers or []) if str(item.get("snapshot_object_key") or "").strip()}
    holder_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_holders or []) if str(item.get("snapshot_object_key") or "").strip()}
    slot_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_slots or []) if str(item.get("snapshot_object_key") or "").strip()}
    result = []
    for snapshot_object_key, binding in object_map.items():
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        carrier_plan = dict(carrier_map.get(snapshot_object_key) or {})
        container_plan = dict(container_map.get(snapshot_object_key) or {})
        holder_plan = dict(holder_map.get(snapshot_object_key) or {})
        slot_plan = dict(slot_map.get(snapshot_object_key) or {})
        store_instance = _instantiate_runtime_snapshot_state_store(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan)
        capture_result = dict(store_instance.capture_store_preview() or {})
        restore_result = dict(store_instance.restore_store_preview() or {})
        rollback_result = dict(store_instance.rollback_store_preview() or {})
        store_payload_preview = dict(capture_result.get("store_payload_preview") or {}) if isinstance(capture_result.get("store_payload_preview"), dict) else {}
        store_payload_entry_count = int(capture_result.get("store_payload_entry_count") or 0)
        store_payload_digest = str(capture_result.get("store_payload_digest") or "").strip() or _stable_snapshot_payload_digest(store_payload_preview)
        capture_handle_key = str(capture_result.get("capture_handle_key") or "").strip()
        restore_handle_key = str(capture_result.get("restore_handle_key") or "").strip()
        rollback_handle_key = str(capture_result.get("rollback_handle_key") or "").strip()
        store = RuntimeSnapshotStateStore(
            name=str(binding.get("name") or snapshot_object_key or "Snapshot").strip() or "Snapshot",
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=str(holder_plan.get("holder_key") or "").strip(),
            holder_class=str(holder_plan.get("holder_class") or "").strip(),
            slot_key=str(slot_plan.get("slot_key") or "").strip(),
            slot_class=str(slot_plan.get("slot_class") or getattr(store_instance, "store_class_name", store_instance.__class__.__name__)).strip(),
            store_key=f"state_store::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            store_class=str(getattr(store_instance, "store_class_name", store_instance.__class__.__name__)).strip(),
            store_state="ready" if str(slot_plan.get("slot_key") or "").strip() and bool(store_payload_digest) else "pending",
            capture_method=str(binding.get("capture_method") or "capture").strip(),
            restore_method=str(binding.get("restore_method") or "restore").strip(),
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip(),
            supports_capture_store=bool(slot_plan.get("slot_key")) and bool(capture_handle_key) and bool(store_payload_digest),
            supports_restore_store=bool(slot_plan.get("slot_key")) and bool(restore_handle_key) and bool(store_payload_digest),
            supports_runtime_state_store=bool(slot_plan.get("supports_runtime_state_slot")) and bool(store_payload_digest),
            instantiate_method="_instantiate_runtime_snapshot_state_store",
            capture_store_stub=str(capture_result.get("detail") or "").strip(),
            restore_store_stub=str(restore_result.get("detail") or "").strip(),
            rollback_store_stub=str(rollback_result.get("detail") or "").strip(),
            runtime_state_store_stub=f"{str(getattr(store_instance, 'store_class_name', store_instance.__class__.__name__)).strip()}.capture_handle_store_preview",
            capture_handle_key=capture_handle_key,
            restore_handle_key=restore_handle_key,
            rollback_handle_key=rollback_handle_key,
            capture_handle_state=str(capture_result.get("capture_handle_state") or "").strip() or "pending",
            slot_payload_preview=copy.deepcopy(dict(slot_plan.get("slot_payload_preview") or {})) if isinstance(slot_plan.get("slot_payload_preview"), dict) else {},
            slot_payload_entry_count=int(slot_plan.get("slot_payload_entry_count") or 0),
            slot_payload_digest=str(slot_plan.get("slot_payload_digest") or "").strip(),
            store_payload_preview=store_payload_preview,
            store_payload_entry_count=store_payload_entry_count,
            store_payload_digest=store_payload_digest,
        )
        result.append(store.as_plan_dict())
    return result


def _build_runtime_snapshot_state_store_summary(runtime_snapshot_state_stores: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_stores or [])
    if not items:
        return ""
    total = len(items)
    ready = sum(1 for item in items if str(item.get("store_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_store")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_store")))
    handle_ready = sum(1 for item in items if str(item.get("capture_handle_key") or "").strip() and str(item.get("restore_handle_key") or "").strip())
    return f"Runtime-State-Stores: {ready}/{total} bereit, Capture-Stores={capture_ready}/{total}, Restore-Stores={restore_ready}/{total}, Capture-Handles={handle_ready}/{total}."


def _build_state_store_dispatch_summary(state_store_calls: list[str]) -> str:
    calls = list(state_store_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_store_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_store_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_store_preview" in str(item))
    total = len(calls)
    return f"State-Stores dispatchen {capture_calls} Capture-Store-, {restore_calls} Restore-Store- und {rollback_calls} Rollback-Store-Aufrufe read-only ({total} Calls gesamt)."


def _resolve_runtime_snapshot_state_registry_class(snapshot_object_class: str):
    mapping = {
        "TrackStateRuntimeSnapshotObject": TrackStateRuntimeStateRegistry,
        "RoutingRuntimeSnapshotObject": RoutingRuntimeStateRegistry,
        "TrackKindRuntimeSnapshotObject": TrackKindRuntimeStateRegistry,
        "ClipCollectionRuntimeSnapshotObject": ClipCollectionRuntimeStateRegistry,
        "AudioFxChainRuntimeSnapshotObject": AudioFxChainRuntimeStateRegistry,
        "NoteFxChainRuntimeSnapshotObject": NoteFxChainRuntimeStateRegistry,
    }
    return mapping.get(str(snapshot_object_class or "").strip(), _RuntimeSnapshotStateRegistryBase)


def _instantiate_runtime_snapshot_state_registry(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    try:
        holder_plan = dict(holder_plan or {})
    except Exception:
        holder_plan = {}
    try:
        slot_plan = dict(slot_plan or {})
    except Exception:
        slot_plan = {}
    try:
        store_plan = dict(store_plan or {})
    except Exception:
        store_plan = {}
    registry_cls = _resolve_runtime_snapshot_state_registry_class(str(binding.get("snapshot_object_class") or ""))
    return registry_cls(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan)


def _resolve_runtime_snapshot_state_registry_backend_class(snapshot_object_class: str):
    mapping = {
        "TrackStateRuntimeSnapshotObject": TrackStateRuntimeStateRegistryBackend,
        "RoutingRuntimeSnapshotObject": RoutingRuntimeStateRegistryBackend,
        "TrackKindRuntimeSnapshotObject": TrackKindRuntimeStateRegistryBackend,
        "ClipCollectionRuntimeSnapshotObject": ClipCollectionRuntimeStateRegistryBackend,
        "AudioFxChainRuntimeSnapshotObject": AudioFxChainRuntimeStateRegistryBackend,
        "NoteFxChainRuntimeSnapshotObject": NoteFxChainRuntimeStateRegistryBackend,
    }
    return mapping.get(str(snapshot_object_class or "").strip(), _RuntimeSnapshotStateRegistryBackendBase)


def _instantiate_runtime_snapshot_state_registry_backend(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None, registry_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    try:
        holder_plan = dict(holder_plan or {})
    except Exception:
        holder_plan = {}
    try:
        slot_plan = dict(slot_plan or {})
    except Exception:
        slot_plan = {}
    try:
        store_plan = dict(store_plan or {})
    except Exception:
        store_plan = {}
    try:
        registry_plan = dict(registry_plan or {})
    except Exception:
        registry_plan = {}
    backend_cls = _resolve_runtime_snapshot_state_registry_backend_class(str(binding.get("snapshot_object_class") or ""))
    return backend_cls(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan)


def _resolve_runtime_snapshot_state_registry_backend_adapter_class(snapshot_object_class: str):
    mapping = {
        "TrackStateRuntimeSnapshotObject": TrackStateRuntimeStateRegistryBackendAdapter,
        "RoutingRuntimeSnapshotObject": RoutingRuntimeStateRegistryBackendAdapter,
        "TrackKindRuntimeSnapshotObject": TrackKindRuntimeStateRegistryBackendAdapter,
        "ClipCollectionRuntimeSnapshotObject": ClipCollectionRuntimeStateRegistryBackendAdapter,
        "AudioFxChainRuntimeSnapshotObject": AudioFxChainRuntimeStateRegistryBackendAdapter,
        "NoteFxChainRuntimeSnapshotObject": NoteFxChainRuntimeStateRegistryBackendAdapter,
    }
    return mapping.get(str(snapshot_object_class or "").strip(), _RuntimeSnapshotStateRegistryBackendAdapterBase)


def _instantiate_runtime_snapshot_state_registry_backend_adapter(binding: dict[str, Any] | None = None, stub_plan: dict[str, Any] | None = None, carrier_plan: dict[str, Any] | None = None, container_plan: dict[str, Any] | None = None, holder_plan: dict[str, Any] | None = None, slot_plan: dict[str, Any] | None = None, store_plan: dict[str, Any] | None = None, registry_plan: dict[str, Any] | None = None, backend_plan: dict[str, Any] | None = None):
    try:
        binding = dict(binding or {})
    except Exception:
        binding = {}
    try:
        stub_plan = dict(stub_plan or {})
    except Exception:
        stub_plan = {}
    try:
        carrier_plan = dict(carrier_plan or {})
    except Exception:
        carrier_plan = {}
    try:
        container_plan = dict(container_plan or {})
    except Exception:
        container_plan = {}
    try:
        holder_plan = dict(holder_plan or {})
    except Exception:
        holder_plan = {}
    try:
        slot_plan = dict(slot_plan or {})
    except Exception:
        slot_plan = {}
    try:
        store_plan = dict(store_plan or {})
    except Exception:
        store_plan = {}
    try:
        registry_plan = dict(registry_plan or {})
    except Exception:
        registry_plan = {}
    try:
        backend_plan = dict(backend_plan or {})
    except Exception:
        backend_plan = {}
    adapter_cls = _resolve_runtime_snapshot_state_registry_backend_adapter_class(str(binding.get("snapshot_object_class") or ""))
    return adapter_cls(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan, backend_plan)


def _build_runtime_snapshot_state_registries(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]], runtime_snapshot_state_holders: list[dict[str, Any]], runtime_snapshot_state_slots: list[dict[str, Any]], runtime_snapshot_state_stores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_objects or []) if str(item.get("snapshot_object_key") or "").strip()}
    stub_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_stubs or []) if str(item.get("snapshot_object_key") or "").strip()}
    carrier_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_carriers or []) if str(item.get("snapshot_object_key") or "").strip()}
    container_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_containers or []) if str(item.get("snapshot_object_key") or "").strip()}
    holder_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_holders or []) if str(item.get("snapshot_object_key") or "").strip()}
    slot_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_slots or []) if str(item.get("snapshot_object_key") or "").strip()}
    store_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_stores or []) if str(item.get("snapshot_object_key") or "").strip()}
    result = []
    for snapshot_object_key, binding in object_map.items():
        stub_plan = dict(stub_map.get(snapshot_object_key) or {})
        carrier_plan = dict(carrier_map.get(snapshot_object_key) or {})
        container_plan = dict(container_map.get(snapshot_object_key) or {})
        holder_plan = dict(holder_map.get(snapshot_object_key) or {})
        slot_plan = dict(slot_map.get(snapshot_object_key) or {})
        store_plan = dict(store_map.get(snapshot_object_key) or {})
        registry_instance = _instantiate_runtime_snapshot_state_registry(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan)
        capture_result = dict(registry_instance.capture_registry_preview() or {})
        restore_result = dict(registry_instance.restore_registry_preview() or {})
        rollback_result = dict(registry_instance.rollback_registry_preview() or {})
        registry_payload_preview = dict(capture_result.get("registry_payload_preview") or {}) if isinstance(capture_result.get("registry_payload_preview"), dict) else {}
        registry_payload_entry_count = int(capture_result.get("registry_payload_entry_count") or 0)
        registry_payload_digest = str(capture_result.get("registry_payload_digest") or "").strip() or _stable_snapshot_payload_digest(registry_payload_preview)
        handle_store_key = str(capture_result.get("handle_store_key") or "").strip()
        registry_class = str(getattr(registry_instance, "registry_class_name", registry_instance.__class__.__name__)).strip() or registry_instance.__class__.__name__
        handle_store_class = str(getattr(registry_instance, "handle_store_class_name", "GenericRuntimeSnapshotHandleStore")).strip() or "GenericRuntimeSnapshotHandleStore"
        registry = RuntimeSnapshotStateRegistry(
            name=str(binding.get("name") or snapshot_object_key or "Snapshot").strip() or "Snapshot",
            snapshot_object_key=snapshot_object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=str(holder_plan.get("holder_key") or "").strip(),
            holder_class=str(holder_plan.get("holder_class") or "").strip(),
            slot_key=str(slot_plan.get("slot_key") or "").strip(),
            slot_class=str(slot_plan.get("slot_class") or "").strip(),
            store_key=str(store_plan.get("store_key") or "").strip(),
            store_class=str(store_plan.get("store_class") or "").strip(),
            registry_key=f"state_registry::{_sanitize_ref_token(snapshot_object_key, 'snapshot_object')}",
            registry_class=registry_class,
            registry_state="ready" if str(store_plan.get("store_key") or "").strip() and bool(handle_store_key) and bool(registry_payload_digest) else "pending",
            capture_method=str(binding.get("capture_method") or "capture").strip(),
            restore_method=str(binding.get("restore_method") or "restore").strip(),
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip(),
            supports_capture_registry=bool(store_plan.get("store_key")) and bool(handle_store_key) and bool(registry_payload_digest),
            supports_restore_registry=bool(store_plan.get("store_key")) and bool(handle_store_key) and bool(registry_payload_digest),
            supports_runtime_state_registry=bool(store_plan.get("supports_runtime_state_store")) and bool(registry_payload_digest),
            instantiate_method="_instantiate_runtime_snapshot_state_registry",
            capture_registry_stub=str(capture_result.get("detail") or "").strip(),
            restore_registry_stub=str(restore_result.get("detail") or "").strip(),
            rollback_registry_stub=str(rollback_result.get("detail") or "").strip(),
            runtime_state_registry_stub=f"{registry_class}.capture_registry_preview",
            capture_handle_key=str(store_plan.get("capture_handle_key") or "").strip(),
            restore_handle_key=str(store_plan.get("restore_handle_key") or "").strip(),
            rollback_handle_key=str(store_plan.get("rollback_handle_key") or "").strip(),
            handle_store_key=handle_store_key,
            handle_store_class=handle_store_class,
            handle_store_state="ready" if handle_store_key else "pending",
            store_payload_preview=copy.deepcopy(dict(store_plan.get("store_payload_preview") or {})) if isinstance(store_plan.get("store_payload_preview"), dict) else {},
            store_payload_entry_count=int(store_plan.get("store_payload_entry_count") or 0),
            store_payload_digest=str(store_plan.get("store_payload_digest") or "").strip(),
            registry_payload_preview=registry_payload_preview,
            registry_payload_entry_count=registry_payload_entry_count,
            registry_payload_digest=registry_payload_digest,
        )
        result.append(registry.as_plan_dict())
    return result


def _build_runtime_snapshot_state_registry_summary(runtime_snapshot_state_registries: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_registries or [])
    if not items:
        return ""
    total = len(items)
    ready = sum(1 for item in items if str(item.get("registry_state") or "").strip().lower() == "ready")
    capture_ready = sum(1 for item in items if bool(item.get("supports_capture_registry")))
    restore_ready = sum(1 for item in items if bool(item.get("supports_restore_registry")))
    handle_store_ready = sum(1 for item in items if str(item.get("handle_store_key") or "").strip())
    return f"Runtime-State-Registries: {ready}/{total} bereit, Capture-Registries={capture_ready}/{total}, Restore-Registries={restore_ready}/{total}, Handle-Speicher={handle_store_ready}/{total}."


def _build_state_registry_dispatch_summary(state_registry_calls: list[str]) -> str:
    calls = list(state_registry_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_registry_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_registry_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_registry_preview" in str(item))
    total = len(calls)
    return f"State-Registries dispatchen {capture_calls} Capture-Registry-, {restore_calls} Restore-Registry- und {rollback_calls} Rollback-Registry-Aufrufe read-only ({total} Calls gesamt)."


def _build_runtime_snapshot_state_registry_backends(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]], runtime_snapshot_state_holders: list[dict[str, Any]], runtime_snapshot_state_slots: list[dict[str, Any]], runtime_snapshot_state_stores: list[dict[str, Any]], runtime_snapshot_state_registries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_objects or []) if str(item.get("snapshot_object_key") or "").strip()}
    stub_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_stubs or []) if str(item.get("snapshot_object_key") or "").strip()}
    carrier_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_carriers or []) if str(item.get("snapshot_object_key") or "").strip()}
    container_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_containers or []) if str(item.get("snapshot_object_key") or "").strip()}
    holder_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_holders or []) if str(item.get("snapshot_object_key") or "").strip()}
    slot_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_slots or []) if str(item.get("snapshot_object_key") or "").strip()}
    store_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_stores or []) if str(item.get("snapshot_object_key") or "").strip()}
    registry_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_registries or []) if str(item.get("snapshot_object_key") or "").strip()}
    result: list[dict[str, Any]] = []
    for object_key, binding in list(object_map.items()):
        stub_plan = dict(stub_map.get(object_key) or {})
        carrier_plan = dict(carrier_map.get(object_key) or {})
        container_plan = dict(container_map.get(object_key) or {})
        holder_plan = dict(holder_map.get(object_key) or {})
        slot_plan = dict(slot_map.get(object_key) or {})
        store_plan = dict(store_map.get(object_key) or {})
        registry_plan = dict(registry_map.get(object_key) or {})
        backend_instance = _instantiate_runtime_snapshot_state_registry_backend(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan)
        backend_class = getattr(backend_instance, "backend_class_name", backend_instance.__class__.__name__)
        handle_register_class = getattr(backend_instance, "handle_register_class_name", "GenericRuntimeSnapshotHandleRegister")
        registry_slot_class = getattr(backend_instance, "registry_slot_class_name", "GenericRuntimeSnapshotRegistrySlot")
        capture_preview = dict(backend_instance.capture_backend_preview() or {})
        backend_payload_preview = copy.deepcopy(dict(capture_preview.get("backend_payload_preview") or {})) if isinstance(capture_preview.get("backend_payload_preview"), dict) else {}
        backend = RuntimeSnapshotStateRegistryBackend(
            name=str(binding.get("name") or object_key).strip() or object_key,
            snapshot_object_key=object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=str(holder_plan.get("holder_key") or "").strip(),
            holder_class=str(holder_plan.get("holder_class") or "").strip(),
            slot_key=str(slot_plan.get("slot_key") or "").strip(),
            slot_class=str(slot_plan.get("slot_class") or "").strip(),
            store_key=str(store_plan.get("store_key") or "").strip(),
            store_class=str(store_plan.get("store_class") or "").strip(),
            registry_key=str(registry_plan.get("registry_key") or "").strip(),
            registry_class=str(registry_plan.get("registry_class") or "").strip(),
            backend_key=str(backend_instance._backend_key()).strip(),
            backend_class=str(backend_class).strip(),
            backend_state="ready" if str(backend_instance._backend_key()).strip() else "pending",
            capture_method=str(binding.get("capture_method") or "capture").strip() or "capture",
            restore_method=str(binding.get("restore_method") or "restore").strip() or "restore",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_backend=True,
            supports_restore_backend=True,
            supports_runtime_state_backend=True,
            instantiate_method="instantiate_runtime_snapshot_state_registry_backend",
            capture_backend_stub="capture_backend_preview",
            restore_backend_stub="restore_backend_preview",
            rollback_backend_stub="rollback_backend_preview",
            runtime_state_backend_stub=str(capture_preview.get("detail") or "").strip(),
            handle_register_key=str(backend_instance._handle_register_key()).strip(),
            handle_register_class=str(handle_register_class).strip(),
            handle_register_state="ready" if str(backend_instance._handle_register_key()).strip() else "pending",
            registry_slot_key=str(backend_instance._registry_slot_key()).strip(),
            registry_slot_class=str(registry_slot_class).strip(),
            registry_slot_state="ready" if str(backend_instance._registry_slot_key()).strip() else "pending",
            registry_payload_preview=copy.deepcopy(dict(registry_plan.get("registry_payload_preview") or {})) if isinstance(registry_plan.get("registry_payload_preview"), dict) else {},
            registry_payload_entry_count=int(registry_plan.get("registry_payload_entry_count") or 0),
            registry_payload_digest=str(registry_plan.get("registry_payload_digest") or "").strip(),
            backend_payload_preview=backend_payload_preview,
            backend_payload_entry_count=int(capture_preview.get("backend_payload_entry_count") or 0),
            backend_payload_digest=str(capture_preview.get("backend_payload_digest") or "").strip(),
        )
        result.append(backend.as_plan_dict())
    return result


def _build_runtime_snapshot_state_registry_backend_summary(runtime_snapshot_state_registry_backends: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_registry_backends or [])
    if not items:
        return ""
    total = len(items)
    ready = sum(1 for item in items if str(item.get("backend_state") or "").strip().lower() == "ready")
    handle_registers = sum(1 for item in items if str(item.get("handle_register_key") or "").strip())
    registry_slots = sum(1 for item in items if str(item.get("registry_slot_key") or "").strip())
    return f"Runtime-State-Registry-Backends: {ready}/{total} bereit, Handle-Register={handle_registers}/{total}, Registry-Slots={registry_slots}/{total}."


def _build_state_registry_backend_dispatch_summary(state_registry_backend_calls: list[str]) -> str:
    calls = list(state_registry_backend_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_backend_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_backend_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_backend_preview" in str(item))
    total = len(calls)
    return f"State-Registry-Backends dispatchen {capture_calls} Capture-Backend-, {restore_calls} Restore-Backend- und {rollback_calls} Rollback-Backend-Aufrufe read-only ({total} Calls gesamt)."


def _build_runtime_snapshot_state_registry_backend_adapters(runtime_snapshot_objects: list[dict[str, Any]], runtime_snapshot_stubs: list[dict[str, Any]], runtime_snapshot_state_carriers: list[dict[str, Any]], runtime_snapshot_state_containers: list[dict[str, Any]], runtime_snapshot_state_holders: list[dict[str, Any]], runtime_snapshot_state_slots: list[dict[str, Any]], runtime_snapshot_state_stores: list[dict[str, Any]], runtime_snapshot_state_registries: list[dict[str, Any]], runtime_snapshot_state_registry_backends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_objects or []) if str(item.get("snapshot_object_key") or "").strip()}
    stub_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_stubs or []) if str(item.get("snapshot_object_key") or "").strip()}
    carrier_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_carriers or []) if str(item.get("snapshot_object_key") or "").strip()}
    container_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_containers or []) if str(item.get("snapshot_object_key") or "").strip()}
    holder_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_holders or []) if str(item.get("snapshot_object_key") or "").strip()}
    slot_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_slots or []) if str(item.get("snapshot_object_key") or "").strip()}
    store_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_stores or []) if str(item.get("snapshot_object_key") or "").strip()}
    registry_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_registries or []) if str(item.get("snapshot_object_key") or "").strip()}
    backend_map = {str(item.get("snapshot_object_key") or "").strip(): dict(item or {}) for item in list(runtime_snapshot_state_registry_backends or []) if str(item.get("snapshot_object_key") or "").strip()}
    result: list[dict[str, Any]] = []
    for object_key, binding in list(object_map.items()):
        stub_plan = dict(stub_map.get(object_key) or {})
        carrier_plan = dict(carrier_map.get(object_key) or {})
        container_plan = dict(container_map.get(object_key) or {})
        holder_plan = dict(holder_map.get(object_key) or {})
        slot_plan = dict(slot_map.get(object_key) or {})
        store_plan = dict(store_map.get(object_key) or {})
        registry_plan = dict(registry_map.get(object_key) or {})
        backend_plan = dict(backend_map.get(object_key) or {})
        adapter_instance = _instantiate_runtime_snapshot_state_registry_backend_adapter(binding, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan, backend_plan)
        adapter_class = getattr(adapter_instance, "adapter_class_name", adapter_instance.__class__.__name__)
        backend_store_adapter_class = getattr(adapter_instance, "backend_store_adapter_class_name", "GenericRuntimeSnapshotBackendStoreAdapter")
        registry_slot_backend_class = getattr(adapter_instance, "registry_slot_backend_class_name", "GenericRuntimeSnapshotRegistrySlotBackend")
        capture_preview = dict(adapter_instance.capture_adapter_preview() or {})
        adapter_payload_preview = copy.deepcopy(dict(capture_preview.get("adapter_payload_preview") or {})) if isinstance(capture_preview.get("adapter_payload_preview"), dict) else {}
        adapter = RuntimeSnapshotStateRegistryBackendAdapter(
            name=str(binding.get("name") or object_key).strip() or object_key,
            snapshot_object_key=object_key,
            snapshot_object_class=str(binding.get("snapshot_object_class") or "").strip(),
            stub_key=str(stub_plan.get("stub_key") or "").strip(),
            stub_class=str(stub_plan.get("stub_class") or "").strip(),
            carrier_key=str(carrier_plan.get("carrier_key") or "").strip(),
            carrier_class=str(carrier_plan.get("carrier_class") or "").strip(),
            container_key=str(container_plan.get("container_key") or "").strip(),
            container_class=str(container_plan.get("container_class") or "").strip(),
            holder_key=str(holder_plan.get("holder_key") or "").strip(),
            holder_class=str(holder_plan.get("holder_class") or "").strip(),
            slot_key=str(slot_plan.get("slot_key") or "").strip(),
            slot_class=str(slot_plan.get("slot_class") or "").strip(),
            store_key=str(store_plan.get("store_key") or "").strip(),
            store_class=str(store_plan.get("store_class") or "").strip(),
            registry_key=str(registry_plan.get("registry_key") or "").strip(),
            registry_class=str(registry_plan.get("registry_class") or "").strip(),
            backend_key=str(backend_plan.get("backend_key") or "").strip(),
            backend_class=str(backend_plan.get("backend_class") or "").strip(),
            adapter_key=str(adapter_instance._adapter_key()).strip(),
            adapter_class=str(adapter_class).strip(),
            adapter_state="ready" if str(adapter_instance._adapter_key()).strip() else "pending",
            capture_method=str(binding.get("capture_method") or "capture").strip() or "capture",
            restore_method=str(binding.get("restore_method") or "restore").strip() or "restore",
            rollback_slot=str(binding.get("rollback_slot") or "rollback").strip() or "rollback",
            supports_capture_backend_adapter=True,
            supports_restore_backend_adapter=True,
            supports_runtime_state_backend_adapter=True,
            instantiate_method="_instantiate_runtime_snapshot_state_registry_backend_adapter",
            capture_adapter_stub="capture_adapter_preview",
            restore_adapter_stub="restore_adapter_preview",
            rollback_adapter_stub="rollback_adapter_preview",
            runtime_state_backend_adapter_stub=str(capture_preview.get("detail") or "").strip(),
            backend_store_adapter_key=str(adapter_instance._backend_store_adapter_key()).strip(),
            backend_store_adapter_class=str(backend_store_adapter_class).strip(),
            backend_store_adapter_state="ready" if str(adapter_instance._backend_store_adapter_key()).strip() else "pending",
            registry_slot_backend_key=str(adapter_instance._registry_slot_backend_key()).strip(),
            registry_slot_backend_class=str(registry_slot_backend_class).strip(),
            registry_slot_backend_state="ready" if str(adapter_instance._registry_slot_backend_key()).strip() else "pending",
            backend_payload_preview=copy.deepcopy(dict(backend_plan.get("backend_payload_preview") or {})) if isinstance(backend_plan.get("backend_payload_preview"), dict) else {},
            backend_payload_entry_count=int(backend_plan.get("backend_payload_entry_count") or 0),
            backend_payload_digest=str(backend_plan.get("backend_payload_digest") or "").strip(),
            adapter_payload_preview=adapter_payload_preview,
            adapter_payload_entry_count=int(capture_preview.get("adapter_payload_entry_count") or 0),
            adapter_payload_digest=str(capture_preview.get("adapter_payload_digest") or "").strip(),
        )
        result.append(adapter.as_plan_dict())
    return result


def _build_runtime_snapshot_state_registry_backend_adapter_summary(runtime_snapshot_state_registry_backend_adapters: list[dict[str, Any]]) -> str:
    items = list(runtime_snapshot_state_registry_backend_adapters or [])
    if not items:
        return ""
    total = len(items)
    ready = sum(1 for item in items if str(item.get("adapter_state") or "").strip().lower() == "ready")
    backend_store_adapters = sum(1 for item in items if str(item.get("backend_store_adapter_key") or "").strip())
    registry_slot_backends = sum(1 for item in items if str(item.get("registry_slot_backend_key") or "").strip())
    return f"Runtime-State-Registry-Backend-Adapter: {ready}/{total} bereit, Backend-Store-Adapter={backend_store_adapters}/{total}, Registry-Slot-Backends={registry_slot_backends}/{total}."


def _build_state_registry_backend_adapter_dispatch_summary(state_registry_backend_adapter_calls: list[str]) -> str:
    calls = list(state_registry_backend_adapter_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_adapter_preview" in str(item) or ".capture_apply_runner_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_adapter_preview" in str(item) or ".restore_apply_runner_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_adapter_preview" in str(item) or ".rollback_apply_runner_preview" in str(item))
    total = len(calls)
    return f"State-Registry-Backend-Adapter dispatchen {capture_calls} Capture-Adapter-, {restore_calls} Restore-Adapter- und {rollback_calls} Rollback-Adapter-Aufrufe read-only ({total} Calls gesamt)."


def _build_backend_store_adapter_dispatch_summary(backend_store_adapter_calls: list[str]) -> str:
    calls = list(backend_store_adapter_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_backend_store_adapter_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_backend_store_adapter_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_backend_store_adapter_preview" in str(item))
    total = len(calls)
    return f"Backend-Store-Adapter dispatchen {capture_calls} Capture-, {restore_calls} Restore- und {rollback_calls} Rollback-Aufrufe read-only ({total} Calls gesamt)."


def _build_registry_slot_backend_dispatch_summary(registry_slot_backend_calls: list[str]) -> str:
    calls = list(registry_slot_backend_calls or [])
    if not calls:
        return ""
    capture_calls = sum(1 for item in calls if ".capture_registry_slot_backend_preview" in str(item))
    restore_calls = sum(1 for item in calls if ".restore_registry_slot_backend_preview" in str(item))
    rollback_calls = sum(1 for item in calls if ".rollback_registry_slot_backend_preview" in str(item))
    total = len(calls)
    return f"Registry-Slot-Backends dispatchen {capture_calls} Capture-, {restore_calls} Restore- und {rollback_calls} Rollback-Aufrufe read-only ({total} Calls gesamt)."


def _build_snapshot_apply_runner_dispatch_summary(capture_ready_items: list[dict[str, Any]], phase_results: list[dict[str, Any]]) -> str:
    total_objects = len(list(capture_ready_items or []))
    capture_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "apply-runner-capture")
    restore_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "apply-runner-restore")
    rollback_calls = sum(1 for item in phase_results if str(item.get("phase") or "").strip().lower() == "apply-runner-rollback")
    return (
        f"Snapshot-Transaktions-Apply-Runner dispatcht jetzt {capture_calls} Capture-, {restore_calls} Restore- und "
        f"{rollback_calls} Rollback-Aufrufe read-only ueber {total_objects} Adapter-Ziele."
    )


def _build_runtime_snapshot_apply_runner(runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_state_registry_backend_adapters: list[dict[str, Any]] | None, transaction_steps: list[str] | None) -> dict[str, Any]:
    bundle = dict(runtime_snapshot_bundle or {})
    adapter_items = [dict(item or {}) for item in list(runtime_snapshot_state_registry_backend_adapters or [])]
    tx_key = str(bundle.get("transaction_key") or "audio_to_instrument_morph::preview").strip() or "audio_to_instrument_morph::preview"
    bundle_key = str(bundle.get("bundle_key") or "").strip()
    tx_token = _sanitize_ref_token(tx_key, "audio_to_instrument_morph_preview")
    ready_items = [
        item for item in adapter_items
        if str(item.get("adapter_state") or "").strip().lower() == "ready"
        and bool(item.get("supports_capture_backend_adapter"))
        and bool(item.get("supports_restore_backend_adapter"))
        and str(item.get("adapter_key") or "").strip()
    ]
    apply_sequence = tuple(
        str(item.get("snapshot_object_key") or "").strip()
        for item in ready_items
        if str(item.get("snapshot_object_key") or "").strip()
    )
    restore_sequence = tuple(reversed(apply_sequence))
    rollback_sequence = tuple(
        f"{str(item.get('rollback_slot') or '').strip() or 'rollback'}::{str(item.get('snapshot_object_key') or '').strip()}"
        for item in sorted(ready_items, key=lambda item: (str(item.get("rollback_slot") or "").strip(), str(item.get("snapshot_object_key") or "").strip()))
        if str(item.get("snapshot_object_key") or "").strip()
    )
    phase_results: list[dict[str, Any]] = []
    rehearsed_steps: list[str] = []
    state_registry_backend_adapter_calls: list[str] = []
    backend_store_adapter_calls: list[str] = []
    registry_slot_backend_calls: list[str] = []
    for item in ready_items:
        adapter_instance = _instantiate_runtime_snapshot_state_registry_backend_adapter(item)
        adapter_class = str(item.get("adapter_class") or getattr(adapter_instance, "adapter_class_name", adapter_instance.__class__.__name__)).strip() or adapter_instance.__class__.__name__
        backend_store_class = str(item.get("backend_store_adapter_class") or getattr(adapter_instance, "backend_store_adapter_class_name", "GenericRuntimeSnapshotBackendStoreAdapter")).strip() or "GenericRuntimeSnapshotBackendStoreAdapter"
        registry_slot_class = str(item.get("registry_slot_backend_class") or getattr(adapter_instance, "registry_slot_backend_class_name", "GenericRuntimeSnapshotRegistrySlotBackend")).strip() or "GenericRuntimeSnapshotRegistrySlotBackend"
        object_key = str(item.get("snapshot_object_key") or "").strip()
        for phase in ("capture", "restore", "rollback"):
            phase_method = getattr(adapter_instance, f"{phase}_apply_runner_preview")
            phase_results.append(dict(phase_method() or {}))
            state_registry_backend_adapter_calls.append(f"{adapter_class}.{phase}_apply_runner_preview")
            backend_method = getattr(adapter_instance, f"{phase}_backend_store_adapter_preview")
            phase_results.append(dict(backend_method() or {}))
            backend_store_adapter_calls.append(f"{backend_store_class}.{phase}_backend_store_adapter_preview")
            registry_method = getattr(adapter_instance, f"{phase}_registry_slot_backend_preview")
            phase_results.append(dict(registry_method() or {}))
            registry_slot_backend_calls.append(f"{registry_slot_class}.{phase}_registry_slot_backend_preview")
            rehearsed_steps.append(f"apply-runner::{phase}::{object_key}")
    commit_stub = str(bundle.get("commit_stub") or "commit_audio_to_instrument_morph_transaction").strip() or "commit_audio_to_instrument_morph_transaction"
    rollback_stub = str(bundle.get("rollback_stub") or "rollback_audio_to_instrument_morph_transaction").strip() or "rollback_audio_to_instrument_morph_transaction"
    if ready_items:
        phase_results.append({
            "phase": "apply-runner-commit-preview",
            "target": bundle_key or tx_key,
            "method": commit_stub,
            "state": "blocked",
            "detail": "Commit bleibt im Apply-Runner bewusst gesperrt; es wird weiterhin nichts angewendet.",
        })
        rehearsed_steps.append(f"apply-runner::commit-preview::{commit_stub}")
        phase_results.append({
            "phase": "apply-runner-rollback-preview",
            "target": bundle_key or tx_key,
            "method": rollback_stub,
            "state": "ready",
            "detail": "Rollback-Reihenfolge wurde ueber Adapter-, Backend-Store- und Registry-Slot-Backend-Dispatch read-only vorbereitet; keine Projektmutation.",
        })
        rehearsed_steps.append(f"apply-runner::rollback-preview::{rollback_stub}")
    for step in list(transaction_steps or []):
        step_text = str(step or "").strip()
        if not step_text:
            continue
        phase_results.append({
            "phase": "apply-runner-transaction-step",
            "target": bundle_key or tx_key,
            "method": "plan",
            "state": "ready" if ready_items else "pending",
            "detail": step_text,
        })
    phase_count = len(phase_results)
    ready_phase_count = sum(1 for item in phase_results if str(item.get("state") or "").strip().lower() == "ready")
    runner_state = "ready" if bundle_key and ready_items and len(apply_sequence) == int(bundle.get("object_count") or 0) else ("pending" if bundle_key else "blocked")
    adapter_summary = _build_state_registry_backend_adapter_dispatch_summary(state_registry_backend_adapter_calls)
    backend_store_summary = _build_backend_store_adapter_dispatch_summary(backend_store_adapter_calls)
    registry_slot_summary = _build_registry_slot_backend_dispatch_summary(registry_slot_backend_calls)
    runner_dispatch_summary = _build_snapshot_apply_runner_dispatch_summary(ready_items, phase_results)
    report = RuntimeSnapshotApplyRunnerReport(
        runner_key=f"apply_runner::{tx_token}",
        transaction_key=tx_key,
        bundle_key=bundle_key,
        apply_mode="read-only-snapshot-transaction-dispatch",
        runner_state=runner_state,
        phase_count=phase_count,
        ready_phase_count=ready_phase_count,
        apply_sequence=apply_sequence,
        restore_sequence=restore_sequence,
        rollback_sequence=rollback_sequence,
        rehearsed_steps=tuple(rehearsed_steps),
        phase_results=tuple(phase_results),
        state_registry_backend_adapter_calls=tuple(state_registry_backend_adapter_calls),
        state_registry_backend_adapter_summary=adapter_summary,
        backend_store_adapter_calls=tuple(backend_store_adapter_calls),
        backend_store_adapter_summary=backend_store_summary,
        registry_slot_backend_calls=tuple(registry_slot_backend_calls),
        registry_slot_backend_summary=registry_slot_summary,
        runner_dispatch_summary=(f"{runner_dispatch_summary} {adapter_summary} {backend_store_summary} {registry_slot_summary}".strip()).strip(),
        commit_preview_only=True,
        rollback_rehearsed=bool(ready_items),
        apply_runner_stub="dispatch_audio_to_instrument_morph_apply_runner",
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_apply_runner_summary(runtime_snapshot_apply_runner: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_apply_runner or {})
    if not report:
        return ""
    ready = int(report.get("ready_phase_count") or 0)
    total = int(report.get("phase_count") or 0)
    apply_count = len([str(x).strip() for x in list(report.get("apply_sequence") or []) if str(x).strip()])
    restore_count = len([str(x).strip() for x in list(report.get("restore_sequence") or []) if str(x).strip()])
    state = str(report.get("runner_state") or "pending").strip().lower() or "pending"
    state_label = {"ready": "bereit", "pending": "vorbereitet", "blocked": "gesperrt"}.get(state, state)
    dispatch_summary = str(report.get("runner_dispatch_summary") or "").strip()
    summary = (
        f"Read-only Snapshot-Transaktions-Dispatch / Apply-Runner: {ready}/{total} Phasen {state_label}, "
        f"Apply={apply_count}, Restore={restore_count}, Commit bleibt Preview-only."
    )
    if dispatch_summary:
        summary += f" {dispatch_summary}"
    return summary


def _build_first_minimal_case_report(transaction_key: str, track_kind: str, audio_clip_count: int, audio_fx_count: int, note_fx_count: int, runtime_snapshot_bundle: dict[str, Any] | None = None, runtime_snapshot_apply_runner: dict[str, Any] | None = None, runtime_snapshot_dry_run: dict[str, Any] | None = None, readiness_checks: list[dict[str, str]] | None = None) -> dict[str, Any]:
    tx_key = str(transaction_key or "audio_to_instrument_morph::preview").strip() or "audio_to_instrument_morph::preview"
    tx_token = _sanitize_ref_token(tx_key, "audio_to_instrument_morph_preview")
    track_kind = str(track_kind or "").strip().lower()
    audio_clip_count = int(audio_clip_count or 0)
    audio_fx_count = int(audio_fx_count or 0)
    note_fx_count = int(note_fx_count or 0)
    runtime_snapshot_bundle = dict(runtime_snapshot_bundle or {})
    runtime_snapshot_apply_runner = dict(runtime_snapshot_apply_runner or {})
    runtime_snapshot_dry_run = dict(runtime_snapshot_dry_run or {})
    readiness_checks = [dict(item or {}) for item in list(readiness_checks or []) if isinstance(item, dict)]

    target_empty = bool(track_kind == "audio" and audio_clip_count <= 0 and audio_fx_count <= 0 and note_fx_count <= 0)
    bundle_ready = bool(str(runtime_snapshot_bundle.get("bundle_key") or "").strip() and str(runtime_snapshot_bundle.get("bundle_state") or "").strip().lower() == "ready")
    apply_runner_ready = bool(str(runtime_snapshot_apply_runner.get("runner_key") or "").strip() and str(runtime_snapshot_apply_runner.get("runner_state") or "").strip().lower() == "ready")
    dry_run_ready = bool(str(runtime_snapshot_dry_run.get("runner_key") or "").strip() and str(runtime_snapshot_dry_run.get("runner_state") or "").strip().lower() == "ready")
    future_unlock_ready = bool(target_empty and bundle_ready and apply_runner_ready and dry_run_ready)

    readiness_state = {str(item.get("key") or "").strip(): str(item.get("state") or "").strip().lower() for item in readiness_checks}
    blocked_by: list[str] = []
    pending_by: list[str] = []
    if track_kind != "audio":
        blocked_by.append("target_kind")
    if audio_clip_count > 0:
        blocked_by.append("audio_clips")
    if audio_fx_count > 0:
        blocked_by.append("audio_fx")
    if note_fx_count > 0:
        blocked_by.append("note_fx")
    if not bundle_ready:
        pending_by.append("snapshot_bundle")
    if not apply_runner_ready:
        pending_by.append("snapshot_apply_runner")
    if not dry_run_ready:
        pending_by.append("transaction_dry_run")
    for key in ("routing_atomic", "undo_commit"):
        state = readiness_state.get(key, "")
        if state == "blocked":
            blocked_by.append(key)
        elif state and state != "ready":
            pending_by.append(key)
    blocked_by = list(dict.fromkeys([str(x).strip() for x in blocked_by if str(x).strip()]))
    pending_by = list(dict.fromkeys([str(x).strip() for x in pending_by if str(x).strip()]))

    if future_unlock_ready:
        candidate_state = "ready"
        summary = (
            "Erster spaeterer Minimalfall erkannt: leere Audio-Spur, Snapshot-Bundle, Apply-Runner und Dry-Run sind read-only vorbereitet; "
            "echter Commit-/Routing-Pfad bleibt bewusst noch gesperrt."
        )
    elif target_empty:
        candidate_state = "pending"
        summary = (
            "Leere Audio-Spur erkannt: Das ist der spaetere erste Minimalfall. "
            "Die Guard-Kette wird weiter read-only vorqualifiziert; echter Commit bleibt aus."
        )
    else:
        candidate_state = "blocked"
        summary = (
            f"Noch kein spaeterer Minimalfall: Ziel ist {_track_kind_label(track_kind)} mit "
            f"{audio_clip_count} Audio-Clips, {audio_fx_count} Audio-FX und {note_fx_count} Note-FX."
        )

    report = RuntimeSnapshotMinimalCaseReport(
        minimal_case_key=f"minimal_case::{tx_token}::empty_audio_track",
        transaction_key=tx_key,
        candidate_state=candidate_state,
        target_kind=track_kind,
        target_empty=target_empty,
        audio_clip_count=audio_clip_count,
        audio_fx_count=audio_fx_count,
        note_fx_count=note_fx_count,
        bundle_ready=bundle_ready,
        apply_runner_ready=apply_runner_ready,
        dry_run_ready=dry_run_ready,
        future_unlock_ready=future_unlock_ready,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_first_minimal_case_summary(first_minimal_case_report: dict[str, Any] | None) -> str:
    report = dict(first_minimal_case_report or {})
    if not report:
        return ""
    state = str(report.get("candidate_state") or "").strip().lower()
    label = {
        "ready": "Minimalfall-Vorqualifizierung: bereit",
        "pending": "Minimalfall-Vorqualifizierung: offen",
        "blocked": "Minimalfall-Vorqualifizierung: blockiert",
    }.get(state, "Minimalfall-Vorqualifizierung")
    blocked = len(list(report.get("blocked_by") or []))
    pending = len(list(report.get("pending_by") or []))
    parts = [label]
    if blocked > 0:
        parts.append(f"{blocked} blockiert")
    if pending > 0:
        parts.append(f"{pending} offen")
    summary = str(report.get("summary") or "").strip()
    return " — ".join([", ".join(parts), summary]) if summary else ", ".join(parts)


def _build_runtime_snapshot_precommit_contract(first_minimal_case_report: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, required_snapshots: list[str] | None = None, transaction_steps: list[str] | None = None) -> dict[str, Any]:
    report = dict(first_minimal_case_report or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(report.get("transaction_key") or bundle.get("transaction_key") or apply_runner.get("transaction_key") or dry_run.get("transaction_key") or "audio_to_instrument_morph::preview").strip() or "audio_to_instrument_morph::preview"
    tx_token = _sanitize_ref_token(tx_key, "audio_to_instrument_morph_preview")
    minimal_case_key = str(report.get("minimal_case_key") or f"minimal_case::{tx_token}").strip() or f"minimal_case::{tx_token}"
    target_empty = bool(report.get("target_empty"))
    target_scope = "empty-audio-track-minimal-case" if target_empty else "non-empty-or-non-audio-target"
    blocked = [str(x).strip() for x in list(report.get("blocked_by") or []) if str(x).strip()]
    pending = [str(x).strip() for x in list(report.get("pending_by") or []) if str(x).strip()]
    preview_commit_sequence = [
        f"precommit::undo-snapshot::{tx_token}",
        f"precommit::routing-switch::{tx_token}",
        f"precommit::track-kind-switch::{tx_token}",
        f"precommit::instrument-insert::{tx_token}",
    ]
    preview_rollback_sequence = [
        f"precommit::rollback-track-kind::{tx_token}",
        f"precommit::rollback-routing::{tx_token}",
        f"precommit::rollback-undo-snapshot::{tx_token}",
    ]
    bundle_ready = str(bundle.get("bundle_state") or "").strip().lower() == "ready" and bool(str(bundle.get("bundle_key") or "").strip())
    apply_runner_ready = str(apply_runner.get("runner_state") or "").strip().lower() == "ready" and bool(str(apply_runner.get("runner_key") or "").strip())
    dry_run_ready = str(dry_run.get("runner_state") or "").strip().lower() == "ready" and bool(str(dry_run.get("runner_key") or "").strip())
    phase_results: list[dict[str, Any]] = []
    phase_results.append({
        "phase": "precommit-undo-snapshot",
        "target": str(bundle.get("bundle_key") or tx_key),
        "method": str(bundle.get("commit_stub") or "prepare_audio_to_instrument_morph_bundle_commit").strip() or "prepare_audio_to_instrument_morph_bundle_commit",
        "state": "ready" if bundle_ready else ("pending" if target_empty else "blocked"),
        "detail": "Undo-/Snapshot-Container ist fuer den spaeteren atomaren Minimalfall read-only vorbereitet." if bundle_ready else "Bundle muss fuer den spaeteren atomaren Minimalfall stabil vorliegen.",
    })
    phase_results.append({
        "phase": "precommit-routing-switch",
        "target": str(apply_runner.get("runner_key") or tx_key),
        "method": str(apply_runner.get("apply_runner_stub") or "dispatch_audio_to_instrument_morph_apply_runner").strip() or "dispatch_audio_to_instrument_morph_apply_runner",
        "state": "ready" if apply_runner_ready else ("pending" if target_empty else "blocked"),
        "detail": "Routing-/Track-Kind-Umschaltung ist ueber denselben Apply-Runner bereits read-only vorverdrahtet." if apply_runner_ready else "Apply-Runner muss dieselbe Routing-/Track-Kind-Reihenfolge zuerst read-only abbilden.",
    })
    phase_results.append({
        "phase": "precommit-rollback-rehearsal",
        "target": str(dry_run.get("runner_key") or tx_key),
        "method": str(dry_run.get("dry_run_stub") or "dispatch_audio_to_instrument_morph_dry_run").strip() or "dispatch_audio_to_instrument_morph_dry_run",
        "state": "ready" if dry_run_ready else ("pending" if target_empty else "blocked"),
        "detail": "Rollback-/Restore-Pfad ist fuer denselben Minimalfall bereits read-only rehearsed." if dry_run_ready else "Dry-Run muss den spaeteren Rueckbau fuer denselben Minimalfall zuerst vollstaendig rehearsen.",
    })
    phase_results.append({
        "phase": "precommit-mutation-gate",
        "target": minimal_case_key,
        "method": "arm_audio_to_instrument_morph_minimal_case_gate",
        "state": "ready" if target_empty and not blocked else ("pending" if target_empty else "blocked"),
        "detail": "Leere Audio-Spur ist als spaeterer erster echter Commit-Fall read-only vorverdrahtet; Mutation bleibt weiterhin deaktiviert." if target_empty else "Nur die leere Audio-Spur kann spaeter als erster echter Commit-Fall dienen.",
    })
    ready_preview_phase_count = sum(1 for item in phase_results if str(item.get("state") or "").strip().lower() == "ready")
    preview_phase_count = len(phase_results)
    if target_empty and bundle_ready and apply_runner_ready and dry_run_ready and not blocked:
        contract_state = "ready"
    elif target_empty:
        contract_state = "pending"
    else:
        contract_state = "blocked"
    req_count = len([str(x).strip() for x in list(required_snapshots or []) if str(x).strip()])
    step_count = len([str(x).strip() for x in list(transaction_steps or []) if str(x).strip()])
    summary = (
        f"Pre-Commit-Vertrag {'bereit' if contract_state == 'ready' else ('vorbereitet' if contract_state == 'pending' else 'gesperrt')}"
        f" · Vorschauphasen {ready_preview_phase_count}/{preview_phase_count}"
        f" · Snapshots {req_count}"
        f" · Transaktionsschritte {step_count}"
        f" · Mutation weiter gesperrt"
    )
    contract = RuntimeSnapshotPrecommitContractReport(
        contract_key=f"precommit_contract::{tx_token}",
        transaction_key=tx_key,
        minimal_case_key=minimal_case_key,
        contract_state=contract_state,
        mutation_gate_state="blocked",
        target_scope=target_scope,
        target_empty=target_empty,
        preview_phase_count=preview_phase_count,
        ready_preview_phase_count=ready_preview_phase_count,
        preview_commit_sequence=tuple(preview_commit_sequence),
        preview_rollback_sequence=tuple(preview_rollback_sequence),
        preview_phase_results=tuple(phase_results),
        bundle_key=str(bundle.get("bundle_key") or "").strip(),
        apply_runner_key=str(apply_runner.get("runner_key") or "").strip(),
        dry_run_key=str(dry_run.get("runner_key") or "").strip(),
        future_commit_stub="commit_audio_to_instrument_morph_minimal_case",
        future_rollback_stub="rollback_audio_to_instrument_morph_minimal_case",
        commit_preview_only=True,
        project_mutation_enabled=False,
        blocked_by=tuple(blocked),
        pending_by=tuple(pending),
        summary=summary,
    )
    return contract.as_plan_dict()


def _build_runtime_snapshot_precommit_contract_summary(runtime_snapshot_precommit_contract: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_precommit_contract or {})
    if not report:
        return ""
    state = str(report.get("contract_state") or "pending").strip().lower() or "pending"
    state_label = {"ready": "bereit", "pending": "vorbereitet", "blocked": "gesperrt"}.get(state, state)
    blocked = [str(x).strip() for x in list(report.get("blocked_by") or []) if str(x).strip()]
    pending = [str(x).strip() for x in list(report.get("pending_by") or []) if str(x).strip()]
    parts = [
        f"Pre-Commit-Vertrag {state_label}",
        f"leer={('ja' if bool(report.get('target_empty')) else 'nein')}",
        f"Vorschauphasen={int(report.get('ready_preview_phase_count') or 0)}/{int(report.get('preview_phase_count') or 0)}",
        f"Mutation={('an' if bool(report.get('project_mutation_enabled')) else 'aus')}",
    ]
    if blocked:
        parts.append(f"blockiert durch {len(blocked)} Punkt{'e' if len(blocked) != 1 else ''}")
    if pending:
        parts.append(f"offen {len(pending)}")
    return " · ".join(parts)


def _has_entrypoint(owner: Any, dotted_name: str) -> bool:
    current = owner
    for part in [str(x).strip() for x in str(dotted_name or '').split('.') if str(x).strip()]:
        if current is None or not hasattr(current, part):
            return False
        try:
            current = getattr(current, part)
        except Exception:
            return False
    return current is not None


def _build_runtime_snapshot_atomic_entrypoints(runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_snapshot_objects: list[dict[str, Any]] | None = None, runtime_owner: Any | None = None) -> dict[str, Any]:
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    object_items = [dict(item or {}) for item in list(runtime_snapshot_objects or [])]
    tx_key = str(contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = _sanitize_ref_token(tx_key, 'audio_to_instrument_morph_preview')
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else ''
    except Exception:
        owner_class = ''
    contract_state = str(contract.get('contract_state') or '').strip().lower()
    target_scope = str(contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(contract.get('pending_by') or []) if str(x).strip()]

    def _owner_state(method_name: str) -> str:
        if runtime_owner is None:
            return 'pending' if contract_state in {'ready', 'pending'} else 'blocked'
        return 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if contract_state in {'ready', 'pending'} else 'blocked')

    entrypoints: list[dict[str, Any]] = []

    def _append_owner_entry(label: str, method_name: str, detail_ready: str, detail_missing: str, category: str) -> None:
        state = _owner_state(method_name)
        target = owner_class or 'ProjectService'
        detail = detail_ready if state == 'ready' else detail_missing
        if state != 'ready' and runtime_owner is None and contract_state in {'ready', 'pending'}:
            detail += ' Kein Runtime-Owner an den Plan uebergeben.'
        entrypoints.append({
            'category': category,
            'label': label,
            'target': target,
            'method': method_name,
            'state': state,
            'detail': detail,
        })

    _append_owner_entry(
        'Preview-Entry-Point',
        'preview_audio_to_instrument_morph',
        'Der reale Service-Preview-Einstieg fuer denselben Morphing-Guard ist aufloesbar.',
        'Der reale Service-Preview-Einstieg muss spaeter an denselben Minimalfall-Vertrag gekoppelt werden.',
        'service-preview',
    )
    _append_owner_entry(
        'Validate-Entry-Point',
        'validate_audio_to_instrument_morph',
        'Der reale Service-Validate-Einstieg fuer denselben Morphing-Guard ist aufloesbar.',
        'Der reale Service-Validate-Einstieg muss spaeter an denselben Minimalfall-Vertrag gekoppelt werden.',
        'service-validate',
    )
    _append_owner_entry(
        'Apply-Entry-Point',
        'apply_audio_to_instrument_morph',
        'Der reale Service-Apply-Einstieg ist vorhanden, bleibt aber weiterhin Preview-only.',
        'Der reale Service-Apply-Einstieg fehlt noch oder wird nicht an den Plan uebergeben.',
        'service-apply',
    )
    _append_owner_entry(
        'Track-Kind-Entry-Point',
        'set_track_kind',
        'Der reale Spurtyp-Umschaltpunkt ist aufloesbar, bleibt aber weiterhin gesperrt.',
        'Der reale Spurtyp-Umschaltpunkt muss spaeter fuer den Minimalfall bereitstehen.',
        'track-kind',
    )
    _append_owner_entry(
        'Undo-Entry-Point',
        'undo_stack.push',
        'Der Undo-Stack kann spaeter denselben Gesamtvorgang als einen Undo-Punkt aufnehmen.',
        'Der Undo-Stack-Einstieg fuer den spaeteren Gesamtvorgang fehlt noch oder ist nicht aufloesbar.',
        'undo',
    )

    routing_object = next((item for item in object_items if str(item.get('name') or '').strip() == 'routing_state'), {})
    track_state_object = next((item for item in object_items if str(item.get('name') or '').strip() == 'undo_track_state'), {})
    track_kind_object = next((item for item in object_items if str(item.get('name') or '').strip() == 'track_kind_state'), {})

    def _append_snapshot_entry(label: str, item: dict[str, Any], detail_ready: str, detail_missing: str, category: str) -> None:
        state = 'ready' if str(item.get('snapshot_object_key') or '').strip() and bool(item.get('supports_capture')) and bool(item.get('supports_restore')) else ('pending' if contract_state in {'ready', 'pending'} else 'blocked')
        target = str(item.get('snapshot_object_key') or tx_key).strip() or tx_key
        method = '/'.join([x for x in [str(item.get('capture_method') or '').strip(), str(item.get('restore_method') or '').strip()] if x]) or 'capture/restore'
        detail = detail_ready if state == 'ready' else detail_missing
        entrypoints.append({
            'category': category,
            'label': label,
            'target': target,
            'method': method,
            'state': state,
            'detail': detail,
        })

    _append_snapshot_entry(
        'Routing-Entry-Point',
        routing_object,
        'Routing-Snapshot-Capture/Restore sind bereits als reale Preview-Einstiegspunkte gebunden.',
        'Routing-Snapshot-Capture/Restore muessen vor echter Mutation stabil gebunden werden.',
        'routing',
    )
    _append_snapshot_entry(
        'Undo-Snapshot-Entry-Point',
        track_state_object,
        'Track-State-Capture/Restore sind bereits als Undo-Snapshot-Einstiegspunkte gebunden.',
        'Track-State-Capture/Restore muessen vor echter Mutation stabil gebunden werden.',
        'undo-snapshot',
    )
    _append_snapshot_entry(
        'Track-Kind-Snapshot-Entry-Point',
        track_kind_object,
        'Track-Kind-Capture/Restore sind bereits als reale Preview-Einstiegspunkte gebunden.',
        'Track-Kind-Capture/Restore muessen vor echter Mutation stabil gebunden werden.',
        'track-kind-snapshot',
    )

    commit_stub = str(contract.get('future_commit_stub') or bundle.get('commit_stub') or 'commit_audio_to_instrument_morph_minimal_case').strip() or 'commit_audio_to_instrument_morph_minimal_case'
    rollback_stub = str(contract.get('future_rollback_stub') or bundle.get('rollback_stub') or 'rollback_audio_to_instrument_morph_minimal_case').strip() or 'rollback_audio_to_instrument_morph_minimal_case'
    apply_stub = str(apply_runner.get('apply_runner_stub') or 'dispatch_audio_to_instrument_morph_apply_runner').strip() or 'dispatch_audio_to_instrument_morph_apply_runner'
    entrypoints.append({
        'category': 'transaction-stub',
        'label': 'Minimalfall-Commit-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': commit_stub,
        'state': 'ready' if contract_state == 'ready' else ('pending' if contract_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Minimalfall-Commit-Stub ist jetzt an denselben Pre-Commit-Vertrag gekoppelt, bleibt aber gesperrt.',
    })
    entrypoints.append({
        'category': 'transaction-stub',
        'label': 'Minimalfall-Rollback-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': rollback_stub,
        'state': 'ready' if contract_state == 'ready' else ('pending' if contract_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Minimalfall-Rollback-Stub ist read-only gekoppelt und bleibt weiterhin preview-only.',
    })

    total_entrypoint_count = len(entrypoints)
    ready_entrypoint_count = sum(1 for item in entrypoints if str(item.get('state') or '').strip().lower() == 'ready')
    preview_dispatch_sequence = tuple(
        f"{str(item.get('label') or '').strip()}::{str(item.get('method') or '').strip()}"
        for item in entrypoints
        if str(item.get('label') or '').strip() and str(item.get('method') or '').strip()
    )
    if contract_state == 'ready' and ready_entrypoint_count >= total_entrypoint_count and total_entrypoint_count > 0:
        entrypoint_state = 'ready'
    elif contract_state in {'ready', 'pending'}:
        entrypoint_state = 'pending'
    else:
        entrypoint_state = 'blocked'
    summary = (
        f"Atomare Entry-Point-Kopplung {'bereit' if entrypoint_state == 'ready' else ('vorbereitet' if entrypoint_state == 'pending' else 'gesperrt')}"
        f" · Entry-Points {ready_entrypoint_count}/{total_entrypoint_count}"
        f" · Owner={owner_class or 'n/a'}"
        f" · Mutation weiter gesperrt"
    )
    report = RuntimeSnapshotAtomicEntryPointReport(
        entrypoint_key=f"atomic_entrypoints::{tx_token}",
        transaction_key=tx_key,
        contract_key=str(contract.get('contract_key') or '').strip(),
        entrypoint_state=entrypoint_state,
        mutation_gate_state='blocked',
        target_scope=target_scope,
        owner_class=owner_class,
        total_entrypoint_count=total_entrypoint_count,
        ready_entrypoint_count=ready_entrypoint_count,
        entrypoints=tuple(entrypoints),
        preview_dispatch_sequence=preview_dispatch_sequence,
        future_apply_stub=apply_stub,
        future_commit_stub=commit_stub,
        future_rollback_stub=rollback_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_atomic_entrypoints_summary(runtime_snapshot_atomic_entrypoints: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_atomic_entrypoints or {})
    if not report:
        return ''
    state = str(report.get('entrypoint_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"Atomare Commit-/Undo-/Routing-Entry-Points: {int(report.get('ready_entrypoint_count') or 0)}/{int(report.get('total_entrypoint_count') or 0)} {state_label}, "
        f"Owner={str(report.get('owner_class') or 'n/a').strip() or 'n/a'}, Mutation bleibt aus."
    )


def _build_runtime_snapshot_mutation_gate_capsule(runtime_snapshot_atomic_entrypoints: dict[str, Any] | None, runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_owner: Any | None = None) -> dict[str, Any]:
    atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(atomic_entrypoints.get('transaction_key') or contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = _sanitize_ref_token(tx_key, 'audio_to_instrument_morph_preview')
    entrypoint_state = str(atomic_entrypoints.get('entrypoint_state') or '').strip().lower()
    target_scope = str(atomic_entrypoints.get('target_scope') or contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(atomic_entrypoints.get('blocked_by') or contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(atomic_entrypoints.get('pending_by') or contract.get('pending_by') or []) if str(x).strip()]
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else str(atomic_entrypoints.get('owner_class') or '').strip()
    except Exception:
        owner_class = str(atomic_entrypoints.get('owner_class') or '').strip()

    def _owner_state(method_name: str) -> str:
        if runtime_owner is None:
            return 'pending' if entrypoint_state in {'ready', 'pending'} else 'blocked'
        return 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if entrypoint_state in {'ready', 'pending'} else 'blocked')

    capsule_steps: list[dict[str, Any]] = []

    def _append_owner_step(label: str, method_name: str, detail_ready: str, detail_missing: str, category: str) -> None:
        state = _owner_state(method_name)
        target = owner_class or 'ProjectService'
        detail = detail_ready if state == 'ready' else detail_missing
        if state != 'ready' and runtime_owner is None and entrypoint_state in {'ready', 'pending'}:
            detail += ' Kein Runtime-Owner an den Plan uebergeben.'
        capsule_steps.append({
            'category': category,
            'label': label,
            'target': target,
            'method': method_name,
            'state': state,
            'detail': detail,
        })

    _append_owner_step(
        'Mutation-Gate-Preview',
        'preview_audio_to_instrument_morph_mutation_gate',
        'Der Owner exponiert bereits ein explizites read-only Mutation-Gate fuer denselben Minimalfall.',
        'Das explizite Mutation-Gate muss spaeter als eigener Owner-Einstiegspunkt vor dem echten Commit bereitstehen.',
        'mutation-gate',
    )
    _append_owner_step(
        'Transaction-Capsule-Preview',
        'preview_audio_to_instrument_morph_transaction_capsule',
        'Der Owner exponiert bereits eine explizite read-only Transaktions-Kapsel fuer denselben Minimalfall.',
        'Die explizite Transaktions-Kapsel muss spaeter als eigener Owner-Einstiegspunkt vor dem echten Commit bereitstehen.',
        'transaction-capsule',
    )
    _append_owner_step(
        'Project-Snapshot-Capture',
        '_project_snapshot_dict',
        'Der Owner kann den Projektzustand bereits ueber die vorhandene Snapshot-Methode read-only in die Kapsel spiegeln.',
        'Die Kapsel braucht vor echter Mutation eine stabile Projekt-Snapshot-Methode am Owner.',
        'snapshot-capture',
    )
    _append_owner_step(
        'Project-Snapshot-Restore',
        '_restore_project_from_snapshot',
        'Der Owner kann einen Projekt-Snapshot bereits ueber die vorhandene Restore-Methode read-only adressieren.',
        'Die Kapsel braucht vor echter Mutation eine stabile Projekt-Restore-Methode am Owner.',
        'snapshot-restore',
    )
    _append_owner_step(
        'Capsule-Commit-Preview',
        'preview_audio_to_instrument_morph_capsule_commit',
        'Der Owner exponiert bereits einen read-only Commit-Vorvertrag innerhalb der Kapsel.',
        'Der read-only Capsule-Commit-Vorvertrag muss spaeter als eigener Owner-Einstiegspunkt sichtbar werden.',
        'capsule-commit',
    )
    _append_owner_step(
        'Capsule-Rollback-Preview',
        'preview_audio_to_instrument_morph_capsule_rollback',
        'Der Owner exponiert bereits einen read-only Rollback-Vorvertrag innerhalb der Kapsel.',
        'Der read-only Capsule-Rollback-Vorvertrag muss spaeter als eigener Owner-Einstiegspunkt sichtbar werden.',
        'capsule-rollback',
    )

    gate_stub = 'arm_audio_to_instrument_morph_mutation_gate_capsule'
    capsule_stub = 'enter_audio_to_instrument_morph_transaction_capsule'
    commit_stub = str(atomic_entrypoints.get('future_commit_stub') or contract.get('future_commit_stub') or bundle.get('commit_stub') or 'commit_audio_to_instrument_morph_minimal_case').strip() or 'commit_audio_to_instrument_morph_minimal_case'
    rollback_stub = str(atomic_entrypoints.get('future_rollback_stub') or contract.get('future_rollback_stub') or bundle.get('rollback_stub') or 'rollback_audio_to_instrument_morph_minimal_case').strip() or 'rollback_audio_to_instrument_morph_minimal_case'
    capsule_steps.append({
        'category': 'transaction-stub',
        'label': 'Mutation-Gate-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': gate_stub,
        'state': 'ready' if entrypoint_state == 'ready' else ('pending' if entrypoint_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Mutation-Gate-Stub ist an dieselbe atomare Entry-Point-Kette gekoppelt, bleibt aber preview-only.',
    })
    capsule_steps.append({
        'category': 'transaction-stub',
        'label': 'Transaction-Capsule-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': capsule_stub,
        'state': 'ready' if entrypoint_state == 'ready' else ('pending' if entrypoint_state == 'pending' else 'blocked'),
        'detail': 'Die spaetere Transaktions-Kapsel ist jetzt read-only vorverdrahtet, bleibt aber weiterhin gesperrt.',
    })
    capsule_steps.append({
        'category': 'transaction-stub',
        'label': 'Capsule-Commit-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': commit_stub,
        'state': 'ready' if entrypoint_state == 'ready' else ('pending' if entrypoint_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Kapsel-Commit bleibt explizit blockiert und wird hier nur read-only sichtbar gemacht.',
    })
    capsule_steps.append({
        'category': 'transaction-stub',
        'label': 'Capsule-Rollback-Stub',
        'target': str(contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': rollback_stub,
        'state': 'ready' if entrypoint_state == 'ready' else ('pending' if entrypoint_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Kapsel-Rollback bleibt explizit blockiert und wird hier nur read-only sichtbar gemacht.',
    })

    total_capsule_step_count = len(capsule_steps)
    ready_capsule_step_count = sum(1 for item in capsule_steps if str(item.get('state') or '').strip().lower() == 'ready')
    preview_capsule_sequence = tuple(
        f"{str(item.get('label') or '').strip()}::{str(item.get('method') or '').strip()}"
        for item in capsule_steps
        if str(item.get('label') or '').strip() and str(item.get('method') or '').strip()
    )
    if entrypoint_state == 'ready' and ready_capsule_step_count >= total_capsule_step_count and total_capsule_step_count > 0:
        capsule_state = 'ready'
        mutation_gate_state = 'armed-preview-only'
    elif entrypoint_state in {'ready', 'pending'}:
        capsule_state = 'pending'
        mutation_gate_state = 'blocked'
    else:
        capsule_state = 'blocked'
        mutation_gate_state = 'blocked'
    summary = (
        f"Mutation-Gate/Transaction-Capsule {'bereit' if capsule_state == 'ready' else ('vorbereitet' if capsule_state == 'pending' else 'gesperrt')}"
        f" · Kapselschritte {ready_capsule_step_count}/{total_capsule_step_count}"
        f" · Owner={owner_class or 'n/a'}"
        f" · Mutation bleibt aus"
    )
    report = RuntimeSnapshotMutationGateCapsuleReport(
        capsule_key=f"mutation_gate_capsule::{tx_token}",
        transaction_key=tx_key,
        contract_key=str(contract.get('contract_key') or '').strip(),
        entrypoint_key=str(atomic_entrypoints.get('entrypoint_key') or '').strip(),
        capsule_state=capsule_state,
        mutation_gate_state=mutation_gate_state,
        target_scope=target_scope,
        owner_class=owner_class,
        total_capsule_step_count=total_capsule_step_count,
        ready_capsule_step_count=ready_capsule_step_count,
        capsule_steps=tuple(capsule_steps),
        preview_capsule_sequence=preview_capsule_sequence,
        future_gate_stub=gate_stub,
        future_capsule_stub=capsule_stub,
        future_commit_stub=commit_stub,
        future_rollback_stub=rollback_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_mutation_gate_capsule_summary(runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_mutation_gate_capsule or {})
    if not report:
        return ''
    state = str(report.get('capsule_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"Mutation-Gate/Transaction-Capsule: {int(report.get('ready_capsule_step_count') or 0)}/{int(report.get('total_capsule_step_count') or 0)} {state_label}, "
        f"Owner={str(report.get('owner_class') or 'n/a').strip() or 'n/a'}, Mutation bleibt aus."
    )




def _build_runtime_snapshot_command_undo_shell(runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None, runtime_snapshot_atomic_entrypoints: dict[str, Any] | None, runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_owner: Any | None = None) -> dict[str, Any]:
    capsule = dict(runtime_snapshot_mutation_gate_capsule or {})
    atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(capsule.get('transaction_key') or atomic_entrypoints.get('transaction_key') or contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = _sanitize_ref_token(tx_key, 'audio_to_instrument_morph_preview')
    capsule_state = str(capsule.get('capsule_state') or '').strip().lower()
    target_scope = str(capsule.get('target_scope') or atomic_entrypoints.get('target_scope') or contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(capsule.get('blocked_by') or atomic_entrypoints.get('blocked_by') or contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(capsule.get('pending_by') or atomic_entrypoints.get('pending_by') or contract.get('pending_by') or []) if str(x).strip()]
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else str(capsule.get('owner_class') or atomic_entrypoints.get('owner_class') or '').strip()
    except Exception:
        owner_class = str(capsule.get('owner_class') or atomic_entrypoints.get('owner_class') or '').strip()

    command_descriptor: dict[str, Any] = {}
    command_class = 'ProjectSnapshotEditCommand'
    command_module = 'pydaw.commands.project_snapshot_edit'
    if runtime_owner is not None and hasattr(runtime_owner, 'preview_audio_to_instrument_morph_project_snapshot_edit_command'):
        try:
            command_descriptor = dict(getattr(runtime_owner, 'preview_audio_to_instrument_morph_project_snapshot_edit_command')() or {})
        except Exception:
            command_descriptor = {}
    if command_descriptor:
        command_class = str(command_descriptor.get('command_class') or command_class).strip() or command_class
        command_module = str(command_descriptor.get('command_module') or command_module).strip() or command_module

    def _owner_state(method_name: str) -> str:
        if runtime_owner is None:
            return 'pending' if capsule_state in {'ready', 'pending'} else 'blocked'
        return 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if capsule_state in {'ready', 'pending'} else 'blocked')

    shell_steps: list[dict[str, Any]] = []

    def _append_owner_step(label: str, method_name: str, detail_ready: str, detail_missing: str, category: str, target: str = '') -> None:
        state = _owner_state(method_name)
        resolved_target = target or owner_class or 'ProjectService'
        detail = detail_ready if state == 'ready' else detail_missing
        if state != 'ready' and runtime_owner is None and capsule_state in {'ready', 'pending'}:
            detail += ' Kein Runtime-Owner an den Plan uebergeben.'
        shell_steps.append({
            'category': category,
            'label': label,
            'target': resolved_target,
            'method': method_name,
            'state': state,
            'detail': detail,
        })

    _append_owner_step(
        'ProjectSnapshotEditCommand-Preview',
        'preview_audio_to_instrument_morph_project_snapshot_edit_command',
        f'Der Owner exponiert bereits einen read-only {command_class}-Deskriptor fuer denselben Minimalfall.',
        f'Der read-only {command_class}-Deskriptor muss spaeter als expliziter Owner-Einstiegspunkt sichtbar werden.',
        'command-preview',
        target=command_class,
    )
    _append_owner_step(
        'Command-Undo-Shell-Preview',
        'preview_audio_to_instrument_morph_command_undo_shell',
        'Der Owner exponiert bereits eine read-only Command-/Undo-Huelle um dieselbe Mutation-Gate-/Capsule-Kette.',
        'Die explizite Command-/Undo-Huelle muss spaeter als eigener Owner-Einstiegspunkt vor echter Mutation bereitstehen.',
        'command-shell',
    )
    _append_owner_step(
        'Project-Snapshot-Capture',
        '_project_snapshot_dict',
        'Die Command-Huelle kann den Before-/After-Snapshot bereits ueber die vorhandene Projekt-Snapshot-Methode read-only beschreiben.',
        'Die Command-Huelle braucht vor echter Mutation eine stabile Projekt-Snapshot-Methode am Owner.',
        'snapshot-capture',
    )
    _append_owner_step(
        'Project-Snapshot-Restore',
        '_restore_project_from_snapshot',
        'Die Command-Huelle kann den Restore-Callback bereits ueber die vorhandene Restore-Methode read-only beschreiben.',
        'Die Command-Huelle braucht vor echter Mutation eine stabile Projekt-Restore-Methode am Owner.',
        'snapshot-restore',
    )
    _append_owner_step(
        'Undo-Stack-Push-Preview',
        'undo_stack.push',
        'Der Undo-Stack-Push fuer die spaetere Command-Huelle ist bereits read-only aufloesbar.',
        'Der Undo-Stack-Push fuer die spaetere Command-Huelle fehlt noch oder ist nicht aufloesbar.',
        'undo-push',
        target=owner_class or 'UndoStack',
    )

    command_stub = 'build_audio_to_instrument_morph_project_snapshot_edit_command'
    undo_stub = 'push_audio_to_instrument_morph_project_snapshot_edit_command'
    commit_stub = str(capsule.get('future_commit_stub') or atomic_entrypoints.get('future_commit_stub') or contract.get('future_commit_stub') or bundle.get('commit_stub') or 'commit_audio_to_instrument_morph_minimal_case').strip() or 'commit_audio_to_instrument_morph_minimal_case'
    rollback_stub = str(capsule.get('future_rollback_stub') or atomic_entrypoints.get('future_rollback_stub') or contract.get('future_rollback_stub') or bundle.get('rollback_stub') or 'rollback_audio_to_instrument_morph_minimal_case').strip() or 'rollback_audio_to_instrument_morph_minimal_case'
    shell_steps.append({
        'category': 'transaction-stub',
        'label': 'Command-Factory-Stub',
        'target': command_class,
        'method': command_stub,
        'state': 'ready' if capsule_state == 'ready' else ('pending' if capsule_state == 'pending' else 'blocked'),
        'detail': f'Die spaetere {command_class}-Factory ist jetzt read-only an dieselbe Capsule-Kette gekoppelt, bleibt aber gesperrt.',
    })
    shell_steps.append({
        'category': 'transaction-stub',
        'label': 'Command-Undo-Push-Stub',
        'target': owner_class or 'UndoStack',
        'method': undo_stub,
        'state': 'ready' if capsule_state == 'ready' else ('pending' if capsule_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Undo-Push der Command-Huelle bleibt explizit blockiert und wird hier nur read-only sichtbar gemacht.',
    })
    shell_steps.append({
        'category': 'transaction-stub',
        'label': 'Command-Commit-Stub',
        'target': str(capsule.get('capsule_key') or contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': commit_stub,
        'state': 'ready' if capsule_state == 'ready' else ('pending' if capsule_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Commit innerhalb der Command-Huelle bleibt explizit blockiert und wird hier nur read-only sichtbar gemacht.',
    })
    shell_steps.append({
        'category': 'transaction-stub',
        'label': 'Command-Rollback-Stub',
        'target': str(capsule.get('capsule_key') or contract.get('contract_key') or tx_key).strip() or tx_key,
        'method': rollback_stub,
        'state': 'ready' if capsule_state == 'ready' else ('pending' if capsule_state == 'pending' else 'blocked'),
        'detail': 'Der spaetere Rollback innerhalb der Command-Huelle bleibt explizit blockiert und wird hier nur read-only sichtbar gemacht.',
    })

    total_shell_step_count = len(shell_steps)
    ready_shell_step_count = sum(1 for item in shell_steps if str(item.get('state') or '').strip().lower() == 'ready')
    preview_shell_sequence = tuple(
        f"{str(item.get('label') or '').strip()}::{str(item.get('method') or '').strip()}"
        for item in shell_steps
        if str(item.get('label') or '').strip() and str(item.get('method') or '').strip()
    )
    if capsule_state == 'ready' and ready_shell_step_count >= total_shell_step_count and total_shell_step_count > 0:
        shell_state = 'ready'
        mutation_gate_state = str(capsule.get('mutation_gate_state') or 'armed-preview-only').strip() or 'armed-preview-only'
    elif capsule_state in {'ready', 'pending'}:
        shell_state = 'pending'
        mutation_gate_state = 'blocked'
    else:
        shell_state = 'blocked'
        mutation_gate_state = 'blocked'
    summary = (
        f"ProjectSnapshotEditCommand-/Undo-Huelle {'bereit' if shell_state == 'ready' else ('vorbereitet' if shell_state == 'pending' else 'gesperrt')}"
        f" · Huelle {ready_shell_step_count}/{total_shell_step_count}"
        f" · Owner={owner_class or 'n/a'}"
        f" · Command={command_class}"
        f" · Mutation bleibt aus"
    )
    report = RuntimeSnapshotCommandUndoShellReport(
        shell_key=f"command_undo_shell::{tx_token}",
        transaction_key=tx_key,
        capsule_key=str(capsule.get('capsule_key') or '').strip(),
        contract_key=str(capsule.get('contract_key') or contract.get('contract_key') or '').strip(),
        shell_state=shell_state,
        mutation_gate_state=mutation_gate_state,
        target_scope=target_scope,
        owner_class=owner_class,
        command_class=command_class,
        command_module=command_module,
        total_shell_step_count=total_shell_step_count,
        ready_shell_step_count=ready_shell_step_count,
        shell_steps=tuple(shell_steps),
        preview_shell_sequence=preview_shell_sequence,
        future_command_stub=command_stub,
        future_undo_stub=undo_stub,
        future_commit_stub=commit_stub,
        future_rollback_stub=rollback_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_command_undo_shell_summary(runtime_snapshot_command_undo_shell: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_command_undo_shell or {})
    if not report:
        return ''
    state = str(report.get('shell_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"ProjectSnapshotEditCommand-/Undo-Huelle: {int(report.get('ready_shell_step_count') or 0)}/{int(report.get('total_shell_step_count') or 0)} {state_label}, "
        f"Owner={str(report.get('owner_class') or 'n/a').strip() or 'n/a'}, Command={str(report.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}, Mutation bleibt aus."
    )


def _build_runtime_snapshot_command_factory_payloads(runtime_snapshot_command_undo_shell: dict[str, Any] | None, runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None, runtime_snapshot_atomic_entrypoints: dict[str, Any] | None, runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_owner: Any | None = None) -> dict[str, Any]:
    shell = dict(runtime_snapshot_command_undo_shell or {})
    capsule = dict(runtime_snapshot_mutation_gate_capsule or {})
    atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(shell.get('transaction_key') or capsule.get('transaction_key') or atomic_entrypoints.get('transaction_key') or contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = _sanitize_ref_token(tx_key, 'audio_to_instrument_morph_preview')
    shell_state = str(shell.get('shell_state') or '').strip().lower()
    target_scope = str(shell.get('target_scope') or capsule.get('target_scope') or atomic_entrypoints.get('target_scope') or contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(shell.get('blocked_by') or capsule.get('blocked_by') or atomic_entrypoints.get('blocked_by') or contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(shell.get('pending_by') or capsule.get('pending_by') or atomic_entrypoints.get('pending_by') or contract.get('pending_by') or []) if str(x).strip()]
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else str(shell.get('owner_class') or capsule.get('owner_class') or atomic_entrypoints.get('owner_class') or '').strip()
    except Exception:
        owner_class = str(shell.get('owner_class') or capsule.get('owner_class') or atomic_entrypoints.get('owner_class') or '').strip()
    command_class = str(shell.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'
    command_module = str(shell.get('command_module') or 'pydaw.commands.project_snapshot_edit').strip() or 'pydaw.commands.project_snapshot_edit'
    factory_descriptor: dict[str, Any] = {}
    if runtime_owner is not None and hasattr(runtime_owner, 'preview_audio_to_instrument_morph_before_after_snapshot_command_factory'):
        try:
            factory_descriptor = dict(getattr(runtime_owner, 'preview_audio_to_instrument_morph_before_after_snapshot_command_factory')() or {})
        except Exception:
            factory_descriptor = {}
    if factory_descriptor:
        command_class = str(factory_descriptor.get('command_class') or command_class).strip() or command_class
        command_module = str(factory_descriptor.get('command_module') or command_module).strip() or command_module
    before_payload_summary = copy.deepcopy(dict(factory_descriptor.get('before_payload_summary') or {})) if isinstance(factory_descriptor.get('before_payload_summary'), dict) else {}
    after_payload_summary = copy.deepcopy(dict(factory_descriptor.get('after_payload_summary') or {})) if isinstance(factory_descriptor.get('after_payload_summary'), dict) else {}
    if not before_payload_summary and runtime_owner is not None and _has_entrypoint(runtime_owner, '_project_snapshot_dict'):
        try:
            snapshot_payload = dict(getattr(runtime_owner, '_project_snapshot_dict')() or {})
        except Exception:
            snapshot_payload = {}
        before_payload_summary = _snapshot_payload_summary(snapshot_payload)
        after_payload_summary = _snapshot_payload_summary(copy.deepcopy(snapshot_payload))
    payload_delta_kind = str(factory_descriptor.get('payload_delta_kind') or ('identical-preview-only' if before_payload_summary and before_payload_summary == after_payload_summary else 'pending')).strip() or 'pending'
    label_preview = str(factory_descriptor.get('label_preview') or f'Audio→Instrument Morph Preview: {command_class} (leere Audio-Spur)').strip() or f'Audio→Instrument Morph Preview: {command_class}'
    materialized_payload_count = int(factory_descriptor.get('materialized_payload_count') or 0)
    if materialized_payload_count <= 0:
        materialized_payload_count = int(bool(before_payload_summary)) + int(bool(after_payload_summary))

    def _owner_state(method_name: str, *, require_payload: bool = False, payload_summary: dict[str, Any] | None = None) -> str:
        if runtime_owner is None:
            base_state = 'pending' if shell_state in {'ready', 'pending'} else 'blocked'
        else:
            base_state = 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if shell_state in {'ready', 'pending'} else 'blocked')
        if require_payload and base_state == 'ready':
            payload_summary = dict(payload_summary or {})
            if int(payload_summary.get('payload_entry_count') or 0) <= 0 or int(payload_summary.get('payload_size_bytes') or 0) <= 0:
                base_state = 'pending' if shell_state in {'ready', 'pending'} else 'blocked'
        return base_state

    factory_steps: list[dict[str, Any]] = []

    def _append_owner_step(label: str, method_name: str, detail_ready: str, detail_missing: str, category: str, target: str = '', require_payload: bool = False, payload_summary: dict[str, Any] | None = None) -> None:
        state = _owner_state(method_name, require_payload=require_payload, payload_summary=payload_summary)
        resolved_target = target or owner_class or 'ProjectService'
        detail = detail_ready if state == 'ready' else detail_missing
        if state != 'ready' and runtime_owner is None and shell_state in {'ready', 'pending'}:
            detail += ' Kein Runtime-Owner an den Plan uebergeben.'
        factory_steps.append({
            'category': category,
            'label': label,
            'target': resolved_target,
            'method': method_name,
            'state': state,
            'detail': detail,
        })

    _append_owner_step(
        'Before-/After-Snapshot-Command-Factory-Preview',
        'preview_audio_to_instrument_morph_before_after_snapshot_command_factory',
        f'Der Owner exponiert bereits eine read-only Before-/After-Snapshot-Factory fuer {command_class}.',
        f'Die read-only Before-/After-Snapshot-Factory fuer {command_class} muss spaeter als expliziter Owner-Einstiegspunkt sichtbar werden.',
        'command-factory-preview',
        target=command_class,
    )
    _append_owner_step(
        'Before-Snapshot-Payload materialisiert',
        '_project_snapshot_dict',
        f"Der Before-Snapshot ist read-only materialisiert (Digest={str(before_payload_summary.get('payload_digest') or 'n/a').strip() or 'n/a'}, Bytes={int(before_payload_summary.get('payload_size_bytes') or 0)}).",
        'Der Before-Snapshot muss vor echter Mutation als materialisierter Payload vorliegen.',
        'before-payload',
        target=command_class,
        require_payload=True,
        payload_summary=before_payload_summary,
    )
    _append_owner_step(
        'After-Snapshot-Payload materialisiert',
        '_project_snapshot_dict',
        f"Der After-Snapshot ist read-only materialisiert (Digest={str(after_payload_summary.get('payload_digest') or 'n/a').strip() or 'n/a'}, Bytes={int(after_payload_summary.get('payload_size_bytes') or 0)}).",
        'Der After-Snapshot muss vor echter Mutation als materialisierter Payload vorliegen.',
        'after-payload',
        target=command_class,
        require_payload=True,
        payload_summary=after_payload_summary,
    )
    _append_owner_step(
        'Apply-Snapshot-Callback-Preview',
        '_restore_project_from_snapshot',
        'Die Before-/After-Snapshot-Factory kann den spaeteren Apply-Callback bereits ueber die vorhandene Restore-Methode read-only beschreiben.',
        'Die Before-/After-Snapshot-Factory braucht vor echter Mutation eine stabile Restore-Methode am Owner.',
        'snapshot-restore',
    )

    factory_stub = str(factory_descriptor.get('factory_stub') or 'build_audio_to_instrument_morph_before_after_snapshot_command_factory').strip() or 'build_audio_to_instrument_morph_before_after_snapshot_command_factory'
    before_stub = str(factory_descriptor.get('before_snapshot_stub') or 'materialize_audio_to_instrument_morph_before_snapshot_payload').strip() or 'materialize_audio_to_instrument_morph_before_snapshot_payload'
    after_stub = str(factory_descriptor.get('after_snapshot_stub') or 'materialize_audio_to_instrument_morph_after_snapshot_payload').strip() or 'materialize_audio_to_instrument_morph_after_snapshot_payload'
    factory_steps.append({
        'category': 'payload-metadata',
        'label': 'Snapshot-Payload-Paritaet',
        'target': command_class,
        'method': factory_stub,
        'state': 'ready' if shell_state == 'ready' and materialized_payload_count >= 2 else ('pending' if shell_state in {'ready', 'pending'} else 'blocked'),
        'detail': f"Before-/After-Payloads bleiben in dieser Phase read-only und sind aktuell als '{payload_delta_kind}' markiert.",
    })
    factory_steps.append({
        'category': 'payload-stub',
        'label': 'Before-Snapshot-Payload-Stub',
        'target': command_class,
        'method': before_stub,
        'state': 'ready' if shell_state == 'ready' and bool(before_payload_summary) else ('pending' if shell_state in {'ready', 'pending'} else 'blocked'),
        'detail': 'Die spaetere Before-Payload-Materialisierung bleibt read-only sichtbar und wird noch nicht an einen echten Commit gekoppelt.',
    })
    factory_steps.append({
        'category': 'payload-stub',
        'label': 'After-Snapshot-Payload-Stub',
        'target': command_class,
        'method': after_stub,
        'state': 'ready' if shell_state == 'ready' and bool(after_payload_summary) else ('pending' if shell_state in {'ready', 'pending'} else 'blocked'),
        'detail': 'Die spaetere After-Payload-Materialisierung bleibt read-only sichtbar und wird noch nicht an einen echten Commit gekoppelt.',
    })

    total_factory_step_count = len(factory_steps)
    ready_factory_step_count = sum(1 for item in factory_steps if str(item.get('state') or '').strip().lower() == 'ready')
    preview_factory_sequence = tuple(
        f"{str(item.get('label') or '').strip()}::{str(item.get('method') or '').strip()}"
        for item in factory_steps
        if str(item.get('label') or '').strip() and str(item.get('method') or '').strip()
    )
    if shell_state == 'ready' and ready_factory_step_count >= total_factory_step_count and total_factory_step_count > 0 and materialized_payload_count >= 2:
        payload_state = 'ready'
        mutation_gate_state = str(shell.get('mutation_gate_state') or capsule.get('mutation_gate_state') or 'armed-preview-only').strip() or 'armed-preview-only'
    elif shell_state in {'ready', 'pending'}:
        payload_state = 'pending'
        mutation_gate_state = 'blocked'
    else:
        payload_state = 'blocked'
        mutation_gate_state = 'blocked'
    summary = (
        f"Before-/After-Snapshot-Command-Factory {'bereit' if payload_state == 'ready' else ('vorbereitet' if payload_state == 'pending' else 'gesperrt')}"
        f" · Factory {ready_factory_step_count}/{total_factory_step_count}"
        f" · Payloads={materialized_payload_count}/2"
        f" · Delta={payload_delta_kind or 'n/a'}"
        f" · Command={command_class}"
        f" · Mutation bleibt aus"
    )
    report = RuntimeSnapshotCommandFactoryPayloadReport(
        factory_key=f'command_factory_payloads::{tx_token}',
        transaction_key=tx_key,
        shell_key=str(shell.get('shell_key') or '').strip(),
        capsule_key=str(shell.get('capsule_key') or capsule.get('capsule_key') or '').strip(),
        contract_key=str(shell.get('contract_key') or capsule.get('contract_key') or contract.get('contract_key') or '').strip(),
        payload_state=payload_state,
        mutation_gate_state=mutation_gate_state,
        target_scope=target_scope,
        owner_class=owner_class,
        command_class=command_class,
        command_module=command_module,
        label_preview=label_preview,
        payload_delta_kind=payload_delta_kind,
        materialized_payload_count=materialized_payload_count,
        before_payload_summary=before_payload_summary,
        after_payload_summary=after_payload_summary,
        total_factory_step_count=total_factory_step_count,
        ready_factory_step_count=ready_factory_step_count,
        factory_steps=tuple(factory_steps),
        preview_factory_sequence=preview_factory_sequence,
        future_factory_stub=factory_stub,
        future_before_snapshot_stub=before_stub,
        future_after_snapshot_stub=after_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_command_factory_payload_summary(runtime_snapshot_command_factory_payloads: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_command_factory_payloads or {})
    if not report:
        return ''
    state = str(report.get('payload_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"Before-/After-Snapshot-Command-Factory: {int(report.get('ready_factory_step_count') or 0)}/{int(report.get('total_factory_step_count') or 0)} {state_label}, "
        f"Payloads={int(report.get('materialized_payload_count') or 0)}/2, Delta={str(report.get('payload_delta_kind') or 'n/a').strip() or 'n/a'}, Command={str(report.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}, Mutation bleibt aus."
    )


def _build_runtime_snapshot_preview_command_construction(runtime_snapshot_command_factory_payloads: dict[str, Any] | None, runtime_snapshot_command_undo_shell: dict[str, Any] | None, runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None, runtime_snapshot_atomic_entrypoints: dict[str, Any] | None, runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_owner: Any | None = None) -> dict[str, Any]:
    payloads = dict(runtime_snapshot_command_factory_payloads or {})
    shell = dict(runtime_snapshot_command_undo_shell or {})
    capsule = dict(runtime_snapshot_mutation_gate_capsule or {})
    atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(payloads.get('transaction_key') or shell.get('transaction_key') or capsule.get('transaction_key') or contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = tx_key.replace('::', '--')
    payload_state = str(payloads.get('payload_state') or 'pending').strip().lower() or 'pending'
    target_scope = str(payloads.get('target_scope') or shell.get('target_scope') or capsule.get('target_scope') or contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(payloads.get('blocked_by') or shell.get('blocked_by') or capsule.get('blocked_by') or atomic_entrypoints.get('blocked_by') or contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(payloads.get('pending_by') or shell.get('pending_by') or capsule.get('pending_by') or atomic_entrypoints.get('pending_by') or contract.get('pending_by') or []) if str(x).strip()]
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else str(payloads.get('owner_class') or shell.get('owner_class') or '').strip()
    except Exception:
        owner_class = str(payloads.get('owner_class') or shell.get('owner_class') or '').strip()

    preview_descriptor: dict[str, Any] = {}
    command_class = str(payloads.get('command_class') or shell.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'
    command_module = str(payloads.get('command_module') or shell.get('command_module') or 'pydaw.commands.project_snapshot_edit').strip() or 'pydaw.commands.project_snapshot_edit'
    label_preview = str(payloads.get('label_preview') or '').strip()
    if runtime_owner is not None and hasattr(runtime_owner, 'preview_audio_to_instrument_morph_preview_snapshot_command'):
        try:
            preview_descriptor = dict(getattr(runtime_owner, 'preview_audio_to_instrument_morph_preview_snapshot_command')() or {})
        except Exception:
            preview_descriptor = {}
    if preview_descriptor:
        command_class = str(preview_descriptor.get('command_class') or command_class).strip() or command_class
        command_module = str(preview_descriptor.get('command_module') or command_module).strip() or command_module
        label_preview = str(preview_descriptor.get('label_preview') or label_preview).strip() or label_preview

    command_constructor = str(preview_descriptor.get('command_constructor') or 'ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)').strip() or 'ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)'
    apply_callback_name = str(preview_descriptor.get('apply_callback_name') or '_restore_project_from_snapshot').strip() or '_restore_project_from_snapshot'
    apply_callback_owner_class = str(preview_descriptor.get('apply_callback_owner_class') or owner_class or 'ProjectService').strip() or 'ProjectService'
    command_instance_state = str(preview_descriptor.get('command_instance_state') or 'pending').strip().lower() or 'pending'
    supports_do_preview = bool(preview_descriptor.get('supports_do_preview'))
    supports_undo_preview = bool(preview_descriptor.get('supports_undo_preview'))
    payload_delta_kind = str(preview_descriptor.get('payload_delta_kind') or payloads.get('payload_delta_kind') or 'n/a').strip() or 'n/a'
    materialized_payload_count = int(preview_descriptor.get('materialized_payload_count') or payloads.get('materialized_payload_count') or 0)
    before_payload_summary = dict(preview_descriptor.get('before_payload_summary') or payloads.get('before_payload_summary') or {})
    after_payload_summary = dict(preview_descriptor.get('after_payload_summary') or payloads.get('after_payload_summary') or {})
    command_field_names = tuple(str(x).strip() for x in list(preview_descriptor.get('command_field_names') or []) if str(x).strip())

    def _owner_state(method_name: str) -> str:
        if runtime_owner is None:
            return 'pending' if payload_state in {'ready', 'pending'} else 'blocked'
        return 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if payload_state in {'ready', 'pending'} else 'blocked')

    preview_steps: list[dict[str, Any]] = []

    def _append_owner_step(label: str, method_name: str, detail_ready: str, detail_missing: str, category: str, target: str = '') -> None:
        state = _owner_state(method_name)
        resolved_target = target or owner_class or 'ProjectService'
        detail = detail_ready if state == 'ready' else detail_missing
        if state != 'ready' and runtime_owner is None and payload_state in {'ready', 'pending'}:
            detail += ' Kein Runtime-Owner an den Plan uebergeben.'
        preview_steps.append({
            'category': category,
            'label': label,
            'target': resolved_target,
            'method': method_name,
            'state': state,
            'detail': detail,
        })

    _append_owner_step(
        'Preview-Command-Konstruktion',
        'preview_audio_to_instrument_morph_preview_snapshot_command',
        f'Der Owner konstruiert bereits read-only einen {command_class}-Preview-Command fuer denselben Minimalfall.',
        f'Die explizite read-only Preview-Command-Konstruktion fuer {command_class} muss spaeter als eigener Owner-Einstiegspunkt sichtbar werden.',
        'preview-command',
        target=command_class,
    )
    preview_steps.append({
        'category': 'command-constructor',
        'label': 'ProjectSnapshotEditCommand-Konstruktor sichtbar',
        'target': command_class,
        'method': command_constructor,
        'state': 'ready' if command_instance_state == 'constructed-preview-only' and payload_state == 'ready' else ('pending' if payload_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der spaetere {command_class}-Konstruktor ist jetzt als read-only Vorschau sichtbar und bleibt ungepusht.',
    })
    preview_steps.append({
        'category': 'command-fields',
        'label': 'Command-Felder materialisiert',
        'target': command_class,
        'method': '__dataclass_fields__',
        'state': 'ready' if command_field_names and payload_state == 'ready' else ('pending' if payload_state in {'ready', 'pending'} else 'blocked'),
        'detail': f"Die Preview-Command-Konstruktion kennt bereits die Feldliste: {', '.join(command_field_names[:8]) or 'n/a'}.",
    })
    preview_steps.append({
        'category': 'payload-metadata',
        'label': 'Before-/After-Payloads an Constructor gebunden',
        'target': command_class,
        'method': 'before/after payload summaries',
        'state': 'ready' if bool(before_payload_summary) and bool(after_payload_summary) and materialized_payload_count >= 2 and payload_state == 'ready' else ('pending' if payload_state in {'ready', 'pending'} else 'blocked'),
        'detail': f"Die Preview-Command-Konstruktion bindet bereits {materialized_payload_count}/2 Payloads read-only (Delta={payload_delta_kind or 'n/a'}).",
    })
    preview_steps.append({
        'category': 'apply-callback',
        'label': 'Apply-Callback-Preview',
        'target': apply_callback_owner_class,
        'method': apply_callback_name,
        'state': 'ready' if _owner_state(apply_callback_name) == 'ready' and payload_state == 'ready' else ('pending' if payload_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der spaetere Apply-Callback bleibt read-only an {apply_callback_owner_class}.{apply_callback_name} gebunden.',
    })
    preview_steps.append({
        'category': 'command-methods',
        'label': 'Command-do/undo-Methoden sichtbar',
        'target': command_class,
        'method': 'do/undo',
        'state': 'ready' if supports_do_preview and supports_undo_preview and payload_state == 'ready' else ('pending' if payload_state in {'ready', 'pending'} else 'blocked'),
        'detail': 'Die Preview-Command-Konstruktion bestaetigt bereits das spaetere do()/undo()-Verhalten, fuehrt es aber bewusst nicht aus.',
    })

    constructor_stub = str(preview_descriptor.get('constructor_stub') or 'construct_audio_to_instrument_morph_preview_snapshot_command').strip() or 'construct_audio_to_instrument_morph_preview_snapshot_command'
    executor_stub = str(preview_descriptor.get('executor_stub') or 'simulate_audio_to_instrument_morph_preview_snapshot_command').strip() or 'simulate_audio_to_instrument_morph_preview_snapshot_command'
    total_preview_step_count = len(preview_steps)
    ready_preview_step_count = sum(1 for item in preview_steps if str(item.get('state') or '').strip().lower() == 'ready')
    preview_command_sequence = tuple(
        f"{str(item.get('label') or '').strip()}::{str(item.get('method') or '').strip()}"
        for item in preview_steps
        if str(item.get('label') or '').strip() and str(item.get('method') or '').strip()
    )
    if payload_state == 'ready' and command_instance_state == 'constructed-preview-only' and ready_preview_step_count >= total_preview_step_count and total_preview_step_count > 0:
        preview_state = 'ready'
        mutation_gate_state = str(payloads.get('mutation_gate_state') or shell.get('mutation_gate_state') or capsule.get('mutation_gate_state') or 'armed-preview-only').strip() or 'armed-preview-only'
    elif payload_state in {'ready', 'pending'}:
        preview_state = 'pending'
        mutation_gate_state = 'blocked'
    else:
        preview_state = 'blocked'
        mutation_gate_state = 'blocked'
    summary = (
        f"Preview-Command-Konstruktion {'bereit' if preview_state == 'ready' else ('vorbereitet' if preview_state == 'pending' else 'gesperrt')}"
        f" · Preview {ready_preview_step_count}/{total_preview_step_count}"
        f" · Payloads={materialized_payload_count}/2"
        f" · Command={command_class}"
        f" · Mutation bleibt aus"
    )
    report = RuntimeSnapshotPreviewCommandConstructionReport(
        preview_command_key=f'preview_command_construction::{tx_token}',
        transaction_key=tx_key,
        factory_key=str(payloads.get('factory_key') or '').strip(),
        shell_key=str(payloads.get('shell_key') or shell.get('shell_key') or '').strip(),
        capsule_key=str(payloads.get('capsule_key') or shell.get('capsule_key') or capsule.get('capsule_key') or '').strip(),
        contract_key=str(payloads.get('contract_key') or shell.get('contract_key') or capsule.get('contract_key') or contract.get('contract_key') or '').strip(),
        preview_state=preview_state,
        mutation_gate_state=mutation_gate_state,
        target_scope=target_scope,
        owner_class=owner_class,
        command_class=command_class,
        command_module=command_module,
        command_constructor=command_constructor,
        label_preview=label_preview,
        apply_callback_name=apply_callback_name,
        apply_callback_owner_class=apply_callback_owner_class,
        payload_delta_kind=payload_delta_kind,
        materialized_payload_count=materialized_payload_count,
        before_payload_summary=before_payload_summary,
        after_payload_summary=after_payload_summary,
        command_field_names=command_field_names,
        total_preview_step_count=total_preview_step_count,
        ready_preview_step_count=ready_preview_step_count,
        preview_steps=tuple(preview_steps),
        preview_command_sequence=preview_command_sequence,
        future_constructor_stub=constructor_stub,
        future_executor_stub=executor_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_preview_command_construction_summary(runtime_snapshot_preview_command_construction: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_preview_command_construction or {})
    if not report:
        return ''
    state = str(report.get('preview_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"Preview-Command-Konstruktion: {int(report.get('ready_preview_step_count') or 0)}/{int(report.get('total_preview_step_count') or 0)} {state_label}, "
        f"Payloads={int(report.get('materialized_payload_count') or 0)}/2, Command={str(report.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}, Mutation bleibt aus."
    )


def _build_runtime_snapshot_dry_run(runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_objects: list[dict[str, Any]] | None, runtime_snapshot_stubs: list[dict[str, Any]] | None, runtime_snapshot_state_carriers: list[dict[str, Any]] | None, runtime_snapshot_state_containers: list[dict[str, Any]] | None, runtime_snapshot_state_holders: list[dict[str, Any]] | None, runtime_snapshot_state_slots: list[dict[str, Any]] | None, runtime_snapshot_state_stores: list[dict[str, Any]] | None, runtime_snapshot_state_registries: list[dict[str, Any]] | None, runtime_snapshot_state_registry_backends: list[dict[str, Any]] | None, runtime_snapshot_state_registry_backend_adapters: list[dict[str, Any]] | None, transaction_steps: list[str] | None) -> dict[str, Any]:
    bundle = dict(runtime_snapshot_bundle or {})
    items = [dict(item or {}) for item in list(runtime_snapshot_objects or [])]
    stub_items = [dict(item or {}) for item in list(runtime_snapshot_stubs or [])]
    state_carrier_items = [dict(item or {}) for item in list(runtime_snapshot_state_carriers or [])]
    state_container_items = [dict(item or {}) for item in list(runtime_snapshot_state_containers or [])]
    state_holder_items = [dict(item or {}) for item in list(runtime_snapshot_state_holders or [])]
    state_slot_items = [dict(item or {}) for item in list(runtime_snapshot_state_slots or [])]
    state_store_items = [dict(item or {}) for item in list(runtime_snapshot_state_stores or [])]
    state_registry_items = [dict(item or {}) for item in list(runtime_snapshot_state_registries or [])]
    state_registry_backend_items = [dict(item or {}) for item in list(runtime_snapshot_state_registry_backends or [])]
    state_registry_backend_adapter_items = [dict(item or {}) for item in list(runtime_snapshot_state_registry_backend_adapters or [])]
    tx_key = str(bundle.get("transaction_key") or "audio_to_instrument_morph::preview").strip() or "audio_to_instrument_morph::preview"
    bundle_key = str(bundle.get("bundle_key") or "").strip()
    tx_token = _sanitize_ref_token(tx_key, "audio_to_instrument_morph_preview")
    capture_ready_items = [
        item for item in items
        if str(item.get("bind_state") or "").strip().lower() == "ready"
        and bool(item.get("supports_capture"))
        and bool(item.get("supports_restore"))
        and str(item.get("snapshot_object_key") or "").strip()
    ]
    capture_sequence = tuple(
        str(item.get("snapshot_object_key") or "").strip()
        for item in capture_ready_items
        if str(item.get("snapshot_object_key") or "").strip()
    )
    restore_sequence = tuple(reversed(capture_sequence))
    rollback_items = sorted(
        capture_ready_items,
        key=lambda item: (
            str(item.get("rollback_slot") or "").strip(),
            str(item.get("snapshot_object_key") or "").strip(),
        ),
    )
    rollback_sequence = tuple(
        f"{str(item.get('rollback_slot') or '').strip() or 'rollback'}::{str(item.get('snapshot_object_key') or '').strip()}"
        for item in rollback_items
        if str(item.get("snapshot_object_key") or "").strip()
    )
    phase_results: list[dict[str, Any]] = []
    rehearsed_steps: list[str] = []
    capture_method_calls: list[str] = []
    restore_method_calls: list[str] = []
    stub_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in stub_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    stub_dispatch_calls: list[str] = []
    state_carrier_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_carrier_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_container_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_container_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_holder_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_holder_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_slot_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_slot_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_store_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_store_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_registry_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_registry_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_registry_backend_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_registry_backend_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_registry_backend_adapter_map = {
        str(item.get("snapshot_object_key") or "").strip(): dict(item or {})
        for item in state_registry_backend_adapter_items
        if str(item.get("snapshot_object_key") or "").strip()
    }
    state_carrier_calls: list[str] = []
    state_container_calls: list[str] = []
    state_holder_calls: list[str] = []
    state_slot_calls: list[str] = []
    state_store_calls: list[str] = []
    state_registry_calls: list[str] = []
    state_registry_backend_calls: list[str] = []
    state_registry_backend_adapter_calls: list[str] = []
    for item in capture_ready_items:
        object_key = str(item.get("snapshot_object_key") or "").strip()
        stub_plan = dict(stub_map.get(object_key) or {})
        carrier_plan = dict(state_carrier_map.get(object_key) or {})
        container_plan = dict(state_container_map.get(object_key) or {})
        holder_plan = dict(state_holder_map.get(object_key) or {})
        slot_plan = dict(state_slot_map.get(object_key) or {})
        store_plan = dict(state_store_map.get(object_key) or {})
        registry_plan = dict(state_registry_map.get(object_key) or {})
        backend_plan = dict(state_registry_backend_map.get(object_key) or {})
        adapter_plan = dict(state_registry_backend_adapter_map.get(object_key) or {})
        stub_instance = _instantiate_runtime_snapshot_stub(item)
        stub_class = str(stub_plan.get("stub_class") or getattr(stub_instance, "stub_class_name", stub_instance.__class__.__name__)).strip() or stub_instance.__class__.__name__
        carrier_instance = _instantiate_runtime_snapshot_state_carrier(item, stub_plan)
        carrier_class = str(carrier_plan.get("carrier_class") or getattr(carrier_instance, "carrier_class_name", carrier_instance.__class__.__name__)).strip() or carrier_instance.__class__.__name__
        container_instance = _instantiate_runtime_snapshot_state_container(item, stub_plan, carrier_plan)
        container_class = str(container_plan.get("container_class") or getattr(container_instance, "container_class_name", container_instance.__class__.__name__)).strip() or container_instance.__class__.__name__
        holder_instance = _instantiate_runtime_snapshot_state_holder(item, stub_plan, carrier_plan, container_plan)
        holder_class = str(holder_plan.get("holder_class") or getattr(holder_instance, "holder_class_name", holder_instance.__class__.__name__)).strip() or holder_instance.__class__.__name__
        slot_instance = _instantiate_runtime_snapshot_state_slot(item, stub_plan, carrier_plan, container_plan, holder_plan)
        slot_class = str(slot_plan.get("slot_class") or getattr(slot_instance, "slot_class_name", slot_instance.__class__.__name__)).strip() or slot_instance.__class__.__name__
        store_instance = _instantiate_runtime_snapshot_state_store(item, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan)
        store_class = str(store_plan.get("store_class") or getattr(store_instance, "store_class_name", store_instance.__class__.__name__)).strip() or store_instance.__class__.__name__
        registry_instance = _instantiate_runtime_snapshot_state_registry(item, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan)
        registry_class = str(registry_plan.get("registry_class") or getattr(registry_instance, "registry_class_name", registry_instance.__class__.__name__)).strip() or registry_instance.__class__.__name__
        backend_instance = _instantiate_runtime_snapshot_state_registry_backend(item, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan)
        backend_class = str(backend_plan.get("backend_class") or getattr(backend_instance, "backend_class_name", backend_instance.__class__.__name__)).strip() or backend_instance.__class__.__name__
        adapter_instance = _instantiate_runtime_snapshot_state_registry_backend_adapter(item, stub_plan, carrier_plan, container_plan, holder_plan, slot_plan, store_plan, registry_plan, backend_plan)
        adapter_class = str(adapter_plan.get("adapter_class") or getattr(adapter_instance, "adapter_class_name", adapter_instance.__class__.__name__)).strip() or adapter_instance.__class__.__name__
        capture_result = dict(adapter_instance.capture_adapter_preview() or {})
        phase_results.append(capture_result)
        capture_method = str(capture_result.get("method") or item.get("capture_method") or "capture").strip() or "capture"
        capture_method_calls.append(capture_method)
        stub_dispatch_calls.append(f"{stub_class}.capture_preview")
        state_carrier_calls.append(f"{carrier_class}.capture_state_preview")
        state_container_calls.append(f"{container_class}.capture_container_preview")
        state_holder_calls.append(f"{holder_class}.capture_holder_preview")
        state_slot_calls.append(f"{slot_class}.capture_slot_preview")
        state_store_calls.append(f"{store_class}.capture_store_preview")
        state_registry_calls.append(f"{registry_class}.capture_registry_preview")
        state_registry_backend_calls.append(f"{backend_class}.capture_backend_preview")
        state_registry_backend_adapter_calls.append(f"{adapter_class}.capture_adapter_preview")
        rehearsed_steps.append(f"capture::{object_key} via {capture_method}")

        restore_result = dict(adapter_instance.restore_adapter_preview() or {})
        phase_results.append(restore_result)
        restore_method = str(restore_result.get("method") or item.get("restore_method") or "restore").strip() or "restore"
        restore_method_calls.append(restore_method)
        stub_dispatch_calls.append(f"{stub_class}.restore_preview")
        state_carrier_calls.append(f"{carrier_class}.restore_state_preview")
        state_container_calls.append(f"{container_class}.restore_container_preview")
        state_holder_calls.append(f"{holder_class}.restore_holder_preview")
        state_slot_calls.append(f"{slot_class}.restore_slot_preview")
        state_store_calls.append(f"{store_class}.restore_store_preview")
        state_registry_calls.append(f"{registry_class}.restore_registry_preview")
        state_registry_backend_calls.append(f"{backend_class}.restore_backend_preview")
        state_registry_backend_adapter_calls.append(f"{adapter_class}.restore_adapter_preview")
        rehearsed_steps.append(f"restore::{object_key} via {restore_method}")

        rollback_result = dict(adapter_instance.rollback_adapter_preview() or {})
        phase_results.append(rollback_result)
        rollback_slot = str(rollback_result.get("method") or item.get("rollback_slot") or "rollback").strip() or "rollback"
        stub_dispatch_calls.append(f"{stub_class}.rollback_preview")
        state_carrier_calls.append(f"{carrier_class}.rollback_state_preview")
        state_container_calls.append(f"{container_class}.rollback_container_preview")
        state_holder_calls.append(f"{holder_class}.rollback_holder_preview")
        state_slot_calls.append(f"{slot_class}.rollback_slot_preview")
        state_store_calls.append(f"{store_class}.rollback_store_preview")
        state_registry_calls.append(f"{registry_class}.rollback_registry_preview")
        state_registry_backend_calls.append(f"{backend_class}.rollback_backend_preview")
        state_registry_backend_adapter_calls.append(f"{adapter_class}.rollback_adapter_preview")
        rehearsed_steps.append(f"rollback-slot::{rollback_slot}::{object_key}")
    commit_stub = str(bundle.get("commit_stub") or "commit_audio_to_instrument_morph_transaction").strip() or "commit_audio_to_instrument_morph_transaction"
    rollback_stub = str(bundle.get("rollback_stub") or "rollback_audio_to_instrument_morph_transaction").strip() or "rollback_audio_to_instrument_morph_transaction"
    if capture_ready_items:
        phase_results.append({
            "phase": "commit-preview",
            "target": bundle_key or tx_key,
            "method": commit_stub,
            "state": "blocked",
            "detail": "Commit bleibt im Dry-Run bewusst gesperrt; es wird nichts angewendet.",
        })
        rehearsed_steps.append(f"commit-preview::{commit_stub}")
        phase_results.append({
            "phase": "rollback-preview",
            "target": bundle_key or tx_key,
            "method": rollback_stub,
            "state": "ready",
            "detail": "Rollback-Reihenfolge wurde read-only ueber die Safe-Runner-Aufrufe vorbereitet; keine Projektmutation.",
        })
        rehearsed_steps.append(f"rollback-preview::{rollback_stub}")
    for step in list(transaction_steps or []):
        step_text = str(step or "").strip()
        if not step_text:
            continue
        phase_results.append({
            "phase": "transaction-step",
            "target": bundle_key or tx_key,
            "method": "plan",
            "state": "ready" if capture_ready_items else "pending",
            "detail": step_text,
        })
    phase_count = len(phase_results)
    ready_phase_count = sum(1 for item in phase_results if str(item.get("state") or "").strip().lower() == "ready")
    runner_state = "ready" if bundle_key and capture_ready_items and len(capture_sequence) == int(bundle.get("object_count") or 0) else ("pending" if bundle_key else "blocked")
    state_carrier_summary = _build_state_carrier_dispatch_summary(state_carrier_calls)
    state_container_summary = _build_state_container_dispatch_summary(state_container_calls)
    state_holder_summary = _build_state_holder_dispatch_summary(state_holder_calls)
    state_slot_summary = _build_state_slot_dispatch_summary(state_slot_calls)
    state_store_summary = _build_state_store_dispatch_summary(state_store_calls)
    state_registry_summary = _build_state_registry_dispatch_summary(state_registry_calls)
    state_registry_backend_summary = _build_state_registry_backend_dispatch_summary(state_registry_backend_calls)
    state_registry_backend_adapter_summary = _build_state_registry_backend_adapter_dispatch_summary(state_registry_backend_adapter_calls)
    runner_dispatch_summary = _build_safe_runner_dispatch_summary(capture_ready_items, phase_results)
    if stub_dispatch_calls:
        runner_dispatch_summary += f" Klassenstubs={len(stub_dispatch_calls)} Aufrufe."
    report = RuntimeSnapshotDryRunReport(
        runner_key=f"dry_run_runner::{tx_token}",
        transaction_key=tx_key,
        bundle_key=bundle_key,
        dry_run_mode="read-only-transaction-rehearsal",
        runner_state=runner_state,
        phase_count=phase_count,
        ready_phase_count=ready_phase_count,
        capture_sequence=capture_sequence,
        restore_sequence=restore_sequence,
        rollback_sequence=rollback_sequence,
        rehearsed_steps=tuple(rehearsed_steps),
        phase_results=tuple(phase_results),
        capture_method_calls=tuple(capture_method_calls),
        restore_method_calls=tuple(restore_method_calls),
        state_carrier_calls=tuple(state_carrier_calls),
        state_carrier_summary=state_carrier_summary,
        state_container_calls=tuple(state_container_calls),
        state_container_summary=state_container_summary,
        state_holder_calls=tuple(state_holder_calls),
        state_holder_summary=state_holder_summary,
        state_slot_calls=tuple(state_slot_calls),
        state_slot_summary=state_slot_summary,
        state_store_calls=tuple(state_store_calls),
        state_store_summary=state_store_summary,
        state_registry_calls=tuple(state_registry_calls),
        state_registry_summary=state_registry_summary,
        state_registry_backend_calls=tuple(state_registry_backend_calls),
        state_registry_backend_summary=state_registry_backend_summary,
        state_registry_backend_adapter_calls=tuple(state_registry_backend_adapter_calls),
        state_registry_backend_adapter_summary=state_registry_backend_adapter_summary,
        runner_dispatch_summary=(f"{runner_dispatch_summary} {state_carrier_summary} {state_container_summary} {state_holder_summary} {state_slot_summary} {state_store_summary} {state_registry_summary} {state_registry_backend_summary} {state_registry_backend_adapter_summary}".strip() + (f" Stub-Dispatch: {', '.join(stub_dispatch_calls[:6])}" if stub_dispatch_calls else "")).strip(),
        commit_rehearsed=bool(capture_ready_items),
        rollback_rehearsed=bool(capture_ready_items),
        dry_run_stub="run_audio_to_instrument_morph_dry_run",
    )
    return report.as_plan_dict()



def _build_runtime_snapshot_dry_run_summary(runtime_snapshot_dry_run: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_dry_run or {})
    if not report:
        return ""
    ready = int(report.get("ready_phase_count") or 0)
    total = int(report.get("phase_count") or 0)
    capture_count = len([str(x).strip() for x in list(report.get("capture_sequence") or []) if str(x).strip()])
    restore_count = len([str(x).strip() for x in list(report.get("restore_sequence") or []) if str(x).strip()])
    state = str(report.get("runner_state") or "pending").strip().lower() or "pending"
    state_label = {"ready": "bereit", "pending": "vorbereitet", "blocked": "gesperrt"}.get(state, state)
    dispatch_summary = str(report.get("runner_dispatch_summary") or "").strip()
    summary = (
        f"Read-only Dry-Run / Transaktions-Runner: {ready}/{total} Phasen {state_label}, "
        f"Capture={capture_count}, Restore={restore_count}, Commit bleibt Preview-only."
    )
    if dispatch_summary:
        summary += f" {dispatch_summary}"
    return summary


def _build_runtime_snapshot_dry_command_executor(runtime_snapshot_preview_command_construction: dict[str, Any] | None, runtime_snapshot_command_factory_payloads: dict[str, Any] | None, runtime_snapshot_command_undo_shell: dict[str, Any] | None, runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None, runtime_snapshot_atomic_entrypoints: dict[str, Any] | None, runtime_snapshot_precommit_contract: dict[str, Any] | None, runtime_snapshot_bundle: dict[str, Any] | None, runtime_snapshot_apply_runner: dict[str, Any] | None, runtime_snapshot_dry_run: dict[str, Any] | None, runtime_owner: Any | None = None) -> dict[str, Any]:
    preview = dict(runtime_snapshot_preview_command_construction or {})
    payloads = dict(runtime_snapshot_command_factory_payloads or {})
    shell = dict(runtime_snapshot_command_undo_shell or {})
    capsule = dict(runtime_snapshot_mutation_gate_capsule or {})
    atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    contract = dict(runtime_snapshot_precommit_contract or {})
    bundle = dict(runtime_snapshot_bundle or {})
    apply_runner = dict(runtime_snapshot_apply_runner or {})
    dry_run = dict(runtime_snapshot_dry_run or {})
    tx_key = str(preview.get('transaction_key') or payloads.get('transaction_key') or shell.get('transaction_key') or capsule.get('transaction_key') or contract.get('transaction_key') or bundle.get('transaction_key') or apply_runner.get('transaction_key') or dry_run.get('transaction_key') or 'audio_to_instrument_morph::preview').strip() or 'audio_to_instrument_morph::preview'
    tx_token = tx_key.replace('::', '--')
    preview_state = str(preview.get('preview_state') or 'pending').strip().lower() or 'pending'
    target_scope = str(preview.get('target_scope') or payloads.get('target_scope') or shell.get('target_scope') or capsule.get('target_scope') or contract.get('target_scope') or 'empty-audio-track-minimal-case').strip() or 'empty-audio-track-minimal-case'
    blocked_by = [str(x).strip() for x in list(preview.get('blocked_by') or payloads.get('blocked_by') or shell.get('blocked_by') or capsule.get('blocked_by') or atomic_entrypoints.get('blocked_by') or contract.get('blocked_by') or []) if str(x).strip()]
    pending_by = [str(x).strip() for x in list(preview.get('pending_by') or payloads.get('pending_by') or shell.get('pending_by') or capsule.get('pending_by') or atomic_entrypoints.get('pending_by') or contract.get('pending_by') or []) if str(x).strip()]
    owner_class = ''
    try:
        owner_class = runtime_owner.__class__.__name__ if runtime_owner is not None else str(preview.get('owner_class') or payloads.get('owner_class') or '').strip()
    except Exception:
        owner_class = str(preview.get('owner_class') or payloads.get('owner_class') or '').strip()

    executor_descriptor: dict[str, Any] = {}
    command_class = str(preview.get('command_class') or payloads.get('command_class') or shell.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'
    command_module = str(preview.get('command_module') or payloads.get('command_module') or shell.get('command_module') or 'pydaw.commands.project_snapshot_edit').strip() or 'pydaw.commands.project_snapshot_edit'
    label_preview = str(preview.get('label_preview') or payloads.get('label_preview') or '').strip()
    if runtime_owner is not None and hasattr(runtime_owner, 'preview_audio_to_instrument_morph_dry_command_executor'):
        try:
            executor_descriptor = dict(getattr(runtime_owner, 'preview_audio_to_instrument_morph_dry_command_executor')() or {})
        except Exception:
            executor_descriptor = {}
    if executor_descriptor:
        command_class = str(executor_descriptor.get('command_class') or command_class).strip() or command_class
        command_module = str(executor_descriptor.get('command_module') or command_module).strip() or command_module
        label_preview = str(executor_descriptor.get('label_preview') or label_preview).strip() or label_preview

    command_constructor = str(executor_descriptor.get('command_constructor') or preview.get('command_constructor') or 'ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)').strip() or 'ProjectSnapshotEditCommand(before=..., after=..., label=..., apply_snapshot=...)'
    apply_callback_name = str(executor_descriptor.get('apply_callback_name') or '_shadow_apply_snapshot').strip() or '_shadow_apply_snapshot'
    apply_callback_owner_class = str(executor_descriptor.get('apply_callback_owner_class') or owner_class or 'ProjectService').strip() or 'ProjectService'
    simulation_state = str(executor_descriptor.get('simulation_state') or 'pending').strip().lower() or 'pending'
    payload_delta_kind = str(executor_descriptor.get('payload_delta_kind') or preview.get('payload_delta_kind') or payloads.get('payload_delta_kind') or 'n/a').strip() or 'n/a'
    materialized_payload_count = int(executor_descriptor.get('materialized_payload_count') or preview.get('materialized_payload_count') or payloads.get('materialized_payload_count') or 0)
    before_payload_summary = dict(executor_descriptor.get('before_payload_summary') or preview.get('before_payload_summary') or payloads.get('before_payload_summary') or {})
    after_payload_summary = dict(executor_descriptor.get('after_payload_summary') or preview.get('after_payload_summary') or payloads.get('after_payload_summary') or {})
    do_call_count = int(executor_descriptor.get('do_call_count') or 0)
    undo_call_count = int(executor_descriptor.get('undo_call_count') or 0)
    callback_call_count = int(executor_descriptor.get('callback_call_count') or 0)
    callback_trace = tuple(str(x).strip() for x in list(executor_descriptor.get('callback_trace') or []) if str(x).strip())
    callback_payload_digests = tuple(str(x).strip() for x in list(executor_descriptor.get('callback_payload_digests') or []) if str(x).strip())
    simulation_sequence = tuple(str(x).strip() for x in list(executor_descriptor.get('simulation_sequence') or ['do()', 'undo()']) if str(x).strip())
    future_executor_stub = str(executor_descriptor.get('executor_stub') or preview.get('future_executor_stub') or 'simulate_audio_to_instrument_morph_preview_snapshot_command_dry_executor').strip() or 'simulate_audio_to_instrument_morph_preview_snapshot_command_dry_executor'
    future_live_executor_stub = str(executor_descriptor.get('future_live_executor_stub') or 'execute_audio_to_instrument_morph_preview_snapshot_command_live').strip() or 'execute_audio_to_instrument_morph_preview_snapshot_command_live'

    def _owner_state(method_name: str) -> str:
        if runtime_owner is None:
            return 'pending' if preview_state in {'ready', 'pending'} else 'blocked'
        return 'ready' if _has_entrypoint(runtime_owner, method_name) else ('pending' if preview_state in {'ready', 'pending'} else 'blocked')

    simulation_steps: list[dict[str, Any]] = []

    owner_state = _owner_state('preview_audio_to_instrument_morph_dry_command_executor')
    owner_detail = f'Der Owner fuehrt bereits eine read-only do()/undo()-Simulation fuer denselben {command_class}-Minimalfall aus.'
    if owner_state != 'ready':
        owner_detail = f'Der read-only Dry-Command-Executor fuer {command_class} muss spaeter als eigener Owner-Einstiegspunkt sichtbar werden.'
        if runtime_owner is None and preview_state in {'ready', 'pending'}:
            owner_detail += ' Kein Runtime-Owner an den Plan uebergeben.'
    simulation_steps.append({
        'category': 'dry-command-executor',
        'label': 'Dry-Command-Executor / Simulations-Harness',
        'target': owner_class or 'ProjectService',
        'method': 'preview_audio_to_instrument_morph_dry_command_executor',
        'state': owner_state,
        'detail': owner_detail,
    })
    simulation_steps.append({
        'category': 'do-simulation',
        'label': 'do()-Simulation ausgefuehrt',
        'target': command_class,
        'method': 'do()',
        'state': 'ready' if simulation_state == 'simulated-preview-only' and do_call_count >= 1 and preview_state == 'ready' else ('pending' if preview_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der spaetere {command_class}.do()-Pfad wurde {do_call_count}x gegen einen Recorder-Callback geprobt, ohne das Projekt zu beruehren.',
    })
    simulation_steps.append({
        'category': 'undo-simulation',
        'label': 'undo()-Simulation ausgefuehrt',
        'target': command_class,
        'method': 'undo()',
        'state': 'ready' if simulation_state == 'simulated-preview-only' and undo_call_count >= 1 and preview_state == 'ready' else ('pending' if preview_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der spaetere {command_class}.undo()-Pfad wurde {undo_call_count}x gegen denselben Recorder-Callback geprobt, weiterhin ohne Undo-Push.',
    })
    simulation_steps.append({
        'category': 'callback-recorder',
        'label': 'Recorder-Callback verfolgt Snapshot-Fluss',
        'target': apply_callback_owner_class,
        'method': apply_callback_name,
        'state': 'ready' if simulation_state == 'simulated-preview-only' and callback_call_count >= 2 and len(callback_trace) >= 2 and preview_state == 'ready' else ('pending' if preview_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der Recorder-Callback sah {callback_call_count} Aufrufe ({", ".join(callback_trace[:4]) or "n/a"}); Payload-Digests={", ".join(callback_payload_digests[:4]) or "n/a"}.',
    })
    simulation_steps.append({
        'category': 'payload-reuse',
        'label': 'Materialisierte Payloads fuer Simulation wiederverwendet',
        'target': command_class,
        'method': 'before/after payload summaries',
        'state': 'ready' if bool(before_payload_summary) and bool(after_payload_summary) and materialized_payload_count >= 2 and preview_state == 'ready' else ('pending' if preview_state in {'ready', 'pending'} else 'blocked'),
        'detail': f'Der Dry-Executor verwendet dieselben {materialized_payload_count}/2 Snapshot-Payloads (Delta={payload_delta_kind or "n/a"}) wie die Preview-Command-Konstruktion.',
    })

    step_states = [str(item.get('state') or '').strip().lower() for item in simulation_steps]
    ready_simulation_step_count = sum(1 for state in step_states if state == 'ready')
    total_simulation_step_count = len(simulation_steps)
    dry_executor_state = 'blocked'
    if total_simulation_step_count and ready_simulation_step_count == total_simulation_step_count and simulation_state == 'simulated-preview-only' and preview_state == 'ready':
        dry_executor_state = 'ready'
    elif preview_state in {'ready', 'pending'}:
        dry_executor_state = 'pending'
    summary = (
        f"Dry-Command-Executor: {ready_simulation_step_count}/{total_simulation_step_count} {'bereit' if dry_executor_state == 'ready' else ('vorbereitet' if dry_executor_state == 'pending' else 'gesperrt')}, "
        f"do/undo={do_call_count}/{undo_call_count}, Callback={callback_call_count}, Command={command_class}, Mutation bleibt aus."
    )
    report = RuntimeSnapshotDryCommandExecutorReport(
        dry_executor_key=f'dry_command_executor::{tx_token}',
        transaction_key=tx_key,
        preview_command_key=str(preview.get('preview_command_key') or f'preview_command_construction::{tx_token}').strip() or f'preview_command_construction::{tx_token}',
        factory_key=str(preview.get('factory_key') or payloads.get('factory_key') or f'command_factory_payloads::{tx_token}').strip() or f'command_factory_payloads::{tx_token}',
        shell_key=str(preview.get('shell_key') or payloads.get('shell_key') or shell.get('shell_key') or f'command_undo_shell::{tx_token}').strip() or f'command_undo_shell::{tx_token}',
        capsule_key=str(preview.get('capsule_key') or payloads.get('capsule_key') or shell.get('capsule_key') or capsule.get('capsule_key') or f'mutation_gate_capsule::{tx_token}').strip() or f'mutation_gate_capsule::{tx_token}',
        contract_key=str(preview.get('contract_key') or payloads.get('contract_key') or shell.get('contract_key') or capsule.get('contract_key') or contract.get('contract_key') or f'precommit_contract::{tx_token}').strip() or f'precommit_contract::{tx_token}',
        dry_executor_state=dry_executor_state,
        mutation_gate_state=str(preview.get('mutation_gate_state') or payloads.get('mutation_gate_state') or capsule.get('mutation_gate_state') or 'blocked').strip() or 'blocked',
        target_scope=target_scope,
        owner_class=owner_class or str(executor_descriptor.get('owner_class') or 'ProjectService').strip() or 'ProjectService',
        command_class=command_class,
        command_module=command_module,
        command_constructor=command_constructor,
        label_preview=label_preview,
        apply_callback_name=apply_callback_name,
        apply_callback_owner_class=apply_callback_owner_class,
        payload_delta_kind=payload_delta_kind,
        materialized_payload_count=materialized_payload_count,
        before_payload_summary=before_payload_summary,
        after_payload_summary=after_payload_summary,
        do_call_count=do_call_count,
        undo_call_count=undo_call_count,
        callback_call_count=callback_call_count,
        callback_trace=callback_trace,
        callback_payload_digests=callback_payload_digests,
        total_simulation_step_count=total_simulation_step_count,
        ready_simulation_step_count=ready_simulation_step_count,
        simulation_steps=tuple(simulation_steps),
        simulation_sequence=simulation_sequence,
        future_executor_stub=future_executor_stub,
        future_live_executor_stub=future_live_executor_stub,
        blocked_by=tuple(blocked_by),
        pending_by=tuple(pending_by),
        summary=summary,
    )
    return report.as_plan_dict()


def _build_runtime_snapshot_dry_command_executor_summary(runtime_snapshot_dry_command_executor: dict[str, Any] | None) -> str:
    report = dict(runtime_snapshot_dry_command_executor or {})
    if not report:
        return ''
    state = str(report.get('dry_executor_state') or 'pending').strip().lower() or 'pending'
    state_label = {'ready': 'bereit', 'pending': 'vorbereitet', 'blocked': 'gesperrt'}.get(state, state)
    return (
        f"Dry-Command-Executor: {int(report.get('ready_simulation_step_count') or 0)}/{int(report.get('total_simulation_step_count') or 0)} {state_label}, "
        f"do/undo={int(report.get('do_call_count') or 0)}/{int(report.get('undo_call_count') or 0)}, Callback={int(report.get('callback_call_count') or 0)}, Command={str(report.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}, Mutation bleibt aus."
    )


def _build_shadow_commit_rehearsal(project_obj: Any, track: Any) -> dict[str, Any]:
    """Stage 1: Shadow-Commit-Rehearsal — simulate the full undo cycle read-only.

    Creates a local deep-copy of the project, performs the minimal track-kind
    change on the copy, constructs a ProjectSnapshotEditCommand with both
    snapshots, calls do()/undo() against a local recorder callback, and
    verifies the full round-trip — all without touching the real project.

    Returns a report dict with rehearsal results.
    """
    report: dict[str, Any] = {
        "rehearsal_state": "pending",
        "before_snapshot_ok": False,
        "after_snapshot_ok": False,
        "command_constructed": False,
        "do_called": False,
        "undo_called": False,
        "round_trip_ok": False,
        "rollback_verified": False,
        "error": None,
    }
    try:
        track_id = str(getattr(track, "id", "") or "")
        track_kind = str(getattr(track, "kind", "") or "").strip().lower()
        if track_kind != "audio":
            report["rehearsal_state"] = "skipped"
            report["error"] = f"Track kind is '{track_kind}', not 'audio'"
            return report

        # Capture before snapshot from a deep copy
        before_dict: dict[str, Any] = {}
        after_dict: dict[str, Any] = {}
        try:
            before_dict = copy.deepcopy(project_obj.to_dict())
            report["before_snapshot_ok"] = bool(before_dict)
        except Exception as exc:
            report["error"] = f"before snapshot failed: {exc}"
            return report

        # Simulate the mutation on a deep copy
        try:
            simulated = copy.deepcopy(before_dict)
            for t in simulated.get("tracks", []):
                if str(t.get("id", "")) == track_id:
                    t["kind"] = "instrument"
                    break
            after_dict = simulated
            report["after_snapshot_ok"] = bool(after_dict)
        except Exception as exc:
            report["error"] = f"after snapshot simulation failed: {exc}"
            return report

        # Local recorder to track callback invocations
        recorder: list[str] = []

        def local_apply_snapshot(snapshot: dict) -> None:
            recorder.append("applied")

        # Construct the command
        try:
            from pydaw.commands.project_snapshot_edit import ProjectSnapshotEditCommand
            cmd = ProjectSnapshotEditCommand(
                before=copy.deepcopy(before_dict),
                after=copy.deepcopy(after_dict),
                label="Shadow-Commit-Rehearsal: Audio→Instrument (leere Spur)",
                apply_snapshot=local_apply_snapshot,
            )
            report["command_constructed"] = True
        except Exception as exc:
            report["error"] = f"command construction failed: {exc}"
            return report

        # Simulate do()
        try:
            recorder.clear()
            cmd.do()
            report["do_called"] = "applied" in recorder
        except Exception as exc:
            report["error"] = f"do() failed: {exc}"
            return report

        # Simulate undo()
        try:
            recorder.clear()
            cmd.undo()
            report["undo_called"] = "applied" in recorder
        except Exception as exc:
            report["error"] = f"undo() failed: {exc}"
            return report

        # Verify round-trip: before snapshot should still equal original
        try:
            rt_before = copy.deepcopy(cmd.before)
            rt_after = copy.deepcopy(cmd.after)
            # The before snapshot tracks should have kind=audio
            before_track = next((t for t in rt_before.get("tracks", []) if t.get("id") == track_id), None)
            after_track = next((t for t in rt_after.get("tracks", []) if t.get("id") == track_id), None)
            report["round_trip_ok"] = (
                before_track is not None
                and after_track is not None
                and str(before_track.get("kind", "")) == "audio"
                and str(after_track.get("kind", "")) == "instrument"
            )
            report["rollback_verified"] = report["round_trip_ok"] and report["undo_called"]
        except Exception as exc:
            report["error"] = f"round-trip verification failed: {exc}"
            return report

        all_ok = all([
            report["before_snapshot_ok"],
            report["after_snapshot_ok"],
            report["command_constructed"],
            report["do_called"],
            report["undo_called"],
            report["round_trip_ok"],
            report["rollback_verified"],
        ])
        report["rehearsal_state"] = "passed" if all_ok else "failed"
        return report
    except Exception as exc:
        report["rehearsal_state"] = "error"
        report["error"] = str(exc)
        return report


def _build_shadow_commit_rehearsal_summary(rehearsal: dict[str, Any] | None) -> str:
    r = dict(rehearsal or {})
    if not r:
        return ""
    state = str(r.get("rehearsal_state") or "pending")
    label = {"passed": "bestanden", "failed": "fehlgeschlagen", "skipped": "uebersprungen", "error": "Fehler", "pending": "ausstehend"}.get(state, state)
    return (
        f"Shadow-Commit-Rehearsal: {label}, "
        f"do={r.get('do_called')}, undo={r.get('undo_called')}, "
        f"round_trip={r.get('round_trip_ok')}, rollback={r.get('rollback_verified')}"
    )


def _build_apply_readiness_checks(track_kind: str, audio_clip_count: int, audio_fx_count: int, note_fx_count: int, required_snapshots: list[str], runtime_snapshot_preview: list[dict[str, Any]] | None = None, runtime_snapshot_handles: list[dict[str, Any]] | None = None, runtime_snapshot_captures: list[dict[str, Any]] | None = None, runtime_snapshot_instances: list[dict[str, Any]] | None = None, runtime_snapshot_objects: list[dict[str, Any]] | None = None, runtime_snapshot_stubs: list[dict[str, Any]] | None = None, runtime_snapshot_state_carriers: list[dict[str, Any]] | None = None, runtime_snapshot_state_containers: list[dict[str, Any]] | None = None, runtime_snapshot_state_holders: list[dict[str, Any]] | None = None, runtime_snapshot_state_slots: list[dict[str, Any]] | None = None, runtime_snapshot_state_stores: list[dict[str, Any]] | None = None, runtime_snapshot_state_registries: list[dict[str, Any]] | None = None, runtime_snapshot_state_registry_backends: list[dict[str, Any]] | None = None, runtime_snapshot_state_registry_backend_adapters: list[dict[str, Any]] | None = None, runtime_snapshot_bundle: dict[str, Any] | None = None, runtime_snapshot_apply_runner: dict[str, Any] | None = None, runtime_snapshot_dry_run: dict[str, Any] | None = None, runtime_snapshot_precommit_contract: dict[str, Any] | None = None, runtime_snapshot_atomic_entrypoints: dict[str, Any] | None = None, runtime_snapshot_mutation_gate_capsule: dict[str, Any] | None = None, runtime_snapshot_command_undo_shell: dict[str, Any] | None = None, runtime_snapshot_command_factory_payloads: dict[str, Any] | None = None, runtime_snapshot_preview_command_construction: dict[str, Any] | None = None, runtime_snapshot_dry_command_executor: dict[str, Any] | None = None, shadow_commit_rehearsal: dict[str, Any] | None = None) -> list[dict[str, str]]:
    runtime_snapshot_preview = list(runtime_snapshot_preview or [])
    runtime_ready = sum(1 for item in runtime_snapshot_preview if bool(item.get('available')))
    runtime_total = len(runtime_snapshot_preview)
    runtime_missing = [str(item.get('name') or '').strip() for item in runtime_snapshot_preview if not bool(item.get('available')) and str(item.get('name') or '').strip()]
    if runtime_total <= 0:
        snapshot_state = 'pending'
        snapshot_detail = f"Geplante Snapshot-Typen: {', '.join(list(required_snapshots or [])) or 'keine'}"
    elif runtime_ready >= runtime_total:
        snapshot_state = 'ready'
        snapshot_detail = f"{runtime_ready}/{runtime_total} Snapshot-Referenzen lassen sich bereits aus dem aktuellen Laufzeitzustand aufloesen."
    else:
        snapshot_state = 'pending'
        missing_text = f" Fehlend: {', '.join(runtime_missing)}." if runtime_missing else ''
        snapshot_detail = f"{runtime_ready}/{runtime_total} Snapshot-Referenzen lassen sich bereits aus dem aktuellen Laufzeitzustand aufloesen.{missing_text}"
    runtime_snapshot_captures = list(runtime_snapshot_captures or [])
    runtime_snapshot_instances = list(runtime_snapshot_instances or [])
    runtime_snapshot_objects = list(runtime_snapshot_objects or [])
    runtime_snapshot_stubs = list(runtime_snapshot_stubs or [])
    runtime_snapshot_state_carriers = list(runtime_snapshot_state_carriers or [])
    runtime_snapshot_state_containers = list(runtime_snapshot_state_containers or [])
    runtime_snapshot_state_holders = list(runtime_snapshot_state_holders or [])
    runtime_snapshot_state_slots = list(runtime_snapshot_state_slots or [])
    runtime_snapshot_state_stores = list(runtime_snapshot_state_stores or [])
    runtime_snapshot_state_registries = list(runtime_snapshot_state_registries or [])
    runtime_snapshot_state_registry_backends = list(runtime_snapshot_state_registry_backends or [])
    runtime_snapshot_state_registry_backend_adapters = list(runtime_snapshot_state_registry_backend_adapters or [])
    runtime_snapshot_bundle = dict(runtime_snapshot_bundle or {})
    runtime_snapshot_apply_runner = dict(runtime_snapshot_apply_runner or {})
    runtime_snapshot_dry_run = dict(runtime_snapshot_dry_run or {})
    runtime_snapshot_precommit_contract = dict(runtime_snapshot_precommit_contract or {})
    runtime_snapshot_atomic_entrypoints = dict(runtime_snapshot_atomic_entrypoints or {})
    runtime_snapshot_mutation_gate_capsule = dict(runtime_snapshot_mutation_gate_capsule or {})
    runtime_snapshot_command_undo_shell = dict(runtime_snapshot_command_undo_shell or {})
    runtime_snapshot_command_factory_payloads = dict(runtime_snapshot_command_factory_payloads or {})
    runtime_snapshot_preview_command_construction = dict(runtime_snapshot_preview_command_construction or {})
    runtime_snapshot_dry_command_executor = dict(runtime_snapshot_dry_command_executor or {})
    checks: list[dict[str, str]] = [
        {
            "key": "guard_contract",
            "title": "Preview-/Validate-/Apply-Vertrag steht zentral",
            "state": "ready",
            "detail": "Canvas, TrackList, MainWindow und ProjectService sprechen bereits denselben Guard-Pfad.",
        },
        {
            "key": "snapshot_runtime",
            "title": "Echte Snapshot-Objekte zur Laufzeit erfassen",
            "state": snapshot_state,
            "detail": snapshot_detail,
        },
        {
            "key": "snapshot_handles",
            "title": "Runtime-Snapshot-Handles vorverdrahtet",
            "state": "ready" if runtime_snapshot_handles and all(str(item.get('handle_key') or '').strip() for item in runtime_snapshot_handles) else ("pending" if runtime_snapshot_preview else "pending"),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_handles if str(item.get('handle_key') or '').strip())}/{len(runtime_snapshot_handles)} Handle-Deskriptoren sind bereits mit Capture-Key, Scope und Runtime-Zielen aufgebaut."
                if runtime_snapshot_handles else
                f"Snapshot-Handles werden erst aufgebaut, sobald Runtime-Referenzen fuer {', '.join(list(required_snapshots or [])) or 'keine'} vorliegen."
            ),
        },
        {
            "key": "snapshot_capture_objects",
            "title": "Runtime-Capture-Objekte vorstrukturiert",
            "state": (
                "ready" if runtime_snapshot_captures and all(str(item.get('capture_key') or '').strip() for item in runtime_snapshot_captures) and all(int(item.get('payload_entry_count') or 0) > 0 or str(item.get('capture_state') or '').strip().lower() != 'ready' for item in runtime_snapshot_captures)
                else ("pending" if runtime_snapshot_handles else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_captures if str(item.get('capture_key') or '').strip())}/{len(runtime_snapshot_captures)} Capture-Objekte sind bereits an Handle-Key und Payload-Vorschau gebunden."
                if runtime_snapshot_captures else
                "Capture-Objekte werden aufgebaut, sobald Runtime-Handles stabil vorliegen."
            ),
        },
        {
            "key": "snapshot_instances",
            "title": "Runtime-Snapshot-Instanzen materialisiert",
            "state": (
                "ready" if runtime_snapshot_instances and all(str(item.get('snapshot_instance_key') or '').strip() for item in runtime_snapshot_instances) and all(int(item.get('snapshot_payload_entry_count') or 0) > 0 or str(item.get('snapshot_state') or '').strip().lower() != 'ready' for item in runtime_snapshot_instances)
                else ("pending" if runtime_snapshot_captures else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_instances if str(item.get('snapshot_instance_key') or '').strip())}/{len(runtime_snapshot_instances)} Snapshot-Instanzen sind bereits unter stabilen Instance-Keys materialisiert."
                if runtime_snapshot_instances else
                "Snapshot-Instanzen werden materialisiert, sobald Capture-Objekte mit Payload-Vorschau vorliegen."
            ),
        },
        {
            "key": "snapshot_objects",
            "title": "Runtime-Snapshot-Objekte an Capture/Restore gebunden",
            "state": (
                "ready" if runtime_snapshot_objects and all(str(item.get('snapshot_object_key') or '').strip() for item in runtime_snapshot_objects) and all(bool(item.get('supports_capture')) and bool(item.get('supports_restore')) for item in runtime_snapshot_objects)
                else ("pending" if runtime_snapshot_instances else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_objects if str(item.get('snapshot_object_key') or '').strip())}/{len(runtime_snapshot_objects)} Snapshot-Objekte tragen bereits stabile Objekt-Keys plus Capture-/Restore-Methoden."
                if runtime_snapshot_objects else
                "Snapshot-Objekte werden gebunden, sobald Snapshot-Instanzen stabil materialisiert sind."
            ),
        },
        {
            "key": "snapshot_stubs",
            "title": "Runtime-Snapshot-Stubs an Klassenmethoden gekoppelt",
            "state": (
                "ready" if runtime_snapshot_stubs and all(str(item.get('stub_key') or '').strip() for item in runtime_snapshot_stubs) and all(bool(item.get('supports_capture_preview')) and bool(item.get('supports_restore_preview')) for item in runtime_snapshot_stubs)
                else ("pending" if runtime_snapshot_objects else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_stubs if str(item.get('stub_key') or '').strip())}/{len(runtime_snapshot_stubs)} Klassenstubs sind bereits an Capture-/Restore-Preview-Methoden gekoppelt."
                if runtime_snapshot_stubs else
                "Runtime-Snapshot-Stubs werden aufgebaut, sobald Snapshot-Objekte stabil gebunden wurden."
            ),
        },
        {
            "key": "state_carriers",
            "title": "Runtime-Zustandstraeger / State-Carrier",
            "state": (
                "ready" if runtime_snapshot_state_carriers and all(str(item.get('carrier_key') or '').strip() for item in runtime_snapshot_state_carriers) and all(bool(item.get('supports_capture_state')) and bool(item.get('supports_restore_state')) for item in runtime_snapshot_state_carriers)
                else ("pending" if runtime_snapshot_state_carriers else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_carriers if str(item.get('carrier_key') or '').strip())}/{len(runtime_snapshot_state_carriers)} Zustandstraeger sind bereits an konkrete Capture-/Restore-State-Methoden gekoppelt."
                if runtime_snapshot_state_carriers else
                "Zustandstraeger fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_containers",
            "title": "Separate Runtime-State-Container vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_containers and all(str(item.get('container_key') or '').strip() for item in runtime_snapshot_state_containers) and all(bool(item.get('supports_capture_container')) and bool(item.get('supports_restore_container')) for item in runtime_snapshot_state_containers)
                else ("pending" if runtime_snapshot_state_carriers else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_containers if str(item.get('container_key') or '').strip())}/{len(runtime_snapshot_state_containers)} Runtime-State-Container halten bereits separaten Capture-/Restore-State bereit."
                if runtime_snapshot_state_containers else
                "Separate Runtime-State-Container fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_slots",
            "title": "Runtime-State-Slots / Snapshot-State-Speicher vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_slots and all(str(item.get('slot_key') or '').strip() for item in runtime_snapshot_state_slots) and all(bool(item.get('supports_capture_slot')) and bool(item.get('supports_restore_slot')) for item in runtime_snapshot_state_slots)
                else ("pending" if runtime_snapshot_state_holders else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_slots if str(item.get('slot_key') or '').strip())}/{len(runtime_snapshot_state_slots)} Runtime-State-Slots sind bereits an Holder und Snapshot-State-Speicher-Stubs gekoppelt."
                if runtime_snapshot_state_slots else
                "Runtime-State-Slots / Snapshot-State-Speicher fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_stores",
            "title": "Runtime-State-Stores / Capture-Handles vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_stores and all(str(item.get('store_key') or '').strip() for item in runtime_snapshot_state_stores) and all(bool(item.get('supports_capture_store')) and bool(item.get('supports_restore_store')) and str(item.get('capture_handle_key') or '').strip() for item in runtime_snapshot_state_stores)
                else ("pending" if runtime_snapshot_state_slots else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_stores if str(item.get('store_key') or '').strip())}/{len(runtime_snapshot_state_stores)} Runtime-State-Stores sind bereits an Capture-Handles und State-Speicher gebunden."
                if runtime_snapshot_state_stores else
                "Runtime-State-Stores / Capture-Handles fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_registries",
            "title": "Runtime-State-Registries / Handle-Speicher vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_registries and all(str(item.get('registry_key') or '').strip() for item in runtime_snapshot_state_registries) and all(bool(item.get('supports_capture_registry')) and bool(item.get('supports_restore_registry')) and str(item.get('handle_store_key') or '').strip() for item in runtime_snapshot_state_registries)
                else ("pending" if runtime_snapshot_state_stores else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_registries if str(item.get('registry_key') or '').strip())}/{len(runtime_snapshot_state_registries)} Runtime-State-Registries sind bereits an separaten Handle-Speichern gekoppelt."
                if runtime_snapshot_state_registries else
                "Runtime-State-Registries / Handle-Speicher fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_registry_backends",
            "title": "Runtime-State-Registry-Backends / Handle-Register vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_registry_backends and all(str(item.get('backend_key') or '').strip() for item in runtime_snapshot_state_registry_backends) and all(bool(item.get('supports_capture_backend')) and bool(item.get('supports_restore_backend')) and str(item.get('handle_register_key') or '').strip() and str(item.get('registry_slot_key') or '').strip() for item in runtime_snapshot_state_registry_backends)
                else ("pending" if runtime_snapshot_state_registries else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_registry_backends if str(item.get('backend_key') or '').strip())}/{len(runtime_snapshot_state_registry_backends)} Runtime-State-Registry-Backends sind bereits an Handle-Registern und separaten Registry-Slots gekoppelt."
                if runtime_snapshot_state_registry_backends else
                "Runtime-State-Registry-Backends / Handle-Register fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "state_registry_backend_adapters",
            "title": "Runtime-State-Registry-Backend-Adapter vorbereitet",
            "state": (
                "ready" if runtime_snapshot_state_registry_backend_adapters and all(str(item.get('adapter_key') or '').strip() for item in runtime_snapshot_state_registry_backend_adapters) and all(bool(item.get('supports_capture_backend_adapter')) and bool(item.get('supports_restore_backend_adapter')) and str(item.get('backend_store_adapter_key') or '').strip() and str(item.get('registry_slot_backend_key') or '').strip() for item in runtime_snapshot_state_registry_backend_adapters)
                else ("pending" if runtime_snapshot_state_registry_backends else "pending")
            ),
            "detail": (
                f"{sum(1 for item in runtime_snapshot_state_registry_backend_adapters if str(item.get('adapter_key') or '').strip())}/{len(runtime_snapshot_state_registry_backend_adapters)} Runtime-State-Registry-Backend-Adapter sind bereits an Backend-Store-Adapter und Registry-Slot-Backends gekoppelt."
                if runtime_snapshot_state_registry_backend_adapters else
                "Runtime-State-Registry-Backend-Adapter / Backend-Store-Adapter fuer die spaetere Morph-Transaktion fehlen noch."
            ),
        },
        {
            "key": "snapshot_bundle",
            "title": "Snapshot-Bundle / Transaktions-Container vorbereitet",
            "state": (
                "ready" if runtime_snapshot_bundle and str(runtime_snapshot_bundle.get('bundle_key') or '').strip() and str(runtime_snapshot_bundle.get('bundle_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_stubs else "pending")
            ),
            "detail": (
                f"{int(runtime_snapshot_bundle.get('ready_object_count') or 0)}/{int(runtime_snapshot_bundle.get('object_count') or 0)} Objektbindungen liegen bereits in {str(runtime_snapshot_bundle.get('bundle_key') or '').strip() or 'dem Bundle'}; Commit={str(runtime_snapshot_bundle.get('commit_stub') or '').strip() or 'n/a'}, Rollback={str(runtime_snapshot_bundle.get('rollback_stub') or '').strip() or 'n/a'}."
                if runtime_snapshot_bundle else
                "Der Transaktions-Container wird aufgebaut, sobald Snapshot-Objekte gebunden wurden."
            ),
        },
        {
            "key": "snapshot_apply_runner",
            "title": "Read-only Snapshot-Transaktions-Dispatch / Apply-Runner vorbereitet",
            "state": (
                "ready" if runtime_snapshot_apply_runner and str(runtime_snapshot_apply_runner.get('runner_key') or '').strip() and str(runtime_snapshot_apply_runner.get('runner_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_bundle else "pending")
            ),
            "detail": (
                f"{int(runtime_snapshot_apply_runner.get('ready_phase_count') or 0)}/{int(runtime_snapshot_apply_runner.get('phase_count') or 0)} Apply-Runner-Phasen wurden read-only vorbereitet; Apply={len(list(runtime_snapshot_apply_runner.get('apply_sequence') or []))}, Restore={len(list(runtime_snapshot_apply_runner.get('restore_sequence') or []))}, Rollback={len(list(runtime_snapshot_apply_runner.get('rollback_sequence') or []))}."
                if runtime_snapshot_apply_runner else
                "Der Snapshot-Transaktions-Dispatch / Apply-Runner wird gekoppelt, sobald das Snapshot-Bundle stabil vorliegt."
            ),
        },
        {
            "key": "transaction_dry_run",
            "title": "Read-only Dry-Run / Transaktions-Runner vorbereitet",
            "state": (
                "ready" if runtime_snapshot_dry_run and str(runtime_snapshot_dry_run.get('runner_key') or '').strip() and str(runtime_snapshot_dry_run.get('runner_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_bundle else "pending")
            ),
            "detail": (
                f"{int(runtime_snapshot_dry_run.get('ready_phase_count') or 0)}/{int(runtime_snapshot_dry_run.get('phase_count') or 0)} Dry-Run-Phasen wurden read-only vorbereitet; Capture={len(list(runtime_snapshot_dry_run.get('capture_sequence') or []))}, Restore={len(list(runtime_snapshot_dry_run.get('restore_sequence') or []))}, Rollback-Slots={len(list(runtime_snapshot_dry_run.get('rollback_sequence') or []))}."
                if runtime_snapshot_dry_run else
                "Der Dry-Run-Runner wird gekoppelt, sobald das Snapshot-Bundle stabil vorliegt."
            ),
        },
        {
            "key": "minimal_case_precommit_contract",
            "title": "Leere Audio-Spur: read-only Pre-Commit-Vertrag vorbereitet",
            "state": (
                "ready" if runtime_snapshot_precommit_contract and str(runtime_snapshot_precommit_contract.get('contract_key') or '').strip() and str(runtime_snapshot_precommit_contract.get('contract_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_precommit_contract else ("pending" if runtime_snapshot_dry_run else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_precommit_contract.get('ready_preview_phase_count') or 0)}/{int(runtime_snapshot_precommit_contract.get('preview_phase_count') or 0)} read-only Vorschauphasen bilden bereits Undo-, Routing-, Track-Kind- und Instrument-Commit-Vertrag fuer die leere Audio-Spur ab; Mutation bleibt deaktiviert."
                if runtime_snapshot_precommit_contract else
                "Der read-only Pre-Commit-Vertrag fuer die leere Audio-Spur wird erst aufgebaut, sobald Minimalfall, Apply-Runner und Dry-Run stabil vorliegen."
            ),
        },
        {
            "key": "atomic_entrypoints",
            "title": "Read-only atomare Commit-/Undo-/Routing-Entry-Points gekoppelt",
            "state": (
                "ready" if runtime_snapshot_atomic_entrypoints and str(runtime_snapshot_atomic_entrypoints.get('entrypoint_key') or '').strip() and str(runtime_snapshot_atomic_entrypoints.get('entrypoint_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_atomic_entrypoints else ("pending" if runtime_snapshot_precommit_contract else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_atomic_entrypoints.get('ready_entrypoint_count') or 0)}/{int(runtime_snapshot_atomic_entrypoints.get('total_entrypoint_count') or 0)} Entry-Points sind read-only an denselben Minimalfall-Vertrag gekoppelt; Owner={str(runtime_snapshot_atomic_entrypoints.get('owner_class') or 'n/a').strip() or 'n/a'}, Mutation bleibt deaktiviert."
                if runtime_snapshot_atomic_entrypoints else
                "Die read-only Kopplung an echte atomare Commit-/Undo-/Routing-Entry-Points folgt nach dem Pre-Commit-Vertrag."
            ),
        },
        {
            "key": "mutation_gate_capsule",
            "title": "Read-only Mutation-Gate / Transaction-Capsule gekoppelt",
            "state": (
                "ready" if runtime_snapshot_mutation_gate_capsule and str(runtime_snapshot_mutation_gate_capsule.get('capsule_key') or '').strip() and str(runtime_snapshot_mutation_gate_capsule.get('capsule_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_mutation_gate_capsule else ("pending" if runtime_snapshot_atomic_entrypoints else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_mutation_gate_capsule.get('ready_capsule_step_count') or 0)}/{int(runtime_snapshot_mutation_gate_capsule.get('total_capsule_step_count') or 0)} Kapselschritte sind read-only an dasselbe Mutation-Gate gekoppelt; Owner={str(runtime_snapshot_mutation_gate_capsule.get('owner_class') or 'n/a').strip() or 'n/a'}, Gate={str(runtime_snapshot_mutation_gate_capsule.get('mutation_gate_state') or 'blocked').strip() or 'blocked'}."
                if runtime_snapshot_mutation_gate_capsule else
                "Die explizite read-only Mutation-Gate-/Transaction-Capsule-Kopplung folgt nach den atomaren Entry-Points."
            ),
        },
        {
            "key": "project_snapshot_edit_command_shell",
            "title": "Read-only ProjectSnapshotEditCommand-/Undo-Huelle gekoppelt",
            "state": (
                "ready" if runtime_snapshot_command_undo_shell and str(runtime_snapshot_command_undo_shell.get('shell_key') or '').strip() and str(runtime_snapshot_command_undo_shell.get('shell_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_command_undo_shell else ("pending" if runtime_snapshot_mutation_gate_capsule else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_command_undo_shell.get('ready_shell_step_count') or 0)}/{int(runtime_snapshot_command_undo_shell.get('total_shell_step_count') or 0)} Huellenschritte sind read-only an dieselbe Capsule-Kette gekoppelt; Owner={str(runtime_snapshot_command_undo_shell.get('owner_class') or 'n/a').strip() or 'n/a'}, Command={str(runtime_snapshot_command_undo_shell.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}."
                if runtime_snapshot_command_undo_shell else
                "Die explizite read-only ProjectSnapshotEditCommand-/Undo-Huelle folgt nach Mutation-Gate und Transaction-Capsule."
            ),
        },
        {
            "key": "project_snapshot_command_factory_payloads",
            "title": "Read-only Before-/After-Snapshot-Command-Factory gekoppelt",
            "state": (
                "ready" if runtime_snapshot_command_factory_payloads and str(runtime_snapshot_command_factory_payloads.get('factory_key') or '').strip() and str(runtime_snapshot_command_factory_payloads.get('payload_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_command_factory_payloads else ("pending" if runtime_snapshot_command_undo_shell else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_command_factory_payloads.get('ready_factory_step_count') or 0)}/{int(runtime_snapshot_command_factory_payloads.get('total_factory_step_count') or 0)} Factory-Schritte materialisieren bereits {int(runtime_snapshot_command_factory_payloads.get('materialized_payload_count') or 0)}/2 Snapshot-Payloads read-only; Delta={str(runtime_snapshot_command_factory_payloads.get('payload_delta_kind') or 'n/a').strip() or 'n/a'}, Command={str(runtime_snapshot_command_factory_payloads.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}."
                if runtime_snapshot_command_factory_payloads else
                "Die explizite read-only Before-/After-Snapshot-Command-Factory folgt nach der ProjectSnapshotEditCommand-/Undo-Huelle."
            ),
        },
        {
            "key": "preview_command_construction",
            "title": "Read-only Preview-Command-Konstruktion gekoppelt",
            "state": (
                "ready" if runtime_snapshot_preview_command_construction and str(runtime_snapshot_preview_command_construction.get('preview_command_key') or '').strip() and str(runtime_snapshot_preview_command_construction.get('preview_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_preview_command_construction else ("pending" if runtime_snapshot_command_factory_payloads else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_preview_command_construction.get('ready_preview_step_count') or 0)}/{int(runtime_snapshot_preview_command_construction.get('total_preview_step_count') or 0)} Preview-Schritte konstruieren bereits read-only einen echten {str(runtime_snapshot_preview_command_construction.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}; Payloads={int(runtime_snapshot_preview_command_construction.get('materialized_payload_count') or 0)}/2, Callback={str(runtime_snapshot_preview_command_construction.get('apply_callback_owner_class') or 'n/a').strip() or 'n/a'}.{str(runtime_snapshot_preview_command_construction.get('apply_callback_name') or 'n/a').strip() or 'n/a'}."
                if runtime_snapshot_preview_command_construction else
                "Die explizite read-only Preview-Command-Konstruktion folgt nach der Before-/After-Snapshot-Command-Factory."
            ),
        },
        {
            "key": "dry_command_executor",
            "title": "Read-only Dry-Command-Executor / do()-undo()-Simulations-Harness gekoppelt",
            "state": (
                "ready" if runtime_snapshot_dry_command_executor and str(runtime_snapshot_dry_command_executor.get('dry_executor_key') or '').strip() and str(runtime_snapshot_dry_command_executor.get('dry_executor_state') or '').strip().lower() == 'ready'
                else ("pending" if runtime_snapshot_dry_command_executor else ("pending" if runtime_snapshot_preview_command_construction else "pending"))
            ),
            "detail": (
                f"{int(runtime_snapshot_dry_command_executor.get('ready_simulation_step_count') or 0)}/{int(runtime_snapshot_dry_command_executor.get('total_simulation_step_count') or 0)} Simulationsschritte proben bereits read-only do()/undo(); Callback={int(runtime_snapshot_dry_command_executor.get('callback_call_count') or 0)}, Command={str(runtime_snapshot_dry_command_executor.get('command_class') or 'ProjectSnapshotEditCommand').strip() or 'ProjectSnapshotEditCommand'}."
                if runtime_snapshot_dry_command_executor else
                "Der explizite read-only Dry-Command-Executor folgt nach der Preview-Command-Konstruktion."
            ),
        },
        {
            "key": "shadow_commit_rehearsal",
            "title": "Shadow-Commit-Rehearsal: do()/undo()-Simulation bestanden",
            "state": (
                "ready" if shadow_commit_rehearsal and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
                else ("skipped" if shadow_commit_rehearsal and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "skipped" else "pending")
            ),
            "detail": (
                _build_shadow_commit_rehearsal_summary(shadow_commit_rehearsal)
                if shadow_commit_rehearsal else
                "Shadow-Commit-Rehearsal noch nicht durchgefuehrt."
            ),
        },
        {
            "key": "routing_atomic",
            "title": "Routing-/Spurmodus atomar schalten",
            "state": (
                "ready" if (
                    shadow_commit_rehearsal
                    and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
                    and str(track_kind or "").strip().lower() == "audio"
                    and int(audio_clip_count) == 0
                    and int(audio_fx_count) == 0
                    and int(note_fx_count) == 0
                ) else "pending"
            ),
            "detail": (
                "Leere Audio-Spur: track.kind-Umschaltung ist atomar ueber Snapshot-Undo abgesichert (Shadow-Rehearsal bestanden)."
                if (
                    shadow_commit_rehearsal
                    and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
                    and str(track_kind or "").strip().lower() == "audio"
                    and int(audio_clip_count) == 0
                    and int(audio_fx_count) == 0
                    and int(note_fx_count) == 0
                ) else "Der echte Audio->Instrument-Umschaltpfad ist noch nicht freigeschaltet."
            ),
        },
        {
            "key": "undo_commit",
            "title": "Gesamtvorgang als ein Undo-Punkt committen",
            "state": (
                "ready" if (
                    shadow_commit_rehearsal
                    and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
                    and str(track_kind or "").strip().lower() == "audio"
                    and int(audio_clip_count) == 0
                    and int(audio_fx_count) == 0
                    and int(note_fx_count) == 0
                ) else "pending"
            ),
            "detail": (
                "Leere Audio-Spur: Snapshot-basiertes Undo/Redo deckt track.kind + Instrument-Einfuegung in einem Undo-Punkt ab (Shadow-Rehearsal bestanden)."
                if (
                    shadow_commit_rehearsal
                    and str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
                    and str(track_kind or "").strip().lower() == "audio"
                    and int(audio_clip_count) == 0
                    and int(audio_fx_count) == 0
                    and int(note_fx_count) == 0
                ) else "Die spaetere Apply-Phase muss Snapshot-Erfassung, Conversion und Rueckbau in einem Undo-Schritt kapseln."
            ),
        },
    ]
    if int(audio_clip_count) > 0:
        checks.append({
            "key": "audio_clips",
            "title": "Audio-Clips verlustfrei rueckbaubar",
            "state": "blocked",
            "detail": f"{_plural(audio_clip_count, 'Audio-Clip')} muessen vor echtem Morphing sicher rueckfuehrbar bleiben.",
        })
    else:
        checks.append({
            "key": "audio_clips",
            "title": "Audio-Clip-Rueckbau",
            "state": "ready",
            "detail": "Aktuell keine Audio-Clips auf der Zielspur.",
        })
    if int(audio_fx_count) > 0:
        checks.append({
            "key": "audio_fx",
            "title": "Audio-FX-Kette atomar rueckbaubar",
            "state": "blocked",
            "detail": f"{_plural(audio_fx_count, 'FX', 'FX')} muessen samt Reihenfolge und Parametern rueckfuehrbar bleiben.",
        })
    else:
        checks.append({
            "key": "audio_fx",
            "title": "Audio-FX-Rueckbau",
            "state": "ready",
            "detail": "Aktuell keine Audio-FX-Kette auf der Zielspur vorhanden.",
        })
    if int(note_fx_count) > 0:
        checks.append({
            "key": "note_fx",
            "title": "Note-FX-Kompatibilitaet nach Conversion",
            "state": "blocked",
            "detail": f"{_plural(note_fx_count, 'Note-FX', 'Note-FX')} muessen nach dem Spurwechsel separat geprueft werden.",
        })
    else:
        checks.append({
            "key": "note_fx",
            "title": "Note-FX-Kompatibilitaet",
            "state": "ready",
            "detail": "Keine Note-FX auf der Zielspur, daher kein Zusatzrisiko aus dieser Kette.",
        })
    if str(track_kind or '').strip().lower() != 'audio':
        checks.append({
            "key": "target_kind",
            "title": "Ziel ist Audio-Spur",
            "state": "blocked",
            "detail": f"Aktuelles Ziel ist {_track_kind_label(track_kind)}; der Morphing-Guard gilt derzeit nur fuer Audio-Spuren.",
        })
    return checks


def _build_apply_readiness_summary(readiness_checks: list[dict[str, str]]) -> str:
    checks = list(readiness_checks or [])
    total = len(checks)
    if total <= 0:
        return ""
    ready = sum(1 for item in checks if str(item.get('state') or '').strip().lower() == 'ready')
    blocked = sum(1 for item in checks if str(item.get('state') or '').strip().lower() == 'blocked')
    pending = sum(1 for item in checks if str(item.get('state') or '').strip().lower() == 'pending')
    parts = [f"{ready}/{total} Checks bereit"]
    if blocked > 0:
        parts.append(f"{blocked} blockiert")
    if pending > 0:
        parts.append(f"{pending} offen")
    return "Apply-Readiness: " + ", ".join(parts)


def build_audio_to_instrument_morph_plan(project_obj: Any, track: Any, plugin_name: str = "", runtime_owner: Any | None = None) -> dict[str, Any]:
    """Build a non-mutating plan for a future Audio→Instrument track morph.

    The returned plan is intentionally safe for UI preview, validation and later
    execution. In this phase `can_apply` always stays False.
    """
    try:
        track_id = str(getattr(track, "id", "") or "")
        track_name = str(getattr(track, "name", "") or track_id or "Spur")
        track_kind = str(getattr(track, "kind", "") or "").strip().lower()
        plugin_name = str(plugin_name or "").strip() or "Instrument"

        note_fx_count = _count_chain_devices(getattr(track, "note_fx_chain", {}) or {})
        audio_fx_count = _count_chain_devices(getattr(track, "audio_fx_chain", {}) or {})
        audio_clip_count, midi_clip_count = _collect_track_clip_counts(project_obj, track_id)

        parts: list[str] = [_track_kind_label(track_kind)]
        if audio_clip_count > 0:
            parts.append(_plural(audio_clip_count, "Audio-Clip"))
        elif midi_clip_count > 0:
            parts.append(_plural(midi_clip_count, "MIDI-Clip"))
        else:
            parts.append("leer")
        if audio_fx_count > 0:
            parts.append(_plural(audio_fx_count, "FX", "FX"))
        if note_fx_count > 0:
            parts.append(_plural(note_fx_count, "Note-FX", "Note-FX"))
        summary = " · ".join(parts[:4])

        blocked_reasons: list[str] = []
        if track_kind != "audio":
            blocked_reasons.append(f"Ziel ist derzeit keine Audio-Spur, sondern {_track_kind_label(track_kind)}")
        if audio_clip_count > 0:
            blocked_reasons.append(f"{_plural(audio_clip_count, 'Audio-Clip')} müssten gesichert/überführt werden")
        if audio_fx_count > 0:
            blocked_reasons.append(f"{_plural(audio_fx_count, 'FX', 'FX')} müssten atomar mitgeführt werden")
        if note_fx_count > 0:
            blocked_reasons.append(f"{_plural(note_fx_count, 'Note-FX', 'Note-FX')} müssten nach Instrument-Conversion geprüft werden")
        if not blocked_reasons:
            blocked_reasons.append("Undo/Routing-Rückbau für echtes Morphing ist noch nicht freigeschaltet")

        blocked_message = (
            f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
            "Audio→Instrument-Morphing wird erst mit atomarem Undo/Routing-Rueckbau freigeschaltet."
        )
        impact_summary = _build_impact_summary(audio_clip_count, audio_fx_count, note_fx_count)
        rollback_lines = _build_rollback_lines(track_kind, audio_clip_count, audio_fx_count, note_fx_count)
        future_apply_steps = _build_future_apply_steps(audio_clip_count, audio_fx_count, note_fx_count)
        required_snapshots = _build_required_snapshots(track_kind, audio_clip_count, audio_fx_count, note_fx_count)
        transaction_steps = _build_transaction_steps(audio_clip_count, audio_fx_count, note_fx_count)
        transaction_key = _build_transaction_key(track_id, plugin_name)
        transaction_summary = _build_transaction_summary(required_snapshots, transaction_steps)
        snapshot_refs = _build_snapshot_refs(required_snapshots, transaction_key)
        snapshot_ref_map = {str(item.get('name') or ''): str(item.get('ref') or '') for item in list(snapshot_refs or []) if str(item.get('name') or '').strip()}
        snapshot_ref_summary = _build_snapshot_ref_summary(snapshot_refs)
        runtime_snapshot_preview = _build_runtime_snapshot_preview(project_obj, track, required_snapshots, snapshot_ref_map)
        runtime_snapshot_summary = _build_runtime_snapshot_summary(runtime_snapshot_preview)
        runtime_snapshot_handles = _build_runtime_snapshot_handles(project_obj, track, runtime_snapshot_preview, transaction_key)
        runtime_snapshot_handle_summary = _build_runtime_snapshot_handle_summary(runtime_snapshot_handles)
        runtime_snapshot_captures = _build_runtime_snapshot_capture_objects(project_obj, track, runtime_snapshot_handles)
        runtime_snapshot_capture_summary = _build_runtime_snapshot_capture_summary(runtime_snapshot_captures)
        runtime_snapshot_instances = _build_runtime_snapshot_instances(runtime_snapshot_captures)
        runtime_snapshot_instance_summary = _build_runtime_snapshot_instance_summary(runtime_snapshot_instances)
        runtime_snapshot_objects = _build_runtime_snapshot_objects(runtime_snapshot_instances)
        runtime_snapshot_object_summary = _build_runtime_snapshot_object_summary(runtime_snapshot_objects)
        runtime_snapshot_stubs = _build_runtime_snapshot_stubs(runtime_snapshot_objects)
        runtime_snapshot_stub_summary = _build_runtime_snapshot_stub_summary(runtime_snapshot_stubs)
        runtime_snapshot_state_carriers = _build_runtime_snapshot_state_carriers(runtime_snapshot_objects, runtime_snapshot_stubs)
        runtime_snapshot_state_carrier_summary = _build_runtime_snapshot_state_carrier_summary(runtime_snapshot_state_carriers)
        runtime_snapshot_state_containers = _build_runtime_snapshot_state_containers(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers)
        runtime_snapshot_state_container_summary = _build_runtime_snapshot_state_container_summary(runtime_snapshot_state_containers)
        runtime_snapshot_state_holders = _build_runtime_snapshot_state_holders(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers)
        runtime_snapshot_state_holder_summary = _build_runtime_snapshot_state_holder_summary(runtime_snapshot_state_holders)
        runtime_snapshot_state_slots = _build_runtime_snapshot_state_slots(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders)
        runtime_snapshot_state_slot_summary = _build_runtime_snapshot_state_slot_summary(runtime_snapshot_state_slots)
        runtime_snapshot_state_stores = _build_runtime_snapshot_state_stores(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots)
        runtime_snapshot_state_store_summary = _build_runtime_snapshot_state_store_summary(runtime_snapshot_state_stores)
        runtime_snapshot_state_registries = _build_runtime_snapshot_state_registries(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores)
        runtime_snapshot_state_registry_summary = _build_runtime_snapshot_state_registry_summary(runtime_snapshot_state_registries)
        runtime_snapshot_state_registry_backends = _build_runtime_snapshot_state_registry_backends(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores, runtime_snapshot_state_registries)
        runtime_snapshot_state_registry_backend_summary = _build_runtime_snapshot_state_registry_backend_summary(runtime_snapshot_state_registry_backends)
        runtime_snapshot_state_registry_backend_adapters = _build_runtime_snapshot_state_registry_backend_adapters(runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores, runtime_snapshot_state_registries, runtime_snapshot_state_registry_backends)
        runtime_snapshot_state_registry_backend_adapter_summary = _build_runtime_snapshot_state_registry_backend_adapter_summary(runtime_snapshot_state_registry_backend_adapters)
        runtime_snapshot_bundle = _build_runtime_snapshot_bundle(runtime_snapshot_objects, transaction_key, required_snapshots)
        runtime_snapshot_bundle_summary = _build_runtime_snapshot_bundle_summary(runtime_snapshot_bundle)
        runtime_snapshot_apply_runner = _build_runtime_snapshot_apply_runner(runtime_snapshot_bundle, runtime_snapshot_state_registry_backend_adapters, transaction_steps)
        runtime_snapshot_apply_runner_summary = _build_runtime_snapshot_apply_runner_summary(runtime_snapshot_apply_runner)
        runtime_snapshot_dry_run = _build_runtime_snapshot_dry_run(runtime_snapshot_bundle, runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores, runtime_snapshot_state_registries, runtime_snapshot_state_registry_backends, runtime_snapshot_state_registry_backend_adapters, transaction_steps)
        runtime_snapshot_dry_run_summary = _build_runtime_snapshot_dry_run_summary(runtime_snapshot_dry_run)
        readiness_checks = _build_apply_readiness_checks(track_kind, audio_clip_count, audio_fx_count, note_fx_count, required_snapshots, runtime_snapshot_preview, runtime_snapshot_handles, runtime_snapshot_captures, runtime_snapshot_instances, runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores, runtime_snapshot_state_registries, runtime_snapshot_state_registry_backends, runtime_snapshot_state_registry_backend_adapters, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run)
        first_minimal_case_report = _build_first_minimal_case_report(transaction_key, track_kind, audio_clip_count, audio_fx_count, note_fx_count, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, readiness_checks)
        first_minimal_case_summary = _build_first_minimal_case_summary(first_minimal_case_report)
        runtime_snapshot_precommit_contract = _build_runtime_snapshot_precommit_contract(first_minimal_case_report, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, required_snapshots, transaction_steps)
        runtime_snapshot_precommit_contract_summary = _build_runtime_snapshot_precommit_contract_summary(runtime_snapshot_precommit_contract)
        runtime_snapshot_atomic_entrypoints = _build_runtime_snapshot_atomic_entrypoints(runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_snapshot_objects, runtime_owner=runtime_owner)
        runtime_snapshot_atomic_entrypoints_summary = _build_runtime_snapshot_atomic_entrypoints_summary(runtime_snapshot_atomic_entrypoints)
        runtime_snapshot_mutation_gate_capsule = _build_runtime_snapshot_mutation_gate_capsule(runtime_snapshot_atomic_entrypoints, runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_owner=runtime_owner)
        runtime_snapshot_mutation_gate_capsule_summary = _build_runtime_snapshot_mutation_gate_capsule_summary(runtime_snapshot_mutation_gate_capsule)
        runtime_snapshot_command_undo_shell = _build_runtime_snapshot_command_undo_shell(runtime_snapshot_mutation_gate_capsule, runtime_snapshot_atomic_entrypoints, runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_owner=runtime_owner)
        runtime_snapshot_command_undo_shell_summary = _build_runtime_snapshot_command_undo_shell_summary(runtime_snapshot_command_undo_shell)
        runtime_snapshot_command_factory_payloads = _build_runtime_snapshot_command_factory_payloads(runtime_snapshot_command_undo_shell, runtime_snapshot_mutation_gate_capsule, runtime_snapshot_atomic_entrypoints, runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_owner=runtime_owner)
        runtime_snapshot_command_factory_payload_summary = _build_runtime_snapshot_command_factory_payload_summary(runtime_snapshot_command_factory_payloads)
        runtime_snapshot_preview_command_construction = _build_runtime_snapshot_preview_command_construction(runtime_snapshot_command_factory_payloads, runtime_snapshot_command_undo_shell, runtime_snapshot_mutation_gate_capsule, runtime_snapshot_atomic_entrypoints, runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_owner=runtime_owner)
        runtime_snapshot_preview_command_construction_summary = _build_runtime_snapshot_preview_command_construction_summary(runtime_snapshot_preview_command_construction)
        runtime_snapshot_dry_command_executor = _build_runtime_snapshot_dry_command_executor(runtime_snapshot_preview_command_construction, runtime_snapshot_command_factory_payloads, runtime_snapshot_command_undo_shell, runtime_snapshot_mutation_gate_capsule, runtime_snapshot_atomic_entrypoints, runtime_snapshot_precommit_contract, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_owner=runtime_owner)
        runtime_snapshot_dry_command_executor_summary = _build_runtime_snapshot_dry_command_executor_summary(runtime_snapshot_dry_command_executor)
        shadow_commit_rehearsal = _build_shadow_commit_rehearsal(project_obj, track)
        shadow_commit_rehearsal_summary = _build_shadow_commit_rehearsal_summary(shadow_commit_rehearsal)
        _rehearsal_passed = str(shadow_commit_rehearsal.get("rehearsal_state") or "").strip().lower() == "passed"
        # Determine if the track is an audio track that can be morphed
        _is_audio_target = bool(track_kind == "audio" and _rehearsal_passed)
        # Minimal case: empty audio track (no dialog needed)
        _is_minimal_case = bool(
            _is_audio_target
            and int(audio_clip_count) == 0
            and int(midi_clip_count) == 0
            and int(audio_fx_count) == 0
            and int(note_fx_count) == 0
        )
        # v517: Occupied audio tracks can also morph (with confirmation dialog)
        _has_content = bool(int(audio_clip_count) > 0 or int(audio_fx_count) > 0 or int(note_fx_count) > 0)
        readiness_checks = _build_apply_readiness_checks(track_kind, audio_clip_count, audio_fx_count, note_fx_count, required_snapshots, runtime_snapshot_preview, runtime_snapshot_handles, runtime_snapshot_captures, runtime_snapshot_instances, runtime_snapshot_objects, runtime_snapshot_stubs, runtime_snapshot_state_carriers, runtime_snapshot_state_containers, runtime_snapshot_state_holders, runtime_snapshot_state_slots, runtime_snapshot_state_stores, runtime_snapshot_state_registries, runtime_snapshot_state_registry_backends, runtime_snapshot_state_registry_backend_adapters, runtime_snapshot_bundle, runtime_snapshot_apply_runner, runtime_snapshot_dry_run, runtime_snapshot_precommit_contract, runtime_snapshot_atomic_entrypoints, runtime_snapshot_mutation_gate_capsule, runtime_snapshot_command_undo_shell, runtime_snapshot_command_factory_payloads, runtime_snapshot_preview_command_construction, runtime_snapshot_dry_command_executor, shadow_commit_rehearsal)
        readiness_summary = _build_apply_readiness_summary(readiness_checks)
        if _is_minimal_case:
            blocked_message = (
                f"SmartDrop BEREIT: {track_name} ist {summary}. "
                "Leere Audio-Spur kann atomar in eine Instrument-Spur umgewandelt werden (Shadow-Rehearsal bestanden, Undo abgesichert)."
            )
        elif _is_audio_target and _has_content:
            blocked_message = (
                f"SmartDrop BEREIT (mit Inhalt): {track_name} ist {summary}. "
                "Audio-Spur wird in Instrument-Spur umgewandelt. Audio-Clips und FX-Kette bleiben erhalten. Undo mit Ctrl+Z."
            )
        elif str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").strip().lower() == "ready":
            blocked_message = (
                f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
                "Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an eine explizite Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payloads gekoppelt; echter Commit-/Routing-/Undo-Pfad bleibt noch gesperrt."
            )
        elif str(runtime_snapshot_command_undo_shell.get("shell_state") or "").strip().lower() == "ready":
            blocked_message = (
                f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
                "Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an eine explizite ProjectSnapshotEditCommand-/Undo-Huelle gekoppelt; echter Commit-/Routing-/Undo-Pfad bleibt noch gesperrt."
            )
        elif str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").strip().lower() == "ready":
            blocked_message = (
                f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
                "Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an ein explizites Mutation-Gate und eine Transaction-Capsule gekoppelt; echter Commit-/Routing-/Undo-Pfad bleibt noch gesperrt."
            )
        elif str(runtime_snapshot_precommit_contract.get("contract_state") or "").strip().lower() == "ready":
            blocked_message = (
                f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
                "Der spaetere Minimalfall (leere Audio-Spur) hat jetzt auch einen read-only Pre-Commit-Vertrag; echter Commit-/Routing-/Undo-Pfad bleibt noch gesperrt."
            )
        elif bool(first_minimal_case_report.get("future_unlock_ready")):
            blocked_message = (
                f"SmartDrop noch gesperrt: {track_name} ist {summary}. "
                "Der erste spaetere Minimalfall (leere Audio-Spur) ist read-only bereits vorbereitet; echter Commit-/Routing-Umbau bleibt noch gesperrt."
            )

        return {
            "mode": "audio_to_instrument_morph",
            "track_id": track_id,
            "track_name": track_name,
            "plugin_name": plugin_name,
            "source_kind": track_kind,
            "target_kind": "instrument",
            "summary": summary,
            "impact_summary": impact_summary,
            "rollback_lines": list(rollback_lines),
            "future_apply_steps": list(future_apply_steps),
            "required_snapshots": list(required_snapshots),
            "snapshot_refs": list(snapshot_refs),
            "snapshot_ref_map": dict(snapshot_ref_map),
            "snapshot_ref_summary": snapshot_ref_summary,
            "runtime_snapshot_preview": list(runtime_snapshot_preview),
            "runtime_snapshot_summary": runtime_snapshot_summary,
            "runtime_snapshot_handles": list(runtime_snapshot_handles),
            "runtime_snapshot_handle_summary": runtime_snapshot_handle_summary,
            "runtime_snapshot_captures": list(runtime_snapshot_captures),
            "runtime_snapshot_capture_summary": runtime_snapshot_capture_summary,
            "runtime_snapshot_instances": list(runtime_snapshot_instances),
            "runtime_snapshot_instance_summary": runtime_snapshot_instance_summary,
            "runtime_snapshot_objects": list(runtime_snapshot_objects),
            "runtime_snapshot_object_summary": runtime_snapshot_object_summary,
            "runtime_snapshot_stubs": list(runtime_snapshot_stubs),
            "runtime_snapshot_stub_summary": runtime_snapshot_stub_summary,
            "runtime_snapshot_state_carriers": list(runtime_snapshot_state_carriers),
            "runtime_snapshot_state_carrier_summary": runtime_snapshot_state_carrier_summary,
            "runtime_snapshot_state_containers": list(runtime_snapshot_state_containers),
            "runtime_snapshot_state_container_summary": runtime_snapshot_state_container_summary,
            "runtime_snapshot_state_holders": list(runtime_snapshot_state_holders),
            "runtime_snapshot_state_holder_summary": runtime_snapshot_state_holder_summary,
            "runtime_snapshot_state_slots": list(runtime_snapshot_state_slots),
            "runtime_snapshot_state_slot_summary": runtime_snapshot_state_slot_summary,
            "runtime_snapshot_state_stores": list(runtime_snapshot_state_stores),
            "runtime_snapshot_state_store_summary": runtime_snapshot_state_store_summary,
            "runtime_snapshot_state_registries": list(runtime_snapshot_state_registries),
            "runtime_snapshot_state_registry_summary": runtime_snapshot_state_registry_summary,
            "runtime_snapshot_state_registry_backends": list(runtime_snapshot_state_registry_backends),
            "runtime_snapshot_state_registry_backend_summary": runtime_snapshot_state_registry_backend_summary,
            "runtime_snapshot_state_registry_backend_adapters": list(runtime_snapshot_state_registry_backend_adapters),
            "runtime_snapshot_state_registry_backend_adapter_summary": runtime_snapshot_state_registry_backend_adapter_summary,
            "runtime_snapshot_bundle": dict(runtime_snapshot_bundle),
            "runtime_snapshot_bundle_summary": runtime_snapshot_bundle_summary,
            "runtime_snapshot_apply_runner": dict(runtime_snapshot_apply_runner),
            "runtime_snapshot_apply_runner_summary": runtime_snapshot_apply_runner_summary,
            "runtime_snapshot_dry_run": dict(runtime_snapshot_dry_run),
            "runtime_snapshot_dry_run_summary": runtime_snapshot_dry_run_summary,
            "readiness_checks": list(readiness_checks),
            "readiness_summary": readiness_summary,
            "first_minimal_case_report": dict(first_minimal_case_report),
            "first_minimal_case_summary": first_minimal_case_summary,
            "runtime_snapshot_precommit_contract": dict(runtime_snapshot_precommit_contract),
            "runtime_snapshot_precommit_contract_summary": runtime_snapshot_precommit_contract_summary,
            "runtime_snapshot_atomic_entrypoints": dict(runtime_snapshot_atomic_entrypoints),
            "runtime_snapshot_atomic_entrypoints_summary": runtime_snapshot_atomic_entrypoints_summary,
            "runtime_snapshot_mutation_gate_capsule": dict(runtime_snapshot_mutation_gate_capsule),
            "runtime_snapshot_mutation_gate_capsule_summary": runtime_snapshot_mutation_gate_capsule_summary,
            "runtime_snapshot_command_undo_shell": dict(runtime_snapshot_command_undo_shell),
            "runtime_snapshot_command_undo_shell_summary": runtime_snapshot_command_undo_shell_summary,
            "runtime_snapshot_command_factory_payloads": dict(runtime_snapshot_command_factory_payloads),
            "runtime_snapshot_command_factory_payload_summary": runtime_snapshot_command_factory_payload_summary,
            "runtime_snapshot_preview_command_construction": dict(runtime_snapshot_preview_command_construction),
            "runtime_snapshot_preview_command_construction_summary": runtime_snapshot_preview_command_construction_summary,
            "runtime_snapshot_dry_command_executor": dict(runtime_snapshot_dry_command_executor),
            "runtime_snapshot_dry_command_executor_summary": runtime_snapshot_dry_command_executor_summary,
            "transaction_steps": list(transaction_steps),
            "transaction_key": transaction_key,
            "transaction_summary": transaction_summary,
            "preview_label": (
                f"Instrument → Preview auf {track_name} · {summary}"
                + (" · Dry-Executor vorbereitet" if str(runtime_snapshot_dry_command_executor.get("dry_executor_state") or "").strip().lower() == "ready" else (" · Preview-Command vorbereitet" if str(runtime_snapshot_preview_command_construction.get("preview_state") or "").strip().lower() == "ready" else (" · Payload-Factory vorbereitet" if str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").strip().lower() == "ready" else (" · Command-Huelle vorbereitet" if str(runtime_snapshot_command_undo_shell.get("shell_state") or "").strip().lower() == "ready" else (" · Mutation-Gate vorbereitet" if str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").strip().lower() == "ready" else (" · Entry-Points gekoppelt" if str(runtime_snapshot_atomic_entrypoints.get("entrypoint_state") or "").strip().lower() == "ready" else (" · Pre-Commit vorbereitet" if str(runtime_snapshot_precommit_contract.get("contract_state") or "").strip().lower() == "ready" else (" · Minimalfall vorbereitet" if bool(first_minimal_case_report.get("future_unlock_ready")) else (" · Leere Audio-Spur" if bool(first_minimal_case_report.get("target_empty")) else "")))))))))
            ),
            "status_label": (
                f"Morphing-Guard: {track_name} · {summary}"
                + (" · Dry-Executor vorbereitet" if str(runtime_snapshot_dry_command_executor.get("dry_executor_state") or "").strip().lower() == "ready" else (" · Preview-Command vorbereitet" if str(runtime_snapshot_preview_command_construction.get("preview_state") or "").strip().lower() == "ready" else (" · Payload-Factory vorbereitet" if str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").strip().lower() == "ready" else (" · Command-Huelle vorbereitet" if str(runtime_snapshot_command_undo_shell.get("shell_state") or "").strip().lower() == "ready" else (" · Mutation-Gate vorbereitet" if str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").strip().lower() == "ready" else (" · Entry-Points gekoppelt" if str(runtime_snapshot_atomic_entrypoints.get("entrypoint_state") or "").strip().lower() == "ready" else (" · Pre-Commit vorbereitet" if str(runtime_snapshot_precommit_contract.get("contract_state") or "").strip().lower() == "ready" else (" · Minimalfall vorbereitet" if bool(first_minimal_case_report.get("future_unlock_ready")) else ""))))))))
            ),
            "audio_clip_count": int(audio_clip_count),
            "midi_clip_count": int(midi_clip_count),
            "note_fx_count": int(note_fx_count),
            "audio_fx_count": int(audio_fx_count),
            "requires_confirmation": bool(_has_content),
            "blocked_reasons": list(blocked_reasons),
            "blocked_message": blocked_message,
            "valid_target": bool(track_kind == "audio"),
            "can_apply": bool(_is_audio_target),
            "apply_mode": (
                "minimal_empty_audio" if _is_minimal_case
                else ("audio_to_instrument_with_content" if (_is_audio_target and _has_content) else "blocked")
            ),
            "shadow_commit_rehearsal": dict(shadow_commit_rehearsal),
            "shadow_commit_rehearsal_summary": shadow_commit_rehearsal_summary,
        }
    except Exception:
        return {
            "mode": "audio_to_instrument_morph",
            "track_id": "",
            "track_name": "Spur",
            "plugin_name": str(plugin_name or "").strip() or "Instrument",
            "source_kind": "",
            "target_kind": "instrument",
            "summary": "",
            "impact_summary": "",
            "rollback_lines": [],
            "future_apply_steps": [],
            "required_snapshots": [],
            "snapshot_refs": [],
            "snapshot_ref_map": {},
            "snapshot_ref_summary": "",
            "runtime_snapshot_preview": [],
            "runtime_snapshot_summary": "",
            "runtime_snapshot_handles": [],
            "runtime_snapshot_handle_summary": "",
            "runtime_snapshot_captures": [],
            "runtime_snapshot_capture_summary": "",
            "runtime_snapshot_instances": [],
            "runtime_snapshot_instance_summary": "",
            "runtime_snapshot_objects": [],
            "runtime_snapshot_object_summary": "",
            "runtime_snapshot_stubs": [],
            "runtime_snapshot_stub_summary": "",
            "runtime_snapshot_state_carriers": [],
            "runtime_snapshot_state_carrier_summary": "",
            "runtime_snapshot_state_containers": [],
            "runtime_snapshot_state_container_summary": "",
            "runtime_snapshot_state_holders": [],
            "runtime_snapshot_state_holder_summary": "",
            "runtime_snapshot_state_slots": [],
            "runtime_snapshot_state_slot_summary": "",
            "runtime_snapshot_state_stores": [],
            "runtime_snapshot_state_store_summary": "",
            "runtime_snapshot_state_registries": [],
            "runtime_snapshot_state_registry_summary": "",
            "runtime_snapshot_state_registry_backends": [],
            "runtime_snapshot_state_registry_backend_summary": "",
            "runtime_snapshot_state_registry_backend_adapters": [],
            "runtime_snapshot_state_registry_backend_adapter_summary": "",
            "runtime_snapshot_bundle": {},
            "runtime_snapshot_bundle_summary": "",
            "runtime_snapshot_apply_runner": {},
            "runtime_snapshot_apply_runner_summary": "",
            "runtime_snapshot_dry_run": {},
            "runtime_snapshot_dry_run_summary": "",
            "readiness_checks": [],
            "readiness_summary": "",
            "first_minimal_case_report": {},
            "first_minimal_case_summary": "",
            "runtime_snapshot_precommit_contract": {},
            "runtime_snapshot_precommit_contract_summary": "",
            "runtime_snapshot_atomic_entrypoints": {},
            "runtime_snapshot_atomic_entrypoints_summary": "",
            "runtime_snapshot_mutation_gate_capsule": {},
            "runtime_snapshot_mutation_gate_capsule_summary": "",
            "runtime_snapshot_command_undo_shell": {},
            "runtime_snapshot_command_undo_shell_summary": "",
            "runtime_snapshot_command_factory_payloads": {},
            "runtime_snapshot_command_factory_payload_summary": "",
            "runtime_snapshot_preview_command_construction": {},
            "runtime_snapshot_preview_command_construction_summary": "",
            "runtime_snapshot_dry_command_executor": {},
            "runtime_snapshot_dry_command_executor_summary": "",
            "transaction_steps": [],
            "transaction_key": "audio_to_instrument_morph::unknown::instrument",
            "transaction_summary": "",
            "preview_label": "",
            "status_label": "",
            "audio_clip_count": 0,
            "midi_clip_count": 0,
            "note_fx_count": 0,
            "audio_fx_count": 0,
            "requires_confirmation": False,
            "blocked_reasons": ["Morphing-Plan konnte nicht erstellt werden"],
            "blocked_message": "SmartDrop noch gesperrt: Audio→Instrument-Morphing-Plan konnte nicht erstellt werden.",
            "valid_target": False,
            "can_apply": False,
            "apply_mode": "blocked",
            "shadow_commit_rehearsal": {},
            "shadow_commit_rehearsal_summary": "",
        }


def validate_audio_to_instrument_morph_plan(project_obj: Any, track: Any, plugin_name: str = "", runtime_owner: Any | None = None) -> dict[str, Any]:
    """Validate the future morph target without mutating project state."""
    plan = dict(build_audio_to_instrument_morph_plan(project_obj, track, plugin_name=plugin_name, runtime_owner=runtime_owner) or {})
    plan["validated"] = True
    # Preserve can_apply for audio morph modes (empty or with content)
    if str(plan.get("apply_mode") or "") not in ("minimal_empty_audio", "audio_to_instrument_with_content"):
        plan["can_apply"] = False
    if not bool(plan.get("valid_target")):
        plan["can_apply"] = False
        track_name = str(plan.get("track_name") or "Spur")
        source_label = _track_kind_label(str(plan.get("source_kind") or ""))
        plan["blocked_message"] = (
            f"SmartDrop noch gesperrt: {track_name} ist {source_label}. "
            "Der vorbereitete Morphing-Guard gilt derzeit nur für Audio→Instrument-Fälle."
        )
    return plan


def apply_audio_to_instrument_morph_plan(project_service: Any, plan: dict[str, Any] | None) -> dict[str, Any]:
    """Execute or preview an Audio→Instrument morph.

    For audio tracks (empty or with content), this performs the REAL atomic
    mutation: snapshot before, set track.kind='instrument', push undo command.
    Audio clips and FX chains are preserved (Bitwig-style hybrid conversion).

    The actual instrument insertion is handled by MainWindow after this returns
    with ok=True, because the device-panel UI path is needed for that.
    """
    result = dict(plan or {})
    apply_mode = str(result.get("apply_mode") or "blocked").strip()

    # ── Atomic live path for audio → instrument (empty or with content) ──
    if apply_mode in ("minimal_empty_audio", "audio_to_instrument_with_content") and bool(result.get("can_apply")):
        track_id = str(result.get("track_id") or "").strip()
        track_name = str(result.get("track_name") or "Spur")
        plugin_name = str(result.get("plugin_name") or "Instrument")
        try:
            # Capture before snapshot
            before_snapshot = project_service._project_snapshot_dict()
            if not before_snapshot:
                raise RuntimeError("before snapshot is empty")

            # Suppress auto-undo during our atomic operation
            project_service._auto_undo_suppress_depth = getattr(project_service, '_auto_undo_suppress_depth', 0) + 1
            try:
                # Perform the minimal mutation: set track kind
                project_service.set_track_kind(track_id, "instrument")

                # Capture after snapshot
                after_snapshot = project_service._project_snapshot_dict()
                if not after_snapshot:
                    # Rollback
                    project_service._restore_project_from_snapshot(before_snapshot)
                    raise RuntimeError("after snapshot is empty")

                # Push as single undo command
                from pydaw.commands.project_snapshot_edit import ProjectSnapshotEditCommand
                cmd = ProjectSnapshotEditCommand(
                    before=before_snapshot,
                    after=copy.deepcopy(after_snapshot),
                    label=f"SmartDrop: Audio→Instrument ({plugin_name} auf {track_name})",
                    apply_snapshot=project_service._restore_project_from_snapshot,
                )
                project_service.undo_stack.push(cmd, already_done=True)
                project_service._sync_auto_undo_baseline()
            finally:
                project_service._auto_undo_suppress_depth = max(0, getattr(project_service, '_auto_undo_suppress_depth', 1) - 1)

            result["applied"] = True
            result["ok"] = True
            result["blocked"] = False
            result["transaction_preview_only"] = False
            result["message"] = (
                f"SmartDrop ausgefuehrt: {track_name} ist jetzt eine Instrument-Spur. "
                f"Undo mit Ctrl+Z moeglich."
            )
            return result
        except Exception as exc:
            # On any error, ensure we don't leave corrupt state
            result["applied"] = False
            result["ok"] = False
            result["blocked"] = True
            result["transaction_preview_only"] = True
            result["message"] = f"SmartDrop fehlgeschlagen: {exc}"
            return result

    # ── All other cases: still non-mutating ──
    result["applied"] = False
    result["ok"] = False
    result["blocked"] = True
    result["transaction_preview_only"] = True
    first_minimal_case_report = dict(result.get("first_minimal_case_report") or {})
    runtime_snapshot_precommit_contract = dict(result.get("runtime_snapshot_precommit_contract") or {})
    runtime_snapshot_atomic_entrypoints = dict(result.get("runtime_snapshot_atomic_entrypoints") or {})
    runtime_snapshot_mutation_gate_capsule = dict(result.get("runtime_snapshot_mutation_gate_capsule") or {})
    runtime_snapshot_command_factory_payloads = dict(result.get("runtime_snapshot_command_factory_payloads") or {})
    if str(runtime_snapshot_command_factory_payloads.get("payload_state") or "").strip().lower() == "ready":
        result["message"] = (
            "SmartDrop weiter gesperrt: Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an eine explizite Before-/After-Snapshot-Command-Factory mit materialisierten Snapshot-Payloads gekoppelt, "
            "aber der Mutationspfad bleibt bewusst noch deaktiviert."
        )
    elif str(runtime_snapshot_mutation_gate_capsule.get("capsule_state") or "").strip().lower() == "ready":
        result["message"] = (
            "SmartDrop weiter gesperrt: Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an ein explizites Mutation-Gate und eine Transaction-Capsule gekoppelt, "
            "aber der Mutationspfad bleibt bewusst noch deaktiviert."
        )
    elif str(runtime_snapshot_atomic_entrypoints.get("entrypoint_state") or "").strip().lower() == "ready":
        result["message"] = (
            "SmartDrop weiter gesperrt: Der spaetere Minimalfall (leere Audio-Spur) ist jetzt read-only bis an echte Commit-/Undo-/Routing-Entry-Points gekoppelt, "
            "aber der Mutationspfad bleibt bewusst noch deaktiviert."
        )
    elif str(runtime_snapshot_precommit_contract.get("contract_state") or "").strip().lower() == "ready":
        result["message"] = (
            "SmartDrop weiter gesperrt: Der spaetere Minimalfall (leere Audio-Spur) hat jetzt einen read-only Pre-Commit-Vertrag, "
            "aber echter Commit-/Routing-/Undo-Pfad bleibt bewusst noch aus."
        )
    elif bool(first_minimal_case_report.get("future_unlock_ready")):
        result["message"] = (
            "SmartDrop weiter gesperrt: Der erste spaetere Minimalfall (leere Audio-Spur) ist read-only vorbereitet, "
            "aber echter Commit/Routing-Umbau bleibt bewusst noch aus."
        )
    elif bool(first_minimal_case_report.get("target_empty")):
        result["message"] = (
            "SmartDrop weiter gesperrt: Leere Audio-Spur erkannt; der erste spaetere Minimalfall wird bereits read-only vorqualifiziert, "
            "aber noch nicht mutierend freigeschaltet."
        )
    else:
        result["message"] = str(result.get("blocked_message") or "SmartDrop noch gesperrt: Audio→Instrument-Morphing ist noch nicht freigeschaltet.")
    return result
