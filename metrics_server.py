import os
from prometheus_client import start_http_server, multiprocess, CollectorRegistry, ProcessCollector

if __name__ == '__main__':
    # Ensure directory exists
    metrics_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR', '/tmp/prometheus_multiproc')
    os.makedirs(metrics_dir, exist_ok=True)

    # Create registry
    registry = CollectorRegistry()

    # Add process collector to the registry
    ProcessCollector(registry=registry)

    # Add multiprocess collector
    multiprocess.MultiProcessCollector(registry)

    # Start metrics server
    metrics_port = int(os.environ.get('PROMETHEUS_METRICS_PORT', 9105))
    start_http_server(metrics_port, registry=registry)

    # Keep the process running
    while True:
        try:
            import time

            time.sleep(1)
        except KeyboardInterrupt:
            break