from io import BytesIO
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app
from PIL import Image, UnidentifiedImageError


class MediaStorageError(Exception):
    pass


def configured():
    return all(current_app.config.get(name) for name in (
        "MEDIA_R2_ENDPOINT_URL",
        "MEDIA_R2_ACCESS_KEY_ID",
        "MEDIA_R2_SECRET_ACCESS_KEY",
        "MEDIA_R2_BUCKET",
    ))


def _client():
    if not configured():
        raise MediaStorageError("Armazenamento de fotos não configurado.")
    return boto3.client(
        "s3",
        endpoint_url=current_app.config["MEDIA_R2_ENDPOINT_URL"],
        aws_access_key_id=current_app.config["MEDIA_R2_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["MEDIA_R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def prepare_avatar(stream):
    raw = stream.read(3 * 1024 * 1024 + 1)
    if not raw or len(raw) > 3 * 1024 * 1024:
        raise MediaStorageError("A foto deve ter no máximo 3 MB.")
    try:
        image = Image.open(BytesIO(raw))
        if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 16_000_000:
            raise MediaStorageError("Envie uma imagem JPEG, PNG ou WebP de até 16 megapixels.")
        image.verify()
        image = Image.open(BytesIO(raw))
        image.thumbnail((512, 512))
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        output = BytesIO()
        image.save(output, "WEBP", quality=82, method=6)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError):
        raise MediaStorageError("Envie uma imagem JPEG, PNG ou WebP válida.") from None
    return output.getvalue()


def upload_avatar(_user_id, content):
    key = f"avatars/{uuid.uuid4().hex}.webp"
    try:
        _client().put_object(
            Bucket=current_app.config["MEDIA_R2_BUCKET"],
            Key=key,
            Body=content,
            ContentType="image/webp",
            CacheControl="private, max-age=3600",
        )
    except (BotoCoreError, ClientError):
        current_app.logger.exception("Avatar upload failed")
        raise MediaStorageError("Não foi possível salvar a foto agora.") from None
    return key


def get_avatar(key):
    try:
        response = _client().get_object(Bucket=current_app.config["MEDIA_R2_BUCKET"], Key=key)
        return response["Body"].read()
    except (BotoCoreError, ClientError):
        raise MediaStorageError("Foto não encontrada.") from None


def delete_avatar(key):
    if not key or not configured():
        return
    try:
        _client().delete_object(Bucket=current_app.config["MEDIA_R2_BUCKET"], Key=key)
    except (BotoCoreError, ClientError):
        current_app.logger.exception("Avatar deletion failed")
        raise MediaStorageError("Não foi possível remover a foto agora.") from None


def get_exercise_gif(provider_id):
    """Return a persistently cached WorkoutX GIF, or None when it is not cached."""
    if not configured():
        return None
    try:
        response = _client().get_object(
            Bucket=current_app.config["MEDIA_R2_BUCKET"],
            Key=f"exercise-gifs/workoutx/{provider_id}.gif",
        )
        limit = current_app.config["WORKOUTX_MAX_RESPONSE_BYTES"]
        content = response["Body"].read(limit + 1)
        if len(content) > limit:
            raise MediaStorageError("GIF excede o tamanho permitido.")
    except ClientError as error:
        code = str(error.response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise MediaStorageError("GIF não encontrado.") from None
    except BotoCoreError:
        raise MediaStorageError("GIF não encontrado.") from None
    return content if content.startswith((b"GIF87a", b"GIF89a")) else None


def upload_exercise_gif(provider_id, content):
    """Persist one approved WorkoutX GIF with immutable browser/CDN caching."""
    if not configured():
        return False
    try:
        _client().put_object(
            Bucket=current_app.config["MEDIA_R2_BUCKET"],
            Key=f"exercise-gifs/workoutx/{provider_id}.gif",
            Body=content,
            ContentType="image/gif",
            CacheControl="public, max-age=31536000, immutable",
        )
    except (BotoCoreError, ClientError):
        current_app.logger.exception("Exercise GIF upload failed")
        raise MediaStorageError("Não foi possível salvar o GIF agora.") from None
    return True
