# Послідовний запуск JMeter-профілів (baseline, load, stress, spike) у non-GUI режимі.
# Запускати з папки sut-b, коли API вже працює (python -m uvicorn store.api:app --host 127.0.0.1 --port 8080).
#
#   .\jmeter\run_jmeter.ps1                                   # повний запуск
#   .\jmeter\run_jmeter.ps1 -Scale 0.2                        # скорочений пробний прогін
#   .\jmeter\run_jmeter.ps1 -Types load,spike                 # лише вибрані профілі
#   .\jmeter\run_jmeter.ps1 -JMeter "C:\tools\apache-jmeter-5.6.3\bin\jmeter.bat"
#   .\jmeter\run_jmeter.ps1 -ResetDb                          # очищати таблиці перед профілем (psql + змінні DB_*)
#
# Рівні навантаження ті самі, що в k6: load = 10 VU, пік stress = 100 VU, пік spike = 80 VU
# (змінюються через -LoadVus / -PeakVus; для порівняння з k6 задавайте однакові значення в обох інструментах).
param(
  [string]$JMeter = "jmeter",
  [string]$ApiHost = "127.0.0.1",
  [int]$Port = 8080,
  [string[]]$Types = @("baseline", "load", "stress", "spike"),
  [double]$Scale = 1.0,
  [int]$LoadVus = 10,
  [int]$StressPeak = 100,
  [int]$SpikePeak = 80,
  [switch]$ResetDb
)

function S([double]$seconds) { [Math]::Max(1, [int][Math]::Round($seconds * $Scale)) }   # масштабування тривалості

function Props($type) {
  switch ($type) {
    "baseline" { return @{ g1_threads = 2; g1_ramp = 1; g1_delay = 0; g1_duration = (S 60) } }
    "load" {     return @{ g1_threads = $LoadVus; g1_ramp = (S 30); g1_delay = 0; g1_duration = (S 150) } }
    "stress" {
      $p = $StressPeak
      $a = [int][Math]::Round($p * 0.2); $b = [int][Math]::Round($p * 0.4); $c = [int][Math]::Round($p * 0.7)
      $end = S 210
      $d2 = S 30; $d3 = S 90; $d4 = S 150
      return @{
        g1_threads = $a;      g1_ramp = (S 30); g1_delay = 0;   g1_duration = $end
        g2_threads = $b - $a; g2_ramp = (S 60); g2_delay = $d2; g2_duration = [Math]::Max(1, $end - $d2)
        g3_threads = $c - $b; g3_ramp = (S 60); g3_delay = $d3; g3_duration = [Math]::Max(1, $end - $d3)
        g4_threads = $p - $c; g4_ramp = (S 60); g4_delay = $d4; g4_duration = [Math]::Max(1, $end - $d4)
      }
    }
    "spike" {
      return @{
        g1_threads = 5;                 g1_ramp = 1;      g1_delay = 0;      g1_duration = (S 140)
        g2_threads = $SpikePeak - 5;    g2_ramp = (S 10); g2_delay = (S 30); g2_duration = (S 40)
      }
    }
  }
}

New-Item -ItemType Directory -Force -Path "jmeter\results" | Out-Null
& $JMeter -v

foreach ($t in $Types) {
  Write-Host ""
  Write-Host "=============== $t ==============="

  if ($ResetDb) {
    $env:PGPASSWORD = $env:DB_PASSWORD
    psql -h $env:DB_HOST -p $env:DB_PORT -U $env:DB_USER -d $env:DB_NAME `
      -c "TRUNCATE order_items, orders, products RESTART IDENTITY;"
  }

  $jtl = "jmeter\results\run-$t.jtl"
  $report = "jmeter\results\report-$t"
  # JMeter дописує в існуючий JTL, а папка звіту має бути порожньою — прибираємо попередній запуск
  Remove-Item -Force -ErrorAction SilentlyContinue $jtl
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $report

  $args = @("-n", "-t", "jmeter\store_$t.jmx", "-l", $jtl, "-e", "-o", $report,
            "-j", "jmeter\results\jmeter-$t.log",
            "-Jhost=$ApiHost", "-Jport=$Port", "-Jrun_id=$(Get-Date -Format 'yyyyMMddHHmmss')",
            "-Jjmeter.reportgenerator.overall_granularity=5000")
  foreach ($kv in (Props $t).GetEnumerator()) { $args += "-J$($kv.Key)=$($kv.Value)" }

  & $JMeter @args
  Write-Host "Код завершення JMeter: $LASTEXITCODE"
  Start-Sleep -Seconds 10   # пауза між запусками
}

Write-Host ""
Write-Host "JTL: jmeter\results\run-<тип>.jtl; HTML-звіти: jmeter\results\report-<тип>\index.html"
Write-Host "Критерії та таблиця:  python jmeter\check_results.py"
