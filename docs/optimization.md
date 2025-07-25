# Optimization Scheduler

The optimization service periodically computes an hourly aggregate of resource metrics.
A job managed by **APScheduler** runs `store.create_hourly_continuous_aggregate()`
every hour. A separate job collects resource usage metrics using ``psutil`` every
minute. The scheduler starts with the FastAPI application and shuts down when the
service stops.

The latest samples can be retrieved via the ``/metrics/recent`` endpoint by
specifying a ``limit`` query parameter:

```bash
curl http://localhost:8000/metrics/recent?limit=5
```

## Cost alerts

The ``/cost_alerts`` endpoint returns a list of warnings when average usage or
estimated monthly cost surpass predefined thresholds. Integrate these alerts
with monitoring dashboards or notification systems to react quickly.
