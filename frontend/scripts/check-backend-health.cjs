/**
 * Backend health check script.
 * Checks that the API gateway is healthy before running integrated tests.
 *
 * Usage: node scripts/check-backend-health.cjs [baseUrl]
 *   baseUrl defaults to http://localhost:8000
 *
 * Exit codes:
 *   0 - OK
 *   1 - Health check failed
 *   2 - Connection refused (server not running)
 */

const BASE_URL = process.argv[2] || 'http://localhost:8000';
const HEALTH_URL = `${BASE_URL}/health`;
const MAX_RETRIES = 5;
const RETRY_DELAY_MS = 2000;

async function checkHealth(retries = MAX_RETRIES) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(HEALTH_URL, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const body = await response.text();
        console.log(`✓ Backend healthy (${BASE_URL}): ${response.status} ${body.substring(0, 120)}`);
        return true;
      }

      console.warn(`⚠  Attempt ${attempt}/${retries}: backend returned ${response.status}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`⚠  Attempt ${attempt}/${retries}: ${msg}`);
    }

    if (attempt < retries) {
      console.log(`   Retrying in ${RETRY_DELAY_MS / 1000}s...`);
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    }
  }

  console.error(`✗ Backend HEALTH CHECK FAILED after ${retries} attempts at ${HEALTH_URL}`);
  console.error('  Make sure the backend services are running:');
  console.error('    docker compose up -d');
  return false;
}

checkHealth()
  .then((ok) => process.exit(ok ? 0 : 1))
  .catch((err) => {
    console.error('Health check error:', err);
    process.exit(2);
  });
