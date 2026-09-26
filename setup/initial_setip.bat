
rem 管理者権限で実行する
whoami /priv | find "SeDebugPrivilege" > nul
if %errorlevel% neq 0 (
 @powershell start-process %~0 -verb runas
 exit
)

rem WSLのインストール
wsl --install
wsl --install Ubuntu

rem rancher-desktopのインストール
rem https://github.com/rancher-sandbox/rancher-desktop/releases



rem 下記を仮想環境で実行する
rem curl -fsSL https://get.docker.com -o get-docker.sh
rem sudo sh ./get-docker.sh
rem sudo usermod -aG docker $USER
rem exit
rem 上記が終わったらWSLを再起動する
rem wsl --shutdown
rem wsl
rem Docker Engine の起動を確認
rem wls上で下記を実行し、エラーが出なければOK
rem docker images
rem 参考 https://qiita.com/ain1084/items/6cb6d82852c91416ec0e#root-%E4%BB%A5%E5%A4%96%E3%81%AE%E3%83%A6%E3%83%BC%E3%82%B6%E3%83%BC%E3%81%8B%E3%82%89-docker-%E3%82%92%E4%BD%BF%E7%94%A8%E3%81%A7%E3%81%8D%E3%82%8B%E6%A7%98%E3%81%AB%E3%81%99%E3%82%8B