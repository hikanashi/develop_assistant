rem 管理者権限で実行する
whoami /priv | find "SeDebugPrivilege" > nul
if %errorlevel% neq 0 (
 @powershell start-process %~0 -verb runas
 exit
)

echo WSLをインストールします
wsl --install

echo WSL上でDockerをセットアップします
echo Docker Desktop のインストールが推奨されますが、そのまま待機してDockerのセットアップを進めてください
wsl bash -c "curl -fsSL https://get.docker.com -o get-docker.sh;sudo sh ./get-docker.sh"

echo WSL上でroot 以外のユーザーから docker を使用できる様にします
wsl bash -c "sudo usermod -aG docker $USER"

echo WSLを再起動します
wsl --shutdown

echo WSLを再起動しました
echo WSL上のDockerの実行結果でエラーが出ないことを確認してください
wsl bash -c "docker images"

echo WSL上のDockerが自動起動することを確認してください
wsl bash -c "systemctl is-enabled docker"
rem wsl bash -c "systemctl status docker"

rem dockerログインの設定（JFrogの設定）
rem wsl bash -c "docker login mycompany.jfrog.io -u <ユーザー名> --password-stdin"

rem NPMのレジストリをJFrogに設定
rem npm config set registry https://[JFrogPlatformURL]/artifactory/api/npm/<REPO_NAME>/
rem npm login --auth-type=web

code --install-extension ms-vscode-remote.remote-wsl
code --install-extension ms-vscode-remote.remote-containers

pause
