import { http, check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// Custom metrics cho SLI/SLO
const errorRate = new Rate("errors");
const latencyP95 = new Trend("latency_p95");
const httpRequests = new Counter("http_requests_total");

export const options = {
  stages: [
    { duration: "1m", target: 10 },   // warm-up
    { duration: "3m", target: 50 },   // spike load (flash-sale / inventory spike)
    { duration: "2m", target: 0 },    // ramp-down
  ],
  thresholds: {
    // SLI: error rate < 1%
    errors: ["rate < 0.01"],
    // SLI: p95 latency < 500ms
    latency_p95: ["p(95) < 500"],
    // SLI: p99 latency < 1000ms
    http_req_duration: ["p(99) < 1000"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

export default function () {
  // 1) Health check (smoke)
  const healthRes = http.get(`${BASE_URL}/health/live`);
  httpRequests.add(1);
  errorRate.add(healthRes.status >= 500);
  check(healthRes, {
    "health live is 200": (r) => r.status === 200,
  });

  sleep(0.5);

  // 2) Inventory read spike (flash-sale scenario)
  const invRes = http.get(`${BASE_URL}/api/v1/inventory/balances`);
  httpRequests.add(1);
  latencyP95.add(invRes.timings.duration);
  errorRate.add(invRes.status >= 500);
  check(invRes, {
    "inventory balances is 200/429": (r) => r.status === 200 || r.status === 429,
    "inventory latency < 500ms": (r) => r.timings.duration < 500,
  });

  sleep(0.5);
}
