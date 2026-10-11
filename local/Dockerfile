# ローカルテスト用の Lambda イメージ（製品の Dockerfile とは別に持つ）。
# ビルドコンテキストはリポジトリ直下（compose.yaml の build.context）で、src/ と requirements/ を参照する。
# 全 Lambda 関数で共通の 1 イメージ。関数ごとのハンドラは CMD の上書きで切り替える
# （AWS では CloudFormation の ImageConfig.Command、ローカルでは compose.yaml の command）。
FROM public.ecr.aws/lambda/python:3.14

COPY requirements/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# src/ の中身を LAMBDA_TASK_ROOT 直下に置く（handler.<service>_function.lambda_handler で参照できる）
COPY src/ ${LAMBDA_TASK_ROOT}/

# 既定のハンドラ。実際には関数ごとに上書きされる
CMD ["handler.register_order_function.lambda_handler"]
