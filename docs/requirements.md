---
id: REQ-001
title: コンテナ版 AWS Lambda のローカルテスト環境（Docker Compose + moto + Bruno CLI）
type: requirements
version: "1.3"
status: approved # draft | review | approved | deprecated
created: 2026-10-10
updated: 2026-10-10
tags:
  - aws-lambda
  - container-image
  - python3.14
  - moto
  - dynamodb
  - s3
  - docker-compose
  - bruno
  - step-functions
related: []
open_items:
  - CI（GitHub Actions）での自動実行は後日検討
  - Lambda ベースイメージでの RIE 起動確認（作業 #3。開発用クラウド環境では ECR からイメージを取得できないため、ローカル環境で実施）
changelog:
  - version: "1.3"
    date: 2026-10-10
    summary: Bruno コレクション・シェルスクリプトの実装に合わせて更新。RIE のエラー時レスポンスを確認
  - version: "1.2"
    date: 2026-10-10
    summary: moto 初期化スクリプト・compose.yaml の実装に合わせて初期データとディレクトリ構成を更新
  - version: "1.1"
    date: 2026-10-10
    summary: Lambda 実装に合わせてディレクトリ構成を更新。moto の状態検証方法を確定（作業 #7）
  - version: "1.0"
    date: 2026-10-10
    summary: 質問 Q1〜Q7 への回答を反映して確定
  - version: "0.1"
    date: 2026-10-10
    summary: 初版ドラフト作成
---

# 要件定義書：コンテナ版 AWS Lambda のローカルテスト環境（Docker Compose + moto + Bruno CLI）

---

## 1. 背景・目的

AWS Lambda をコンテナイメージ形式で開発し、AWS 環境にデプロイせずにローカルで動作確認・テストを行いたい。

- Lambda は将来 **AWS Step Functions から呼び出される** ことを想定する
- Lambda 本体は **コンテナイメージ（Python 3.14）** としてビルドし、ローカルで起動する
- Lambda が依存する **DynamoDB / S3** は **moto server** でモックする
- 起動は **Docker Compose** で一括管理する
- テストは **Bruno CLI (`bru`)** でホストから Lambda に **Payload（イベント JSON）を直接 POST** して検証する
- 一連の手順は **シェルスクリプト** で手順化する

### ゴール

`./scripts/run-all.sh` を 1 回実行するだけで、AWS アカウントなしに
「環境起動 → テストデータ投入 → Bruno テスト → 後片付け」が行われ、結果が成功/失敗（終了コード）で判定できる状態にする。

---

## 2. スコープ

### 対象（In Scope）

1. サンプル Lambda 関数（Python 3.14 / コンテナイメージ）の作成
2. moto server による DynamoDB / S3 のモック環境
3. Docker Compose による Lambda + moto の一括起動
4. moto へのリソース作成・テストデータ投入の仕組み
5. Bruno コレクション（リクエスト定義・アサーション・環境変数）
6. ホストからの Bruno CLI 実行とレポート出力
7. 手順化したシェルスクリプト
8. 実行手順をまとめた README

### 対象外（Out of Scope）

- 実 AWS 環境へのデプロイ（ECR push、SAM/CDK/Terraform 等）
- Step Functions 本体のローカル実行（ステートマシン定義の実行）→ 将来拡張（10 章）
- 複数 Lambda 関数 → 将来拡張（10 章）。ただし追加しやすい構成にしておく
- API Gateway のエミュレート（Step Functions からの呼び出しが前提のため不要）
- CI（GitHub Actions）での自動実行 → 後日検討
- 性能・負荷試験、IAM 権限の厳密な検証

---

## 3. システム構成

```
 ホスト
┌──────────────────────────────┐
│ scripts/run-all.sh           │
│   ├ up.sh   (compose up)     │
│   ├ test.sh (bru run)        │
│   └ down.sh (compose down)   │
│                              │
│ Bruno CLI ───────────────────┼──┐ POST /2015-03-31/functions/function/invocations
│   │                          │  │ Body = Step Functions から渡される想定の Payload
└───┼──────────────────────────┘  ▼
    │                    ┌─────────────────────────────┐
    │                    │ lambda コンテナ               │
    │                    │  public.ecr.aws/lambda/       │
    │                    │    python:3.14 (RIE 同梱)     │
    │                    │  :8080 → host :9000           │
    │                    └──────────────┬──────────────┘
    │ 状態検証 / リセット                 │ boto3
    │                                   │ AWS_ENDPOINT_URL=http://moto:5000
    ▼                                   ▼
┌──────────────────────────────────────────────────────┐
│ moto コンテナ (motoserver/moto)  :5000 → host :5000    │
│   DynamoDB / S3                                       │
└──────────────────────────────────────────────────────┘
    ▲
    │ テーブル・バケット作成、初期データ投入
┌───┴──────────────┐
│ init コンテナ      │ (amazon/aws-cli。完了後に終了)
└──────────────────┘
```

### 3.1 コンポーネント

| コンポーネント | 役割 | イメージ / ツール |
| --- | --- | --- |
| lambda | テスト対象の Lambda 関数 | `public.ecr.aws/lambda/python:3.14`（RIE 同梱） |
| moto | DynamoDB / S3 のモック | `motoserver/moto`（バージョン固定） |
| init | moto へのリソース作成・データ投入 | `amazon/aws-cli`（バージョン固定） |
| Bruno CLI | Payload 送信・アサーション | `@usebruno/cli`（ホストで `npx` 実行、バージョン固定） |
| シェルスクリプト | 手順の自動化 | bash |

### 3.2 Lambda の呼び出し方式

Step Functions の Lambda タスク（`arn:aws:states:::lambda:invoke`）は、Lambda の Invoke API に
任意の JSON を Payload として渡す。ローカルではこれを RIE の Invoke エンドポイントへの直接 POST で再現する。

- エンドポイント：`POST http://localhost:9000/2015-03-31/functions/function/invocations`
- リクエストボディ：Step Functions から渡される想定の **Payload（任意の JSON）**
- 正常時レスポンス：ハンドラの戻り値（JSON）がそのまま返る
- 異常時レスポンス：ハンドラが例外を送出した場合、`errorType` / `errorMessage` を含む JSON が返る
  （Step Functions の `Retry` / `Catch` は `errorType` で判定されるため、テストでも `errorType` を検証する）

---

## 4. サンプル Lambda 仕様（暫定）

既存コードはないため、DynamoDB と S3 の両方を使う簡単な「注文登録」関数をサンプルとする。

### 4.1 処理概要

1. Payload を検証する
2. DynamoDB テーブル `Orders` に注文を登録する（同一 `orderId` が存在する場合はエラー）
3. S3 バケット `orders-bucket` に注文内容の JSON を `orders/{orderId}.json` として保存する
4. 結果を返す（Step Functions の次ステートに渡す想定）

### 4.2 入力（Payload）

```json
{
  "orderId": "ORD-0001",
  "customerId": "CUST-001",
  "items": [
    { "sku": "SKU-001", "quantity": 2, "price": 1200 }
  ]
}
```

### 4.3 出力

```json
{
  "orderId": "ORD-0001",
  "status": "REGISTERED",
  "totalAmount": 2400,
  "s3Key": "orders/ORD-0001.json"
}
```

### 4.4 エラー（例外として送出）

| errorType | 発生条件 |
| --- | --- |
| `ValidationError` | 必須項目の欠落、`items` が空、数量・価格が不正 |
| `OrderAlreadyExistsError` | 同一 `orderId` が既に登録済み |

---

## 5. 機能要件

### FR-1 Lambda 関数（コンテナイメージ）

| ID | 要件 |
| --- | --- |
| FR-1-1 | `public.ecr.aws/lambda/python:3.14` をベースにした `Dockerfile` でビルドできること |
| FR-1-2 | ローカルでは RIE 経由で Payload を POST して呼び出せること |
| FR-1-3 | boto3 の接続先は環境変数 `AWS_ENDPOINT_URL` で切り替え、コードに moto 固有の分岐を持たないこと |
| FR-1-4 | テーブル名・バケット名は環境変数で与えること（`ORDERS_TABLE_NAME` / `ORDERS_BUCKET_NAME`） |
| FR-1-5 | 業務エラーは独自例外として送出し、Step Functions の `errorType` で判別できること |
| FR-1-6 | 同じイメージを将来そのまま実 AWS にデプロイできる構成であること |

### FR-2 AWS モック（moto server）

| ID | 要件 |
| --- | --- |
| FR-2-1 | moto server を Docker Compose で起動できること |
| FR-2-2 | DynamoDB と S3 をモックできること |
| FR-2-3 | 起動時に init コンテナが テーブル `Orders`・バケット `orders-bucket` を作成し、初期データ（登録済み注文 `ORD-SEED-0001`。重複登録エラーのテストに使用）を投入すること。何度実行しても同じ状態になること |
| FR-2-4 | テスト前に状態をリセット・再投入できること（moto の `POST /moto-api/reset` ＋ init 再実行） |

### FR-3 Docker Compose

| ID | 要件 |
| --- | --- |
| FR-3-1 | `docker compose up -d --build` で lambda / moto / init を起動できること |
| FR-3-2 | moto にヘルスチェックを設定し、init は moto 起動後、lambda は init 完了後に起動すること（`depends_on` の `condition`） |
| FR-3-3 | ダミーの AWS 認証情報・リージョンを環境変数で設定し、実認証情報を使わないこと |
| FR-3-4 | ポート番号等は `.env` で変更可能とすること |
| FR-3-5 | Lambda はサービス単位で定義し、関数の追加が service の追加だけで済む構成にすること |

### FR-4 Bruno コレクション

| ID | 要件 |
| --- | --- |
| FR-4-1 | Bruno コレクションを `bruno/` 配下に `.bru` ファイルとして管理すること |
| FR-4-2 | 接続先 URL 等は環境ファイル `bruno/environments/local.bru` で管理すること |
| FR-4-3 | Lambda ごとにフォルダを分け、将来の関数追加に対応できること |
| FR-4-4 | 正常系・異常系（`ValidationError` / `OrderAlreadyExistsError`）のテストケースを含めること |
| FR-4-5 | Lambda 実行後の moto の状態（DynamoDB のレコード・S3 のオブジェクト）を検証するリクエストを含めること |
| FR-4-6 | Bruno GUI でもそのまま開いて手動実行できること |

### FR-5 シェルスクリプト

| スクリプト | 処理 |
| --- | --- |
| `scripts/up.sh` | `docker compose up -d --build`、moto-init の完了と Lambda の応答を待機 |
| `scripts/reset.sh` | moto の状態をリセットし、テストデータを再投入 |
| `scripts/test.sh` | reset.sh を実行してから `bru run` を実行し、`bruno/reports/` に JUnit XML / HTML レポートを出力（`SKIP_RESET=1` でリセット省略） |
| `scripts/down.sh` | `docker compose down -v` で後片付け |
| `scripts/run-all.sh` | up → test（reset を含む）→ down を順に実行。テスト結果を終了コードで返し、失敗時も down は必ず実行する |

| ID | 要件 |
| --- | --- |
| FR-5-1 | 各スクリプトは単体でも実行できること |
| FR-5-2 | `set -euo pipefail` を使い、途中失敗時は非 0 で終了すること |
| FR-5-3 | 前提ツール（docker / docker compose / node）がない場合はわかりやすいメッセージで終了すること |
| FR-5-4 | 待機処理にはタイムアウトを設け、タイムアウト時はコンテナログを表示して終了すること |

---

## 6. 非機能要件

| ID | 区分 | 要件 |
| --- | --- | --- |
| NFR-1 | 再現性 | 使用イメージ・ツールのバージョンを固定する（`latest` を使わない） |
| NFR-2 | 独立性 | AWS アカウント・実 AWS 環境に一切アクセスしないこと |
| NFR-3 | 実行時間 | ビルド済みの状態で、`run-all.sh` が 1 分程度で完了することを目安とする |
| NFR-4 | 冪等性 | 何度実行しても同じ結果になること |
| NFR-5 | 可搬性 | ホストの前提は Docker（Compose v2）、Node.js、bash のみ。macOS / Linux / Windows(WSL2) で動くこと |
| NFR-6 | 保守性 | README に前提ツール、手順、Lambda・テストの追加方法を記載すること |

---

## 7. ディレクトリ構成

```
.
├── README.md
├── docs/
│   └── requirements.md            # 本書
├── compose.yaml
├── .env.example
├── scripts/
│   ├── up.sh
│   ├── reset.sh
│   ├── test.sh
│   ├── down.sh
│   └── run-all.sh
├── functions/
│   └── register-order/            # Lambda ごとにディレクトリを分ける
│       ├── Dockerfile
│       ├── requirements.txt       # 実行時依存（boto3）
│       ├── requirements-dev.txt   # テスト用依存（moto, pytest）
│       ├── pytest.ini
│       ├── app/
│       │   ├── handler.py         # ハンドラ（app.handler.lambda_handler）
│       │   └── errors.py          # 業務エラー（errorType になる）
│       └── tests/
│           └── test_handler.py    # moto を使ったユニットテスト
├── moto/
│   └── init/
│       ├── init.sh                # テーブル・バケット作成、初期データ投入
│       └── seed/orders/           # 初期データ（<orderId>.dynamodb.json と S3 用の <orderId>.json）
└── bruno/
    ├── bruno.json
    ├── environments/
    │   └── local.bru
    ├── register-order/
    │   ├── folder.bru
    │   ├── 01_正常系_注文登録.bru
    │   ├── 02_正常系_DynamoDB検証.bru
    │   ├── 03_正常系_S3検証.bru
    │   ├── 04_異常系_必須項目欠落.bru
    │   ├── 05_異常系_数量不正.bru
    │   ├── 06_異常系_入力エラー時は登録されない.bru
    │   ├── 07_異常系_重複登録.bru
    │   └── 08_異常系_重複登録時は既存データが変わらない.bru
    └── reports/                   # 出力先（git 管理外）
```

---

## 8. 作業項目（やる事リスト）

| # | 作業 | 成果物 | 依存 |
| --- | --- | --- | --- |
| 1 | 要件定義の確定 | 本書 v1.0 | — |
| 2 | サンプル Lambda の実装・Dockerfile 作成 | `functions/register-order/` | 1 |
| 3 | Lambda 単体を RIE で起動し、curl で疎通確認 | — | 2 |
| 4 | moto 初期化スクリプト作成 | `moto/init/init.sh` | 1 |
| 5 | `compose.yaml` 作成（healthcheck・depends_on・環境変数） | `compose.yaml`, `.env.example` | 2, 4 |
| 6 | Lambda → moto（DynamoDB / S3）の疎通確認 | — | 5 |
| 7 | Bruno から moto の状態を検証する方法を確定（10 章 技術メモ参照） | — | 5 |
| 8 | Bruno コレクション・環境ファイル作成 | `bruno/` | 6, 7 |
| 9 | 正常系・異常系テストケースとアサーション実装 | `bruno/register-order/*.bru` | 8 |
| 10 | シェルスクリプト作成 | `scripts/*.sh` | 9 |
| 11 | `run-all.sh` の通し実行・レポート出力確認 | `bruno/reports/` | 10 |
| 12 | README 整備 | `README.md` | 11 |

---

## 9. 決定事項

| No. | 質問 | 決定 |
| --- | --- | --- |
| Q1 | Lambda の実装言語・ランタイム | Python 3.14 |
| Q2 | 利用する AWS サービス | DynamoDB、S3 |
| Q3 | Bruno からの呼び出し方式 | Payload を RIE に直接 POST（Step Functions からの呼び出しを想定しているため） |
| Q4 | 既存の Lambda コード | なし。サンプル（注文登録）を新規作成 |
| Q5 | CI | 後日検討（今回は対象外） |
| Q6 | Bruno CLI の実行場所 | ホストから実行。シェルスクリプトで手順化 |
| Q7 | Lambda 関数の数 | まずは 1 つ。将来、Step Functions を想定して複数にする |

---

## 10. 将来拡張・技術メモ

### 10.1 将来拡張

- **複数 Lambda 化**：`functions/<name>/` と compose の service を追加し、ホスト側ポートを 9001, 9002 … と割り当てる。
  Bruno は環境変数で関数ごとの URL を持つ
- **Step Functions のローカル実行**：ステートマシン定義ごと検証したくなった場合は、
  AWS Step Functions Local（`amazon/aws-stepfunctions-local`）や moto の Step Functions サポートを候補として別途検討する
- **CI**：`run-all.sh` をそのまま GitHub Actions から呼べるようにしておく

### 10.2 技術メモ

- **RIE のエンドポイント**：コンテナ内 `:8080`、パスは `/2015-03-31/functions/function/invocations` 固定
- **SDK の接続先切り替え**：boto3 は `AWS_ENDPOINT_URL` 環境変数に対応している
- **ダミー認証情報**：`AWS_ACCESS_KEY_ID=test` / `AWS_SECRET_ACCESS_KEY=test` / `AWS_DEFAULT_REGION=ap-northeast-1`
- **RIE の例外時レスポンス**：ハンドラが例外を送出しても HTTP `200`、`Content-Type: text/plain` で、
  ボディに `errorType` / `errorMessage` / `stackTrace` を含む JSON が返る。`X-Amz-Function-Error` ヘッダは付かない
  （aws-lambda-rie で確認済み）。このためアサーションはステータスコードではなくボディの `errorType` で行う
- **RIE の起動確認**：空の Payload `{}` は `ValidationError` になるだけで副作用がないため、`up.sh` の起動待ちに使う
- **moto の状態検証**：Bruno から moto に直接リクエストして検証する方針
  - moto は Authorization ヘッダの資格情報スコープ（`.../<region>/<service>/aws4_request`）で振り分け先のサービスを判定する。
    署名は検証されないため、**ダミーの Authorization ヘッダ** を付ければ素の HTTP で問い合わせできる（moto 5.2.3 で確認済み）。
    ヘッダがない場合、S3 は `403` になる
  - S3：`GET http://localhost:5000/orders-bucket/orders/ORD-0001.json`（パス形式）＋
    `Authorization: AWS4-HMAC-SHA256 Credential=test/20261010/ap-northeast-1/s3/aws4_request, SignedHeaders=host, Signature=dummy`
  - DynamoDB：`POST http://localhost:5000/`、`X-Amz-Target: DynamoDB_20120810.GetItem`、
    `Content-Type: application/x-amz-json-1.0`、資格情報スコープを `dynamodb` にした Authorization ヘッダ
- **moto のリセット**：`POST http://localhost:5000/moto-api/reset`
- **moto のダッシュボード**：`http://localhost:5000/moto-api/` でモック中のリソースを確認できる
- **Bruno CLI**：`npx @usebruno/cli@<version> run --env local --reporter-junit reports/junit.xml --reporter-html reports/report.html`
