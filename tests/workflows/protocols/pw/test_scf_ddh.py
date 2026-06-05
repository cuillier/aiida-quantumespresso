"""Tests for the ``PwSelfConsistentDDHWorkChain.get_builder_from_protocol`` method."""

import pytest
from aiida.engine import ProcessBuilder

from aiida_quantumespresso.workflows.pw.scf_ddh import PwSelfConsistentDDHWorkChain

pytestmark = pytest.mark.usefixtures('pseudo_family')


def test_get_available_protocols():
    """Test ``PwSelfConsistentDDHWorkChain.get_available_protocols``."""
    protocols = PwSelfConsistentDDHWorkChain.get_available_protocols()
    assert sorted(protocols.keys()) == ['balanced', 'fast', 'stringent']
    assert all('description' in protocol for protocol in protocols.values())


def test_get_default_protocol():
    """Test ``PwSelfConsistentDDHWorkChain.get_default_protocol``."""
    assert PwSelfConsistentDDHWorkChain.get_default_protocol() == 'balanced'


def test_default(fixture_code, generate_structure, data_regression, serialize_builder):
    """Test ``PwSelfConsistentDDHWorkChain.get_builder_from_protocol`` for the default protocol."""
    code = fixture_code('quantumespresso.pw')
    structure = generate_structure()
    builder = PwSelfConsistentDDHWorkChain.get_builder_from_protocol(code, structure)

    assert isinstance(builder, ProcessBuilder)
    data_regression.check(serialize_builder(builder))
