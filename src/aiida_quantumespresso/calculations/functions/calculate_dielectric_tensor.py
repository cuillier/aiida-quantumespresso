"""Calculation function to compute the macroscopic dielectric tensor from Berry-phase dipoles."""

from aiida.engine import calcfunction


@calcfunction
def calculate_dielectric_tensor(output_trajectory_scf, efield_strength, **efield_trajectories):
    """Compute the 3x3 dielectric tensor from finite-field Berry phase dipoles.

    Each finite-field trajectory corresponds to a separate SCF with a field applied along one Cartesian
    direction. The full 3-vector of the electronic dipole fills column d of the dielectric tensor.
    When only the z-direction trajectory is provided, isotropy is assumed: eps_tensor = eps_zz * I.

    :param output_trajectory_scf: TrajectoryData from the zero-field SCF (D(0), full 3-vector)
    :param efield_strength: Float, field magnitude in Ry/bohr a.u. (same for every direction)
    :param efield_trajectories: TrajectoryData nodes keyed as ``output_trajectory_efield_0``,
        ``output_trajectory_efield_1``, ``output_trajectory_efield_2``. Providing only key 2
        triggers the isotropic approximation: eps_tensor = eps_zz * I.
    :returns: dict of AiiDA nodes — ``dielectric_constant`` (Float, mean eigenvalue) and
        ``dielectric_tensor`` (ArrayData, shape (3, 3))
    """
    import numpy as np
    from aiida.orm import ArrayData, Float
    from qe_tools import CONSTANTS

    e_field = efield_strength.value
    cell_ang = output_trajectory_scf.get_array('cells')[-1]  # shape (3, 3), Å
    vol_bohr3 = abs(np.linalg.det(cell_ang)) / CONSTANTS.bohr_to_ang**3
    d_ref = output_trajectory_scf.get_array('electronic_dipole_cartesian_axes')[-1]  # shape (3,)

    computed_directions = sorted(
        int(key.split('_')[-1]) for key in efield_trajectories if key.startswith('output_trajectory_efield_')
    )

    eps_tensor = np.eye(3)
    for d in computed_directions:
        d_efield = efield_trajectories[f'output_trajectory_efield_{d}'].get_array('electronic_dipole_cartesian_axes')[
            -1
        ]
        for i in range(3):
            eps_tensor[i, d] += 4 * np.pi * (d_efield[i] - d_ref[i]) / (e_field * vol_bohr3)

    if computed_directions == [2]:
        eps_tensor = np.eye(3) * eps_tensor[2, 2]

    eigenvalues = np.linalg.eigvalsh(eps_tensor)
    eps_inf = float(eigenvalues.mean())

    tensor_data = ArrayData()
    tensor_data.set_array('dielectric_tensor', eps_tensor)

    return {'dielectric_constant': Float(eps_inf), 'dielectric_tensor': tensor_data}
