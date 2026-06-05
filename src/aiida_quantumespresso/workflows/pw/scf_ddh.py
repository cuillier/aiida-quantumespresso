"""Workchain to perform a self-consistent dielectric-dependent hybrid (sc-DDH) calculation."""

import copy

from aiida import orm
from aiida.common import AttributeDict
from aiida.engine import ToContext, WorkChain, if_, while_

from aiida_quantumespresso.calculations.functions.calculate_dielectric_tensor import calculate_dielectric_tensor
from aiida_quantumespresso.utils.mapping import prepare_process_inputs
from aiida_quantumespresso.workflows.pw.base import PwBaseWorkChain

from ..protocols.utils import ProtocolMixin


class PwSelfConsistentDDHWorkChain(ProtocolMixin, WorkChain):
    """Workchain for self-consistent dielectric-dependent hybrid (sc-DDH) calculations.

    Implements the sc-DDH scheme of Skone, Govoni & Galli (PRB 89, 195112, 2014) where the
    exact-exchange fraction α = 1/ε∞ is iterated to self-consistency. ε∞ is computed from finite
    electric-field perturbations using the Berry phase approach (lelfield=.true.).
    """

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        super().define(spec)
        spec.expose_inputs(
            PwBaseWorkChain,
            namespace='scf',
            exclude=('clean_workdir', 'pw.structure', 'pw.parent_folder'),
            namespace_options={'help': 'Inputs for the `PwBaseWorkChain` for the SCF calculation.'},
        )
        spec.expose_inputs(
            PwBaseWorkChain,
            namespace='scf_metal',
            exclude=('clean_workdir', 'pw.structure', 'pw.parent_folder'),
            namespace_options={
                'required': False,
                'populate_defaults': False,
                'help': 'Inputs for the metallic-fallback SCF. If omitted, reuses `scf` with alpha=0.',
            },
        )
        spec.input('structure', valid_type=orm.StructureData, help='The input structure.')
        spec.input(
            'clean_workdir',
            valid_type=orm.Bool,
            default=lambda: orm.Bool(False),
            help='If `True`, work directories of all called calculation will be cleaned at the end of execution.',
        )
        spec.input(
            'alpha_start',
            valid_type=orm.Float,
            default=lambda: orm.Float(0.25),
            help='Initial exact-exchange fraction α = exx_fraction.',
        )
        spec.input(
            'efield_strength',
            valid_type=orm.Float,
            default=lambda: orm.Float(0.001),
            help='Magnitude of efield_cart in each separate finite-field calculation (Ry/bohr a.u.).',
        )
        spec.input(
            'full_dielectric_tensor',
            valid_type=orm.Bool,
            default=lambda: orm.Bool(True),
            help=(
                'If True, run a separate finite-field SCF along each Cartesian direction and construct the full '
                'dielectric tensor. If False, run only along z and assume isotropy.'
            ),
        )
        spec.input(
            'convergence_threshold',
            valid_type=orm.Float,
            default=lambda: orm.Float(0.05),
            help='Relative change in ε∞ between successive iterations required for convergence.',
        )
        spec.input(
            'max_iterations',
            valid_type=orm.Int,
            default=lambda: orm.Int(10),
            help='Maximum number of sc-DDH self-consistency iterations.',
        )
        spec.outline(
            cls.setup,
            while_(cls.should_run_iteration)(
                cls.run_scf,
                cls.inspect_scf,
                if_(cls.is_metallic)(
                    cls.run_scf_metal,
                    cls.inspect_scf_metal,
                ).else_(
                    cls.run_scf_efield,
                    cls.inspect_scf_efield,
                    cls.compute_dielectric_constant,
                ),
            ),
            cls.results,
        )
        spec.exit_code(
            400,
            'ERROR_MAX_ITERATIONS_EXCEEDED',
            message='The maximum number of sc-DDH iterations was exceeded.',
        )
        spec.exit_code(
            401,
            'ERROR_SUB_PROCESS_FAILED_SCF',
            message='The SCF `PwBaseWorkChain` sub process failed.',
        )
        spec.exit_code(
            402,
            'ERROR_SUB_PROCESS_FAILED_EFIELD_SCF',
            message='A finite-field SCF `PwBaseWorkChain` sub process failed.',
        )
        spec.exit_code(
            403,
            'ERROR_SUB_PROCESS_FAILED_METAL_SCF',
            message='The metallic-fallback `PwBaseWorkChain` sub process failed.',
        )
        spec.expose_outputs(PwBaseWorkChain)
        spec.output(
            'dielectric_constant',
            valid_type=orm.Float,
            required=False,
            help='Average of eigenvalues of the dielectric tensor, used for exx_fraction = 1/eps_inf.',
        )
        spec.output(
            'dielectric_tensor',
            valid_type=orm.ArrayData,
            required=False,
            help='3x3 dielectric tensor; diagonal ε_zz·I when full_dielectric_tensor=False.',
        )
        spec.output('is_metallic', valid_type=orm.Bool)

    @classmethod
    def get_protocol_filepath(cls):
        """Return ``pathlib.Path`` to the ``.yaml`` file that defines the protocols."""
        from importlib_resources import files

        from ..protocols import pw as pw_protocols

        return files(pw_protocols) / 'scf_ddh.yaml'

    @classmethod
    def get_builder_from_protocol(cls, code, structure, protocol=None, overrides=None, options=None, **kwargs):
        """Return a builder prepopulated with inputs selected according to the chosen protocol.

        :param code: the ``Code`` instance configured for the ``quantumespresso.pw`` plugin.
        :param structure: the ``StructureData`` instance to use.
        :param protocol: protocol to use, if not specified, the default will be used.
        :param overrides: optional dictionary of inputs to override the defaults of the protocol.
        :param options: A dictionary of options that will be recursively set for the ``metadata.options`` input of all
            the ``CalcJobs`` that are nested in this work chain.
        :param kwargs: additional keyword arguments that will be passed to the ``get_builder_from_protocol`` of all the
            sub processes that are called by this workchain.
        :return: a process builder instance with all inputs defined ready for launch.
        """
        inputs = cls.get_protocol_inputs(protocol, overrides)

        scf = PwBaseWorkChain.get_builder_from_protocol(
            code, structure, protocol, overrides=inputs.get('scf', None), options=options, **kwargs
        )
        scf['pw'].pop('structure', None)
        scf.pop('clean_workdir', None)

        builder = cls.get_builder()
        builder.structure = structure
        builder.scf = scf
        builder.clean_workdir = orm.Bool(inputs['clean_workdir'])
        builder.alpha_start = orm.Float(inputs['alpha_start'])
        builder.efield_strength = orm.Float(inputs['efield_strength'])
        builder.full_dielectric_tensor = orm.Bool(inputs['full_dielectric_tensor'])
        builder.convergence_threshold = orm.Float(inputs['convergence_threshold'])
        builder.max_iterations = orm.Int(inputs['max_iterations'])

        return builder

    def setup(self):
        """Input validation and context setup."""
        self.ctx.alpha = self.inputs.alpha_start.value
        self.ctx.eps_inf = None
        self.ctx.is_metallic = False
        self.ctx.converged = False
        self.ctx.iteration = 0

        self.ctx.scf_inputs = AttributeDict(self.exposed_inputs(PwBaseWorkChain, namespace='scf'))
        self.ctx.scf_inputs.pw.parameters = self.ctx.scf_inputs.pw.parameters.get_dict()

    def should_run_iteration(self):
        """Return whether another sc-DDH iteration should be run."""
        return (
            not self.ctx.converged
            and not self.ctx.is_metallic
            and self.ctx.iteration < self.inputs.max_iterations.value
        )

    def run_scf(self):
        """Run the zero-field SCF `PwBaseWorkChain` with the current hybrid fraction α."""
        inputs = self.ctx.scf_inputs
        inputs.pw.structure = self.inputs.structure

        inputs.pw.parameters.setdefault('SYSTEM', {})
        inputs.pw.parameters['SYSTEM']['input_dft'] = 'PBE0'
        inputs.pw.parameters['SYSTEM']['exx_fraction'] = self.ctx.alpha

        inputs.pw.parameters.setdefault('CONTROL', {})
        inputs.pw.parameters['CONTROL']['lelfield'] = True

        inputs.pw.parameters.setdefault('ELECTRONS', {})
        inputs.pw.parameters['ELECTRONS']['efield_cart'] = [0.0, 0.0, 0.0]

        if self.ctx.iteration > 0:
            inputs.pw.parent_folder = self.ctx.workchain_scf.outputs.remote_folder
            inputs.pw.parameters['ELECTRONS']['startingwfc'] = 'file'

        inputs.metadata.call_link_label = f'scf_{self.ctx.iteration:02d}'
        inputs = prepare_process_inputs(PwBaseWorkChain, inputs)

        base_wc = self.submit(PwBaseWorkChain, **inputs)
        self.report(f'launching PwBaseWorkChain<{base_wc.pk}> for SCF iteration {self.ctx.iteration}.')

        return ToContext(workchain_scf=base_wc)

    def inspect_scf(self):
        """Inspect the result of the SCF `PwBaseWorkChain` and detect metallicity."""
        from aiida.orm import find_bandgap

        workchain = self.ctx.workchain_scf

        if workchain.is_excepted or workchain.is_killed:
            self.report('SCF PwBaseWorkChain was excepted or killed')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_SCF

        if workchain.is_failed:
            self.report(f'SCF PwBaseWorkChain failed with exit status {workchain.exit_status}')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_SCF

        bands_node = workchain.outputs.output_bands
        number_electrons = workchain.outputs.output_parameters.get_dict()['number_of_electrons']
        is_insulator, gap = find_bandgap(bands_node, number_electrons=number_electrons)
        self.ctx.is_metallic = not is_insulator
        self.ctx.band_gap = gap

        if self.ctx.is_metallic:
            self.report('System detected as metallic; switching to metallic fallback.')
        else:
            self.report(f'System is insulating with band gap {gap:.3f} eV.')

    def is_metallic(self):
        """Return whether the system was detected as metallic."""
        return self.ctx.is_metallic

    def run_scf_metal(self):
        """Run a plain-PBE SCF for metallic systems."""
        if 'scf_metal' in self.inputs:
            inputs = AttributeDict(self.exposed_inputs(PwBaseWorkChain, namespace='scf_metal'))
        else:
            inputs = AttributeDict(self.ctx.scf_inputs)
            inputs.pw = AttributeDict(self.ctx.scf_inputs.pw)
            inputs.pw.parameters = copy.deepcopy(self.ctx.scf_inputs.pw.parameters)
            inputs.pw.parameters['SYSTEM'].pop('input_dft', None)
            inputs.pw.parameters['SYSTEM']['exx_fraction'] = 0.0

        inputs.pw.structure = self.inputs.structure
        inputs.metadata.call_link_label = 'scf_metal'
        inputs = prepare_process_inputs(PwBaseWorkChain, inputs)

        base_wc = self.submit(PwBaseWorkChain, **inputs)
        self.report(f'launching PwBaseWorkChain<{base_wc.pk}> for metallic fallback SCF.')

        return ToContext(workchain_metal=base_wc)

    def inspect_scf_metal(self):
        """Inspect the result of the metallic fallback `PwBaseWorkChain`."""
        workchain = self.ctx.workchain_metal

        if workchain.is_excepted or workchain.is_killed:
            self.report('Metallic SCF PwBaseWorkChain was excepted or killed')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_METAL_SCF

        if workchain.is_failed:
            self.report(f'Metallic SCF PwBaseWorkChain failed with exit status {workchain.exit_status}')
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED_METAL_SCF

    def run_scf_efield(self):
        """Run finite-field SCF calculations to compute the dielectric tensor."""
        directions = [0, 1, 2] if self.inputs.full_dielectric_tensor.value else [2]
        submitted = {}

        for d in directions:
            inputs = AttributeDict(self.ctx.scf_inputs)
            inputs.pw = AttributeDict(self.ctx.scf_inputs.pw)
            inputs.pw.parameters = copy.deepcopy(self.ctx.scf_inputs.pw.parameters)

            inputs.pw.structure = self.inputs.structure
            inputs.pw.parameters['CONTROL']['lelfield'] = True
            inputs.pw.parameters['ELECTRONS']['startingwfc'] = 'file'
            inputs.pw.parameters['ELECTRONS']['nberrycyc'] = 3

            efield_cart = [0.0, 0.0, 0.0]
            efield_cart[d] = self.inputs.efield_strength.value
            inputs.pw.parameters['ELECTRONS']['efield_cart'] = efield_cart

            inputs.pw.parent_folder = self.ctx.workchain_scf.outputs.remote_folder

            mesh, offset = self.ctx.workchain_scf.outputs.output_kpoints.get_kpoints_mesh()
            mesh = list(mesh)
            mesh[d] = 2 * mesh[d] + mesh[d] % 2
            kpoints = orm.KpointsData()
            kpoints.set_kpoints_mesh(mesh, offset=offset)
            inputs.pw.kpoints = kpoints

            inputs.metadata.call_link_label = f'scf_efield_{self.ctx.iteration:02d}_{d}'
            inputs = prepare_process_inputs(PwBaseWorkChain, inputs)

            base_wc = self.submit(PwBaseWorkChain, **inputs)
            self.report(f'launching PwBaseWorkChain<{base_wc.pk}> for efield SCF direction {d}.')
            submitted[d] = base_wc

        return ToContext(**{f'workchain_efield_{d}': wc for d, wc in submitted.items()})

    def inspect_scf_efield(self):
        """Inspect the results of the finite-field SCF `PwBaseWorkChain` calculations."""
        directions = [0, 1, 2] if self.inputs.full_dielectric_tensor.value else [2]

        for d in directions:
            workchain = self.ctx[f'workchain_efield_{d}']

            if workchain.is_excepted or workchain.is_killed:
                self.report(f'Efield SCF PwBaseWorkChain for direction {d} was excepted or killed')
                return self.exit_codes.ERROR_SUB_PROCESS_FAILED_EFIELD_SCF

            if workchain.is_failed:
                self.report(
                    f'Efield SCF PwBaseWorkChain for direction {d} failed with exit status {workchain.exit_status}'
                )
                return self.exit_codes.ERROR_SUB_PROCESS_FAILED_EFIELD_SCF

    def compute_dielectric_constant(self):
        """Compute the dielectric tensor and check convergence of α."""
        directions = [0, 1, 2] if self.inputs.full_dielectric_tensor.value else [2]

        kwargs = {
            'output_trajectory_scf': self.ctx.workchain_scf.outputs.output_trajectory,
            'efield_strength': self.inputs.efield_strength,
        }
        for d in directions:
            kwargs[f'output_trajectory_efield_{d}'] = self.ctx[f'workchain_efield_{d}'].outputs.output_trajectory

        result = calculate_dielectric_tensor(**kwargs)
        eps = result['dielectric_constant'].value
        self.ctx.dielectric_tensor = result['dielectric_tensor']

        if self.ctx.eps_inf is not None:
            if abs(eps - self.ctx.eps_inf) / eps < self.inputs.convergence_threshold.value:
                self.ctx.converged = True
                self.report(f'sc-DDH converged after {self.ctx.iteration + 1} iterations: ε∞ = {eps:.4f}.')

        self.ctx.eps_inf = eps

        if not self.ctx.converged:
            self.ctx.alpha = 1.0 / eps
            self.ctx.iteration += 1

    def results(self):
        """Attach outputs to the workchain node."""
        self.out('is_metallic', orm.Bool(self.ctx.is_metallic))

        if self.ctx.is_metallic:
            self.out_many(self.exposed_outputs(self.ctx.workchain_metal, PwBaseWorkChain))
            return

        if not self.ctx.converged:
            self.report('Maximum number of sc-DDH iterations reached.')
            return self.exit_codes.ERROR_MAX_ITERATIONS_EXCEEDED

        self.out_many(self.exposed_outputs(self.ctx.workchain_scf, PwBaseWorkChain))
        self.out('dielectric_constant', orm.Float(self.ctx.eps_inf))
        self.out('dielectric_tensor', self.ctx.dielectric_tensor)

    def on_terminated(self):
        """Clean the working directories of all child calculations if `clean_workdir=True` in the inputs."""
        super().on_terminated()

        if self.inputs.clean_workdir.value is False:
            self.report('remote folders will not be cleaned')
            return

        cleaned_calcs = []

        for called_descendant in self.node.called_descendants:
            if isinstance(called_descendant, orm.CalcJobNode):
                try:
                    called_descendant.outputs.remote_folder._clean()  # noqa: SLF001
                    cleaned_calcs.append(called_descendant.pk)
                except (OSError, KeyError):
                    pass

        if cleaned_calcs:
            self.report(f'cleaned remote folders of calculations: {" ".join(map(str, cleaned_calcs))}')
