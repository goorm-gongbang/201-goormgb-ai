"""Policy package — snapshot + loader.

Ref: L2/obs_opt/policy_v1.yaml
"""

from .loader import (
    FilePolicyStore,
    InMemoryPolicyStore,
    PolicyLoader,
    RuntimePolicyAuthorityError,
    RuntimePolicyReadAdapter,
    snapshot_to_document,
)
from .runtime_read_adapter import (
    RuntimeProjectedPolicyDocument,
    RuntimeProjectedRolloutState,
    RuntimeProjectionDecodeError,
    RuntimeProjectionNotFoundError,
    RuntimeProjectionStaleError,
    decode_runtime_projected_policy_document,
    decode_runtime_projected_rollout_state,
    ensure_runtime_rollout_state_is_fresh,
    serialize_runtime_projected_policy_document,
    serialize_runtime_projected_rollout_state,
)
from .snapshot import PolicySnapshot

__all__ = [
    "PolicyLoader",
    "PolicySnapshot",
    "InMemoryPolicyStore",
    "FilePolicyStore",
    "RuntimePolicyAuthorityError",
    "RuntimePolicyReadAdapter",
    "RuntimeProjectedPolicyDocument",
    "RuntimeProjectedRolloutState",
    "RuntimeProjectionDecodeError",
    "RuntimeProjectionNotFoundError",
    "RuntimeProjectionStaleError",
    "decode_runtime_projected_policy_document",
    "decode_runtime_projected_rollout_state",
    "ensure_runtime_rollout_state_is_fresh",
    "serialize_runtime_projected_policy_document",
    "serialize_runtime_projected_rollout_state",
    "snapshot_to_document",
]
