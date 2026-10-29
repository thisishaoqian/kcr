"""Plot LockinAmplifier against seconds elapsed since the first measurement.

Install matplotlib with: python3 -m pip install matplotlib
Full uptake and desorption workflow: python3 analyze.py 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt
Uptake only: python3 analyze.py 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt --uptake
Select desorption points and baseline: python3 analyze.py 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt --desorb
Adjust a saved interval's baseline: python3 analyze.py 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt --baseline
Replay saved points and baseline: python3 analyze.py 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt --replay
The original full plot is saved before selecting two uptake points.
Then drag the horizontal baseline and click Confirm baseline to save it.
"""

import argparse
import csv
import json
from datetime import datetime, timedelta
from math import ceil, isfinite
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator
from matplotlib.widgets import Button


def filename_references(value):
    """Keep file references portable, including references in older saved results."""
    if isinstance(value, dict):
        return {
            key: Path(item).name if key in ("source_file", "image_file", "uptake_json")
            and isinstance(item, str) else filename_references(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [filename_references(item) for item in value]
    return value


def read_selection_store(path, source_file):
    """Read shared data, accepting the older single-phase JSON format."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON must contain an object")
    if Path(data["source_file"]).name != source_file.name:
        raise ValueError("JSON belongs to a different measurement file")
    if "phases" not in data:
        phase = data.get("phase", "uptake")
        data = {"source_file": data["source_file"], "phases": {phase: data}}
    if not isinstance(data["phases"], dict):
        raise ValueError("JSON phases must contain an object")
    for phase, selection in data["phases"].items():
        if phase not in ("uptake", "desorption") or not isinstance(selection, dict):
            raise ValueError("Invalid phase selection")
    return filename_references(data)


def save_selection(selection, json_path, store):
    """Replace only the active phase, preserving the other phase's data."""
    store["phases"][selection["phase"]] = selection
    json_path.write_text(json.dumps(filename_references(store), indent=2) + "\n", encoding="utf-8")


def parse_filename_metadata(path):
    """Parse YYMMDD_label_plastic_probe_flow_condition_time_weight_BET.txt."""
    if path.suffix != ".txt":
        raise ValueError("Measurement filename must end with .txt")
    parts = path.stem.split("_")
    if len(parts) != 9 or any(not part.strip() for part in parts):
        raise ValueError(
            "Expected YYMMDD_label_plastic_probe_flow_condition_time_weight_BET.txt "
            "(for example 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt)"
        )
    date, label, plastic, probe, flow, condition, condition_time, weight, bet = parts
    if len(date) != 6 or not date.isascii() or not date.isdigit():
        raise ValueError("Experiment date must have six digits: YYMMDD")
    try:
        experiment_date = datetime.strptime("20" + date, "%Y%m%d").date().isoformat()
    except ValueError as error:
        raise ValueError(f"Invalid experiment date: {date}") from error
    numbers = {}
    for name, value in (("condition_time", condition_time),
                        ("material_weight", weight), ("flow_rate", flow),
                        ("bet_surface", bet)):
        try:
            number = float(value)
        except ValueError as error:
            raise ValueError(f"{name} must be a number, got {value!r}") from error
        if not isfinite(number) or number < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
        numbers[name] = number
    return {
        "experiment_date": experiment_date,
        "label": label,
        "plastic_name": plastic,
        "probe_gas_name": probe,
        "condition": condition,
        "condition_time": numbers["condition_time"],
        "condition_time_units": "mins",
        "material_weight": numbers["material_weight"],
        "material_weight_units": "mg",
        "bet_surface": numbers["bet_surface"],
        "bet_surface_units": "cm^2/mg",
        "area": numbers["bet_surface"] * numbers["material_weight"],
        "area_units": "cm^2",
        "flow_rate": numbers["flow_rate"],
        "flow_rate_units": "molecules/s",
    }


def uptake_area(seconds, values, baseline, desorption=False):
    """Integrate signed baseline-relative data without bridging rejected points."""
    threshold = baseline + 0.2 * abs(baseline)
    valid = [isfinite(t) and isfinite(y) and (desorption or y <= threshold)
             for t, y in zip(seconds, values)]
    area = 0.0
    duration = 0.0
    polygons = []
    for i in range(len(seconds) - 1):
        if not (valid[i] and valid[i + 1]):
            continue
        x0, x1 = seconds[i], seconds[i + 1]
        y0, y1 = values[i], values[i + 1]
        dt = x1 - x0
        if dt <= 0:
            continue
        d0, d1 = y0 - baseline, y1 - baseline
        duration += dt
        area += (1 if desorption else -1) * dt * (d0 + d1) / 2
        if d0 * d1 < 0:
            # Split shading at crossings so polygons do not intersect themselves.
            crossing = x0 + dt * abs(d0) / (abs(d0) + abs(d1))
            polygons.extend([
                [(x0, baseline), (x0, y0), (crossing, baseline)],
                [(crossing, baseline), (x1, y1), (x1, baseline)],
            ])
        else:
            polygons.append([(x0, baseline), (x0, y0), (x1, y1), (x1, baseline)])
    return {
        "value": float(area),
        "units": "LockinAmplifier units * seconds",
        "method": ("Signed trapezoidal integral of "
                   + ("data minus baseline" if desorption else "baseline minus data")
                   + "; both endpoints must be accepted"),
        "upper_threshold": None if desorption else float(threshold),
        "exclusion_rule": ("nonfinite data" if desorption else
                           "value > baseline + 0.20 * abs(baseline), or nonfinite data"),
        "excluded_points": int(len(valid) - sum(valid)),
        "included_duration_seconds": float(duration),
    }, polygons


def save_baseline(fig, ax, baseline, baseline_value, selection, json_path, image_path, store):
    """Save the baseline plot and integral for a confirmed or replayed value."""
    phase = selection.get("phase", "uptake")
    desorption = phase == "desorption"
    molecule_baseline = selection["uptake_baseline"] if desorption else baseline_value
    if not isfinite(molecule_baseline) or molecule_baseline == 0:
        raise ValueError("Uptake baseline must be finite and nonzero to calculate the molecule count.")
    for collection in list(ax.collections):
        if collection.get_gid() == "uptake_endpoints":
            collection.remove()
    seconds, values = ax.lines[0].get_data()
    baseline.set_label(f"Baseline: {baseline_value:.3g}")
    difference = "data − baseline" if desorption else "baseline − data"
    area, polygons = uptake_area(seconds, values, baseline_value, desorption=desorption)
    molecules = selection["flow_rate"] * area["value"] / molecule_baseline
    ax.add_collection(PolyCollection(
        polygons, facecolors="mediumseagreen", edgecolors="none", alpha=0.4,
        label=(f"Net area ({difference}): {area['value']:.3g}\n"
               f"{phase.capitalize()} molecule count: {molecules:.2e} molecules"), zorder=1,
    ))
    selection["area"] = area
    selection[phase] = {
        "molecules": molecules,
        "formula": "flow_rate * area / uptake_baseline",
        "uptake_baseline": molecule_baseline,
    }
    ax.text(
        0.02, 0.98, f"Flow rate: {selection['flow_rate']:.2e} molecules/s",
        transform=ax.transAxes, ha="left", va="top",
        bbox={"boxstyle": "round,pad=0.3", "facecolor": "white",
              "edgecolor": "lightgray", "alpha": 0.9},
    )
    ax.legend(loc="upper right" if desorption else "lower right")
    fig.tight_layout()
    baseline_path = image_path.with_name(f"{image_path.stem}_baseline{image_path.suffix}")
    fig.savefig(baseline_path, dpi=200)
    selection["baseline"] = {
        "LockinAmplifier": baseline_value,
        "slope": 0.0,
        "elapsed_start_seconds": selection["points"][0]["elapsed_seconds"],
        "elapsed_end_seconds": selection["points"][1]["elapsed_seconds"],
        "image_file": baseline_path.name,
    }
    save_selection(selection, json_path, store)
    print(f"Saved baseline picture to {baseline_path.name}")
    print(f"Saved confirmed baseline to {json_path.name}")
    print(f"Net area ({difference}): {area['value']:.3g} "
          f"({area['units']})")
    print(f"{phase.capitalize()} molecule count: {molecules:.2e} molecules")
    print(f"Excluded points: {area['excluded_points']}; "
          f"included duration: {area['included_duration_seconds']:.2f} s")
    if area["upper_threshold"] is not None:
        print(f"Upper threshold: {area['upper_threshold']:.3g}")


def choose_baseline(fig, ax, initial_value, selection, json_path, image_path,
                    store, close_on_confirm=False):
    """Allow vertical dragging; export the baseline only on explicit confirmation."""
    original_title = ax.get_title()
    seconds, values = ax.lines[0].get_data()
    baseline = ax.axhline(initial_value, color="crimson", linestyle="--", linewidth=1.5)
    ax.set_title("Drag the red baseline up or down, then click Confirm baseline")
    readout = ax.text(0.02, 0.97, f"Baseline: {initial_value:.3g}",
                      transform=ax.transAxes, va="top", color="crimson")
    fig.subplots_adjust(bottom=0.32)
    button_ax = fig.add_axes([0.7, 0.03, 0.25, 0.07])
    button = Button(button_ax, "Confirm baseline")
    state = {"dragging": False, "confirmed": False, "value": initial_value}

    def press(event):
        toolbar = getattr(fig.canvas, "toolbar", None)
        if toolbar and toolbar.mode:
            return
        if event.inaxes is ax and event.button == 1 and baseline.contains(event)[0]:
            state["dragging"] = True

    def move(event):
        if state["dragging"] and event.inaxes is ax and event.ydata is not None:
            state["value"] = float(event.ydata)
            baseline.set_ydata([event.ydata, event.ydata])
            readout.set_text(f"Baseline: {event.ydata:.3g}")
            fig.canvas.draw_idle()

    def release(event):
        state["dragging"] = False

    connections = [
        fig.canvas.mpl_connect("button_press_event", press),
        fig.canvas.mpl_connect("motion_notify_event", move),
        fig.canvas.mpl_connect("button_release_event", release),
    ]

    def confirm(event):
        if state["confirmed"]:
            return
        if state["value"] == 0 and selection.get("phase", "uptake") != "desorption":
            print("Choose a nonzero baseline to calculate the molecule count.")
            return
        state["confirmed"] = True
        for connection in connections:
            fig.canvas.mpl_disconnect(connection)
        button.disconnect_events()
        button_ax.remove()
        readout.remove()
        ax.set_title(original_title)
        save_baseline(fig, ax, baseline, state["value"], selection, json_path, image_path, store)
        fig.canvas.draw_idle()
        if close_on_confirm:
            plt.close(fig)

    button.on_clicked(confirm)
    print("Drag the red horizontal line, then click Confirm baseline.")
    print("Closing without confirming leaves the saved JSON and baseline picture unchanged.")
    plt.show(block=True)
    for connection in connections:
        fig.canvas.mpl_disconnect(connection)
    return state["confirmed"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "file", type=Path,
        help="Tab-separated measurement file, for example 231013_SS8_PET_HA_2.74e15_Reference_0_0_0.txt",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", type=Path, help="Shared uptake/desorption JSON path (defaults to input stem + .json beside output)")
    parser.add_argument("--uptake-json", type=Path,
                        help="Import uptake calibration from a legacy or shared JSON for --desorb")
    modes = parser.add_mutually_exclusive_group()
    phases = parser.add_mutually_exclusive_group()
    phases.add_argument("--uptake", action="store_true",
                       help="Choose only uptake points and baseline (default runs uptake then desorption)")
    phases.add_argument("--desorb", action="store_true",
                       help="Choose desorption points and baseline; combine with --baseline or --replay")
    modes.add_argument("--baseline", action="store_true",
                       help="Reuse selected points from JSON and choose only the baseline")
    modes.add_argument("--no-show", action="store_true",
                       help="Save a plain plot without interactive uptake selection")
    modes.add_argument("--replay", action="store_true",
                       help="Regenerate all plots using saved JSON points and baseline without interaction")
    args = parser.parse_args(argv)
    try:
        metadata = parse_filename_metadata(args.file)
    except ValueError as error:
        parser.error(f"Invalid measurement filename: {error}")
    full_workflow = not any((args.uptake, args.desorb, args.baseline,
                             args.replay, args.no_show))
    phase = "desorption" if args.desorb else "uptake"
    reuse_selection = args.baseline or args.replay
    if args.no_show or args.replay:
        plt.switch_backend("Agg")
    if args.output is None:
        suffix = "" if args.no_show else ("_desorb" if args.desorb else "_uptake")
        args.output = Path.cwd() / (
            f"{args.file.stem.strip()}{suffix}.png"
        )
    json_path = args.json or args.output.with_name(
        f"{args.file.stem.strip()}.json"
    )
    store = {"source_file": args.file.name, "phases": {}}
    selection = None
    if not args.no_show:
        try:
            if json_path.exists():
                store = read_selection_store(json_path, args.file)
            elif args.json is None:
                # Import existing phase files without modifying the originals.
                for suffix in ("uptake", "desorb"):
                    legacy_path = json_path.with_name(
                        f"{args.file.stem.strip()}_LockinAmplifier_{suffix}.json"
                    )
                    if legacy_path.exists():
                        legacy = read_selection_store(legacy_path, args.file)
                        store["phases"].update(legacy["phases"])
            if args.desorb and args.uptake_json:
                imported = read_selection_store(args.uptake_json, args.file)
                store["phases"]["uptake"] = imported["phases"]["uptake"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f"Cannot read selection data: {error}")
    # Metadata precedes both phase sections in the serialized JSON.
    store = {"source_file": store["source_file"], "metadata": metadata,
             "phases": store["phases"]}
    if reuse_selection:
        try:
            # Keep stored results unchanged until a baseline is confirmed.
            selection = dict(store["phases"][phase])
            if len(selection["points"]) != 2:
                raise ValueError("JSON must contain two selected points")
            indices = [point["measurement_index"] for point in selection["points"]]
            if not all(type(index) is int and index >= 0 for index in indices):
                raise ValueError("Invalid measurement indices")
        except (ValueError, KeyError, TypeError) as error:
            parser.error(f"Cannot reuse {phase} selection from {json_path}: {error}. Select points first.")

    if not args.no_show:
        flow_rate = metadata["flow_rate"]
        print(f"Flow rate from filename: {flow_rate:.2e} molecules/s")
        if args.desorb:
            try:
                uptake_settings = store["phases"]["uptake"]
                uptake_baseline = float(uptake_settings["baseline"]["LockinAmplifier"])
                if not isfinite(uptake_baseline) or uptake_baseline == 0:
                    raise ValueError("Uptake baseline must be finite and nonzero")
                print(f"Using uptake baseline from {json_path.name}")
            except (ValueError, KeyError, TypeError) as error:
                parser.error(f"Desorption requires a saved uptake baseline: {error}. "
                             "Run --uptake first, or import it with --uptake-json.")

    elapsed_seconds = []
    values = []
    start_time = None
    with args.file.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter="\t")
        if not {"Time", "LockinAmplifier"}.issubset(reader.fieldnames or []):
            parser.error("The file must contain Time and LockinAmplifier columns.")
        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp = datetime.strptime(row["Time"], "%d.%m.%Y %H:%M:%S.%f")
                value = float(row["LockinAmplifier"])
            except (ValueError, TypeError) as error:
                parser.error(f"Invalid data on line {line_number}: {error}")
            if start_time is None:
                start_time = timestamp
            elapsed_seconds.append((timestamp - start_time).total_seconds())
            values.append(value)

    if not values:
        parser.error("The file contains no measurements.")
    if reuse_selection:
        for index, point in zip(indices, selection["points"]):
            if (index >= len(values)
                    or elapsed_seconds[index] != point.get("elapsed_seconds")
                    or values[index] != point.get("LockinAmplifier")):
                parser.error("Saved points do not match the data. Select points again.")
        first, last = indices
        uptake_start, uptake_end = elapsed_seconds[first], elapsed_seconds[last]
        if uptake_end <= uptake_start:
            parser.error("Saved interval end must be after its start.")
        try:
            if args.replay and "LockinAmplifier" not in selection.get("baseline", {}):
                raise ValueError("Replay requires a saved baseline")
            saved_baseline = float(selection.get("baseline", {}).get("LockinAmplifier", values[first]))
            if not isfinite(saved_baseline):
                raise ValueError("Baseline must be finite")
            if args.replay and saved_baseline == 0 and not args.desorb:
                raise ValueError("Baseline must be nonzero to calculate the molecule count")
        except (TypeError, ValueError) as error:
            parser.error(f"Invalid saved baseline: {error}")
        print(f"Loaded {phase} points from {json_path.name}")

    fig, ax = plt.subplots(figsize=(10, 5))
    plotted_seconds, plotted_values = elapsed_seconds, values
    line, = ax.plot(plotted_seconds, plotted_values, linewidth=0.8)
    # Show elapsed seconds with the corresponding clock time from the file below.
    tick_seconds = max(60, ceil(max(elapsed_seconds) / 8 / 60) * 60)
    ax.xaxis.set_major_locator(MultipleLocator(tick_seconds))

    def format_elapsed(seconds, position):
        clock_time = start_time + timedelta(seconds=seconds)
        return f"{seconds:.0f}\n{clock_time:%H:%M}"

    ax.xaxis.set_major_formatter(FuncFormatter(format_elapsed))
    ax.set_xlim(left=0)
    ax.set_xlabel("Elapsed time (s)\nClock time (HH:MM, as recorded in file)")
    ax.set_ylabel("LockinAmplifier")
    ax.set_title("LockinAmplifier vs. elapsed time")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    original_path = (args.output if args.no_show else args.output.with_name(
        f"{args.file.stem.strip()}.png"
    ))
    if not args.no_show and original_path.resolve() == args.output.resolve():
        original_path = args.output.with_name(f"{args.output.stem}_original{args.output.suffix}")
    fig.savefig(original_path, dpi=200)
    print(f"Saved original plot to {original_path.name}")

    if not args.no_show:
        if not reuse_selection:
            print(f"Click the {phase} start and end on the plot (either order).")
            print("Right-click undoes a point; close the window to cancel without saving.")
        while not reuse_selection:
            ax.set_title(f"Select two points: {phase} start and end")
            fig.canvas.draw_idle()
            points = fig.ginput(n=2, timeout=0, show_clicks=True)
            if len(points) != 2 or not plt.fignum_exists(fig.number):
                print(f"Selection cancelled; original picture saved, {phase} pictures unchanged.")
                plt.close(fig)
                return
            # Snap each click to an actual measurement; use its time and signal value.
            indices = [
                min(range(len(values)), key=lambda i: abs(elapsed_seconds[i] - x))
                for x, _ in points
            ]
            indices.sort(key=lambda i: elapsed_seconds[i])
            first, last = indices
            uptake_start, uptake_end = elapsed_seconds[first], elapsed_seconds[last]
            if uptake_end > uptake_start:
                break
            print("Choose two different measurement times. Please try again.")

        selected = [
            (seconds, value) for seconds, value in zip(elapsed_seconds, values)
            if uptake_start <= seconds <= uptake_end
        ]
        plotted_seconds, plotted_values = zip(*selected)
        line.set_data(plotted_seconds, plotted_values)
        line.set_label(f"{phase.capitalize()} ({uptake_end - uptake_start:.2f} s)")
        ax.relim()
        ax.autoscale(enable=True, axis="y")
        ax.set_xlim(uptake_start, uptake_end)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.scatter([uptake_start, uptake_end], [values[first], values[last]],
                   color="darkorange", zorder=3, gid="uptake_endpoints")
        start_clock = start_time + timedelta(seconds=uptake_start)
        end_clock = start_time + timedelta(seconds=uptake_end)
        ax.set_title(
            f"LockinAmplifier — {phase}: {start_clock:%H:%M:%S}–{end_clock:%H:%M:%S}"
        )
        ax.legend(loc="upper right" if args.desorb else "best")
        fig.tight_layout()
        print(f"{phase.capitalize()}: {uptake_start:.2f}–{uptake_end:.2f} s "
              f"({start_clock:%Y-%m-%d %H:%M:%S} to {end_clock:%Y-%m-%d %H:%M:%S})")

    if not args.baseline:
        fig.savefig(args.output, dpi=200)
    print(f"Plotted {len(plotted_values)} measurements; "
          f"duration: {max(plotted_seconds) - min(plotted_seconds):.2f} s")
    if not args.baseline:
        print(f"Saved plot to {args.output.name}")
    if not args.no_show:
        selection = selection if reuse_selection else {
            "source_file": args.file.name,
            "image_file": args.output.name,
            "duration_seconds": uptake_end - uptake_start,
            "points": [
                {
                    "role": role,
                    "measurement_index": index,
                    "time": (start_time + timedelta(seconds=elapsed_seconds[index])).isoformat(),
                    "elapsed_seconds": elapsed_seconds[index],
                    "LockinAmplifier": values[index],
                }
                for role, index in zip(("start", "end"), indices)
            ],
        }
        selection["source_file"] = args.file.name
        selection["image_file"] = args.output.name
        selection["phase"] = phase
        selection["flow_rate"] = flow_rate
        selection["flow_rate_units"] = "molecules/s"
        if args.desorb:
            selection["uptake_baseline"] = uptake_baseline
            selection.pop("uptake_json", None)
        if not args.baseline:
            save_selection(selection, json_path, store)
            print(f"Saved selected points to {json_path.name}")
        initial_baseline = saved_baseline if reuse_selection else plotted_values[0]
        if args.replay:
            baseline = ax.axhline(initial_baseline, color="crimson", linestyle="--", linewidth=1.5)
            save_baseline(fig, ax, baseline, initial_baseline, selection, json_path, args.output, store)
        else:
            confirmed = choose_baseline(
                fig, ax, initial_baseline, selection, json_path, args.output,
                store, close_on_confirm=full_workflow,
            )
            if full_workflow and confirmed:
                desorb_output = args.output.with_name(
                    f"{args.output.stem.removesuffix('_uptake')}_desorb{args.output.suffix}"
                )
                print("Uptake saved. Continue with desorption point and baseline selection.")
                main([str(args.file), "--desorb", "--output", str(desorb_output),
                      "--json", str(json_path)])
    plt.close(fig)


if __name__ == "__main__":
    main()
