"""
歌词押韵 AI 引擎

P3-7: 智能歌词押韵生成
支持：
- ABAB/AABB/ABCB 等押韵格式
- 中文押韵 (拼音韵母匹配)
- 英文押韵 (音节匹配)
- 多语言混排押韵
"""

import re
from typing import List, Dict, Optional
from pypinyin import lazy_pinyin, Style


class RhymeEngine:
    """押韵引擎"""
    
    def __init__(self):
        # 中文韵母分类 (十三辙)
        self.chinese_rhymes = {
            '发花': ['a', 'ia', 'ua'],
            '梭波': ['o', 'e', 'uo'],
            '乜斜': ['ie', 'üe'],
            '一七': ['i', 'ü', 'er'],
            '姑苏': ['u'],
            '怀来': ['ai', 'uai'],
            '灰堆': ['ei', 'ui'],
            '遥条': ['ao', 'iao'],
            '由求': ['ou', 'iu'],
            '言前': ['an', 'ian', 'uan', 'üan'],
            '人臣': ['en', 'in', 'un', 'ün'],
            '江阳': ['ang', 'iang', 'uang'],
            '中东': ['eng', 'ing', 'ong', 'iong'],
        }
        
        # 英文常见韵脚
        self.english_rhymes = {
            'ay': ['ay', 'ey', 'ai'],
            'ee': ['ee', 'ea', 'ie', 'y'],
            'ight': ['ight', 'ite', 'ite'],
            'ow': ['ow', 'oe', 'ough'],
            'ue': ['ue', 'oo', 'ew'],
            'ar': ['ar', 'ear'],
            'or': ['or', 'ore', 'our'],
        }
    
    def get_chinese_rhyme(self, char: str) -> Optional[str]:
        """获取中文字符的韵母分类"""
        pinyin_list = lazy_pinyin(char, style=Style.NORMAL)
        if not pinyin_list:
            return None
        
        pinyin = pinyin_list[0]
        # 提取韵母
        for rhyme_name, rhymes in self.chinese_rhymes.items():
            for rhyme in rhymes:
                if pinyin.endswith(rhyme):
                    return rhyme_name
        
        return None
    
    def get_english_rhyme(self, word: str) -> Optional[str]:
        """获取英文单词的韵脚"""
        word = word.lower()
        for rhyme_name, endings in self.english_rhymes.items():
            for ending in endings:
                if word.endswith(ending):
                    return rhyme_name
        return None
    
    def detect_rhyme_scheme(self, lyrics: List[str]) -> str:
        """
        检测歌词押韵格式
        
        Returns:
            'AABB', 'ABAB', 'ABCB', 'AAAA', etc.
        """
        if len(lyrics) < 4:
            return 'UNKNOWN'
        
        # 提取每句最后一个字/词
        endings = []
        for line in lyrics[-4:]:  # 分析最后 4 句
            line = line.strip()
            if not line:
                continue
            
            # 检测语言
            if re.search(r'[\u4e00-\u9fa5]', line):
                # 中文：取最后一个字
                last_char = line[-1]
                rhyme = self.get_chinese_rhyme(last_char)
                endings.append(rhyme or line[-1])
            else:
                # 英文：取最后一个单词
                last_word = line.split()[-1] if line.split() else ''
                rhyme = self.get_english_rhyme(last_word)
                endings.append(rhyme or last_word)
        
        if len(endings) < 4:
            return 'UNKNOWN'
        
        # 分析押韵模式
        pattern = []
        rhyme_map = {}
        counter = 0
        
        for ending in endings:
            if ending not in rhyme_map:
                rhyme_map[ending] = chr(ord('A') + counter)
                counter += 1
            pattern.append(rhyme_map[ending])
        
        return ''.join(pattern)
    
    def suggest_rhymes(self, keyword: str, language: str = 'zh') -> List[str]:
        """
        根据关键词推荐押韵词汇
        
        Args:
            keyword: 关键词
            language: 'zh' or 'en'
        
        Returns:
            押韵词汇列表
        """
        suggestions = []
        
        if language == 'zh':
            # 中文押韵
            target_rhyme = self.get_chinese_rhyme(keyword[-1])
            if not target_rhyme:
                return []
            
            # 从韵母表查找同韵字
            for rhyme_name, rhymes in self.chinese_rhymes.items():
                if rhyme_name == target_rhyme:
                    # 这里应该连接词典 API
                    # 暂时返回示例
                    suggestions = [
                        f"{keyword}的花",
                        f"{keyword}的家",
                        f"{keyword}的涯",
                    ]
                    break
        
        elif language == 'en':
            # 英文押韵
            target_rhyme = self.get_english_rhyme(keyword.split()[-1])
            if not target_rhyme:
                return []
            
            suggestions = [
                f"with {keyword} today",
                f"like {keyword} away",
                f"and {keyword} stay",
            ]
        
        return suggestions
    
    def generate_rhyming_line(self, previous_line: str, scheme: str = 'AABB') -> str:
        """
        根据上一句生成押韵的下一句
        
        Args:
            previous_line: 上一句歌词
            scheme: 押韵格式
        
        Returns:
            押韵的下一句
        """
        # 提取上一句的韵脚
        if re.search(r'[\u4e00-\u9fa5]', previous_line):
            last_char = previous_line.strip()[-1]
            rhyme = self.get_chinese_rhyme(last_char)
            language = 'zh'
        else:
            last_word = previous_line.strip().split()[-1]
            rhyme = self.get_english_rhyme(last_word)
            language = 'en'
        
        # 生成建议
        suggestions = self.suggest_rhymes(
            last_char if language == 'zh' else last_word,
            language
        )
        
        if suggestions:
            return suggestions[0]
        
        #  fallback
        return f"... (押{rhyme}韵)"


# 全局实例
rhyme_engine = RhymeEngine()


# API 端点函数
def analyze_lyrics_rhyme(lines: List[str]) -> dict:
    """
    分析歌词押韵
    
    Returns:
        {
            "scheme": "AABB",
            "rhyme_words": ["花", "家", "涯"],
            "score": 85,
            "suggestions": [...]
        }
    """
    scheme = rhyme_engine.detect_rhyme_scheme(lines)
    
    # 计算押韵得分
    if scheme in ['AAAA', 'AABB', 'ABAB']:
        score = 90
    elif scheme == 'ABCB':
        score = 75
    else:
        score = 60
    
    return {
        "scheme": scheme,
        "score": score,
        "suggestions": []
    }


def generate_rhyme_suggestion(previous: str) -> str:
    """生成押韵建议"""
    return rhyme_engine.generate_rhyming_line(previous)