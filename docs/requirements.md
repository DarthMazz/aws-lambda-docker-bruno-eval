# 要件定義書：コンテナ版 AWS Lambda のローカルテスト環境（Docker Compose + moto + Bruno CLI）

| 項目 | 内容 |
| --- | --- |
| 版数 | 0.1（ドラフト） |
| 作成日 | 2026-10-10 |
| ステータス | 未確定事項あり（「8. 未確定事項・質問」参照） |

---

## 1. 背景・目的

AWS Lambda をコンテナイメージ形式で開発し、AWS 環境にデプロイせずにローカルで動作確認・API テストを行いたい。

- Lambda 本体は **コンテナイメージ** としてビルドし、ローカルで起動する
- Lambda が依存する AWS サービスは **moto server** でモックする
- 起動は **Docker Compose** で一括管理する
- テストは **Bruno CLI (`bru`)** で API コールし、レスポンスを検証する

### ゴール

`docker compose up` → `bru run` の 2 コマンド（または 1 つのスクリプト）で、
AWS アカウントなしに Lambda の動作をテストでき、結果が成功/失敗で判定できる状態にする。

---

## 2. スコープ

### 対象（In Scope）

1. サンプル Lambda 関数（コンテナイメージ）の作成
2. moto server を利用した AWS サービスのモック環境
3. Docker Compose による Lambda + moto の一括起動
4. moto へのテストデータ投入（初期化）の仕組み
5. Bruno コレクション（リクエスト定義・アサーション・環境変数）
6. Bruno CLI によるテスト実行とレポート出力
7. 実行手順をまとめた README

### 対象外（Out of Scope）

- 実 AWS 環境へのデプロイ（ECR push、CloudFormation/SAM/CDK/Terraform 等）
- 本番相当の性能・負荷試験
- IAM 権限の厳密な検証（moto は認証・認可をほぼ検証しないため）
- （未確定）CI（GitHub Actions）での自動実行 → 質問 Q5 参照

---

## 3. システム構成

```
┌──────────────┐  HTTP (POST /2015-03-31/functions/function/invocations)
│  Bruno CLI   │ ───────────────────────────────┐
│  (bru run)   │                                 ▼
└──────┬───────┘                    ┌──────────────────────────┐
       │                            │ lambda コンテナ            │
       │ (任意) 状態確認/リセット     │  AWS 公式ベースイメージ     │
       │                            │  + Runtime Interface      │
       │                            │    Emulator (RIE)         │
       │                            │  :8080 → host :9000       │
       │                            └────────────┬─────────────┘
       │                                         │ AWS SDK
       │                                         │ (AWS_ENDPOINT_URL=http://moto:5000)
       ▼                                         ▼
┌──────────────────────────────────────────────────────────┐
│ moto コンテナ (motoserver/moto)  :5000 → host :5000        │
│  DynamoDB / S3 / SQS 等をモック                             │
└──────────────────────────────────────────────────────────┘
          ▲
          │ 起動時にテストデータ投入
┌─────────┴────────┐
│ init コンテナ      │ (aws-cli 等。投入完了後に終了)
└──────────────────┘
```

### 3.1 コンポーネント

| コンポーネント | 役割 | 想定イメージ / ツール |
| --- | --- | --- |
| lambda | テスト対象の Lambda 関数 | `public.ecr.aws/lambda/<runtime>`（RIE 同梱） |
| moto | AWS サービスのモック | `motoserver/moto` |
| init | moto へのリソース作成・データ投入 | `amazon/aws-cli` もしくはスクリプト |
| Bruno CLI | API コール・アサーション | `@usebruno/cli`（`bru`） |

### 3.2 Lambda の呼び出し方式

AWS 公式ベースイメージに同梱されている **Runtime Interface Emulator (RIE)** を利用する。

- エンドポイント：`POST http://localhost:9000/2015-03-31/functions/function/invocations`
- リクエストボディ：Lambda に渡す **イベント JSON そのもの**
- レスポンス：Lambda の戻り値（API Gateway 形式なら `statusCode` / `headers` / `body`）

> 注意：RIE は API Gateway をエミュレートしないため、`GET /users/1` のような
> 素の HTTP リクエストは送れない。Bruno 側で API Gateway 形式のイベントを組み立てて送る。
> 素の HTTP で叩きたい場合はプロキシ層が必要（質問 Q3 参照）。

---

## 4. 機能要件

### FR-1 Lambda 関数（コンテナイメージ）

| ID | 要件 |
| --- | --- |
| FR-1-1 | Lambda は AWS 公式ベースイメージを使った `Dockerfile` でビルドできること |
| FR-1-2 | ローカルでは RIE 経由で HTTP 呼び出しできること |
| FR-1-3 | AWS SDK の接続先は環境変数で切り替えられ、コード上に moto 固有の分岐を持たないこと（`AWS_ENDPOINT_URL` を使用） |
| FR-1-4 | 正常系・異常系（バリデーションエラー、データなし等）で適切なステータス/エラーを返すこと |
| FR-1-5 | 同じイメージを（将来）実 AWS にもそのままデプロイできる構成であること |

### FR-2 AWS モック（moto server）

| ID | 要件 |
| --- | --- |
| FR-2-1 | moto server を Docker Compose で起動できること |
| FR-2-2 | Lambda から利用する AWS サービス（質問 Q2 で確定）をモックできること |
| FR-2-3 | 起動時に必要なリソース（テーブル/バケット/キュー等）とテストデータが自動で作成されること |
| FR-2-4 | テスト前に状態をリセットできること（moto の `POST /moto-api/reset` を利用） |

### FR-3 Docker Compose

| ID | 要件 |
| --- | --- |
| FR-3-1 | `docker compose up -d --build` で lambda / moto / init を起動できること |
| FR-3-2 | moto にヘルスチェックを設定し、init と lambda は moto の起動完了後に起動すること（`depends_on: condition`） |
| FR-3-3 | ダミーの AWS 認証情報・リージョンを環境変数で設定すること（実認証情報を使わない） |
| FR-3-4 | ポート番号等は `.env` で変更可能とすること |
| FR-3-5 | `docker compose down -v` で完全にクリーンアップできること |

### FR-4 Bruno コレクション

| ID | 要件 |
| --- | --- |
| FR-4-1 | Bruno コレクションをリポジトリ内（例：`bruno/`）に `.bru` ファイルとして管理すること |
| FR-4-2 | 接続先 URL 等は Bruno の環境ファイル（例：`environments/local.bru`）で管理すること |
| FR-4-3 | 各リクエストにアサーション（ステータス、レスポンスボディ）を定義すること |
| FR-4-4 | 正常系・異常系の両方のテストケースを含めること |
| FR-4-5 | 必要に応じて、Lambda 実行後の moto 上の状態（DB の値等）を検証するリクエストを含めること |
| FR-4-6 | Bruno GUI でもそのまま開いて手動実行できること |

### FR-5 テスト実行

| ID | 要件 |
| --- | --- |
| FR-5-1 | `bru run --env local` でコレクション全体を実行できること |
| FR-5-2 | テスト失敗時は非 0 の終了コードを返すこと |
| FR-5-3 | JUnit XML / HTML 形式のレポートを出力できること（`--reporter-junit` / `--reporter-html`） |
| FR-5-4 | 起動 → 待機 → テスト → 停止 を 1 コマンドで行うスクリプト（`Makefile` 等）を用意すること |

---

## 5. 非機能要件

| ID | 区分 | 要件 |
| --- | --- | --- |
| NFR-1 | 再現性 | 使用イメージ・ツールのバージョンを固定する（`latest` を使わない） |
| NFR-2 | 独立性 | AWS アカウント・インターネット上の AWS 環境に一切アクセスしないこと |
| NFR-3 | 実行時間 | ビルド済みの状態で、起動〜テスト完了まで数十秒程度を目安とする |
| NFR-4 | 冪等性 | 何度実行しても同じ結果になること（状態リセットを前提とする） |
| NFR-5 | 可搬性 | Docker / Docker Compose v2 / Node.js があれば macOS・Linux・Windows(WSL2) で動くこと |
| NFR-6 | 保守性 | README に前提ツール、起動手順、テスト追加方法を記載すること |

---

## 6. 想定ディレクトリ構成

```
.
├── README.md
├── docs/
│   └── requirements.md          # 本書
├── compose.yaml
├── .env.example
├── Makefile                     # up / test / down / all
├── lambda/
│   ├── Dockerfile
│   ├── app/                     # ハンドラ実装
│   └── tests/                   # （任意）ユニットテスト
├── moto/
│   └── init/                    # リソース作成・データ投入スクリプト
└── bruno/
    ├── bruno.json
    ├── environments/
    │   └── local.bru
    ├── <機能名>/
    │   ├── 01_正常系.bru
    │   └── 02_異常系.bru
    └── reports/                 # 出力先（git 管理外）
```

---

## 7. 作業項目（やる事リスト）

| # | 作業 | 成果物 | 依存 |
| --- | --- | --- | --- |
| 1 | 未確定事項の確定（本書 8 章） | 本書 v1.0 | — |
| 2 | サンプル Lambda の実装と Dockerfile 作成 | `lambda/` | 1 |
| 3 | 単体で RIE 起動し curl で疎通確認 | — | 2 |
| 4 | moto server と初期化スクリプトの作成 | `moto/init/` | 1 |
| 5 | `compose.yaml` 作成（healthcheck・depends_on・ネットワーク・環境変数） | `compose.yaml`, `.env.example` | 2, 4 |
| 6 | Lambda → moto の疎通確認 | — | 5 |
| 7 | Bruno コレクション・環境ファイル作成 | `bruno/` | 5 |
| 8 | 正常系・異常系テストケースとアサーション実装 | `bruno/**/*.bru` | 7 |
| 9 | `bru run` 実行・レポート出力の確認 | `bruno/reports/` | 8 |
| 10 | 一括実行スクリプト（Makefile 等） | `Makefile` | 9 |
| 11 | README 整備 | `README.md` | 10 |
| 12 | （任意）GitHub Actions で CI 実行 | `.github/workflows/` | 10 |

---

## 8. 未確定事項・質問

| No. | 質問 | 仮の前提（回答がなければこれで進める） |
| --- | --- | --- |
| Q1 | Lambda の実装言語・ランタイムは？ | Python 3.12 |
| Q2 | Lambda が利用する AWS サービスは？（DynamoDB / S3 / SQS / SNS / Secrets Manager 等） | DynamoDB（簡単な CRUD API） |
| Q3 | Bruno からの呼び出し方式は？<br>A. RIE に直接イベント JSON を POST（シンプル）<br>B. API Gateway 風の HTTP（`GET /items/1` 等）で叩けるようプロキシを挟む | A |
| Q4 | 既存の Lambda コードはあるか？ なければサンプルを新規作成でよいか？ | サンプルを新規作成 |
| Q5 | GitHub Actions での CI 実行も対象に含めるか？ | 含める（任意扱い） |
| Q6 | Bruno CLI はホストで実行するか、コンテナ化して Compose に含めるか？ | ホスト実行（`npx @usebruno/cli`）、CI 用にコンテナ実行も可能にする |
| Q7 | 複数の Lambda 関数を扱う想定はあるか？ | 当面 1 関数 |

---

## 9. 技術メモ

- **RIE のエンドポイント**：コンテナ内 `:8080`、パスは `/2015-03-31/functions/function/invocations` 固定
- **SDK の接続先切り替え**：`AWS_ENDPOINT_URL` 環境変数は boto3 1.28+ / AWS SDK for JavaScript v3 などで対応済み。
  サービス個別に `AWS_ENDPOINT_URL_DYNAMODB` のような指定も可能
- **ダミー認証情報**：`AWS_ACCESS_KEY_ID=test` / `AWS_SECRET_ACCESS_KEY=test` / `AWS_DEFAULT_REGION=ap-northeast-1`
- **moto のリセット**：`POST http://localhost:5000/moto-api/reset`（Bruno のコレクション先頭で呼ぶ想定）
- **moto のダッシュボード**：`http://localhost:5000/moto-api/` でモック中のリソースを確認可能
- **Bruno CLI**：`bru run <dir> --env local --reporter-junit reports/junit.xml --reporter-html reports/report.html`
