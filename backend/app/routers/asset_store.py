"""
素材商店路由 (Asset Store Router)

功能:
- 付费素材/效果器浏览
- 购买/下载
- 用户已购列表
- 试用预览

API 端点:
- GET /api/v1/store/assets - 素材列表
- GET /api/v1/store/assets/{id} - 素材详情
- POST /api/v1/store/purchase - 购买素材
- GET /api/v1/store/purchases - 已购列表
- POST /api/v1/store/download/{id} - 下载素材
- GET /api/v1/store/preview/{id} - 预览素材
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum

router = APIRouter(prefix="/api/v1/store", tags=["Asset Store"])


class AssetType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    EFFECT = "effect"
    TEMPLATE = "template"
    TRANSITION = "transition"


class AssetDetail(BaseModel):
    id: str
    name: str
    description: str
    type: AssetType
    price: float
    thumbnail_url: str
    preview_url: Optional[str] = None
    tags: List[str]
    rating: float = 5.0
    downloads: int = 0
    is_premium: bool = True  # True=付费，False=免费


# 素材商店数据
ASSETS = [
    # 付费视频素材
    AssetDetail(
        id="vid_001",
        name="城市夜景航拍",
        description="4K 城市夜景延时摄影，适合 MV 开场",
        type=AssetType.VIDEO,
        price=9.9,
        thumbnail_url="/thumbnails/vid_001.jpg",
        preview_url="/previews/vid_001.mp4",
        tags=["城市", "夜景", "航拍", "4K"],
        downloads=1250
    ),
    AssetDetail(
        id="vid_002",
        name="海浪沙滩",
        description="热带海滩海浪慢镜头",
        type=AssetType.VIDEO,
        price=7.9,
        thumbnail_url="/thumbnails/vid_002.jpg",
        preview_url="/previews/vid_002.mp4",
        tags=["海滩", "海浪", "自然", "慢动作"],
        downloads=980
    ),
    
    # 付费效果器
    AssetDetail(
        id="fx_001",
        name="赛博朋克调色",
        description="专业电影级赛博朋克色彩预设",
        type=AssetType.EFFECT,
        price=15.9,
        thumbnail_url="/thumbnails/fx_001.jpg",
        tags=["调色", "赛博朋克", "电影感", "专业"],
        downloads=2340,
        is_premium=True
    ),
    AssetDetail(
        id="fx_002",
        name="复古胶片颗粒",
        description="模拟 80 年代胶片质感",
        type=AssetType.EFFECT,
        price=12.9,
        thumbnail_url="/thumbnails/fx_002.jpg",
        tags=["复古", "胶片", "颗粒", "怀旧"],
        downloads=1876
    ),
    
    # 转场效果
    AssetDetail(
        id="trans_001",
        name="光效转场包",
        description="20 种专业光效转场",
        type=AssetType.TRANSITION,
        price=19.9,
        thumbnail_url="/thumbnails/trans_001.jpg",
        tags=["光效", "转场", "专业", "套装"],
        downloads=3421
    ),
    
    # 免费素材
    AssetDetail(
        id="vid_free_001",
        name="城市街景",
        description="免费城市街景素材",
        type=AssetType.VIDEO,
        price=0,
        thumbnail_url="/thumbnails/vid_free_001.jpg",
        preview_url="/previews/vid_free_001.mp4",
        tags=["城市", "街景", "免费"],
        downloads=5670,
        is_premium=False
    )
]


# 用户购买记录
purchases_db: Dict[str, List[str]] = {}  # user_id -> [asset_ids]


class PurchaseRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    asset_id: str = Field(..., description="素材 ID")
    payment_method: str = Field("alipay", description="支付方式")


class PurchaseResponse(BaseModel):
    success: bool
    asset_id: str
    download_url: str
    message: str


@router.get("/assets")
async def get_assets(
    type_filter: Optional[AssetType] = None,
    is_premium: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = Query("downloads", description="排序：downloads/rating/price"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """获取素材列表"""
    filtered = ASSETS
    
    if type_filter:
        filtered = [a for a in filtered if a.type == type_filter]
    
    if is_premium is not None:
        filtered = [a for a in filtered if a.is_premium == is_premium]
    
    if search:
        filtered = [a for a in filtered if search.lower() in a.name.lower() or search.lower() in ' '.join(a.tags)]
    
    # 排序
    if sort_by == "downloads":
        filtered.sort(key=lambda x: x.downloads, reverse=True)
    elif sort_by == "rating":
        filtered.sort(key=lambda x: x.rating, reverse=True)
    elif sort_by == "price":
        filtered.sort(key=lambda x: x.price)
    
    # 分页
    paginated = filtered[offset:offset + limit]
    return paginated


@router.get("/assets/{asset_id}")
async def get_asset_detail(asset_id: str):
    """获取素材详情"""
    for asset in ASSETS:
        if asset.id == asset_id:
            return asset
    
    raise HTTPException(status_code=404, detail="素材不存在")


@router.post("/purchase", response_model=PurchaseResponse)
async def purchase_asset(request: PurchaseRequest):
    """购买素材"""
    # 查找素材
    asset = None
    for a in ASSETS:
        if a.id == request.asset_id:
            asset = a
            break
    
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    
    if asset.price == 0:
        # 免费素材直接下载
        return PurchaseResponse(
            success=True,
            asset_id=request.asset_id,
            download_url=f"/api/v1/store/download/{request.asset_id}",
            message="免费素材，可直接下载"
        )
    
    # TODO: 实际支付流程
    # 1. 创建支付订单
    # 2. 调起支付
    # 3. 处理回调
    # 4. 添加购买记录
    
    # 添加购买记录
    if request.user_id not in purchases_db:
        purchases_db[request.user_id] = []
    if request.asset_id not in purchases_db[request.user_id]:
        purchases_db[request.user_id].append(request.asset_id)
    
    return PurchaseResponse(
        success=True,
        asset_id=request.asset_id,
        download_url=f"/api/v1/store/download/{request.asset_id}",
        message="购买成功！"
    )


@router.get("/purchases")
async def get_purchases(user_id: str = Query(..., description="用户 ID")):
    """获取已购素材列表"""
    if user_id not in purchases_db:
        return []
    
    purchased_ids = purchases_db[user_id]
    return [a for a in ASSETS if a.id in purchased_ids]


@router.get("/download/{asset_id}")
async def download_asset(asset_id: str, user_id: str = Query(..., description="用户 ID")):
    """下载素材 (需已购买)"""
    # 先查找素材
    asset = None
    for a in ASSETS:
        if a.id == asset_id:
            asset = a
            break
    
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    
    # 检查是否已购买或免费
    if asset.price == 0:
        # 免费素材直接下载
        return {"download_url": f"https://storage.example.com/assets/{asset_id}.mp4", "expires_in": 3600}
    
    # 检查购买记录
    if user_id not in purchases_db or asset_id not in purchases_db[user_id]:
        raise HTTPException(status_code=403, detail="未购买该素材")
    
    # 生成下载链接
    return {"download_url": f"https://storage.example.com/assets/{asset_id}.mp4", "expires_in": 3600}


@router.get("/preview/{asset_id}")
async def preview_asset(asset_id: str):
    """预览素材"""
    asset = None
    for a in ASSETS:
        if a.id == asset_id:
            asset = a
            break
    
    if not asset:
        raise HTTPException(status_code=404, detail="素材不存在")
    
    if not asset.preview_url:
        raise HTTPException(status_code=404, detail="无预览视频")
    
    return {
        "preview_url": asset.preview_url,
        "duration": 30,  # 预览 30 秒
        "watermark": True  # 带水印
    }