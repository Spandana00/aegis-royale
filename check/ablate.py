"""Matched feature screen against a pinned third-party simulator; never an official score.

python3 check/ablate.py --sim-root ../reference-juan --seeds 3300-3315 --jobs 4
The simulator is supplied separately and is not shipped in the competition image.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OFF = dict(arm_commit=0, pickup_race=0, wide_band=0, focus_lock=0, fight_boost=0, pursuit_range=0, predictive_move=0,
           cover_all=0, final_fire=0, combat_cube=0, critical_recover=0)
ARMS = {
    "v10": {},
    "control": {},
    "cover_all": {"cover_all": 1},
    "final_fire": {"final_fire": 1},
    "combat_cube": {"combat_cube": 1},
    "critical_recover": {"critical_recover": 1},
    "cover_fire": {"cover_all": 1, "final_fire": 1},
    "cover_cube": {"cover_all": 1, "combat_cube": 1},
    "cover_fire_cube": {"cover_all": 1, "final_fire": 1, "combat_cube": 1},
    "arm_cube": {"arm_commit": 1, "combat_cube": 1},
    "reference_jishnu": {},
    "sentinel": {},
    "v11_arm": {"arm_commit": 1},
    "pickup_race": {"pickup_race": 1},
    "wide_band": {"wide_band": 1},
    "focus_lock": {"focus_lock": 1},
    "fight_boost": {"fight_boost": 40},
    "pursuit_range": {"pursuit_range": 1},
    "wide_pursuit": {"wide_band": 1, "pursuit_range": 1},
    "pickup_pursuit": {"pickup_race": 1, "pursuit_range": 1},
    "predictive_move": {"predictive_move": 1},
    "arm_predictive": {"arm_commit": 1, "predictive_move": 1},
    "pursuit_predictive": {"pursuit_range": 1, "predictive_move": 1},
    "arm_pursuit": {"arm_commit": 1, "pursuit_range": 1},
    "arm_boost": {"arm_commit": 1, "fight_boost": 40},
    "pickup_wide": {"pickup_race": 1, "wide_band": 1},
    "pickup_focus": {"pickup_race": 1, "focus_lock": 1},
    "wide_focus": {"wide_band": 1, "focus_lock": 1},
    "pickup_boost": {"pickup_race": 1, "fight_boost": 40},
    "wide_boost": {"wide_band": 1, "fight_boost": 40},
}


def metrics(rows):
    values = [16 - r["mech"]["place"] for r in rows]
    bots = [r["mech"] for r in rows]
    brains = [(b.get("bot_stats") or {}).get("brain", {}) for b in bots]
    armed_times = [b["first_weapon_t"] for b in brains if b.get("first_weapon_t") is not None]
    def count(key):
        return sum(b.get(key, 0) for b in bots)
    return {
        "n": len(rows), "mean_proxy_points": statistics.mean(values),
        "sd": statistics.stdev(values) if len(values) > 1 else 0,
        "mean_alive_s": statistics.mean(b["death_t"] if b.get("death_t") is not None else b.get("sim_t", 480) for b in bots),
        "mean_zone_damage": statistics.mean(b.get("zone_dmg", 0) for b in bots),
        "armed": sum(len(b.get("loadout", [])) >= 2 for b in bots),
        "armed_by_30_s": sum(t <= 30 for t in armed_times),
        "mean_first_weapon_s": statistics.mean(armed_times) if armed_times else None,
        "mean_cubes": statistics.mean(b.get("cubes", 0) for b in bots),
        "mean_damage_dealt": statistics.mean(b.get("dmg_dealt", 0) for b in bots),
        "deaths": dict(Counter(b.get("death_cause") for b in bots)),
        "late": count("late_replies"), "missed": count("missed_replies"),
        "tracebacks": count("bot_stderr_tracebacks"),
        "fallbacks": sum((b.get("bot_stats") or {}).get("fallbacks", 0) for b in bots),
        "module_errors": sum(sum((b.get("bot_stats") or {}).get("errors", {}).values()) for b in bots)
                         + sum(b.get("combat", {}).get("errors", 0) for b in brains),
    }


def summarize(path):
    raw = [json.loads(line) for line in path.read_text().splitlines() if line]
    grouped = {}
    for r in raw:
        if "error" in r:
            raise RuntimeError(r["error"])
        grouped.setdefault(r["arm"], []).append({"seed": r["seed"], "mech": r})
    output = {"kind": "third-party simulator diagnostics, not official placement", "arms": {}}
    base = {r["seed"]: 16 - r["mech"]["place"] for r in grouped.get("v10", [])}
    for name, rows in grouped.items():
        out = metrics(rows)
        paired = [16 - r["mech"]["place"] - base[r["seed"]] for r in rows if r["seed"] in base]
        if paired:
            out["paired_n"] = len(paired)
            out["paired_delta"] = statistics.mean(paired)
            # Conservative t multiplier for small samples; this is sampling uncertainty only.
            table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 10: 2.228,
                     15: 2.131, 20: 2.086, 30: 2.042, 40: 2.021, 60: 2., 120: 1.98}
            df = max(1, len(paired) - 1)
            critical = table[max(k for k in table if k <= df)]
            out["paired_95pct_halfwidth"] = critical * statistics.stdev(paired) / math.sqrt(len(paired)) if len(paired) > 1 else None
            out["better_tied_worse"] = [sum(x > 0 for x in paired), sum(x == 0 for x in paired), sum(x < 0 for x in paired)]
        output["arms"][name] = out
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sim-root", type=Path, required=True)
    p.add_argument("--baseline-root", type=Path, help="exact scored V10 checkout; otherwise control retains V11's pickup ordering")
    p.add_argument("--historic-root", action="append", default=[], help="arm=/absolute/path to use an immutable historical checkout")
    p.add_argument("--traces", type=Path, help="optional per-arm trace directory")
    p.add_argument("--seeds", default="3300-3315")
    p.add_argument("--arms", default="v10,v11_arm,pickup_race,wide_band,focus_lock,fight_boost,pursuit_range")
    p.add_argument("--join-per-loss", type=float, default=.6)
    p.add_argument("--mode", choices=("squad", "ffa"), default="squad")
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--out", type=Path, default=ROOT / "local-results/ablation.jsonl")
    a = p.parse_args()
    a.sim_root = a.sim_root.resolve()
    historic = dict(x.split("=", 1) for x in a.historic_root)
    a.out = a.out.resolve()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    if a.baseline_root:
        a.baseline_root = a.baseline_root.resolve()
    if a.out.exists():
        p.error("output exists; use a fresh path so previous experiments remain intact")
    sim_sha = subprocess.check_output(["git", "-C", str(a.sim_root), "rev-parse", "HEAD"], text=True).strip()
    metadata = {"sim_commit": sim_sha, "seeds": a.seeds, "mode": a.mode,
                "join_per_loss": a.join_per_loss, "jobs": a.jobs, "policy": str(ROOT),
                "baseline_root": str(a.baseline_root) if a.baseline_root else None,
                "control_note": "exact V10 checkout" if a.baseline_root else "V11 minus arm commitment; retains V11 inventory ordering and zero-HP guard",
                "policy_tree": subprocess.check_output(["git", "diff"], cwd=ROOT, text=True),
                "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "arms": {}}
    for name in a.arms.split(","):
        params = dict(OFF, **ARMS[name])
        root = Path(historic[name]).resolve() if name in historic else (a.baseline_root if name == "v10" and a.baseline_root else ROOT)
        entrypoint = root / "sentinel/main.py" if name == "sentinel" else (root / "pilot/main.py" if (root / "pilot/main.py").is_file() else root / "combat.py")
        source_dir = root / "sentinel" if name == "sentinel" else (root / "pilot" if (root / "pilot").is_dir() else root)
        metadata["arms"][name] = {"switches": params, "root": str(root), "entrypoint": str(entrypoint),
            "source_sha256": {str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
                              for f in sorted(source_dir.glob("*.py"))}}
        spec = ",".join(f"{k}={v}" for k, v in params.items())
        # All arms run the same source tree and production process guard. Only these switches differ.
        env = dict(os.environ, MECH_BRAIN=spec, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", PYTHONHASHSEED="0")
        temp = a.out.with_name(a.out.stem + "-" + name + ".jsonl")
        bot_cmd = f"{sys.executable} -B -u -m sentinel.main" if name == "sentinel" else f"{sys.executable} -B -u {entrypoint}"
        command = [sys.executable, "sim/run_matches.py", "--mode", a.mode,
                   "--bot", bot_cmd,
                   "--arena", str(ROOT / "arena"), "--seeds", a.seeds, "--jobs", str(a.jobs),
                   "--squad", f"join_per_loss={a.join_per_loss}", "--out", str(temp)]
        if name == "sentinel":
            command += ["--cwd", str(root)]
        if a.traces:
            command += ["--traces", str(a.traces.resolve() / name)]
        print(f"Starting {name}: {spec}", flush=True)
        with a.out.with_name(a.out.stem + "-" + name + ".log").open("w") as log:
            subprocess.run(command, cwd=a.sim_root, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        with a.out.open("a") as out:
            for line in temp.read_text().splitlines():
                row = json.loads(line)
                row["arm"] = name
                out.write(json.dumps(row, separators=(",", ":")) + "\n")
        report = summarize(a.out)
        print(json.dumps({name: report["arms"][name]}), flush=True)
        a.out.with_suffix(".summary.json").write_text(json.dumps(report, indent=2) + "\n")
        a.out.with_suffix(".meta.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    main()
