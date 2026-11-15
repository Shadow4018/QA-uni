# Послідовний запуск усіх профілів навантаження (baseline, load, stress, spike).
# Запускати з папки sut-b, коли API вже працює (python -m uvicorn store.api:app --host 127.0.0.1 --port 8080).
#
#   .\k6\run_all.ps1                      # повний запуск
#   .\k6\run_all.ps1 -Scale 0.2           # скорочений пробний прогін
#   .\k6\run_all.ps1 -Types load,spike    # лише вибрані профілі
#   .\k6\run_all.ps1 -ResetDb             # перед кожним профілем очищати таблиці (потрібні psql і змінні DB_*)
param(
  [string]$BaseUrl = "http://127.0.0.1:8080",
  [string[]]$Types = @("baseline", "load", "stress", "spike"),
  [double]$Scale = 1.0,
  [switch]$ResetDb
)

New-Item -ItemType Directory -Force -Path "k6\results" | Out-Null
k6 version

foreach ($t in $Types) {
  Write-Host ""
  Write-Host "=============== $t ==============="

  if ($ResetDb) {
    # Однакові початкові умови для всіх запусків. Пароль береться з DB_PASSWORD.
    $env:PGPASSWORD = $env:DB_PASSWORD
    psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME `
      -c "TRUNCATE order_items, orders, products RESTART IDENTITY;"
  }

  $env:K6_WEB_DASHBOARD = "true"
  $env:K6_WEB_DASHBOARD_OPEN = "false"
  $env:K6_WEB_DASHBOARD_PERIOD = "2s"
  $env:K6_WEB_DASHBOARD_EXPORT = "k6\results\report-$t.html"

  k6 run -e BASE_URL=$BaseUrl -e TEST_TYPE=$t -e SCALE=$Scale `
    --summary-export "k6\results\summary-$t.json" k6\store_load_test.js

  Write-Host "Код завершення: $LASTEXITCODE  (0 = усі thresholds виконано, 99 = хоча б один threshold порушено)"
  Start-Sleep -Seconds 10   # пауза, щоб система заспокоїлась між запусками
}

Write-Host ""
Write-Host "Звіти: k6\results\report-<тип>.html, підсумки: k6\results\summary-<тип>.json"
