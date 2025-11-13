# PowerShell скрипт для автоматической выдачи прав в PostgreSQL
# Требует установленный psql в PATH или указание полного пути

param(
    [string]$Host = "localhost",
    [int]$Port = 5432,
    [string]$Database = "postgres",  # Подключаемся к системной БД
    [string]$SuperUser = "postgres",  # Суперпользователь
    [string]$TargetUser = "taobao",  # Пользователь, которому выдаём права
    [string]$TargetDatabase = "taobao_scraper"  # Целевая БД
)

Write-Host "🔧 Выдача прав пользователю $TargetUser в базе $TargetDatabase..." -ForegroundColor Cyan

# SQL команды для выполнения
$sqlCommands = @"
-- Выдаём права на схему public
GRANT ALL ON SCHEMA public TO $TargetUser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $TargetUser;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $TargetUser;

-- Выдаём права на создание таблиц в будущем
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $TargetUser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $TargetUser;

-- Если схема public не существует, создаём её
CREATE SCHEMA IF NOT EXISTS public;

-- Выдаём права на использование схемы
GRANT USAGE ON SCHEMA public TO $TargetUser;
GRANT CREATE ON SCHEMA public TO $TargetUser;
"@

# Сохраняем SQL во временный файл
$tempFile = [System.IO.Path]::GetTempFileName()
$sqlCommands | Out-File -FilePath $tempFile -Encoding UTF8

Write-Host "📝 Выполняем SQL команды..." -ForegroundColor Yellow

# Пытаемся найти psql
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psqlPath) {
    # Попытка найти в стандартных местах
    $possiblePaths = @(
        "C:\Program Files\PostgreSQL\15\bin\psql.exe",
        "C:\Program Files\PostgreSQL\14\bin\psql.exe",
        "C:\Program Files\PostgreSQL\16\bin\psql.exe",
        "$env:ProgramFiles\PostgreSQL\*\bin\psql.exe"
    )
    
    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $psqlPath = $path
            break
        }
    }
    
    if (-not $psqlPath) {
        Write-Host "❌ psql не найден. Установите PostgreSQL или укажите путь к psql.exe" -ForegroundColor Red
        Write-Host "💡 Альтернатива: выполните скрипт scripts/fix_db_permissions.sql вручную через pgAdmin или другой клиент PostgreSQL" -ForegroundColor Yellow
        exit 1
    }
} else {
    $psqlPath = $psqlPath.Source
}

Write-Host "🔑 Введите пароль для суперпользователя $SuperUser:" -ForegroundColor Yellow
$password = Read-Host -AsSecureString
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password)
)

# Формируем команду
$env:PGPASSWORD = $passwordPlain
$psqlCommand = "`"$psqlPath`" -h $Host -p $Port -U $SuperUser -d $TargetDatabase -f `"$tempFile`""

try {
    Write-Host "▶️  Команда: $psqlCommand" -ForegroundColor DarkGray
    & $psqlPath -h $Host -p $Port -U $SuperUser -d $TargetDatabase -f $tempFile
    Write-Host "✅ Права успешно выданы!" -ForegroundColor Green
} catch {
    Write-Host "❌ Ошибка при выполнении: $_" -ForegroundColor Red
    Write-Host "💡 Попробуйте выполнить скрипт вручную через pgAdmin" -ForegroundColor Yellow
} finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "📝 Теперь можно запустить: python scripts/bootstrap_db.py" -ForegroundColor Cyan

