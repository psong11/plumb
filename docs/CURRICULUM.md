# Where this is going

Modules 01–03 are built. 04–06 are the ladder they were designed for.

**04 · The agent, three tools.** `list_metrics`, `describe_metric`, `run_metric(spec)`.
No raw SQL, no escape hatch. The constraint is the lesson — you'll be surprised how far
it gets, and the failures will be about *ambiguity*, not about SQL.

**05 · The eval harness.** 50 questions with verified gold answers, automated scoring.
Then go break something in Module 02 and watch the evals catch it. This is the artifact
that makes engineers take a PM seriously — most arrive with a demo, almost none arrive
with a regression suite.

**06 · Red team week.** Try to make your own agent lie. Ambiguous metric names. Questions
requiring a join it can't do. Prompt injection buried in a retrieved document. An
aggregate that re-identifies an individual. Write up every failure. Showing the failure
modes before someone else finds them is worth more than any demo.

**Later, if it earns its place:** an A2A envelope (a second agent calling the first over
MCP, forced to carry provenance) and row-level authorization enforced in the catalog
rather than the prompt.
