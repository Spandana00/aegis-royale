"""Disqualify strength forecasts that reverse known official regressions."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def evaluate(root=ROOT):
    history = json.loads((root/'docs/v19_official_history.json').read_text())
    modeled = json.loads((root/'docs/v18_experiments.json').read_text())
    actual_delta = (history['latest_regression']['integer_total'] - history['baseline']['integer_total']) / 48
    proxy_delta = modeled['pooled']['selected_validation']['spacing70']['matched_difference_from_control']
    sign_agrees = actual_delta * proxy_delta > 0
    return {'qualified_for_strength_forecasts': False,
            'known_comparison': 'V18 versus V17', 'official_delta': actual_delta,
            'modeled_delta': proxy_delta, 'direction_agrees': sign_agrees,
            'reason': 'Known official regression predicted as improvement.' if not sign_agrees else
                      'One comparison is insufficient; require multiple independent scored comparisons.',
            'allowed_uses': ['Protocol and timing checks', 'Hypothesis generation', 'Mechanistic diagnostics'],
            'required_before_forecasting': ['Correctly rank V15/V14, V16/V14, V17/V16 and V18/V17 on matched settings.',
                'Validate on additional official results not used to tune the simulator.',
                'Report model discrepancy separately from sampling uncertainty.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--require-qualified', action='store_true')
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    report = evaluate()
    text = json.dumps(report, indent=2)+'\n'
    if args.out:
        args.out.write_text(text)
    print(text, end='')
    if args.require_qualified and not report['qualified_for_strength_forecasts']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
