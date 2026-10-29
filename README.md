# Lock-in amplifier analysis

`analyze.py` plots the `LockinAmplifier` signal from a tab-separated measurement file against elapsed time. It supports interactive uptake and desorption interval selection, adjustable horizontal baselines, signed area integration, and molecule-count calculations. Both phases share one JSON file containing filename metadata, selected intervals, baselines, and molecule counts. `generate_database.py` combines these JSON files into a CSV database.

## Setup

Use Python 3.9 or newer and install Matplotlib:

```sh
python3 -m pip install matplotlib
```

Interactive selection requires a graphical environment and an interactive Matplotlib backend. `--no-show` and `--replay` use the noninteractive Agg backend.

## Required filename format

**Every input measurement filename must follow this format.** `analyze.py` validates it before reading measurement data or writing outputs, in every mode (including `--baseline`, `--replay`, and `--no-show`). Invalid names stop the command with an `Invalid measurement filename` error.

Use exactly nine underscore-separated fields in this order:

```text
YYMMDD_label_plastic_probe_flow_condition_time_weight_BET.txt
240119_SS18_PET_HA_2.38e15_O3_20_200.3_5.8.txt
```

| Field | Example | Meaning |
| --- | --- | --- |
| Experiment date | `240119` | January 19, 2024; `YYMMDD` means a year in 2000–2099 |
| Label | `SS18` | Experiment label |
| Plastic name | `PET` | Material name |
| Probe gas name | `HA` | Probe gas |
| Flow rate | `2.38e15` | Molecules/s |
| Condition | `O3` | Experiment condition |
| Condition time | `20` | Minutes |
| Material weight | `200.3` | Milligrams |
| `bet_surface` | `5.8` | BET surface area in cm²/mg |

The filename rules enforced by the code are:

- The extension must be exactly `.txt` (lowercase).
- All nine fields must be present and nonempty. Underscores separate fields and cannot occur inside a field.
- The date must contain exactly six ASCII digits (`YYMMDD`) and be a valid calendar date in 2000–2099.
- Flow rate, condition time, material weight, and BET surface area must be finite, nonnegative numbers. Decimal and scientific notation are accepted; use a decimal point, not a comma. Do not append units to these numbers.
- Label, plastic, probe gas, and condition are text fields; the script does not restrict them to a predefined list.

Valid examples:

```text
240119_SS18_PET_HA_2.38e15_O3_20_200.3_5.8.txt
231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt
```

Examples that are rejected:

| Filename | Reason |
| --- | --- |
| `240119_PET_HA_O3_20_200.3_SS18_2.38e15.txt` | Older eight-field format |
| `240230_SS18_PET_HA_2.38e15_O3_20_200.3_5.8.txt` | Invalid calendar date |
| `240119_SS18_PET_HA_2.38e15_O3_20_200.3mg_5.8.txt` | Weight includes a unit instead of being numeric |
| `240119_SS18_PET_HA_2.38e15_O3_20_200.3_5.8.csv` | Wrong extension |

The filename supplies metadata and the flow rate for both phases, including replay; there is no terminal flow-rate prompt. Rename older measurement files before analysis. When reusing existing results after a rename, update the saved `source_file` references and use the matching JSON filename (or pass `--json`). The program does not automatically migrate renamed measurements.

All JSON file references contain filenames only. Moving files between directories is supported; pass the input path and the appropriate `--json`/`--output` paths when the files are outside the current working directory.

Metadata is written before the phase sections in the shared JSON:

```json
{
  "source_file": "240119_SS18_PET_HA_2.38e15_O3_20_200.3_5.8.txt",
  "metadata": {
    "experiment_date": "2024-01-19",
    "label": "SS18",
    "plastic_name": "PET",
    "probe_gas_name": "HA",
    "condition": "O3",
    "condition_time": 20.0,
    "condition_time_units": "mins",
    "material_weight": 200.3,
    "material_weight_units": "mg",
    "bet_surface": 5.8,
    "bet_surface_units": "cm^2/mg",
    "area": 1161.74,
    "area_units": "cm^2",
    "flow_rate": 2380000000000000.0,
    "flow_rate_units": "molecules/s"
  },
  "phases": {
    "uptake": {},
    "desorption": {}
  }
}
```

All saved file references use filenames only, including source and plot files. Each units field immediately follows its numeric field.

The phase objects above are placeholders; actual selections and results fill them as each phase is saved. Metadata is saved with the selection, not when a cancelled run starts. `--no-show` saves only a plot.

## Input format

The input must be a UTF-8 tab-separated file (an optional UTF-8 byte-order mark is supported), with these case-sensitive column names:

| Column | Format |
| --- | --- |
| `Time` | `DD.MM.YYYY HH:MM:SS.ffffff`, e.g. `13.10.2023 12:00:00.250` |
| `LockinAmplifier` | A floating-point number, including scientific notation |

Additional columns are ignored. At least one measurement is required. Use measurements in chronological order; the script does not sort the input. Elapsed time starts at the first measurement, and the horizontal axis also shows the clock time as recorded in the file, without timezone conversion.

## Quick start

Run the full uptake and desorption workflow with a measurement file named in the standard format:

```sh
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt"
```

1. The script reads the metadata and flow rate from the filename automatically.
2. On the full signal plot, click the uptake start and end in either order. Clicks snap to the nearest measurement time; the click's vertical position does not affect the selection. Right-click to undo a point.
3. On the selected interval, drag the red horizontal baseline up or down, then click **Confirm baseline**. Disable toolbar pan or zoom before dragging. The uptake baseline must be nonzero.
4. After uptake confirmation, the script opens the full signal again for desorption selection. Select two points, adjust the desorption baseline, and confirm it.
5. Close the final plot window to finish.

The full plot is saved before point selection. Closing during point selection cancels that phase. Once two points are selected, the interval plot and selection JSON are written immediately; the baseline image and calculated results are written on baseline confirmation. Closing a newly selected interval without confirming can therefore leave a JSON containing points but no baseline. When using `--baseline`, closing without confirmation preserves the saved JSON and baseline image.

## Commands

In these examples, replace `231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt` with your input path. Quote paths containing spaces or shell characters such as `&`.

```sh
# Full workflow: uptake, then desorption
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt"

# Uptake only
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --uptake

# Desorption only, using a previously confirmed uptake calibration
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --desorb

# Adjust the baseline while retaining saved interval endpoints
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --baseline
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --desorb --baseline

# Regenerate each phase from its saved endpoints and baseline
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --replay
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --desorb --replay

# Save only the full signal plot, without prompts or selection
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --no-show

# Display command-line help
python3 analyze.py --help
```

`--replay` processes one phase per invocation and rewrites its plots and JSON results. It requires a saved baseline and reads the flow rate from the filename. Desorption reads the uptake section of the same JSON and uses its current calibration.

### Output paths and calibration

| Option | Purpose |
| --- | --- |
| `--output PATH` | Set the interval image path, or the full plot path with `--no-show`. Use a `.png` extension for PNG output. |
| `--json PATH` | Set the shared JSON path for both phases; defaults to `<input_stem>.json` beside the output image. |
| `--uptake-json PATH` | Import the uptake baseline from an older separate JSON or another shared JSON for desorption. |

For example, after creating the `results` directory:

```sh
mkdir -p results
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --uptake \
  --output results/uptake.png --json results/measurement.json
python3 analyze.py "231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt" --desorb \
  --output results/desorption.png --json results/measurement.json
```

Parent output directories must already exist. Both phases use the same default JSON when their output images are in the same directory, regardless of the image name. When using a custom `--json`, pass that same path for uptake, desorption, baseline adjustment, and replay. Desorption requires a confirmed uptake baseline in the shared file.

If the default shared JSON does not yet exist, the script imports existing `<input_stem>_LockinAmplifier_uptake.json` and `<input_stem>_LockinAmplifier_desorb.json` files beside the output image. The older files remain unchanged. An older single-phase JSON supplied explicitly with `--json` is converted to the shared format on the next save.

`--uptake` and `--desorb` are mutually exclusive. `--baseline`, `--no-show`, and `--replay` are also mutually exclusive. With no phase or mode flag, the script runs both phases in sequence.

## Generated files

By default, files are written to the **current working directory**. Using `measurement` below as shorthand for the full input filename stem, the complete confirmed workflow produces:

| File | Contents |
| --- | --- |
| `measurement.png` | Full signal plot |
| `measurement_uptake.png` | Selected uptake interval with endpoint markers |
| `measurement_uptake_baseline.png` | Uptake baseline, shaded integral, flow rate, and molecule count |
| `measurement_desorb.png` | Selected desorption interval with endpoint markers |
| `measurement_desorb_baseline.png` | Desorption baseline, shaded integral, flow rate, and molecule count |
| `measurement.json` | Both phases: selections, calibration, and results |

Images are saved at 200 dpi. Existing files at the same output paths are overwritten. `--baseline` updates the baseline image and JSON after confirmation but does not regenerate the plain interval image.

The JSON contains a top-level `source_file`, filename-derived `metadata`, and a `phases` object with separate `uptake` and `desorption` sections. Each section records image filenames, selected measurement indices and their times/values, interval duration, flow rate, confirmed baseline, integration metadata, and molecule count. Desorption also records the uptake baseline used for its calculation. Saving one phase preserves the other section.

Changing the uptake calibration does not automatically recalculate previously saved desorption results. Run `--desorb --replay` to refresh them.

Saved selections are matched by source filename, without a directory path. Reuse checks that the endpoint indices, elapsed times, and signal values still match the input; it does not validate every interior measurement. Renaming the input or changing its selected endpoints can require a new selection.

## Calculation method

The total material surface area is stored as `metadata.area`:

```text
area (cm²) = bet_surface (cm²/mg) × material_weight (mg)
```

For SS18, `5.8 × 200.3 = 1161.74 cm²`. A reference with zero weight or zero BET surface area has an area of zero. Uptake and desorption are reported as total molecule counts; counts per cm² are not calculated.

The signal integrals stored as `phases.uptake.area` and `phases.desorption.area` are separate from this material surface area.

Let `y(t)` be the signal, `B_u` the uptake baseline, `B_d` the desorption baseline, and `F` the molecular flow rate in molecules/s. The script calculates signed trapezoidal integrals:

```text
Uptake area:       A_u = integral of (B_u - y(t)) dt
Desorption area:   A_d = integral of (y(t) - B_d) dt

Uptake molecules:      N_u = F * A_u / B_u
Desorption molecules: N_d = F * A_d / B_u
```

Both molecule counts use the **uptake baseline** for normalization. The desorption baseline controls its integrated area and may be zero. The uptake baseline must be finite and nonzero.

For uptake, points above `B_u + 0.20 * abs(B_u)` are excluded. Desorption has no upper signal threshold. Both phases exclude nonfinite times or signals. A trapezoid contributes only when both adjacent endpoints are accepted and its time step is positive; excluded points are never bridged. The reported included duration sums only accepted time steps and can be shorter than the selected interval.

Signal integrals have units of `LockinAmplifier units * seconds`. Integration is signed: contributions on the opposite side of the baseline subtract from the total, so areas and molecule counts can be negative. The flow rate is read from the fifth filename field; the script does not infer it from the measurement data.

## Export a CSV database

Combine all supported analysis JSON files in the current directory:

```sh
python3 generate_database.py
```

This writes `database.csv`. To use another directory or output path:

```sh
python3 generate_database.py results --output experiments.csv
```

The CSV has one row per shared analysis JSON, sorted by filename, with these columns in order:

```text
date,Lable,plastic,probe gas,condition,condition time(mins),weight(mg),bet_surface,area(cm^2),flow rate,uptake #,desorb #
```

`Lable` is the experiment label; `date` is the experiment date in `YYYY-MM-DD` format. Condition time is interpreted as minutes and material weight as milligrams, with no conversion. `bet_surface` is in cm^2/mg. The metadata field `area` and CSV column `area(cm^2)` contain `bet_surface * material_weight`, the total material surface area in cm^2. This differs from the signal integral stored inside each phase as `area` and does not change the molecule-count calculations. Flow rate is in molecules/s. `uptake #` and `desorb #` are the saved molecule counts, not integrated areas; results are not recalculated during export. Missing or unfinished phase results produce blank cells, while zero counts remain zero.

The exporter reads metadata from JSON contents; it does not parse or enforce the measurement naming pattern on JSON filenames. Only JSON files directly inside the selected directory are scanned. Files without the shared metadata format (including older separate phase files), malformed JSON, and invalid structures are reported and skipped. An existing output CSV is overwritten when supported experiments are found; if none are found, the command exits with an error and leaves the output unchanged. The exporter uses only the Python standard library.

After adjusting a saved baseline, replay the affected phases as needed and run `python3 generate_database.py` again to refresh the CSV. The analysis script does not update the CSV automatically.
