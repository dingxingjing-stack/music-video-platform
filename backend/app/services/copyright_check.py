"""
版权检测服务 (Copyright Check Service)

功能:
- 音频指纹提取
- 相似度检测
- 风险评估报告
- 数据库比对

算法:
- 频谱峰值检测 (Spectral Peak)
- 梅尔频率倒谱系数 (MFCC)
- 哈希指纹生成
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Body
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import hashlib
import numpy as np
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/v1/copyright", tags=["版权检测"])


# ============ Data Models ============

class AudioFingerprint(BaseModel):
    """音频指纹"""
    fingerprint_id: str
    hash: str
    mfcc_features: List[float]
    spectral_peaks: List[Dict[str, float]]
    duration: float
    created_at: datetime = Field(default_factory=datetime.now)


class CopyrightMatch(BaseModel):
    """版权匹配结果"""
    match_id: str
    reference_track_id: str
    reference_track_name: str
    similarity_score: float  # 0-1
    match_segments: List[Dict[str, Any]]  # 匹配片段
    risk_level: str  # "low", "medium", "high", "critical"


class CopyrightReport(BaseModel):
    """版权检测报告"""
    report_id: str
    audio_file_id: str
    audio_filename: str
    analyzed_at: datetime
    total_duration: float
    matches: List[CopyrightMatch]
    overall_risk: str  # "clear", "low", "medium", "high", "critical"
    risk_score: float  # 0-100
    recommendations: List[str]
    is_clear_for_use: bool


# ============ Mock Database ============

# 模拟的版权数据库 (实际应使用百万级曲库)
copyright_database: Dict[str, AudioFingerprint] = {
    # 示例：一些知名歌曲的指纹
}

# 风险阈值
RISK_THRESHOLDS = {
    "low": 0.3,       # < 30% 相似度 = 低风险
    "medium": 0.5,    # 30-50% = 中风险
    "high": 0.7,      # 50-70% = 高风险
    "critical": 0.85  # > 85% = 极高风险
}


# ============ Helper Functions ============

def extract_audio_fingerprint(audio_data: np.ndarray, sample_rate: int) -> AudioFingerprint:
    """
    提取音频指纹
    
    简化实现：
    1. 计算 MFCC 特征
    2. 检测频谱峰值
    3. 生成哈希指纹
    """
    # 实际实现需要 librosa 或类似的音频处理库
    # 这里是简化的 Mock 版本
    
    # 1. 简化 MFCC 提取 (Mock)
    mfcc_features = [float(x) for x in np.random.random(13) * 2 - 1]
    
    # 2. 简化频谱峰值检测 (Mock)
    spectral_peaks = []
    for i in range(0, len(audio_data), 1000):
        peak = {
            "time": i / sample_rate,
            "frequency": float(np.random.random() * 20000),  # 0-20kHz
            "magnitude": float(np.random.random())
        }
        spectral_peaks.append(peak)
    
    # 3. 生成哈希指纹
    audio_hash = hashlib.sha256(audio_data.tobytes()).hexdigest()[:16]
    
    return AudioFingerprint(
        fingerprint_id=str(uuid.uuid4()),
        hash=audio_hash,
        mfcc_features=mfcc_features,
        spectral_peaks=spectral_peaks[:20],  # 只保留前 20 个峰值
        duration=len(audio_data) / sample_rate
    )


def calculate_similarity(fp1: AudioFingerprint, fp2: AudioFingerprint) -> float:
    """
    计算两个指纹的相似度
    
    简化实现:
    - 比较 MFCC 特征的欧氏距离
    - 比较频谱峰值的重合度
    """
    # 1. MFCC 相似度 (简化为余弦相似度)
    mfcc1 = np.array(fp1.mfcc_features)
    mfcc2 = np.array(fp2.mfcc_features)
    
    cos_similarity = np.dot(mfcc1, mfcc2) / (np.linalg.norm(mfcc1) * np.linalg.norm(mfcc2))
    
    # 2. 哈希相似度 (简化：完全相同才给分)
    hash_similarity = 1.0 if fp1.hash == fp2.hash else 0.0
    
    # 3. 综合相似度 (加权平均)
    similarity = 0.7 * cos_similarity + 0.3 * hash_similarity
    
    return max(0, min(1, similarity))


def determine_risk_level(similarity: float) -> str:
    """根据相似度判断风险等级"""
    if similarity >= RISK_THRESHOLDS["critical"]:
        return "critical"
    elif similarity >= RISK_THRESHOLDS["high"]:
        return "high"
    elif similarity >= RISK_THRESHOLDS["medium"]:
        return "medium"
    elif similarity >= RISK_THRESHOLDS["low"]:
        return "low"
    else:
        return "clear"


def generate_recommendations(matches: List[CopyrightMatch]) -> List[str]:
    """生成建议"""
    recommendations = []
    
    if not matches:
        recommendations.append("✅ 未发现版权风险，可以安全使用")
        return recommendations
    
    for match in matches:
        if match.risk_level == "critical":
            recommendations.append(f"❌ 与《{match.reference_track_name}》高度相似 ({match.similarity_score*100:.1f}%) - 建议重新编曲或获取授权")
        elif match.risk_level == "high":
            recommendations.append(f"⚠️  与《{match.reference_track_name}》相似度较高 ({match.similarity_score*100:.1f}%) - 建议修改旋律或和声")
        elif match.risk_level == "medium":
            recommendations.append(f"⚠️  与《{match.reference_track_name}》存在相似性 ({match.similarity_score*100:.1f}%) - 建议审查相似段落")
        else:
            recommendations.append(f"ℹ️  与《{match.reference_track_name}》有轻微相似 ({match.similarity_score*100:.1f}%) - 风险较低，可自行决定")
    
    return recommendations


# ============ Endpoints ============

@router.post("/analyze")
async def analyze_copyright(
    audio_file: UploadFile = File(...)
):
    """
    上传音频文件进行版权检测
    
    返回:
    - 版权检测报告
    - 匹配结果列表
    - 风险评估
    """
    try:
        # 1. 读取音频文件
        audio_data = await audio_file.read()
        
        # 2. 简化处理：将文件内容转换为 numpy 数组 (Mock)
        # 实际实现需要使用 librosa 或 pydub 加载音频
        audio_array = np.frombuffer(audio_data, dtype=np.float32)
        
        # 3. 提取指纹
        fingerprint = extract_audio_fingerprint(audio_array, 44100)
        
        # 4. 在数据库中比对
        matches: List[CopyrightMatch] = []
        
        for ref_id, ref_fp in copyright_database.items():
            similarity = calculate_similarity(fingerprint, ref_fp)
            
            # 只返回相似度 > 30% 的匹配
            if similarity >= RISK_THRESHOLDS["low"]:
                risk_level = determine_risk_level(similarity)
                
                match = CopyrightMatch(
                    match_id=str(uuid.uuid4()),
                    reference_track_id=ref_id,
                    reference_track_name=f"Reference Track {ref_id[:8]}",  # Mock 名称
                    similarity_score=similarity,
                    match_segments=[{"start": 0, "end": fingerprint.duration, "confidence": similarity}],
                    risk_level=risk_level
                )
                matches.append(match)
        
        # 5. 计算总体风险
        if matches:
            max_similarity = max(m.similarity_score for m in matches)
            overall_risk = determine_risk_level(max_similarity)
            is_clear = False
        else:
            overall_risk = "clear"
            max_similarity = 0
            is_clear = True
        
        # 6. 生成建议
        recommendations = generate_recommendations(matches)
        
        # 7. 创建报告
        report = CopyrightReport(
            report_id=str(uuid.uuid4()),
            audio_file_id=fingerprint.fingerprint_id,
            audio_filename=audio_file.filename or "unknown.wav",
            analyzed_at=datetime.now(),
            total_duration=fingerprint.duration,
            matches=sorted(matches, key=lambda x: x.similarity_score, reverse=True),
            overall_risk=overall_risk,
            risk_score=max_similarity * 100,
            recommendations=recommendations,
            is_clear_for_use=is_clear
        )
        
        return report.dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"音频分析失败：{str(e)}")


@router.post("/fingerprint/compare")
async def compare_fingerprints(
    fingerprint1_id: str = Body(...),
    fingerprint2_id: str = Body(...)
):
    """直接比较两个指纹的相似度"""
    
    if fingerprint1_id not in copyright_database:
        raise HTTPException(status_code=404, detail="指纹 1 不存在")
    if fingerprint2_id not in copyright_database:
        raise HTTPException(status_code=404, detail="指纹 2 不存在")
    
    fp1 = copyright_database[fingerprint1_id]
    fp2 = copyright_database[fingerprint2_id]
    
    similarity = calculate_similarity(fp1, fp2)
    risk_level = determine_risk_level(similarity)
    
    return {
        "similarity": similarity,
        "similarity_percentage": f"{similarity*100:.2f}%",
        "risk_level": risk_level,
        "is_clear": similarity < RISK_THRESHOLDS["low"]
    }


@router.get("/report/{report_id}")
async def get_copyright_report(report_id: str):
    """获取版权检测报告"""
    # Mock 实现：实际应从数据库加载
    raise HTTPException(status_code=404, detail="报告需要存储在数据库中，当前为 Mock 实现")


@router.post("/database/register")
async def register_to_database(
    audio_fingerprint: AudioFingerprint
):
    """
    将音频指纹注册到版权数据库
    
    用于:
    - 用户上传自己的原创作品进行保护
    - 导入已知版权曲目数据库
    """
    copyright_database[audio_fingerprint.fingerprint_id] = audio_fingerprint
    
    return {
        "success": True,
        "message": "版权指纹已注册",
        "fingerprint_id": audio_fingerprint.fingerprint_id,
        "database_size": len(copyright_database)
    }


@router.get("/database/stats")
async def get_database_stats():
    """获取版权数据库统计信息"""
    return {
        "total_tracks": len(copyright_database),
        "database_status": "mock",  # Mock 模式
        "message": "当前为测试数据库，实际部署需要百万级版权曲库"
    }


# ============ Batch Processing ============

@router.post("/batch/analyze")
async def batch_analyze(
    audio_files: List[UploadFile] = File(...)
):
    """批量版权检测"""
    
    results = []
    
    for audio_file in audio_files:
        # 简化：逐个处理
        audio_data = await audio_file.read()
        audio_array = np.frombuffer(audio_data, dtype=np.float32)
        fingerprint = extract_audio_fingerprint(audio_array, 44100)
        
        # 快速比对
        matches = []
        for ref_id, ref_fp in copyright_database.items():
            similarity = calculate_similarity(fingerprint, ref_fp)
            if similarity >= RISK_THRESHOLDS["low"]:
                matches.append({
                    "track_id": ref_id,
                    "similarity": similarity,
                    "risk_level": determine_risk_level(similarity)
                })
        
        results.append({
            "filename": audio_file.filename,
            "fingerprint_id": fingerprint.fingerprint_id,
            "match_count": len(matches),
            "max_similarity": max((m["similarity"] for m in matches), default=0),
            "matches": matches[:5]  # 只返回前 5 个匹配
        })
    
    return {
        "total_analyzed": len(results),
        "results": results
    }