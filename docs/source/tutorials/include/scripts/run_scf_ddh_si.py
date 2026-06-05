#!/usr/bin/env runaiida
"""Submit a PwSelfConsistentDDHWorkChain to compute the dielectric constant of silicon.

Requirements:
  - A ``Code`` configured for ``quantumespresso.pw`` (adjust the label below).
  - A pseudo-potential family installed, e.g.:
        aiida-pseudo install sssp -v 1.3 -x PBEsol -p efficiency
    then set PSEUDO_FAMILY to match.
  - An AiiDA profile with a running daemon (``verdi daemon start``).

Usage::

    verdi run docs/source/tutorials/include/scripts/run_scf_ddh_si.py

After submission check progress with::

    verdi process list
    verdi process show <PK>
"""

from aiida.engine import submit
from aiida.orm import StructureData, load_code
from ase.build import bulk

from aiida_quantumespresso.workflows.pw.scf_ddh import PwSelfConsistentDDHWorkChain

# ---------------------------------------------------------------------------
# User settings — adjust before running
# ---------------------------------------------------------------------------
PW_CODE_LABEL = 'pw@localhost'
PSEUDO_FAMILY = 'SSSP/1.3/PBEsol/efficiency'
# ---------------------------------------------------------------------------

code = load_code(PW_CODE_LABEL)

# Conventional cubic Si cell (a ≈ 5.43 Å, 8 atoms).
# A conventional cell gives a non-zero macroscopic volume, which is required
# for the Berry-phase dielectric calculation (a primitive cell works too, but
# the conventional cell is more natural for lelfield calculations).
structure = StructureData(ase=bulk('Si', 'diamond', 5.43, cubic=True))

builder = PwSelfConsistentDDHWorkChain.get_builder_from_protocol(
    code=code,
    structure=structure,
    protocol='balanced',
    overrides={
        'scf': {
            'pseudo_family': PSEUDO_FAMILY,
            'pw': {
                'metadata': {
                    'options': {
                        'resources': {'num_machines': 1},
                        'max_wallclock_seconds': 3600,
                        'withmpi': True,
                    }
                }
            },
        }
    },
)

node = submit(builder)
print(f'Submitted PwSelfConsistentDDHWorkChain<{node.pk}>')
print(f'Monitor with: verdi process show {node.pk}')
print('When finished, retrieve results with:')
print(f'  verdi calcjob res {node.pk}')
print(f'  python -c "from aiida.orm import load_node; n = load_node({node.pk}); print(n.outputs.dielectric_constant)"')
