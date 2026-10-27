"""Read secrets from SSM Parameter Store (SecureString) once per Lambda container."""
from functools import lru_cache


@lru_cache(maxsize=None)
def get_secret(name: str) -> str:
    import boto3

    return boto3.client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
