---
name: writing-tests
description: Use when writing new pytest tests, fixtures, or regression tests for aiida-quantumespresso.
---

# Writing tests for aiida-quantumespresso

Tests live under `tests/` and mirror the source layout in `src/aiida_quantumespresso/`.
Reusable fixtures live in `tests/conftest.py`.

## Philosophy

- **Prefer real objects over mocks.** Use fixtures to create real nodes, processes, computers, etc.
  Mocks should only be used for genuinely external dependencies (network, SSH), or when you need to force an exception that would not otherwise appear naturally.
- **Don't chase coverage with shallow tests.** A test that mocks everything tests nothing.
- **Test the contract, not the implementation.** Assert observable outcomes, not internal method calls.
- **Make assertions as strong as possible.** `assert result == expected_value`, not `assert result is not None`.
- **Regression tests for bugs.** First write a test that reproduces the bug, then fix the code.
- **One behaviour per test.** Each test must be independent and deterministic.

## Pytest plugins

Only two non-standard plugins are used:

- `pytest~=8.4` — core test runner
- `pytest-regressions~=2.8` — golden-file regression testing (see patterns below)

`aiida.tools.pytest_fixtures` (from `aiida-core`) is loaded via `pytest_plugins` in `conftest.py` and provides `aiida_localhost`, `aiida_code_installed`, `generate_upf_data` and related AiiDA infrastructure fixtures.

There are **no custom pytest markers** in this repo beyond `@pytest.mark.parametrize` and `@pytest.mark.skip`.

## Test patterns

### CalcJob input-file tests (`tests/calculations/test_<code>.py`)

These tests verify that a `CalcJob` generates the correct input files for QE.

```python
def test_default(generate_calc_job, fixture_sandbox, generate_inputs_pw, file_regression):
    inputs = generate_inputs_pw()
    calc_info = generate_calc_job(fixture_sandbox, 'quantumespresso.pw', inputs)
    with fixture_sandbox.open('aiida.in') as fhandle:
        file_regression.check(fhandle.read())
```

- `generate_calc_job(folder, entry_point, inputs)` instantiates the process and calls `prepare_for_submission`, returning `CalcInfo` and writing input files into `folder`.
- `file_regression.check(text)` (from `pytest-regressions`) compares against the golden file in `tests/calculations/test_<code>/<test_name>.txt`. On first run, or with `--gen-files`, the golden file is created automatically.
- Golden files live in `tests/calculations/test_<code>/` next to the test module.

### Parser tests (`tests/parsers/test_<code>.py`)

These tests verify that a parser correctly extracts outputs from QE output files.

```python
def test_default(generate_calc_job_node, generate_parser, generate_upf_data):
    node = generate_calc_job_node('quantumespresso.pw', test_name='default')
    parser = generate_parser('quantumespresso.pw')
    results, calcfunction = parser.parse_from_node(node, store_provenance=False)
    assert calcfunction.is_finished_ok
    assert 'output_parameters' in results
```

- `generate_calc_job_node(entry_point, test_name=...)` loads fixture output files from `tests/parsers/fixtures/<code>/<test_name>/` and attaches them as `retrieved`.
- Fixture directories contain the actual QE output files (`aiida.out`, `aiida.xml`, etc.) that the parser will read.

### WorkChain tests (`tests/workflows/`)

Use the `generate_workchain_*` fixtures to instantiate a work chain in a controlled state:

```python
def test_handle_scf_convergence_not_achieved(generate_workchain_pw):
    from aiida_quantumespresso.calculations.pw import PwCalculation
    process = generate_workchain_pw(exit_code=PwCalculation.exit_codes.ERROR_CONVERGENCE_NOT_REACHED)
    process.handle_scf_convergence_not_achieved()
    assert process.node.is_finished
```

## Key fixtures (`tests/conftest.py`)

| Fixture | Purpose |
|---------|---------|
| `fixture_localhost` | A `Computer` configured for local execution |
| `fixture_code(entry_point)` | An `InstalledCode` for the given QE entry point |
| `fixture_sandbox` | A temporary `SandboxFolder` for input-file tests |
| `generate_calc_job(folder, ep, inputs)` | Calls `prepare_for_submission`, returns `CalcInfo` |
| `generate_calc_job_node(ep, test_name, ...)` | Node with attached `FolderData` from fixture files |
| `generate_upf_data(element)` | Minimal fake UPF pseudopotential |
| `generate_structure(structure_id)` | `StructureData` (silicon, water, cobalt-prim, 1D/2D variants) |
| `generate_kpoints_mesh(npoints)` | `KpointsData` with uniform mesh |
| `generate_parser(entry_point)` | Loads a parser class by entry point |
| `generate_workchain(entry_point, inputs)` | Instantiates a `WorkChain` without running it |
| `generate_inputs_pw/ph/cp/neb/matdyn/q2r/bands` | Minimal valid inputs for each calculation |
| `generate_workchain_pw/ph/neb` | Pre-configured work chain instances for handler tests |
| `serialize_builder(builder)` | Serialise a `ProcessBuilder` to a plain dict (for regression checks) |
| `pseudo_family` | Full SSSP + PseudoDojo pseudo families (session-scoped) |

## Running the tests

See the `running-tests` skill for the full `uv run pytest` cheatsheet.
