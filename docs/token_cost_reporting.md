# Token and Cost Reporting

`draftpaper token-report --project <project>` reads the append-only `token_ledger.jsonl` and returns:

- total input and output tokens, using actual values when recorded and estimates otherwise;
- totals grouped by stage and model;
- the latest active manuscript-writing packet for each section task;
- comparison with the manuscript input-token budget;
- monetary cost only when the producing runtime recorded a cost value.

Draftpaper-loop does not maintain a hidden provider price table and does not infer currency cost from token counts. If only some receipts contain `recorded_cost_usd`, the report marks monetary coverage as partial. If no receipt contains a recorded cost, it reports that a price contract is unavailable rather than fabricating a number.

The report is read-only and uses schema `dpl.token_cost_report.v1`. Historical retries remain in lifetime totals, while the active manuscript budget uses only the latest packet for each writing task.
