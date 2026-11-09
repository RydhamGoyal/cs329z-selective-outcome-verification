"""Descriptive success-versus-readback figure; no inferential claim from five tasks."""
import argparse
import csv
import os
import tempfile
from pathlib import Path

os.environ.setdefault('MPLBACKEND', 'Agg')
os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cs329z_mpl'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path(tempfile.gettempdir()) / 'cs329z_cache'))
import matplotlib.pyplot as plt

COLORS = {'none': '#64748b', 'final-only': '#8b5cf6', 'exhaustive': '#ef4444',
          'random': '#f59e0b', 'risk': '#0d9488'}


def load(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--development', type=Path, default=Path('outputs/benchmark_final_dev/policy_summary.csv'))
    parser.add_argument('--heldout', type=Path, default=Path('outputs/benchmark_heldout/policy_summary.csv'))
    parser.add_argument('--out', type=Path, default=Path('report/figures/policy_tradeoff.png'))
    args = parser.parse_args()
    datasets = [(name, path) for name, path in [('Development', args.development), ('Held-out', args.heldout)] if path.exists()]
    if not datasets:
        raise SystemExit('No policy_summary.csv found; run scripts.summarize_comparison first')
    fig, axes = plt.subplots(1, len(datasets), figsize=(5.8 * len(datasets), 4.2), sharey=True)
    if len(datasets) == 1:
        axes = [axes]
    for ax, (name, path) in zip(axes, datasets):
        rows = load(path)
        for row in rows:
            policy = row['policy']
            tasks = int(row['tasks'])
            x = int(row['readback_calls']) / tasks
            y = float(row['success_rate'])
            ax.scatter(x, y, s=110, color=COLORS[policy], zorder=3)
            offset = (-48, -13) if policy == 'random' else (5, 6)
            ax.annotate(policy, (x, y), xytext=offset, textcoords='offset points', fontsize=9)
        ax.set_title(f'{name} (n={rows[0]["tasks"]} tasks per policy)')
        ax.set_xlabel('Mean readback calls per task')
        ax.set_xlim(left=-.2)
        ax.set_ylim(-.05, 1.05)
        ax.grid(alpha=.18)
    axes[0].set_ylabel('Official tau2 success rate')
    fig.suptitle('Observed reliability and verification overhead', fontsize=13, fontweight='bold')
    fig.text(.5, .01, 'Descriptive single-seed results; model trajectories vary and no natural FAIL was observed.',
             ha='center', fontsize=8, color='#475569')
    fig.tight_layout(rect=(0, .04, 1, .94))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=180)
    print(args.out)


if __name__ == '__main__':
    main()
