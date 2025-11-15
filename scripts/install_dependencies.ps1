# ==============================================================================
# СКРИПТ УСТАНОВКИ ЗАВИСИМОСТЕЙ С УВЕЛИЧЕННЫМ ТАЙМАУТОМ
# ==============================================================================
# Используется для решения проблем с таймаутом при установке пакетов из PyPI
# Примечание: Сообщения на английском для совместимости с PowerShell
# ==============================================================================

# Установка кодировки UTF-8 для правильного отображения кириллицы
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Installing project dependencies" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия виртуального окружения
if (-not (Test-Path ".venv")) {
    Write-Host "ERROR: Virtual environment .venv not found!" -ForegroundColor Red
    Write-Host "Create it with: python -m venv .venv" -ForegroundColor Yellow
    exit 1
}

# Активация виртуального окружения
Write-Host "Activating virtual environment..." -ForegroundColor Green
& ".venv\Scripts\Activate.ps1"

# Обновление pip
Write-Host ""
Write-Host "Updating pip..." -ForegroundColor Green
python.exe -m pip install --upgrade pip --default-timeout=300
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: Failed to update pip, continuing..." -ForegroundColor Yellow
}

# Установка зависимостей с увеличенным таймаутом
Write-Host ""
Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Green
Write-Host "Timeout set to: 300 seconds (5 minutes)" -ForegroundColor Yellow
Write-Host ""

# Повторные попытки установки с увеличенным таймаутом
$maxRetries = 3
$retryCount = 0
$success = $false

while ($retryCount -lt $maxRetries -and -not $success) {
    $retryCount++
    Write-Host "Attempt $retryCount of $maxRetries..." -ForegroundColor Cyan
    
    python.exe -m pip install -r requirements.txt --default-timeout=300 --retries=5
    
    if ($LASTEXITCODE -eq 0) {
        $success = $true
        Write-Host ""
        Write-Host "Installation completed successfully!" -ForegroundColor Green
    }
    else {
        Write-Host ""
        Write-Host "Error during installation (attempt $retryCount of $maxRetries)" -ForegroundColor Red
        if ($retryCount -lt $maxRetries) {
            Write-Host "Retrying in 5 seconds..." -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    }
}

if (-not $success) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "INSTALLATION FAILED" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative options:" -ForegroundColor Yellow
    Write-Host "1. Use PyPI mirror (for Russia):" -ForegroundColor Yellow
    Write-Host "   pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --default-timeout=300" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "2. Install packages one by one:" -ForegroundColor Yellow
    Write-Host "   pip install aiogram>=3.0.0 --default-timeout=300" -ForegroundColor Cyan
    Write-Host "   pip install httpx>=0.24.0 --default-timeout=300" -ForegroundColor Cyan
    Write-Host "   ... etc." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "3. Check internet connection and try again" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "ALL DEPENDENCIES INSTALLED" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Don't forget to install Playwright browsers:" -ForegroundColor Yellow
Write-Host "playwright install chromium" -ForegroundColor Cyan
