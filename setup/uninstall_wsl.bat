
rem 管理者権限で実行する
whoami /priv | find "SeDebugPrivilege" > nul
if %errorlevel% neq 0 (
 @powershell start-process %~0 -verb runas
 exit
)

rem WSLの停止
wsl --shutdown

rem ディストリビューションの削除
wsl -l -v
wsl --unregister Ubuntu
