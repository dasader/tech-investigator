import boto3
from botocore.client import Config
from app.config import settings


def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.minio_endpoint}",
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def upload_pdf(job_id: int, pdf_bytes: bytes) -> str:
    client = get_minio_client()
    key = f"reports/job_{job_id}.pdf"
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.minio_bucket, "Key": key},
        ExpiresIn=86400,
    )
    return url
