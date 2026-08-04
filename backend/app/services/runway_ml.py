"""
RunwayML AI 特效服务 (P3-2)
精简版：KISS + DRY
"""

import os
import httpx
from typing import Optional, Dict, Any

RUNWAYML_API_KEY = os.getenv('RUNWAYML_API_KEY')
RUNWAYML_BASE_URL = 'https://api.runwayml.com/v1'


class RunwayMLService:
    """RunwayML AI 特效服务"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or RUNWAYML_API_KEY
        if not self.api_key:
            raise ValueError('RUNWAYML_API_KEY not configured')
        
        self.client = httpx.AsyncClient(
            base_url=RUNWAYML_BASE_URL,
            headers={'Authorization': f'Bearer {self.api_key}'},
            timeout=60.0
        )
    
    async def generate_video(
        self,
        image_url: str,
        prompt: str = '',
        motion_score: int = 5,
        duration: int = 4,
        aspect_ratio: str = '16:9'
    ) -> Dict[str, Any]:
        """图生视频 (Gen-2)"""
        payload = {
            'model': 'gen2',
            'image': image_url,
            'prompt': prompt,
            'motion_score': motion_score,
            'duration': duration,
            'aspect_ratio': aspect_ratio,
        }
        
        res = await self.client.post('/video/generation', json=payload)
        res.raise_for_status()
        data = res.json()
        
        return {
            'task_id': data['id'],
            'status': data['status'],
        }
    
    async def inpaint(
        self,
        image_url: str,
        mask_url: str,
        prompt: str = ''
    ) -> Dict[str, Any]:
        """AI 扩图/修复"""
        payload = {
            'model': 'inpaint',
            'image': image_url,
            'mask': mask_url,
            'prompt': prompt,
        }
        
        res = await self.client.post('/video/inpaint', json=payload)
        res.raise_for_status()
        data = res.json()
        
        return {
            'task_id': data['id'],
            'status': data['status'],
        }
    
    async def remove_background(self, image_url: str) -> Dict[str, Any]:
        """背景移除"""
        payload = {
            'model': 'segmentation',
            'image': image_url,
            'segments': ['foreground'],
        }
        
        res = await self.client.post('/image/segmentation', json=payload)
        res.raise_for_status()
        data = res.json()
        
        return {
            'task_id': data['id'],
            'status': 'completed',
            'output_url': data['output_url'],
        }
    
    async def get_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        res = await self.client.get(f'/video/generation/{task_id}')
        res.raise_for_status()
        data = res.json()
        
        status_map = {
            'pending': 'processing',
            'processing': 'processing',
            'completed': 'completed',
            'failed': 'failed',
        }
        
        return {
            'task_id': task_id,
            'status': status_map.get(data['status'], 'processing'),
            'progress': data.get('progress', 0),
            'output_url': data.get('output_url'),
            'error': data.get('error'),
        }
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()


# 全局单例
_runway_service: Optional[RunwayMLService] = None


def get_runway_service() -> RunwayMLService:
    """获取 RunwayML 服务单例"""
    global _runway_service
    if not _runway_service:
        _runway_service = RunwayMLService()
    return _runway_service


# 便捷函数
async def runway_generate_video(**kwargs):
    service = get_runway_service()
    return await service.generate_video(**kwargs)


async def runway_inpaint(**kwargs):
    service = get_runway_service()
    return await service.inpaint(**kwargs)


async def runway_remove_background(image_url: str):
    service = get_runway_service()
    return await service.remove_background(image_url)


async def runway_get_status(task_id: str):
    service = get_runway_service()
    return await service.get_status(task_id)