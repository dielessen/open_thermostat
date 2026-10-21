"""Graph SOURCE handoff consumes readback, never proposes config to a remote."""
import pytest
from copy import deepcopy
from test_graph_native_caller import native_caller,emit,saved_graph

@pytest.mark.asyncio
async def test_graph_source_unknown_remote_revision_cannot_use_normal_config_proposal(native_caller):
    n=native_caller
    before=deepcopy(n.client.journal)
    # Existing normal-config helper is intentionally NOT a second apply path for
    # this selected read-only graph handoff, even if a remote reports revision0.
    await n.client.propose(0)
    assert not n.publications
    assert n.client.journal==before
    assert not n.client.ready and n.client.graph_source_review_required
    emit(dict(scenario="readonly_graph_source_never_proposes_unknown_remote_config",
        previous_journal_preserved=True,physical_outputs_enabled=False))
