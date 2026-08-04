"""
CDN 上传服务

支持:
- Cloudflare R2 (推荐，免费 10GB/月)
- AWS S3
- 本地存储回退

功能:
1. 上传音频/视频文件到 CDN
2. 生成 CDN URLs
3. 自动压缩优化
4. 缓存控制
"""

import os
import uuid
from typing import Optional, Dict
from enum import Enum


class CDNProvider(Enum):
    """CDN 提供商"""
    LOCAL = "local"      # 本地存储
    R2 = "r2"           # Cloudflare R2
    S3 = "s3"           # AWS S3


class CDNUploader:
    """CDN 上传器"""
    
    def __init__(self):
        self.provider = self._detect_provider()
        self.base_url = (os.getenv("CDN_BASE_URL", "") or "").rstrip("/")
        self.bucket = os.getenv("CDN_BUCKET", "")

        # R2 配置
        self.r2_account_id = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID")
        self.r2_access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY")
        self.r2_secret_key = os.getenv("CLOUDFLARE_R2_SECRET_KEY")

        # S3 配置
        self.s3_access_key = os.getenv("AWS_ACCESS_KEY")
        self.s3_secret_key = os.getenv("AWS_SECRET_KEY")
        self.s3_region = os.getenv("AWS_REGION", "us-east-1")

    def _resolve_cdn_url(self, key: str) -> str:
        """
        根据 self.base_url 是否配置返回拼接后的 URL。

        - 若设置 CDN_BASE_URL，则返回 {CDN_BASE_URL}/{key}（已去掉末尾斜杠）
        - 若未配置，则退回 R2 / S3 默认 endpoint，并打印告警以提醒用户配置
        """
        if self.base_url:
            return f"{self.base_url}/{key}"
        if self.provider == CDNProvider.R2 and self.r2_account_id and self.bucket:
            fallback = f"https://{self.r2_account_id}.r2.cloudflarestorage.com/{self.bucket}/{key}"
            print(f"[R2 上传] ⚠️ 未设置 CDN_BASE_URL，返回 R2 默认 URL: {fallback}")
            return fallback
        if self.provider == CDNProvider.S3 and self.bucket:
            fallback = f"https://{self.bucket}.s3.{self.s3_region}.amazonaws.com/{key}"
            print(f"[S3 上传] ⚠️ 未设置 CDN_BASE_URL，返回 S3 默认 URL: {fallback}")
            return fallback
        print(f"[CDN 上传] ⚠️ 未配置 CDN_BASE_URL 且无默认 endpoint，返回相对路径 /{key}")
        return f"/{key}"
    
    def _detect_provider(self) -> CDNProvider:
        """自动检测 CDN 提供商"""
        if os.getenv("CLOUDFLARE_R2_ACCOUNT_ID"):
            return CDNProvider.R2
        elif os.getenv("AWS_ACCESS_KEY"):
            return CDNProvider.S3
        else:
            return CDNProvider.LOCAL
    
    async def upload_audio(self, file_path: str, content_type: str = "audio/wav") -> str:
        """
        上传音频文件到 CDN
        
        Args:
            file_path: 本地文件路径
            content_type: MIME 类型
        
        Returns:
            CDN URL
        """
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file_path)[1] or ".wav"
        key = f"audio/{file_id}{file_ext}"
        
        if self.provider == CDNProvider.R2:
            return await self._upload_r2(file_path, key, content_type)
        elif self.provider == CDNProvider.S3:
            return await self._upload_s3(file_path, key, content_type)
        else:
            return self._upload_local(file_path, key)
    
    async def upload_video(self, file_path: str, content_type: str = "video/mp4") -> str:
        """
        上传视频文件到 CDN
        
        Returns:
            CDN URL
        """
        # 生成唯一文件名
        file_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file_path)[1] or ".mp4"
        key = f"video/{file_id}{file_ext}"
        
        if self.provider == CDNProvider.R2:
            return await self._upload_r2(file_path, key, content_type)
        elif self.provider == CDNProvider.S3:
            return await self._upload_s3(file_path, key, content_type)
        else:
            return self._upload_local(file_path, key)
    
    async def upload_image(self, file_path: str, content_type: str = "image/png") -> str:
        """
        上传图片文件到 CDN
        
        Returns:
            CDN URL
        """
        file_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file_path)[1] or ".png"
        key = f"images/{file_id}{file_ext}"
        
        if self.provider == CDNProvider.R2:
            return await self._upload_r2(file_path, key, content_type)
        elif self.provider == CDNProvider.S3:
            return await self._upload_s3(file_path, key, content_type)
        else:
            return self._upload_local(file_path, key)
    
    async def _upload_r2(self, file_path: str, key: str, content_type: str) -> str:
        """上传到 Cloudflare R2"""
        import boto3
        from botocore.config import Config
        
        # R2 endpoint
        endpoint_url = f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        
        # 创建 S3 兼容客户端
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.r2_access_key,
            aws_secret_access_key=self.r2_secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        
        # 上传
        with open(file_path, 'rb') as f:
            s3_client.upload_file(
                file_path,
                self.bucket,
                key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ACL': 'public-read'
                }
            )
        
        # 生成 CDN URL
        cdn_url = self._resolve_cdn_url(key)
        print(f"[R2 上传] ✅ {key} -> {cdn_url}")
        return cdn_url
    
    async def _upload_s3(self, file_path: str, key: str, content_type: str) -> str:
        """上传到 AWS S3"""
        import boto3
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
            region_name=self.s3_region
        )
        
        # 上传
        with open(file_path, 'rb') as f:
            s3_client.upload_file(
                file_path,
                self.bucket,
                key,
                ExtraArgs={
                    'ContentType': content_type,
                    'ACL': 'public-read'
                }
            )
        
        # 生成 CDN URL
        cdn_url = f"https://{self.bucket}.s3.{self.s3_region}.amazonaws.com/{key}"
        print(f"[S3 上传] ✅ {key} -> {cdn_url}")
        return cdn_url
    
    def _upload_local(self, file_path: str, key: str) -> str:
        """
        本地存储回退
        
        将文件复制到 public/static 目录
        """
        # 目标路径
        target_dir = "C:/Users/dingx/music-video-platform/backend/public/static"
        os.makedirs(target_dir, exist_ok=True)
        
        # 复制文件
        import shutil
        target_path = os.path.join(target_dir, key.replace("/", "_"))
        shutil.copy2(file_path, target_path)
        
        # 生成本地 URL
        local_url = f"http://localhost:8000/static/{os.path.basename(target_path)}"
        print(f"[本地上传] ✅ {key} -> {local_url}")
        return local_url
    
    def get_upload_url(self, file_type: str, file_ext: str) -> Dict:
        """
        获取预签名上传 URL (用于前端直传)
        
        Args:
            file_type: audio/video/image
            file_ext: 文件扩展名
        
        Returns:
            包含 upload_url 和 file_key 的字典
        """
        file_id = str(uuid.uuid4())
        key = f"{file_type}/{file_id}{file_ext}"
        
        if self.provider == CDNProvider.R2:
            return self._get_r2_presigned_url(key)
        elif self.provider == CDNProvider.S3:
            return self._get_s3_presigned_url(key)
        else:
            return {"upload_url": None, "file_key": key, "provider": "local"}
    
    def _get_r2_presigned_url(self, key: str) -> Dict:
        """生成 R2 预签名上传 URL"""
        import boto3
        from botocore.config import Config
        
        endpoint_url = f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        
        s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=self.r2_access_key,
            aws_secret_access_key=self.r2_secret_key,
            config=Config(signature_version='s3v4'),
            region_name='auto'
        )
        
        # 生成预签名 URL (15 分钟有效)
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': self.bucket,
                'Key': key,
                'ACL': 'public-read'
            },
            ExpiresIn=900
        )
        
        cdn_url = self._resolve_cdn_url(key)

        return {
            "upload_url": upload_url,
            "file_key": key,
            "cdn_url": cdn_url,
            "provider": "r2"
        }
    
    def _get_s3_presigned_url(self, key: str) -> Dict:
        """生成 S3 预签名上传 URL"""
        import boto3
        
        s3_client = boto3.client(
            's3',
            aws_access_key_id=self.s3_access_key,
            aws_secret_access_key=self.s3_secret_key,
            region_name=self.s3_region
        )
        
        # 生成预签名 URL
        upload_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': self.bucket,
                'Key': key,
                'ACL': 'public-read'
            },
            ExpiresIn=900
        )
        
        cdn_url = f"https://{self.bucket}.s3.{self.s3_region}.amazonaws.com/{key}"
        
        return {
            "upload_url": upload_url,
            "file_key": key,
            "cdn_url": cdn_url,
            "provider": "s3"
        }


# 全局实例
cdn_uploader = CDNUploader()


# 便捷函数
async def upload_to_cdn(file_path: str, file_type: str = "audio") -> str:
    """
    便捷函数：上传文件到 CDN
    
    Args:
        file_path: 本地文件路径
        file_type: audio/video/image
    
    Returns:
        CDN URL
    """
    if file_type == "video":
        return await cdn_uploader.upload_video(file_path)
    elif file_type == "image":
        return await cdn_uploader.upload_image(file_path)
    else:
        return await cdn_uploader.upload_audio(file_path)