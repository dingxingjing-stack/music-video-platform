"""
素材库扩充脚本 - 批量爬取免费素材

目标：从 Pexels/Pixabay 爬取 100+ 免费模板和素材
用途：快速扩充 MV 模板库

功能:
- 批量下载 Pexels 视频
- 批量下载 Pixabay 视频/图片
- 自动分类和标签化
- 生成素材索引 JSON
"""

import requests
import os
import json
from typing import List, Dict
import time

# ========== 配置 ==========

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")  # https://www.pexels.com/api/
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")  # https://pixabay.com/api/docs/

# 分类标签
CATEGORIES = {
    "nature": ["nature", "forest", "mountain", "ocean", "sunset", "sky"],
    "city": ["city", "urban", "building", "street", "night", "downtown"],
    "people": ["people", "dance", "party", "concert", "crowd", "friends"],
    "technology": ["technology", "computer", "phone", "digital", "cyber"],
    "abstract": ["abstract", "colorful", "pattern", "geometric", "fluid"],
    "music": ["music", "concert", "instrument", "guitar", "piano", "dj"],
    "sports": ["sports", "fitness", "gym", "running", "cycling", "yoga"],
    "food": ["food", "cooking", "restaurant", "cafe", "drink"],
    "travel": ["travel", "beach", "vacation", "adventure", "road"],
    "emotions": ["love", "happy", "sad", "romantic", "dreamy"]
}

# 输出目录
OUTPUT_DIR = r"C:\Users\dingx\music-video-platform\frontend\public\assets\stock"
INDEX_FILE = os.path.join(OUTPUT_DIR, "stock_index.json")


class StockScraper:
    """素材爬取器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.downloaded = []
    
    def search_pexels(self, query: str, per_page: int = 15) -> List[Dict]:
        """搜索 Pexels 视频"""
        if not PEXELS_API_KEY:
            print(f"⚠️ Pexels API Key 未设置，跳过 {query}")
            return []
        
        url = f"https://api.pexels.com/videos/search?query={query}&per_page={per_page}"
        headers = {"Authorization": PEXELS_API_KEY}
        
        try:
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                videos = data.get("videos", [])
                print(f"✅ Pexels '{query}': 找到 {len(videos)} 个视频")
                return videos[:per_page]  # 限制数量
            else:
                print(f"❌ Pexels API 错误：{response.status_code}")
                return []
        except Exception as e:
            print(f"⚠️ Pexels 请求失败：{e}")
            return []
    
    def search_pixabay(self, query: str, per_page: int = 15) -> List[Dict]:
        """搜索 Pixabay 视频"""
        if not PIXABAY_API_KEY:
            print(f"⚠️ Pixabay API Key 未设置，跳过 {query}")
            return []
        
        url = f"https://pixabay.com/api/videos/?key={PIXABAY_API_KEY}&q={query}&per_page={per_page}"
        
        try:
            response = self.session.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                videos = data.get("hits", [])
                print(f"✅ Pixabay '{query}': 找到 {len(videos)} 个视频")
                return videos[:per_page]
            else:
                print(f"❌ Pixabay API 错误：{response.status_code}")
                return []
        except Exception as e:
            print(f"⚠️ Pixabay 请求失败：{e}")
            return []
    
    def download_video(self, url: str, save_path: str) -> bool:
        """下载视频文件"""
        try:
            response = self.session.get(url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"  ✅ 下载：{save_path}")
                return True
            else:
                print(f"  ❌ 下载失败：{url}")
                return False
        except Exception as e:
            print(f"  ⚠️ 下载异常：{e}")
            return False
    
    def scrape_category(self, category: str, keywords: List[str], limit: int = 10):
        """爬取单个分类的素材"""
        print(f"\n{'='*60}")
        print(f"📁 爬取分类：{category}")
        print(f"{'='*60}")
        
        category_dir = os.path.join(OUTPUT_DIR, category)
        os.makedirs(category_dir, exist_ok=True)
        
        all_videos = []
        
        for keyword in keywords:
            print(f"\n🔍 搜索关键词：{keyword}")
            
            # Pexels
            pexels_videos = self.search_pexels(keyword, per_page=5)
            for video in pexels_videos[:3]:  # 每个关键词下载 3 个
                video_files = video.get("video_files", [])
                if video_files:
                    # 选择最低分辨率以节省空间
                    video_file = min(video_files, key=lambda x: x.get("width", 1920))
                    video_url = video_file.get("link")
                    
                    if video_url:
                        # 生成文件名
                        video_id = video.get("id")
                        ext = video_url.split(".")[-1].split("?")[0] or "mp4"
                        filename = f"{keyword}_{video_id}.{ext}"
                        save_path = os.path.join(category_dir, filename)
                        
                        # 下载
                        if not os.path.exists(save_path):
                            success = self.download_video(video_url, save_path)
                            if success:
                                all_videos.append({
                                    "id": str(video_id),
                                    "category": category,
                                    "keyword": keyword,
                                    "filename": filename,
                                    "path": f"/assets/stock/{category}/{filename}",
                                    "width": video_file.get("width"),
                                    "height": video_file.get("height"),
                                    "duration": video.get("duration", 0),
                                    "user": video.get("user", {}).get("name", "Unknown"),
                                    "url": video.get("url", ""),
                                    "tags": [category, keyword],
                                    "source": "pexels",
                                    "license": "Pexels License (Free)"
                                })
                        
                        # 限制总数
                        if len(all_videos) >= limit:
                            break
            
            # Pixabay (类似逻辑，简化)
            pixabay_videos = self.search_pixabay(keyword, per_page=5)
            for video in pixabay_videos[:2]:  # 每个关键词下载 2 个
                videos_list = video.get("videos", {})
                if videos_list:
                    # 选择可用视频
                    for quality in ["sd", "hd", "fullhd"]:
                        if quality in videos_list:
                            video_url = videos_list[quality].get("url")
                            if video_url:
                                video_id = video.get("id")
                                filename = f"{keyword}_pixabay_{video_id}.mp4"
                                save_path = os.path.join(category_dir, filename)
                                
                                if not os.path.exists(save_path):
                                    success = self.download_video(video_url, save_path)
                                    if success:
                                        all_videos.append({
                                            "id": str(video_id),
                                            "category": category,
                                            "keyword": keyword,
                                            "filename": filename,
                                            "path": f"/assets/stock/{category}/{filename}",
                                            "width": videos_list[quality].get("width"),
                                            "height": videos_list[quality].get("height"),
                                            "duration": 0,
                                            "user": video.get("user", "Unknown"),
                                            "url": video.get("url", ""),
                                            "tags": [category, keyword],
                                            "source": "pixabay",
                                            "license": "Pixabay License (Free)"
                                        })
                                
                                if len(all_videos) >= limit:
                                    break
            
            if len(all_videos) >= limit:
                break
        
        print(f"\n✅ 分类 {category} 完成：{len(all_videos)} 个视频")
        return all_videos
    
    def scrape_all(self, limit_per_category: int = 10):
        """爬取所有分类"""
        print("🚀 开始批量爬取素材...")
        print(f"目标：{len(CATEGORIES)} 分类 × {limit_per_category} = {len(CATEGORIES) * limit_per_category} 个素材")
        
        all_videos = []
        
        for category, keywords in CATEGORIES.items():
            videos = self.scrape_category(category, keywords, limit=limit_per_category)
            all_videos.extend(videos)
            
            # 避免 IP 被封，暂停一下
            time.sleep(2)
        
        # 保存索引
        self.save_index(all_videos)
        
        return all_videos
    
    def generate_mock_data(self, total: int = 100) -> List[Dict]:
        """生成 Mock 演示数据 (用于测试)"""
        print(f"🎭 生成 {total} 个 Mock 素材...")
        
        categories_list = list(CATEGORIES.keys())
        mock_videos = []
        
        for i in range(total):
            category = categories_list[i % len(categories_list)]
            source = "pexels" if i % 2 == 0 else "pixabay"
            
            mock_videos.append({
                "id": f"mock-{i}",
                "category": category,
                "keyword": CATEGORIES[category][0],
                "filename": f"{category}_{i}.mp4",
                "path": f"/assets/stock/{category}/{category}_{i}.mp4",
                "title": f"{category.title()} Video {i+1}",
                "width": 1920,
                "height": 1080,
                "duration": (i % 30) + 5,
                "user": f"User{i}",
                "url": f"https://example.com/video/{i}",
                "tags": [category, "free", "hd"],
                "source": source,
                "license": "Pexels License (Free)" if source == "pexels" else "Pixabay License (Free)"
            })
        
        # 保存索引
        self.save_index(mock_videos)
        
        return mock_videos
    
    def save_index(self, videos: List[Dict]):
        """保存素材索引 JSON"""
        index = {
            "total": len(videos),
            "categories": list(set(v["category"] for v in videos)),
            "sources": {
                "pexels": sum(1 for v in videos if v["source"] == "pexels"),
                "pixabay": sum(1 for v in videos if v["source"] == "pixabay")
            },
            "videos": videos,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "license_info": """
所有素材来自 Pexels 和 Pixabay，遵循免费许可协议:
- 可用于商业用途
- 无需署名 (但建议)
- 可修改和二次创作
- 不可转售原始素材
            """.strip()
        }
        
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        
        print(f"\n📊 索引已保存：{INDEX_FILE}")
        print(f"   总素材数：{len(videos)}")
        print(f"   分类数：{len(index['categories'])}")
        print(f"   Pexels: {index['sources']['pexels']}")
        print(f"   Pixabay: {index['sources']['pixabay']}")


# ========== 主函数 ==========

def main():
    """主函数"""
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    scraper = StockScraper()
    
    # 开始爬取
    # 如果没有 API Key，使用 Mock 模式生成演示数据
    if not PEXELS_API_KEY and not PIXABAY_API_KEY:
        print("⚠️ 未设置 API Key，生成 Mock 演示数据...")
        videos = scraper.generate_mock_data()
    else:
        videos = scraper.scrape_all(limit_per_category=10)
    
    return videos


if __name__ == "__main__":
    videos = main()
    print(f"\n🎉 完成！共获取 {len(videos)} 个素材")
    print(f"📁 查看：{OUTPUT_DIR}")
    print(f"📄 索引：{INDEX_FILE}")