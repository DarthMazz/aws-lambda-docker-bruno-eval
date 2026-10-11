# aws-lambda-docker-bruno-eval

AWS Lambda（コンテナイメージ）を Docker Compose + moto + Bruno CLI でローカルテストする環境。
AWS アカウントは不要。要件は [docs/requirements.md](docs/requirements.md) を参照。

```
                         ┌ register-order (RIE :9000) ┐
Bruno CLI ──POST Payload─┤                            ├──boto3──▶ moto (:5050) [DynamoDB / S3]
                         └ get-order      (RIE :9001) ┘
    └──────── 状態検証（DynamoDB GetItem / S3 GetObject）────────▶ moto
```

Lambda は Step Functions から呼ばれる想定のため、API Gateway は使わず、
Runtime Interface Emulator (RIE) に Payload（イベント JSON）を直接 POST する。

ディレクトリ構成は製品の app リポジトリ（`src/` と `tests/`）に合わせている。
**全 Lambda 関数で 1 つのコンテナイメージを使い、関数ごとにハンドラ（CMD）を上書きする**。
AWS では CloudFormation の `ImageConfig.Command`、ローカルでは `compose.yaml` の `command` で上書きする。

## 前提ツール

| ツール | 用途 |
| --- | --- |
| Docker + Docker Compose v2 | Lambda / moto の起動 |
| Node.js（`npx` が使えること） | Bruno CLI の実行（初回に `@usebruno/cli` を自動取得） |
| bash, curl | シェルスクリプト |

動作確認済み：macOS（Apple Silicon）+ Docker Desktop 4.94（Engine 29.8 / Compose v5.5）+ Node.js 26。
Linux / Windows（WSL2）でも同じ手順で動く想定。

> **macOS の場合**：AirPlay レシーバーがポート 5000 を使うため、moto はホストの **5050** で公開している。
> 他のポートにしたい場合は `.env` の `MOTO_PORT` を変える（後述）。

## クイックスタート

```bash
./scripts/run-all.sh
```

起動 → moto のリセット・初期データ投入 → Bruno テスト → 後片付け を一括で行い、テスト結果を終了コードで返す。
レポートは `bruno/reports/report.html`（HTML）と `bruno/reports/junit.xml`（JUnit）に出力される。

## スクリプト

| スクリプト | 内容 |
| --- | --- |
| `scripts/up.sh` | `docker compose up -d --build --wait`。初期データ投入の完了と Lambda の応答を待つ |
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

## サンプル Lambda

すべて `src/handler/<service>_function.py` の `lambda_handler` で、ハンドラ指定は `handler.<service>_function.lambda_handler`。

### register-order（`handler.register_order_function.lambda_handler`、ポート 9000）

Payload を検証し、DynamoDB テーブル `Orders` に注文を登録して、S3 バケット `orders-bucket` に
`orders/{orderId}.json` を保存する。詳細は [docs/requirements.md](docs/requirements.md) の 4 章を参照。

| 入力（Payload） | 出力 |
| --- | --- |
| `{"orderId", "customerId", "items": [{"sku", "quantity", "price"}]}` | `{"orderId", "status": "REGISTERED", "totalAmount", "s3Key"}` |

| errorType | 発生条件 |
| --- | --- |
| `ValidationError` | 必須項目の欠落、`items` が空、数量・価格が不正 |
| `OrderAlreadyExistsError` | 同一 `orderId` が既に登録済み |

### get-order（`handler.get_order_function.lambda_handler`、ポート 9001）

DynamoDB テーブル `Orders` から注文を取得して返す。

| 入力（Payload） | 出力 |
| --- | --- |
| `{"orderId"}` | 登録済みの注文（`orderId`, `customerId`, `items`, `totalAmount`, `status`, `s3Key`, `createdAt`） |

| errorType | 発生条件 |
| --- | --- |
| `ValidationError` | `orderId` の欠落 |
| `OrderNotFoundError` | 指定した `orderId` の注文が存在しない |

## テストケース

`bruno/<関数名>/` のリクエストは `seq` の順に実行され、前のリクエストの結果を後のリクエストで検証する。
そのため **単体で実行するときは、依存先（例：02 なら 01）も一緒に実行する** か、フォルダ単位で実行する。

`bruno/register-order/`

| # | ケース | 呼び出し先 | 検証内容 |
| --- | --- | --- | --- |
| 01 | 正常系：注文登録 | Lambda | `status` / `totalAmount` / `s3Key` |
| 02 | 正常系：DynamoDB 検証 | moto | 01 の注文が登録されている |
| 03 | 正常系：S3 検証 | moto | 01 の注文 JSON が保存されている |
| 04 | 異常系：必須項目欠落 | Lambda | `ValidationError` |
| 05 | 異常系：数量不正 | Lambda | `ValidationError` |
| 06 | 異常系：入力エラー時は登録されない | moto | 05 の注文が DynamoDB にない |
| 07 | 異常系：重複登録 | Lambda | 初期データ `ORD-SEED-0001` の再登録で `OrderAlreadyExistsError` |
| 08 | 異常系：重複登録時は既存データが変わらない | moto | `ORD-SEED-0001` の S3 オブジェクトが上書きされていない |

`bruno/get-order/`

| # | ケース | 呼び出し先 | 検証内容 |
| --- | --- | --- | --- |
| 01 | 正常系：注文取得 | Lambda | 初期データ `ORD-SEED-0001` の内容（数値が JSON の数値で返る） |
| 02 | 異常系：存在しない注文 | Lambda | `OrderNotFoundError` |
| 03 | 異常系：必須項目欠落 | Lambda | `ValidationError` |

## 手動で呼び出す

```bash
./scripts/up.sh
curl -s localhost:9000/2015-03-31/functions/function/invocations \
  -d '{"orderId":"ORD-0001","customerId":"CUST-001","items":[{"sku":"SKU-001","quantity":2,"price":1200}]}'
# => {"orderId": "ORD-0001", "status": "REGISTERED", "totalAmount": 2400, "s3Key": "orders/ORD-0001.json"}
curl -s localhost:9001/2015-03-31/functions/function/invocations -d '{"orderId":"ORD-0001"}'
# => {"orderId": "ORD-0001", "customerId": "CUST-001", ..., "totalAmount": 2400, ...}
```

- エラー時も HTTP 200 で、ボディに `errorType` / `errorMessage` が入る（RIE の仕様）。
  Step Functions の Retry / Catch も `errorType` で判定するため、テストでは `errorType` を検証する
- moto に作成されたリソースは http://localhost:5050/moto-api/ で確認できる
- Bruno GUI で `bruno/` フォルダを開き、環境 `local` を選べば手動実行もできる

## ディレクトリ構成

```
# ── アプリケーション（製品の app リポジトリと同じ構成）──
├── requirements/
│   ├── requirements.txt          # Lambda 実行時の依存
│   └── requirements-dev.txt      # ユニットテスト用の依存
├── pytest.ini                    # pythonpath = src（Lambda 実行時と同じインポートのルート）
├── src/
│   ├── handler/
│   │   ├── register_order_function.py   # 注文登録
│   │   └── get_order_function.py        # 注文取得
│   └── common/
│       └── errors.py             # 業務エラー（クラス名が errorType になる）
├── tests/                        # ユニットテスト（moto のインプロセスモック）
│
# ── ローカルテスト環境（製品リポジトリにはこの部分を追加する）──
├── local/
│   ├── Dockerfile                # 全関数共通の 1 イメージ（src/ の中身を LAMBDA_TASK_ROOT に置く）
│   └── Dockerfile.dockerignore   # 上の Dockerfile 専用の除外設定
├── compose.yaml                  # moto / moto-init / 関数ごとの Lambda サービス
├── .env.example
├── scripts/                      # up / reset / test / down / run-all
├── moto/init/                    # moto の初期化スクリプトと初期データ
├── bruno/                        # Bruno コレクション
│   ├── environments/local.bru
│   ├── register-order/           # 関数ごとのテスト
│   └── get-order/
└── docs/requirements.md          # 要件定義書
```

製品リポジトリに適用するときは、下半分（テスト環境）をリポジトリ直下に追加し、
製品の Dockerfile・`.dockerignore` には手を入れない（テスト用は `local/` に別に持つ）。
`compose.yaml` の `command` を製品のハンドラ名に、`moto/init/` を製品が使う AWS リソースに書き換える。

## Lambda のユニットテスト

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements/requirements-dev.txt
.venv/bin/python -m pytest
```

## テストを追加するとき

`bruno/<関数名>/` に `.bru` ファイルを追加する（Bruno GUI で作ると楽）。

- `meta` の `seq` で実行順を決める。テストは毎回 moto をリセットした状態から始まる
- Lambda の呼び出しは `{{registerOrderUrl}}` に Payload をそのまま POST する。
  エラーは HTTP 200 で返るため、`res.status` ではなく `res.body.errorType` を検証する
- moto の状態は素の HTTP で検証できる。moto は Authorization ヘッダの資格情報スコープで
  サービスを判定する（署名は検証しない）ため、環境変数のダミーヘッダを付ける

```
# DynamoDB（例：02_正常系_DynamoDB検証.bru）
post { url: {{motoUrl}}/ }
headers {
  X-Amz-Target: DynamoDB_20120810.GetItem
  Content-Type: application/x-amz-json-1.0
  Authorization: {{motoAuthDynamodb}}
}

# S3（例：03_正常系_S3検証.bru）
get { url: {{motoUrl}}/{{ordersBucket}}/orders/<orderId>.json }
headers { Authorization: {{motoAuthS3}} }
```

- 事前に登録済みのデータが必要なら `moto/init/seed/orders/` に `<orderId>.dynamodb.json`（DynamoDB 形式）と
  `<orderId>.json`（S3 に置く内容）を追加する

## Lambda を追加するとき

1. `src/handler/<service>_function.py` に `lambda_handler` を作り、`tests/` にユニットテストを追加する
   （イメージは共通なので `local/Dockerfile` の変更は不要）
2. `compose.yaml` にサービスを追加する。`<<: *lambda` で共通設定を取り込み、
   `command` にハンドラ（`handler.<service>_function.lambda_handler`）を、ホスト側ポートに 9002, 9003 … を指定する
3. 必要なら `moto/init/init.sh` にリソースを、`moto/init/seed/` に初期データを追加
4. `bruno/environments/local.bru` に関数の URL 変数を追加し、`bruno/<関数名>/` にテストを作成
5. `scripts/lib.sh` に URL を追加し、`scripts/test.sh` の `--env-var` と `scripts/up.sh` の起動待ちに加える

## トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| `bind: address already in use`（5000 / 5050 / 9000 / 9001） | 他のプロセスがポートを使っている。`lsof -nP -iTCP:<port> -sTCP:LISTEN` で確認し、`.env` の `MOTO_PORT` / `REGISTER_ORDER_PORT` / `GET_ORDER_PORT` を変える |
| `Docker デーモンに接続できません` | Docker Desktop が起動していない。アプリを起動してから再実行する |
| `docker: command not found`（Docker Desktop 導入直後） | `/usr/local/bin` が `PATH` に入っていない。シェルを開き直すか `PATH` に追加する |
| `brew install --cask docker-desktop` が `already a Binary at '/usr/local/bin/docker-credential-osxkeychain'` で失敗する | Finch など他のツールが同名のリンクを置いている。`ls -l` でリンク先を確認し、不要なら削除してから再インストールする |
| 初回の `test.sh` が遅い | `npx` が Bruno CLI を取得しているため。2 回目以降はキャッシュされる |
| 起動待ちでタイムアウトする | 初回はイメージの取得・ビルドに時間がかかる。`WAIT_TIMEOUT_SEC=300 ./scripts/run-all.sh` のように延ばす |
| テストが失敗した原因を調べたい | `KEEP_UP=1 ./scripts/run-all.sh` でコンテナを残し、`docker compose logs register-order` や http://localhost:5050/moto-api/ で状態を確認する |
