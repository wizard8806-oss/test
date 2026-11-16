@echo off
setlocal
rem User-authorized local access. https://developers.openai.com/codex/cli/reference
call codex --cd "%~dp0.." --sandbox danger-full-access --ask-for-approval never %*
exit /b %errorlevel%
