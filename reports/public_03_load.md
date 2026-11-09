# Load test — public_03_load (12 workflows, ~650k dials/day)

Machine: Darwin arm64, 10 CPUs. Controller and simulator on the same box.

Controller total wall-clock (after simulator was ready, incl. 7 history days ingest + 5 live days): 166s
Simulator RSS at end: 158 MB

```
sim time D5 00:00; ticks 247; events ingested 9,737,695 at 78,483 events/s
decide time per tick p50 0.006s p95 0.107s max 0.951s
wall-clock per simulated day 0.47 min (incl. simulator); peak RSS 345 MB
credits remaining 400.0; spent 0
pending approvals 0; decisions/sim-hour 2.4
proposals: applied 63, rejected 2
```

Per-day breakdown (wall seconds spent per simulated day, from the metrics table):

```
D0|6377588|32.5|1.0|5.4|345.0|196451.0
D1|840029|13.4|1.5|5.5|345.0|62498.0
D2|840034|22.7|2.1|6.1|345.0|37066.0
D3|840023|26.0|2.1|7.9|345.0|32284.0
D4|840021|29.5|1.7|8.0|345.0|28490.0
D5|0|0.0|0.0|0.0|345.0|0.0
```

Decision lag per tick (ingest + decide, seconds): p50/p95/max
```
0.39|0.87|24.016
```
[ctl] D5 00:00 events+0 ingest 0.00s decide 0.00s credits 400 pending 0 rss 345MB
           344621056  maximum resident set size
