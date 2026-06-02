---
name: debugging-processes
description: Use when diagnosing failed, stuck, or misbehaving AiiDA processes or the daemon.
---

# Debugging processes and the daemon

## Inspecting a single process

```bash
verdi process status <PK>       # call stack and where execution stopped
verdi process report <PK>       # log messages emitted during execution
verdi process show <PK>         # inputs, outputs, exit code
verdi node show <PK>            # node attributes and extras
```

For a full provenance dump including input/output files:

```bash
verdi process dump <PK>         # dump a process and its provenance
```

For CalcJobs specifically, jump to the remote working directory on the HPC (requires SSH access):

```bash
verdi calcjob gotocomputer <PK>
```

## Inspecting the daemon

```bash
verdi status                    # storage + daemon & broker status
verdi daemon logshow            # tail daemon logs (best with a single worker)
verdi process repair            # requeue processes stuck after a daemon crash (stop daemon first)
```

## Common failure modes

### General AiiDA issues

- **Process stuck in `waiting`**: daemon lost track after a crash/restart. Run `verdi process repair`.
- **Process state inconsistent**: check whether `seal()` has been called on the node.

### Quantum ESPRESSO–specific issues

- **SCF convergence not reached** (`ERROR_CONVERGENCE_NOT_REACHED`): `PwBaseWorkChain` automatically retries with adjusted `mixing_beta` or `diagonalization`. If it exhausts all handlers the work chain exits with `ERROR_UNRECOVERABLE_FAILURE`.
- **Ionic convergence not reached**: reported as `ERROR_IONIC_CONVERGENCE_NOT_REACHED`; `PwBaseWorkChain` may restart with smaller `ion_dynamics` step.
- **XML parse failure**: `PwParser` raises if `aiida.xml` is missing or malformed. Check the remote folder for `aiida.xml`; the file may be absent if pw.x crashed early (walltime, OOM, missing pseudos).
- **Missing/wrong pseudopotentials**: CalcJob raises `ERROR_INVALID_INPUT_PSEUDO_POTENTIALS` during `prepare_for_submission`. Verify pseudo labels match structure kind names exactly.
- **Walltime exceeded**: CalcJob exits with `ERROR_SCHEDULER_OUT_OF_WALLTIME`; the `BaseWorkChain` restart handler will copy the remote folder and restart from the latest checkpoint.
- **Known unrecoverable errors** (`ERROR_KNOWN_UNRECOVERABLE_FAILURE`, code 310): the error handler recognised the QE error but cannot fix it (e.g., `read_namelists` crash). Inspect `verdi process report <PK>` for the matched error message.

## Interactive inspection

```bash
verdi shell                                    # IPython shell with AiiDA loaded
verdi devel run-sql "SELECT ..."               # raw SQL against the profile DB (USE WITH CAUTION)
```

Useful patterns inside `verdi shell`:

```python
from aiida.orm import load_node, QueryBuilder

node = load_node(<PK>)
node.base.attributes.all              # stored attributes
node.base.extras.all                  # extras (mutable)
node.base.repository.list_object_names()  # files in node repository

# Read a retrieved output file
with node.outputs.retrieved.open('aiida.out') as f:
    print(f.read())
```

## Relevant source in this repo

| File | Purpose |
|------|---------|
| `src/aiida_quantumespresso/workflows/pw/base.py` | `PwBaseWorkChain` — error handlers and exit codes |
| `src/aiida_quantumespresso/workflows/ph/base.py` | `PhBaseWorkChain` — error handlers |
| `src/aiida_quantumespresso/workflows/neb/base.py` | `NebBaseWorkChain` — error handlers |
| `src/aiida_quantumespresso/parsers/pw.py` | `PwParser` — top-level parser logic |
| `src/aiida_quantumespresso/parsers/parse_xml/parse.py` | XML schema-based output parser |
| `src/aiida_quantumespresso/parsers/parse_raw/pw.py` | stdout text parser |
| `src/aiida_quantumespresso/calculations/pw.py` | `PwCalculation` — exit codes and input preparation |
