<!-- Parent: ../../AGENTS.md -->
<!-- Generated: 2026-04-09 | Updated: 2026-04-09 -->

# skill-creator (v1.0.0)

## Purpose

Claude Code skill creation, improvement, and benchmarking. Fork of Anthropic's example skill-creator.

## Key Files

### Skills
- `skills/skill-creator/` - Skill creation workflow scripts, agents, evaluation tools

## Subdirectories

- `skills/skill-creator/` - Contains `scripts/`, `agents/`, `assets/`, `eval-viewer/`, `references/` subdirectories

## Scripts

Located in `skills/skill-creator/scripts/`:
- `run_eval.py` - Run skill evaluations
- `run_loop.py` - Iterative skill improvement loop
- `aggregate_benchmark.py` - Aggregate evaluation results
- Additional utility scripts for skill development workflow

## AI Instructions

Eval-driven skill improvement workflow. Create skills, run benchmarks, analyze results, iterate improvements. Follow Claude Code skill structure conventions (SKILL.md, agents/, scripts/, references/). Use evaluation metrics to guide skill refinement.
