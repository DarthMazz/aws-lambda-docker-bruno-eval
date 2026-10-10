"""業務エラー定義。

Lambda が例外を送出すると、クラス名が errorType として呼び出し元に返る。
Step Functions の Retry / Catch は errorType で判定するため、クラス名は変更しないこと。
"""


class ValidationError(Exception):
    """Payload の内容が不正。"""


class OrderAlreadyExistsError(Exception):
    """同一 orderId の注文が既に登録されている。"""
