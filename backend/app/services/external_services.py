"""
第三方服务预留模块 - V1.1 公测

已对接:
  - Gemini API (歌词/文案生成) ✅
  - HuggingFace Spaces (音乐生成) ✅
  - Mureka API (音乐生成) ✅
  - Supabase (数据库) ✅

预留接口（代码位置已准备好，密钥配置后即可启用）:
  - Resend (邮件服务)
  - Sentry (错误监控)
  - Cloudflare R2 (对象存储)
"""

import os
from typing import Optional


# ============================================================================
# Resend 邮件服务 (预留)
# ============================================================================
class ResendEmailService:
    """
    Resend 邮件服务 - 预留代码位置
    
    配置方法:
      1. 在 Render Environment Variables 添加: RESEND_API_KEY=xxx
      2. 取消下面代码的注释即可启用
    """
    
    API_KEY = os.getenv("RESEND_API_KEY", "")
    API_URL = "https://api.resend.com/emails"
    
    @classmethod
    def is_available(cls) -> bool:
        """检查是否已配置 Resend"""
        return bool(cls.API_KEY)
    
    @classmethod
    async def send_email(
        cls,
        to: str,
        subject: str,
        html: str,
        from_email: str = "noreply@musicplatform.com"
    ) -> dict:
        """
        发送邮件 (Resend API)
        
        Args:
            to: 收件人邮箱
            subject: 邮件标题
            html: HTML 邮件内容
            from_email: 发件人
        
        Returns:
            {"success": bool, "message": str}
        """
        if not cls.is_available():
            return {"success": False, "message": "RESEND_API_KEY 未配置"}
        
        # TODO: 配置密钥后启用
        # import httpx
        # async with httpx.AsyncClient() as client:
        #     response = await client.post(
        #         cls.API_URL,
        #         headers={
        #             "Authorization": f"Bearer {cls.API_KEY}",
        #             "Content-Type": "application/json",
        #         },
        #         json={
        #             "from": from_email,
        #             "to": [to],
        #             "subject": subject,
        #             "html": html,
        #         }
        #     )
        #     return {"success": response.status_code == 200, "message": response.text}
        
        return {"success": False, "message": "Resend 邮件服务未启用（预留代码）"}


# ============================================================================
# Sentry 错误监控 (预留)
# ============================================================================
class SentryMonitorService:
    """
    Sentry 错误监控 - 预留代码位置
    
    配置方法:
      1. pip install sentry-sdk
      2. 在 Render Environment Variables 添加: SENTRY_DSN=https://xxx@sentry.io/xxx
      3. 在 main.py 启动时调用 SentryMonitorService.init()
    """
    
    DSN = os.getenv("SENTRY_DSN", "")
    
    @classmethod
    def is_available(cls) -> bool:
        """检查是否已配置 Sentry"""
        return bool(cls.DSN)
    
    @classmethod
    def init(cls):
        """
        初始化 Sentry SDK
        在 main.py 应用启动时调用
        """
        if not cls.is_available():
            print("⚠️ SENTRY_DSN 未配置，错误监控未启用")
            return
        
        # TODO: 配置密钥后启用
        # import sentry_sdk
        # sentry_sdk.init(
        #     dsn=cls.DSN,
        #     traces_sample_rate=1.0,
        #     profiles_sample_rate=1.0,
        # )
        print("✅ Sentry 已配置（预留代码，需安装 sentry-sdk）")
    
    @classmethod
    def capture_exception(cls, exception: Exception):
        """捕获异常并发送到 Sentry"""
        if not cls.is_available():
            return
        
        # TODO: 配置后启用
        # import sentry_sdk
        # sentry_sdk.capture_exception(exception)
        print(f"[Sentry 预留] 异常: {str(exception)}")


# ============================================================================
# Cloudflare R2 对象存储 (预留)
# ============================================================================
class R2StorageService:
    """
    Cloudflare R2 对象存储 - 预留代码位置
    
    配置方法:
      1. 在 Render Environment Variables 添加:
         CLOUDFLARE_R2_ACCOUNT_ID=xxx
         CLOUDFLARE_R2_ACCESS_KEY=xxx
         CLOUDFLARE_R2_SECRET_KEY=xxx
         R2_BUCKET_NAME=music-audio-storage
      2. 取消下面代码的注释即可启用
    """
    
    ACCOUNT_ID = os.getenv("CLOUDFLARE_R2_ACCOUNT_ID", "")
    ACCESS_KEY = os.getenv("CLOUDFLARE_R2_ACCESS_KEY", "")
    SECRET_KEY = os.getenv("CLOUDFLARE_R2_SECRET_KEY", "")
    BUCKET = os.getenv("R2_BUCKET_NAME", "music-audio-storage")
    
    @classmethod
    def is_available(cls) -> bool:
        """检查是否已配置 R2"""
        return bool(cls.ACCOUNT_ID and cls.ACCESS_KEY and cls.SECRET_KEY)
    
    @classmethod
    def get_client(cls):
        """获取 R2 S3 兼容客户端"""
        if not cls.is_available():
            return None
        
        # TODO: 配置密钥后启用
        # import boto3
        # return boto3.client(
        #     "s3",
        #     endpoint_url=f"https://{cls.ACCOUNT_ID}.r2.cloudflarestorage.com",
        #     aws_access_key_id=cls.ACCESS_KEY,
        #     aws_secret_access_key=cls.SECRET_KEY,
        #     region_name="auto",
        # )
        return None
    
    @classmethod
    async def upload_audio(cls, file_data: bytes, filename: str) -> dict:
        """
        上传音频文件到 R2
        
        Args:
            file_data: 文件二进制数据
            filename: 文件名 (如 "song_123.mp3")
        
        Returns:
            {"success": bool, "url": str, "error": str}
        """
        if not cls.is_available():
            return {
                "success": False,
                "url": None,
                "error": "R2 密钥未配置（CLOUDFLARE_R2_ACCOUNT_ID/ACCESS_KEY/SECRET_KEY）"
            }
        
        # TODO: 配置密钥后启用
        # client = cls.get_client()
        # client.put_object(
        #     Bucket=cls.BUCKET,
        #     Key=filename,
        #     Body=file_data,
        #     ContentType="audio/mpeg"
        # )
        # url = f"https://{cls.BUCKET}.r2.cloudflarestorage.com/{filename}"
        # return {"success": True, "url": url, "error": None}
        
        return {
            "success": False,
            "url": None,
            "error": "R2 存储未启用（预留代码）"
        }


# ============================================================================
# 服务状态汇总
# ============================================================================
def get_service_status() -> dict:
    """获取所有第三方服务配置状态"""
    return {
        "gemini": {
            "configured": bool(os.getenv("GEMINI_API_KEY", "")),
            "usage": "歌词/文案生成"
        },
        "huggingface": {
            "configured": bool(os.getenv("HF_TOKEN", "")),
            "usage": "音乐生成 (MusicGen/ACE-Step/YuE)"
        },
        "mureka": {
            "configured": bool(os.getenv("MUREKA_API_KEY", "")),
            "usage": "专业音乐生成"
        },
        "supabase": {
            "configured": bool(os.getenv("SUPABASE_URL", "")),
            "usage": "数据库/用户/任务记录"
        },
        "resend": {
            "configured": ResendEmailService.is_available(),
            "usage": "邮件通知（预留）"
        },
        "sentry": {
            "configured": SentryMonitorService.is_available(),
            "usage": "错误监控（预留）"
        },
        "cloudflare_r2": {
            "configured": R2StorageService.is_available(),
            "usage": "音频文件存储（预留）"
        }
    }
