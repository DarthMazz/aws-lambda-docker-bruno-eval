# aws-lambda-docker-bruno-eval

AWS Lambda（コンテナイメージ）を Docker Compose + moto + Bruno CLI でローカルテストする環境。
AWS アカウントは不要。要件は [docs/requirements.md](docs/requirements.md) を参照。

```
Bruno CLI ──POST Payload──▶ Lambda (RIE :9000) ──boto3──▶ moto (:5050) [DynamoDB / S3]
    └──────── 状態検証（DynamoDB GetItem / S3 GetObject）────────▶ moto
```

Lambda は Step Functions から呼ばれる想定のため、API Gateway は使わず、
Runtime Interface Emulator (RIE) に Payload（イベント JSON）を直接 POST する。

## 前提ツール

| ツール | 用途 |
| --- | --- |
| Docker + Docker Compose v2 | Lambda / moto の起動 |
| Node.js（`npx` が使えること） | Bruno CLI の実行（初回に `@usebruno/cli` を自動取得） |
| bash, curl | シェルスクリプト |

## クイックスタート

```bash
./scripts/run-all.sh
```

起動 → moto のリセット・初期データ投入 → Bruno テスト → 後片付け を一括で行い、テスト結果を終了コードで返す。
レポートは `bruno/reports/report.html`（HTML）と `bruno/reports/junit.xml`（JUnit）に出力される。

## スクリプト

| スクリプト | 内容 |
| --- | --- |
| `scripts/up.sh` | `docker compose up -d --build`。初期データ投入の完了と Lambda の応答を待つ |
| `scripts/reset.sh` | moto をリセットし、テーブル・バケット・初期データを作り直す |
| `scripts/test.sh` | `reset.sh` の後に Bruno CLI でテストを実行する |
| `scripts/down.sh` | コンテナ・ネットワーク・ボリュームを削除する |
| `scripts/run-all.sh` | up → test → down。テストが失敗しても down は必ず実行する |

開発中は環境を起動したままテストを繰り返すと速い。

```bash
./scripts/up.sh
./scripts/test.sh                                          # 全テスト
./scripts/test.sh register-order                           # フォルダ指定
./scripts/test.sh "register-order/01_正常系_注文登録.bru"     # 1 リクエストだけ
SKIP_RESET=1 ./scripts/test.sh                             # リセットせずに実行
./scripts/down.sh
```

| 環境変数 | 既定値 | 内容 |
| --- | --- | --- |
| `KEEP_UP` | `0` | `1` で `run-all.sh` 終了後もコンテナを残す（調査用） |
| `SKIP_RESET` | `0` | `1` で `test.sh` の実行前リセットを省略する |
| `BRUNO_CLI_VERSION` | `4.2.0` | 使用する Bruno CLI のバージョン |
| `WAIT_TIMEOUT_SEC` | `120` | 起動待ちのタイムアウト（秒） |

ポート番号やリソース名を変えるときは `cp .env.example .env` して編集する（`compose.yaml` とスクリプトの両方に反映される）。

## 手動で呼び出す

```bash
./scripts/up.sh
curl -s localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"orderId":"ORD-0001","customerId":"CUST-001","items":[{"sku":"SKU-001","quantity":2,"price":1200}]}'
# => {"orderId": "ORD-0001", "status": "REGISTERED", "totalAmount": 2400, "s3Key": "orders/ORD-0001.json"}
```

- エラー時も HTTP 200 で、ボディに `errorType` / `errorMessage` が入る（RIE の仕様）。
  Step Functions の Retry / Catch も `errorType` で判定するため、テストでは `errorType` を検証する
- moto に作成されたリソースは http://localhost:5050/moto-api/ で確認できる
- Bruno GUI で `bruno/` フォルダを開き、環境 `local` を選べば手動実行もできる

## ディレクトリ構成

```
├── compose.yaml                  # moto / moto-init / Lambda
├── .env.example
├── scripts/                      # up / reset / test / down / run-all
├── functions/
│   └── register-order/           # 注文登録 Lambda（Python 3.14）
├── moto/init/                    # moto の初期化スクリプトと初期データ
├── bruno/                        # Bruno コレクション
│   ├── environments/local.bru
│   └── register-order/           # 関数ごとのテスト
└── docs/requirements.md          # 要件定義書
```

## Lambda のユニットテスト

```bash
cd functions/register-order
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Lambda を追加するとき

1. `functions/<関数名>/` を作成（`register-order` を参考に Dockerfile とハンドラを用意）
2. `compose.yaml` にサービスを追加し、ホスト側ポートを 9001, 9002 … と割り当てる。
   `depends_on` で `moto-init` の完了を待つようにする
3. 必要なら `moto/init/init.sh` にリソースを、`moto/init/seed/` に初期データを追加
4. `bruno/environments/local.bru` に関数の URL 変数を追加し、`bruno/<関数名>/` にテストを作成
5. `scripts/lib.sh` に URL を追加し、`scripts/test.sh` の `--env-var` と `scripts/up.sh` の起動待ちに加える
