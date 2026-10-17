Webアプリケーションから利用するバックエンドの開発をします。
下記に従ってローカル環境を構築してください。
下記に記載のないライブラリやサービスを利用する場合は、ユーザーに確認してください。
・WebアプリケーションはNext.jsで構築する。
・バックエンドのデータはAmazon RDS for PostgreSQLに保持する
・Webアプリケーションからバックエンドのデータ取得APIを呼び出し、バックエンドでPosgreSQLのデータをJSON形式に変換してWebアプリケーションに応答したい。
・Webアプリケーションから設定対象のJSONを指定してバックエンドのデータ設定APIを呼び出し、バックエンドでDBのレコードの形式に変換してPosgreSQLで更新したい。
・Webアプリケーションか以外にDifyやClaudeCodeから、MCPでバックエンドに接続し、バックエンドが提供するAPIを利用したい。
・上記は本番環境で、vscodeとGitHub Copilot、WSLやMacOSの環境でAWSを使わないローカルの開発環境を構築できるようにしたい。
・チームの複数人で同じ環境を共有できるように、devcontenersとdocker composeを使用する。
・ローカル環境のPosgreSQLの初期データは、JSONk形式のファイルで定義できるようにしたい。
・データベースは、PostgreSQL 18を使用する。
・バックエンドは下記の構成で構築する。
	パッケージ名,用途,ライセンス,商用利用,ソース公開義務,備考
	FastAPI,Webフレームワーク,MIT,可能（無償）,なし,改変・商用配布・閉域利用すべて自由
	Pydantic v2 (pydantic / pydantic-core),JSON検証・変換,MIT,可能（無償）,なし,※開発元の監視SaaS「Pydantic Logfire」を使う場合のみ別料金。ライブラリ自体は完全無償のMIT
	SQLAlchemy,ORM・DB操作,MIT,可能（無償）,なし,バージョン1.4 / 2.0ともにMITライセンス
	SQLModel,統合ORM,MIT,可能（無償）,なし,FastAPIと同じ作者によるMITライセンス
	Alembic,DBマイグレーション,MIT,可能（無償）,なし,SQLAlchemy作者による標準マイグレーションツール
	Uvicorn,ASGI Webサーバー,BSD-3-Clause,可能（無償）,なし,MITと同等の寛容なライセンス
	FastMCP / MCP SDK,MCPサーバー構築,Apache-2.0 / MIT,可能（無償）,なし,公式 mcp SDKはMIT、FastMCP はApache-2.0
・ローカル環境では、データベースの内容を簡単に確認できるようにする。
・データベースの内容をエクスポートし、データベースへ初期投入するデータとして活用できるjson形式で保存できるようにする。