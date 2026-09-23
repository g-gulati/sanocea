@echo off
REM Double-click this file. It starts everything the SANOCEA / Premium Basket demo needs:
REM Docker, WhatsApp, Postgres, the public tunnel, the API server, and re-syncs the real
REM Shopify webhooks + WhatsApp contact to today's tunnel URL automatically.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1"
