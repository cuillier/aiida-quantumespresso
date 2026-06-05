"""Tests for the `PwSelfConsistentDDHWorkChain` class."""

import numpy as np
import pytest
from aiida.common import AttributeDict
from aiida.orm import Float, TrajectoryData

from aiida_quantumespresso.calculations.functions.calculate_dielectric_tensor import calculate_dielectric_tensor


@pytest.fixture
def generate_workchain_scf_ddh(generate_workchain, generate_inputs_pw, generate_structure, generate_kpoints_mesh):
    """Generate an instance of a ``PwSelfConsistentDDHWorkChain``."""

    def _generate_workchain_scf_ddh(inputs=None):
        entry_point = 'quantumespresso.pw.scf_ddh'

        if inputs is None:
            pw_inputs = generate_inputs_pw()
            pw_inputs.pop('structure', None)
            kpoints = pw_inputs.pop('kpoints')
            inputs = {
                'structure': generate_structure(),
                'scf': {'pw': pw_inputs, 'kpoints': kpoints},
            }

        return generate_workchain(entry_point, inputs)

    return _generate_workchain_scf_ddh


def _make_trajectory(cell_ang, dipoles):
    """Create a minimal TrajectoryData with cell and electronic dipole arrays."""
    traj = TrajectoryData()
    traj.set_array('cells', np.array([cell_ang]))
    traj.set_array('electronic_dipole_cartesian_axes', np.array([dipoles]))
    return traj


def test_setup(generate_workchain_scf_ddh):
    """Test `PwSelfConsistentDDHWorkChain.setup`."""
    process = generate_workchain_scf_ddh()
    process.setup()

    assert process.ctx.alpha == pytest.approx(0.25)
    assert process.ctx.eps_inf is None
    assert process.ctx.is_metallic is False
    assert process.ctx.converged is False
    assert process.ctx.iteration == 0
    assert isinstance(process.ctx.scf_inputs, AttributeDict)
    assert isinstance(process.ctx.scf_inputs.pw.parameters, dict)


def test_should_run_iteration(generate_workchain_scf_ddh):
    """Test `PwSelfConsistentDDHWorkChain.should_run_iteration`."""
    process = generate_workchain_scf_ddh()
    process.setup()

    assert process.should_run_iteration() is True

    process.ctx.converged = True
    assert process.should_run_iteration() is False

    process.ctx.converged = False
    process.ctx.is_metallic = True
    assert process.should_run_iteration() is False

    process.ctx.is_metallic = False
    process.ctx.iteration = process.inputs.max_iterations.value
    assert process.should_run_iteration() is False


def test_calculate_dielectric_tensor_isotropic():
    """Test the calcfunction for the z-only (isotropic) case using the Si lelfield example values."""
    from qe_tools import CONSTANTS

    # Si 8-atom cubic cell: celldm(1) = 10.18 bohr
    a_bohr = 10.18
    a_ang = a_bohr * CONSTANTS.bohr_to_ang
    cell_ang = [[a_ang, 0, 0], [0, a_ang, 0], [0, 0, a_ang]]
    vol_bohr3 = a_bohr**3
    e_field = 0.001

    d_ref_z = 1e-4  # small non-zero reference (as in the Si example)
    d_efield_z = 0.9265

    traj_scf = _make_trajectory(cell_ang, [0.0, 0.0, d_ref_z])
    traj_efield_z = _make_trajectory(cell_ang, [0.0, 0.0, d_efield_z])

    result = calculate_dielectric_tensor(
        output_trajectory_scf=traj_scf,
        efield_strength=Float(e_field),
        output_trajectory_efield_2=traj_efield_z,
        metadata={'store_provenance': False},
    )

    eps_inf = result['dielectric_constant'].value
    tensor = result['dielectric_tensor'].get_array('dielectric_tensor')

    expected_eps_zz = 1.0 + 4 * np.pi * (d_efield_z - d_ref_z) / (e_field * vol_bohr3)

    assert eps_inf == pytest.approx(expected_eps_zz, rel=1e-6)
    assert tensor[0, 0] == pytest.approx(expected_eps_zz, rel=1e-6)
    assert tensor[1, 1] == pytest.approx(expected_eps_zz, rel=1e-6)
    assert tensor[2, 2] == pytest.approx(expected_eps_zz, rel=1e-6)


def test_calculate_dielectric_tensor_full():
    """Test the calcfunction for the full 3-direction case with a cubic structure."""
    from qe_tools import CONSTANTS

    a_bohr = 10.18
    a_ang = a_bohr * CONSTANTS.bohr_to_ang
    cell_ang = [[a_ang, 0, 0], [0, a_ang, 0], [0, 0, a_ang]]
    vol_bohr3 = a_bohr**3
    e_field = 0.001

    d_efield = 0.9265  # same response along each axis for cubic symmetry

    traj_scf = _make_trajectory(cell_ang, [0.0, 0.0, 0.0])
    traj_x = _make_trajectory(cell_ang, [d_efield, 0.0, 0.0])
    traj_y = _make_trajectory(cell_ang, [0.0, d_efield, 0.0])
    traj_z = _make_trajectory(cell_ang, [0.0, 0.0, d_efield])

    result = calculate_dielectric_tensor(
        output_trajectory_scf=traj_scf,
        efield_strength=Float(e_field),
        output_trajectory_efield_0=traj_x,
        output_trajectory_efield_1=traj_y,
        output_trajectory_efield_2=traj_z,
        metadata={'store_provenance': False},
    )

    eps_inf = result['dielectric_constant'].value
    tensor = result['dielectric_tensor'].get_array('dielectric_tensor')

    expected_eps = 1.0 + 4 * np.pi * d_efield / (e_field * vol_bohr3)

    # All diagonal elements should be equal for a cubic cell
    assert tensor[0, 0] == pytest.approx(expected_eps, rel=1e-6)
    assert tensor[1, 1] == pytest.approx(expected_eps, rel=1e-6)
    assert tensor[2, 2] == pytest.approx(expected_eps, rel=1e-6)
    # Off-diagonal elements should be zero
    assert tensor[0, 1] == pytest.approx(0.0, abs=1e-10)
    assert tensor[0, 2] == pytest.approx(0.0, abs=1e-10)
    assert tensor[1, 2] == pytest.approx(0.0, abs=1e-10)
    # Scalar should be the diagonal value
    assert eps_inf == pytest.approx(expected_eps, rel=1e-6)
