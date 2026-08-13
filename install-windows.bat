@echo off
setlocal enabledelayedexpansion
title 小企业财务记账系统 - 本地一键安装/启动/更新
chcp 65001 >nul
rem 前置:已安装 Docker Desktop(https://www.docker.com/products/docker-desktop/)
rem 用法:下载本文件后双击运行。幂等:首次安装并构建;再次运行更新代码并重启(数据保留)。

set "REPO=lsgoodlionel/CW"
set "BRANCH=main"
set "APP_DIR=%USERPROFILE%\CW"

echo(
echo ============================================
echo   小企业财务记账系统 - Windows 本地安装/启动
echo ============================================
echo(

rem 1) 检查 Docker Desktop
where docker >nul 2>&1
if errorlevel 1 (
  echo [错误] 未检测到 Docker Desktop。即将打开下载页,请安装后重新运行本文件。
  start "" "https://www.docker.com/products/docker-desktop/"
  pause & exit /b 1
)
docker info >nul 2>&1
if errorlevel 1 (
  echo [提示] 正在启动 Docker Desktop,请稍候(首次较慢)...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" 2>nul
  for /L %%i in (1,1,60) do (
    docker info >nul 2>&1
    if not errorlevel 1 goto dockerok
    timeout /t 3 >nul
  )
  :dockerok
  docker info >nul 2>&1
  if errorlevel 1 (
    echo [错误] Docker 未就绪。请手动打开 Docker Desktop,待其变为绿色后重试。
    pause & exit /b 1
  )
)

rem 2) 下载/更新代码(Windows 10+ 自带 curl 与 tar,免 git)
set "TMP_TGZ=%TEMP%\cw_download.tar.gz"
if not exist "%APP_DIR%\docker-compose.yml" (
  echo [提示] 下载应用代码到 %APP_DIR% ...
  mkdir "%APP_DIR%" 2>nul
  curl -fsSL "https://codeload.github.com/%REPO%/tar.gz/refs/heads/%BRANCH%" -o "%TMP_TGZ%"
  if errorlevel 1 ( echo [错误] 下载失败,请检查网络。& pause & exit /b 1 )
  tar -xzf "%TMP_TGZ%" -C "%APP_DIR%" --strip-components=1
  if errorlevel 1 ( echo [错误] 解压失败。& pause & exit /b 1 )
  del "%TMP_TGZ%" 2>nul
) else (
  echo [提示] 更新应用代码...
  curl -fsSL "https://codeload.github.com/%REPO%/tar.gz/refs/heads/%BRANCH%" -o "%TMP_TGZ%"
  if not errorlevel 1 (
    tar -xzf "%TMP_TGZ%" -C "%APP_DIR%" --strip-components=1
    del "%TMP_TGZ%" 2>nul
  ) else (
    echo [提示] 更新失败(网络原因),使用本地已有代码继续。
  )
)

cd /d "%APP_DIR%"

rem 3) 配置 .env(本地默认即可)
if not exist ".env" copy ".env.example" ".env" >nul

rem 4) 构建并启动
echo [提示] 构建并启动容器(首次较慢,请耐心等待)...
docker compose up -d --build
if errorlevel 1 ( echo [错误] 启动失败,请查看上方错误信息。& pause & exit /b 1 )

rem 5) 读取端口并打开浏览器
set "PORT=8080"
for /f "usebackq tokens=2 delims==" %%p in (`findstr /b "HTTP_PORT=" .env`) do set "PORT=%%p"
echo [完成] 启动成功!正在打开 http://localhost:!PORT!
timeout /t 3 >nul
start "" "http://localhost:!PORT!"
echo(
echo 初始账号 admin / admin123(请登录后立即修改密码)。
echo 以后打开系统:再次运行本文件,或浏览器访问 http://localhost:!PORT!
echo 停止服务:打开 Docker Desktop 停止 CW 容器,或在 %APP_DIR% 执行 docker compose stop
echo(
pause
