"""
智能抠图服务

P1-7: 集成 Remove.bg API 实现一键智能抠图
支持:
- 人物抠图
- 产品抠图
- 通用场景抠图
- 批量处理

替代方案:
- Remove.bg API (推荐，精准)
- MohammedRageeb/remove-bg (本地，免费)
- PIL + opencv (基础，需调优)
"""

import os
import httpx
from typing import Optional, List
from pathlib import Path


class BGRoomService:
    """智能抠图服务"""
    
    def __init__(self):
        self.api_key = os.getenv("REMOVE_BG_API_KEY", "")
        self.api_url = "https://api.remove.bg/v1.0/removebg"
        self.use_local = not self.api_key  # 无 API 密钥时使用本地方案
    
    async def remove_background(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        size: str = "auto",
        format: str = "png",
        channels: str = "rgba",
        bg_color: Optional[str] = None,
        bg_image: Optional[str] = None,
        scale: Optional[float] = None,
        crop: Optional[bool] = None,
        crop_margin: Optional[str] = None,
        type: str = "auto",
        crop_guess: Optional[bool] = None,
        channels_alpha: Optional[bool] = None,
        **kwargs
    ) -> dict:
        """
        移除图片背景
        
        Args:
            image_path: 输入图片路径
            output_path: 输出图片路径 (可选，默认自动生成)
            size: 输出尺寸 (auto, preview, full)
            format: 输出格式 (png, jpg)
            channels: 通道 (rgba, rgb)
            bg_color: 背景颜色 (如 "red", "#FF0000")
            bg_image: 背景图片 URL
            scale: 缩放比例 (0-1)
            crop: 是否裁剪
            crop_margin: 裁剪边距 (如 "0px")
            type: 抠图类型 (auto, person, product, car, graphics)
            crop_guess: 自动猜测裁剪
            channels_alpha: 仅 alpha 通道
            
        Returns:
            {
                "success": bool,
                "output_path": str,
                "credits_charged": int,
                "credits_remaining": int,
                "error": Optional[str]
            }
        """
        if self.use_local:
            return await self._remove_background_local(image_path, output_path)
        
        # 准备请求参数
        params = {
            "size": size,
            "format": format,
            "channels": channels,
            "type": type,
        }
        
        # 添加可选参数
        if bg_color:
            params["bg_color"] = bg_color
        if bg_image:
            params["bg_image_url"] = bg_image
        if scale:
            params["scale"] = str(scale)
        if crop is not None:
            params["crop"] = str(crop).lower()
        if crop_margin:
            params["crop_margin"] = crop_margin
        if crop_guess is not None:
            params["crop_guess"] = str(crop_guess).lower()
        if channels_alpha is not None:
            params["channels_alpha"] = str(channels_alpha).lower()
        
        # 读取图片
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        # 调用 API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers={
                    "X-Api-Key": self.api_key,
                },
                files={
                    "image_file": image_data,
                },
                data=params,
                timeout=30.0
            )
        
        if response.status_code == 200:
            # 生成输出路径
            if not output_path:
                input_path = Path(image_path)
                output_path = str(input_path.parent / f"{input_path.stem}_no_bg.png")
            
            # 保存结果
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            # 解析响应头获取配额信息
            credits_charged = int(response.headers.get("X-Credits-Charged", "1"))
            credits_remaining = int(response.headers.get("X-Credits-Remaining", "0"))
            
            return {
                "success": True,
                "output_path": output_path,
                "credits_charged": credits_charged,
                "credits_remaining": credits_remaining,
                "error": None
            }
        
        else:
            # 解析错误
            try:
                error_data = response.json()
                error_msg = error_data.get("errors", [{}])[0].get("title", "未知错误")
            except:
                error_msg = f"HTTP {response.status_code}"
            
            return {
                "success": False,
                "output_path": None,
                "credits_charged": 0,
                "credits_remaining": 0,
                "error": error_msg
            }
    
    async def _remove_background_local(
        self,
        image_path: str,
        output_path: Optional[str] = None
    ) -> dict:
        """
        本地抠图方案 (使用 rembg 库)
        
        安装：pip install rembg[gpu]
        """
        try:
            from rembg import remove
            from PIL import Image
            
            # 读取图片
            input_image = Image.open(image_path)
            
            # 移除背景
            output_image = remove(input_image)
            
            # 生成输出路径
            if not output_path:
                input_path = Path(image_path)
                output_path = str(input_path.parent / f"{input_path.stem}_no_bg.png")
            
            # 保存结果
            output_image.save(output_path, format="PNG")
            
            return {
                "success": True,
                "output_path": output_path,
                "credits_charged": 0,
                "credits_remaining": 0,
                "error": None
            }
        
        except ImportError:
            return {
                "success": False,
                "output_path": None,
                "credits_charged": 0,
                "credits_remaining": 0,
                "error": "rembg 库未安装，请运行：pip install rembg[gpu]"
            }
        
        except Exception as e:
            return {
                "success": False,
                "output_path": None,
                "credits_charged": 0,
                "credits_remaining": 0,
                "error": str(e)
            }
    
    async def batch_remove_background(
        self,
        image_paths: List[str],
        output_dir: Optional[str] = None,
        max_concurrent: int = 5
    ) -> List[dict]:
        """
        批量抠图
        
        Args:
            image_paths: 图片路径列表
            output_dir: 输出目录 (可选)
            max_concurrent: 最大并发数
        
        Returns:
            每个图片的处理结果列表
        """
        import asyncio
        
        async def process_one(image_path: str, idx: int):
            if output_dir:
                input_name = Path(image_path).name
                output_path = str(Path(output_dir) / f"{Path(input_name).stem}_no_bg.png")
            else:
                output_path = None
            
            result = await self.remove_background(image_path, output_path)
            result["index"] = idx
            result["input_path"] = image_path
            return result
        
        # 并发处理
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def limited_process(image_path: str, idx: int):
            async with semaphore:
                return await process_one(image_path, idx)
        
        tasks = [limited_process(path, i) for i, path in enumerate(image_paths)]
        results = await asyncio.gather(*tasks)
        
        return sorted(results, key=lambda x: x["index"])
    
    def get_quota_info(self) -> dict:
        """
        获取配额信息
        
        Returns:
            {
                "api_key_configured": bool,
                "plan": str,
                "credits_remaining": int,
                "monthly_limit": int,
                "reset_date": str
            }
        """
        if not self.api_key:
            return {
                "api_key_configured": False,
                "plan": "local",
                "credits_remaining": "unlimited",
                "monthly_limit": "unlimited",
                "reset_date": "N/A"
            }
        
        # 查询配额 (需要 API 调用)
        # 这里简化返回
        return {
            "api_key_configured": True,
            "plan": "pay_as_you_go",
            "credits_remaining": "check_headers",
            "monthly_limit": "N/A",
            "reset_date": "N/A"
        }
    
    def get_pricing_info(self) -> dict:
        """
        获取价格信息
        
        Returns:
            价格方案详情
        """
        return {
            "free_trial": {
                "credits": 50,
                "price": "免费",
                "description": "新用户免费 50 次"
            },
            "pay_as_you_go": {
                "price_per_credit": "$0.20",
                "min_purchase": "$10",
                "description": "按需购买，永不过期"
            },
            "subscription": [
                {
                    "name": "Subscription 50",
                    "credits_per_month": 50,
                    "price_per_month": "$9",
                    "rollover": False
                },
                {
                    "name": "Subscription 200",
                    "credits_per_month": 200,
                    "price_per_month": "$29",
                    "rollover": True
                },
                {
                    "name": "Subscription 1000",
                    "credits_per_month": 1000,
                    "price_per_month": "$99",
                    "rollover": True
                }
            ]
        }


# 全局实例
bg_removal_service = BGRoomService()


# 便捷函数
async def remove_background(image_path: str, output_path: Optional[str] = None) -> dict:
    """抠图便捷函数"""
    return await bg_removal_service.remove_background(image_path, output_path)


async def batch_remove_background(image_paths: List[str], output_dir: Optional[str] = None) -> List[dict]:
    """批量抠图便捷函数"""
    return await bg_removal_service.batch_remove_background(image_paths, output_dir)