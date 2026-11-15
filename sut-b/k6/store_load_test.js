// Навантажувальне тестування REST API "Інтернет-магазин" (SUT B, варіант 04) за допомогою k6.
//
// Сценарій однієї ітерації (один віртуальний користувач):
//   1. POST /products          -> створює унікальний товар, з відповіді беремо product_id
//   2. POST /orders            -> створює замовлення на цей товар, з відповіді беремо order_id
//   3. GET  /orders/{id}       -> читає створене замовлення й звіряє його з тим, що створили
// Між ітераціями — пауза (think time) THINK_TIME секунд, однакова для всіх профілів.
//
// Тип тесту вибирається змінною TEST_TYPE: baseline | load | stress | spike.
// Приклад:  k6 run -e TEST_TYPE=load k6/store_load_test.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

// ---------- Параметри середовища ----------
const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const TEST_TYPE = __ENV.TEST_TYPE || 'baseline';
const SCALE = Number(__ENV.SCALE) || 1;          // 0.2 = скорочений "пробний" прогін
const LOAD_VUS = Number(__ENV.LOAD_VUS) || 10;   // рівень очікуваного робочого навантаження
const PEAK_VUS = Number(__ENV.PEAK_VUS) || (TEST_TYPE === 'spike' ? 80 : 100);
const THINK_TIME = 1;                            // секунд між ітераціями
const RUN_ID = __ENV.RUN_ID || Date.now().toString(36);  // унікальність sku/reference між запусками

// Тривалість у секундах -> рядок k6 з урахуванням SCALE (мінімум 1 с)
const sec = (s) => `${Math.max(1, Math.round(s * SCALE))}s`;

// ---------- Профілі навантаження (workload profile) ----------
// Модель закрита: VU повторюють сценарій, тому кількість запитів/с залежить від тривалості ітерації та пауз.
const PROFILES = {
  // Мінімальне контрольне навантаження — точка відліку для порівняння.
  baseline: {
    executor: 'constant-vus',
    vus: 2,
    duration: sec(60),
  },
  // Очікуване робоче навантаження: розгін, плато, спад.
  load: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: sec(30), target: LOAD_VUS },
      { duration: sec(120), target: LOAD_VUS },
      { duration: sec(30), target: 0 },
    ],
    gracefulRampDown: '10s',
  },
  // Поступове зростання понад норму до пікового рівня.
  stress: {
    executor: 'ramping-vus',
    startVUs: 0,
    stages: [
      { duration: sec(30), target: Math.round(PEAK_VUS * 0.2) },
      { duration: sec(60), target: Math.round(PEAK_VUS * 0.4) },
      { duration: sec(60), target: Math.round(PEAK_VUS * 0.7) },
      { duration: sec(60), target: PEAK_VUS },
      { duration: sec(30), target: 0 },
    ],
    gracefulRampDown: '10s',
  },
  // Різкий короткий стрибок і подальше відновлення.
  spike: {
    executor: 'ramping-vus',
    startVUs: 5,
    stages: [
      { duration: sec(30), target: 5 },          // нормальний фон
      { duration: sec(10), target: PEAK_VUS },   // різкий стрибок
      { duration: sec(30), target: PEAK_VUS },   // утримання піку
      { duration: sec(10), target: 5 },          // різкий спад
      { duration: sec(60), target: 5 },          // відновлення
      { duration: sec(10), target: 0 },
    ],
    gracefulRampDown: '10s',
  },
};

// ---------- Критерії прийнятності (thresholds), задані ДО запуску ----------
// p95 — час відповіді (мс), err — допустима частка помилкових HTTP-запитів, chk — частка успішних checks.
const CRITERIA = {
  baseline: { p95: 200, err: 0.01, chk: 0.99 },
  load:     { p95: 500, err: 0.01, chk: 0.99 },
  stress:   { p95: 1500, err: 0.05, chk: 0.95 },
  spike:    { p95: 1500, err: 0.05, chk: 0.95 },
};

if (!PROFILES[TEST_TYPE]) {
  throw new Error(`Невідомий TEST_TYPE="${TEST_TYPE}". Допустимо: ${Object.keys(PROFILES).join(', ')}`);
}
const crit = CRITERIA[TEST_TYPE];

export const options = {
  scenarios: { [TEST_TYPE]: PROFILES[TEST_TYPE] },
  tags: { testtype: TEST_TYPE },
  thresholds: {
    http_req_duration: [`p(95)<${crit.p95}`],
    http_req_failed: [`rate<${crit.err}`],
    checks: [`rate>${crit.chk}`],
    // Окремий критерій для операції читання (стабільна назва через tag name, без унікальних id в URL)
    'http_req_duration{name:GET /orders/{id}}': [`p(95)<${crit.p95}`],
  },
};

// Власна метрика: кількість повністю успішних бізнес-сценаріїв (не плутати з HTTP-запитами)
const scenariosCompleted = new Counter('full_scenarios_completed');

const JSON_HEADERS = { 'Content-Type': 'application/json' };
const TIMEOUT = '10s';

// Безпечне читання поля з JSON: при помилці мережі/неJSON-тілі повертає undefined, а не кидає виняток
function field(response, path) {
  try {
    return response.json(path);
  } catch (e) {
    return undefined;
  }
}

function runScenario() {
  // --- Крок 1: створення товару (sku має бути унікальним — обмеження UNIQUE у БД) ---
  const sku = `K6-${RUN_ID}-${__VU}-${__ITER}`;
  const productRes = http.post(
    `${BASE_URL}/products`,
    JSON.stringify({ sku: sku, unit_price: 60000, stock: 10, on_sale: false }),
    { headers: JSON_HEADERS, timeout: TIMEOUT, tags: { name: 'POST /products' } },
  );
  const productId = field(productRes, 'id');
  const productOk = check(productRes, {
    'POST /products: status 201': (r) => r.status === 201,
    'POST /products: id returned': () => Number.isInteger(productId) && productId > 0,
  });
  if (!productOk) {
    return; // передумова не виконана — наступні запити з невалідним id не надсилаємо
  }

  // --- Крок 2: створення замовлення; product_id береться з відповіді кроку 1 (dynamic data) ---
  const orderRes = http.post(
    `${BASE_URL}/orders`,
    JSON.stringify({
      reference: `K6-O-${RUN_ID}-${__VU}-${__ITER}`,
      product_id: productId,
      quantity: 1,
      premium: false,
      coupon_claimed: false,
    }),
    { headers: JSON_HEADERS, timeout: TIMEOUT, tags: { name: 'POST /orders' } },
  );
  const orderId = field(orderRes, 'id');
  const orderOk = check(orderRes, {
    'POST /orders: status 201': (r) => r.status === 201,
    'POST /orders: id returned': () => Number.isInteger(orderId) && orderId > 0,
  });
  if (!orderOk) {
    return;
  }

  // --- Крок 3: читання замовлення; order_id береться з відповіді кроку 2 ---
  const getRes = http.get(`${BASE_URL}/orders/${orderId}`, {
    timeout: TIMEOUT,
    tags: { name: 'GET /orders/{id}' }, // стабільна назва замість унікального URL
  });
  const readOk = check(getRes, {
    'GET /orders/{id}: status 200': (r) => r.status === 200,
    'GET /orders/{id}: same order, CONFIRMED': () =>
      field(getRes, 'id') === orderId && field(getRes, 'status') === 'CONFIRMED',
  });
  if (readOk) {
    scenariosCompleted.add(1);
  }
}

export default function () {
  runScenario();
  sleep(THINK_TIME);
}
