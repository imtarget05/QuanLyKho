import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export const options = {
  stages: [
    { duration: '1m', target: 20 },
    { duration: '2m', target: 50 },
    { duration: '1m', target: 0 },
  ],
  thresholds: {
    errors: ['rate<0.05'],
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';

export default function () {
  // Health check
  let res = http.get(`${BASE_URL}/health/live`);
  check(res, {
    'health live is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  // Inventory list
  res = http.get(`${BASE_URL}/api/v1/inventory/items`);
  check(res, {
    'inventory list is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1);

  // Cash sim balance
  res = http.get(`${BASE_URL}/api/v1/cash-sim/balances`);
  check(res, {
    'cash-sim balances is 200': (r) => r.status === 200,
  }) || errorRate.add(1);

  sleep(1);
}