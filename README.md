# CS329Z Final Project

I built an AI customer-service agent that handles retail tasks in [tau2-bench](https://github.com/sierra-research/tau2-bench). When the agent changes an order, my system can read the order back and check whether the change matches what the customer asked for. I compare several ways of deciding when to check, including checking every change and checking only changes that appear risky. The setup below pins tau2-bench to commit `033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f`. I did not change its source code.

**What I have so far:** I ran 70 benchmark trials and built a viewer with five examples. In one held-out set, checking risky changes made 14 readbacks and completed 2 of 5 tasks. The agent with no checks made no readbacks and completed 3 of 5. Across three held-out seeds, both approaches completed 10 of 15 tasks. These results do not show a reliability gain yet.

## Explore the saved runs

Public demo: [cs329z-selective-outcome-verificati.vercel.app](https://cs329z-selective-outcome-verificati.vercel.app/)

From the repository folder, launch the local viewer. It builds a sanitized replay bundle from the included traces and serves only the `demo/` directory. This command needs no API key and makes no model calls.

```bash
python3 -m scripts.serve_demo
```

Open `http://127.0.0.1:8765`. The home page explains the experiment. **Saved traces** contains five named examples chosen to show the mechanism and its limits; each has a short explanation of what happened and why it matters. The repeat trials are summarized in **Results** rather than listed individually. Click a tool step to inspect its arguments, response, risk features, and independent readback. **Replay simulation** presents the saved run at a reading pace; the slider adjusts playback speed. Replay does not start a new experiment. The two controlled fault traces are labeled separately from natural benchmark trials. Saved runs remain under `outputs/` for reproduction.

To publish the same static viewer on Vercel, regenerate its five sanitized traces and deploy from `demo/`. The deployment does not need a model key or the tau2 runtime.

```bash
npm install -g vercel
vercel login
python3 -m scripts.build_demo_data
cd demo
vercel deploy --prod
```

## Setup

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). Clone tau2 as a sibling of this project folder, then install its frozen lockfile:

```bash
git clone https://github.com/sierra-research/tau2-bench.git ../tau2-bench
git -C ../tau2-bench checkout 033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f
(cd ../tau2-bench && uv sync --extra dev --frozen && uv run --frozen tau2 check-data)
```

Create a private `.env` in this project folder from `.env.example` and set `OPENROUTER_API_KEY` for the course-credit configuration. The runner loads this file explicitly. Do not commit it. To check authentication without a model call:

```bash
../tau2-bench/.venv/bin/python scripts/check_openrouter_key.py
```

All commands below run from this project folder. Define the benchmark import path once per Terminal session:

```bash
export PYTHONPATH="$PWD:$(cd ../tau2-bench && pwd)/src"
```

## Tests and a single official run

```bash
../tau2-bench/.venv/bin/python -m pytest -q tests
../tau2-bench/.venv/bin/python -m scripts.real_tool_fault
../tau2-bench/.venv/bin/python -m selective_verify.run \
  --task-id 34 --policy risk --model openrouter/openai/gpt-4.1-mini \
  --out outputs/smoke_task34_risk.json
```

The tests and `scripts.real_tool_fault` require no API key. The last command incurs model charges and writes an official tau2 reward and structured trace. Each model-backed run uses at most 40 orchestrator steps and a 180-second timeout.

## Reproduce the experiments

The development suite is task IDs `34, 22, 72, 41, 87` from tau2's train split. The held-out suite is `17, 42, 71, 97, 102` from its test split. These tasks have reference writes and empty natural-language assertions, so the unchanged official `EvaluationType.ALL` evaluator does not require a separate judge model. This convenience subset limits generality.

```bash
../tau2-bench/.venv/bin/python -m scripts.run_dev_suite \
  --output-dir outputs/benchmark_final_dev --max-estimated-usd 5
../tau2-bench/.venv/bin/python -m scripts.run_heldout_suite \
  --development-dir outputs/benchmark_final_dev \
  --output-dir outputs/benchmark_heldout --max-estimated-usd 5
python3 -m scripts.summarize_comparison outputs/benchmark_final_dev
python3 -m scripts.summarize_comparison outputs/benchmark_heldout
python3 -m scripts.audit_verdicts outputs/benchmark_final_dev/*_task*_seed*_*.json
python3 -m scripts.audit_verdicts outputs/benchmark_heldout/*_task*_seed*_*.json
python3 -m scripts.validate_traces outputs/benchmark_final_dev outputs/benchmark_heldout outputs/benchmark_repeats
```

Both suite runners resume completed traces and stop before their `$5` public-list-price *estimate* cap. They use `openrouter/openai/gpt-4.1-mini` for both the actor and user simulator, temperature 0, seed 42, and the same domain policy and agent prompt. The risk threshold is `.55`. The random checkpoint probability is calibrated from development risk traces only (`10/14 = 0.7143`) and frozen in `outputs/benchmark_heldout/run_config.json`. Random and risk matched exactly in development (10 checkpoints each); realized held-out budgets also matched (7 each). Paired seeds do not force identical model trajectories.

For the optional repeated-seed and controlled-fault runs:

```bash
../tau2-bench/.venv/bin/python -m scripts.finish_experiments
```

The controlled fault is explicitly excluded from natural task-success comparisons. It persists a wrong address while the write response reports the requested address, so only independent readback reveals the discrepancy. Tau2's official evaluator replays recorded tool arguments; its reward does **not** score this injected storage fault. The controlled trace instead records whether the final persisted street was repaired.

The traces are JSON; per-run tables are `comparison.csv`, aggregate tables are `policy_summary.csv`, and the descriptive figure is `report/figures/policy_tradeoff.png`. Regenerate the figure with `python3 -m scripts.plot_results` in an environment with `matplotlib==3.8.4`.

The viewer reads saved JSON traces. It shows customer instructions, state-changing actions, risk features, readback evidence, verdicts, and official reward. The injected fault is excluded from natural benchmark success rates. To regenerate its data without serving the UI, run `python3 -m scripts.build_demo_data`.

## Architecture and limits

`selective_verify/core.py` overrides tau2's synchronous `Orchestrator._execute_tool_calls` seam. Tau2's `tool_mutates_state` metadata classifies writes; readback uses ordinary retail read tools. The deterministic score uses impact, downstream dependence, irreversibility, and outcome uncertainty with weights `.35/.25/.20/.20`. A selected write gets pre/post readback, and the verifier returns `PASS`, `FAIL`, or `INCONCLUSIVE`. A `FAIL` gives the actor one correction opportunity. The verifier sees only user-visible dialogue and ordinary tool evidence, never task gold or reward. Final-only verification happens after task completion and cannot affect reward.

The current verifier has narrow rules for user-stated street addresses and cancellation. Item changes and implicit addresses are often `INCONCLUSIVE`. The uncertainty feature is static for successful tool responses, and weights are manually set rather than learned. No natural `FAIL` was detected in the seed-42 suites; observed success differences cannot be causally attributed to verification. OpenRouter/LiteLLM did not report actual USD charges, so cost fields use public list-price estimates. A Shepherd-inspired AI-supervisor baseline remains future work; this is not a Shepherd reproduction.

The comparison tables and run configurations are stored with the saved traces under `outputs/benchmark_final_dev`, `outputs/benchmark_heldout`, and `outputs/benchmark_repeats`.
