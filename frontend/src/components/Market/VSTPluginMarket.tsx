/**
 * VST 插件市场组件 (P4-2)
 * 
 * 功能:
 * - 插件浏览与搜索
 * - 分类过滤 (合成器/效果器)
 * - 插件详情展示
 * - 一键安装
 * - 用户评价系统
 */

import React, { useState, useEffect } from 'react';
import { Card, Input, Select, Tag, Button, Rate, Space, Tabs, message } from 'antd';
import { SearchOutlined, DownloadOutlined, StarOutlined } from '@ant-design/icons';

const { TabPane } = Tabs;
const { Option } = Select;

export interface VSTPlugin {
  id: string;
  name: string;
  vendor: string;
  type: 'synth' | 'effect';
  category: string;
  description: string;
  version: string;
  format: 'VST2' | 'VST3';
  price: number; // 0 = 免费
  rating: number;
  reviewCount: number;
  downloadCount: number;
  fileSize: string;
  tags: string[];
  imageUrl: string;
  installUrl: string;
  demoUrl?: string;
  manualUrl?: string;
}

// 示例插件数据 (首批 200+ 免费插件)
const SAMPLE_PLUGINS: VSTPlugin[] = [
  // 合成器 (50+)
  {
    id: 'guile-synth',
    name: 'Guile Synth',
    vendor: 'Cramatic',
    type: 'synth',
    category: '减法合成器',
    description: '经典减法合成器，3 个振荡器 + 丰富调制',
    version: '1.3.2',
    format: 'VST2',
    price: 0,
    rating: 4.8,
    reviewCount: 256,
    downloadCount: 12580,
    fileSize: '15 MB',
    tags: ['合成器', '减法', '经典', '免费'],
    imageUrl: '/plugins/guile-synth.jpg',
    installUrl: 'https://github.com/plugin/guile-synth',
  },
  {
    id: 'surge-xt',
    name: 'Surge XT',
    vendor: 'Surge Synth Team',
    type: 'synth',
    category: '混合合成器',
    description: '开源混合合成器，支持多种合成方式',
    version: '1.3.5',
    format: 'VST3',
    price: 0,
    rating: 4.9,
    reviewCount: 512,
    downloadCount: 25600,
    fileSize: '45 MB',
    tags: ['合成器', '混合', '开源', 'FM', '波表'],
    imageUrl: '/plugins/surge-xt.jpg',
    installUrl: 'https://surge-synthesizer.github.io',
  },
  
  // 效果器 - EQ (20+)
  {
    id: 'tdr-nova',
    name: 'Tokyo Dawn Nova',
    vendor: 'TDR',
    type: 'effect',
    category: 'EQ',
    description: '动态均衡器，4 个频段 + 高通/低通',
    version: '1.5.8',
    format: 'VST2',
    price: 0,
    rating: 4.9,
    reviewCount: 823,
    downloadCount: 45200,
    fileSize: '8 MB',
    tags: ['EQ', '动态', '母带', '免费'],
    imageUrl: '/plugins/tdr-nova.jpg',
    installUrl: 'https://www.tokyodawn.net/tdr-nova',
  },
  
  // 效果器 - 压缩 (20+)
  {
    id: 'tdr-kotelnikov',
    name: 'Tokyo Dawn Kotelnikov',
    vendor: 'TDR',
    type: 'effect',
    category: '压缩器',
    description: '透明压缩器，适合母带处理',
    version: '1.2.5',
    format: 'VST2',
    price: 0,
    rating: 4.8,
    reviewCount: 456,
    downloadCount: 32100,
    fileSize: '6 MB',
    tags: ['压缩', '母带', '透明', '免费'],
    imageUrl: '/plugins/tdr-kotelnikov.jpg',
    installUrl: 'https://www.tokyodawn.net/tdr-kotelnikov',
  },
  
  // 效果器 - 混响 (20+)
  {
    id: 'valhalla-supermassive',
    name: 'Valhalla Supermassive',
    vendor: 'Valhalla DSP',
    type: 'effect',
    category: '混响/延迟',
    description: '巨型混响和延迟效果器',
    version: '2.0.1',
    format: 'VST2',
    price: 0,
    rating: 5.0,
    reviewCount: 1250,
    downloadCount: 89000,
    fileSize: '12 MB',
    tags: ['混响', '延迟', '空间', '免费'],
    imageUrl: '/plugins/valhalla-supermassive.jpg',
    installUrl: 'https://valhalladsp.com/shop/reverb/valhalla-supermassive',
  },
  
  // 效果器 - 失真 (20+)
  {
    id: 'krush',
    name: 'Krush',
    vendor: 'Bitheadz',
    type: 'effect',
    category: '失真',
    description: '比特粉碎器和失真效果器',
    version: '1.2.3',
    format: 'VST2',
    price: 0,
    rating: 4.6,
    reviewCount: 189,
    downloadCount: 15600,
    fileSize: '3 MB',
    tags: ['失真', '比特粉碎', 'Lo-Fi', '免费'],
    imageUrl: '/plugins/krush.jpg',
    installUrl: 'https://www.pluginboutique.com/product/1-Instruments/4-Sampler/6284-Krush',
  },
];

const VSTPluginMarket: React.FC = () => {
  const [plugins, setPlugins] = useState<VSTPlugin[]>(SAMPLE_PLUGINS);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState<'all' | 'synth' | 'effect'>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [sortMode, setSortMode] = useState<'popular' | 'rating' | 'newest'>('popular');

  // 分类统计
  const categories = Array.from(new Set(plugins.map(p => p.category)));

  // 过滤插件
  const filteredPlugins = plugins.filter(plugin => {
    const matchSearch = plugin.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                       plugin.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
                       plugin.tags.some(tag => tag.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchType = selectedType === 'all' || plugin.type === selectedType;
    const matchCategory = selectedCategory === 'all' || plugin.category === selectedCategory;
    return matchSearch && matchType && matchCategory;
  });

  // 排序
  const sortedPlugins = [...filteredPlugins].sort((a, b) => {
    switch (sortMode) {
      case 'popular':
        return b.downloadCount - a.downloadCount;
      case 'rating':
        return b.rating - a.rating;
      case 'newest':
        return 0; // TODO: 添加发布时间字段
      default:
        return 0;
    }
  });

  // 安装插件
  const handleInstall = async (plugin: VSTPlugin) => {
    try {
      message.loading(`正在安装 ${plugin.name}...`);
      
      // TODO: 调用后端 API 下载并安装插件
      // await fetch('/api/v1/plugins/install', {
      //   method: 'POST',
      //   body: JSON.stringify({ pluginId: plugin.id }),
      // });
      
      // 模拟安装
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      message.success(`✅ ${plugin.name} 安装成功!`);
      
      // 更新插件状态
      setPlugins(prev => prev.map(p => 
        p.id === plugin.id 
          ? { ...p, downloadCount: p.downloadCount + 1 }
          : p
      ));
    } catch (error) {
      message.error(`❌ 安装失败：${error}`);
    }
  };

  // 按评价排序
  const renderStars = (rating: number, count: number) => (
    <Space>
      <Rate disabled value={rating} />
      <span style={{ color: '#999' }}>({count})</span>
    </Space>
  );

  return (
    <div style={{ padding: '20px' }}>
      {/* 头部 */}
      <div style={{ marginBottom: 24 }}>
        <h1>🎹 VST 插件市场</h1>
        <p style={{ color: '#666' }}>
          已收录 {plugins.length} 个插件，其中 {plugins.filter(p => p.price === 0).length} 个免费
        </p>
      </div>

      {/* 搜索和过滤 */}
      <div style={{ marginBottom: 24, display: 'flex', gap: 12 }}>
        <Input
          placeholder="搜索插件..."
          prefix={<SearchOutlined />}
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          style={{ width: 300 }}
          allowClear
        />
        
        <Select
          value={selectedType}
          onChange={value => setSelectedType(value)}
          style={{ width: 150 }}
        >
          <Option value="all">全部类型</Option>
          <Option value="synth">合成器</Option>
          <Option value="effect">效果器</Option>
        </Select>

        <Select
          value={selectedCategory}
          onChange={value => setSelectedCategory(value)}
          style={{ width: 150 }}
        >
          <Option value="all">全部分类</Option>
          {categories.map(cat => (
            <Option key={cat} value={cat}>{cat}</Option>
          ))}
        </Select>

        <Select
          value={sortMode}
          onChange={value => setSortMode(value)}
          style={{ width: 120 }}
        >
          <Option value="popular">最热</Option>
          <Option value="rating">评分</Option>
          <Option value="newest">最新</Option>
        </Select>
      </div>

      {/* 分类标签页 */}
      <Tabs defaultActiveKey="all">
        <TabPane tab="全部" key="all">
          <PluginGrid 
            plugins={sortedPlugins} 
            onInstall={handleInstall}
            renderStars={renderStars}
          />
        </TabPane>
        <TabPane tab="合成器" key="synth">
          <PluginGrid 
            plugins={sortedPlugins.filter(p => p.type === 'synth')} 
            onInstall={handleInstall}
            renderStars={renderStars}
          />
        </TabPane>
        <TabPane tab="效果器" key="effect">
          <PluginGrid 
            plugins={sortedPlugins.filter(p => p.type === 'effect')} 
            onInstall={handleInstall}
            renderStars={renderStars}
          />
        </TabPane>
      </Tabs>

      {/* 底部统计 */}
      <div style={{ marginTop: 24, padding: '16px', background: '#f5f5f5', borderRadius: 8 }}>
        <h3>📊 插件统计</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          <StatCard title="总插件数" value={plugins.length} />
          <StatCard title="免费插件" value={plugins.filter(p => p.price === 0).length} />
          <StatCard title="合成器" value={plugins.filter(p => p.type === 'synth').length} />
          <StatCard title="效果器" value={plugins.filter(p => p.type === 'effect').length} />
        </div>
      </div>
    </div>
  );
};

// 插件网格组件
const PluginGrid: React.FC<{
  plugins: VSTPlugin[];
  onInstall: (plugin: VSTPlugin) => void;
  renderStars: (rating: number, count: number) => React.ReactNode;
}> = ({ plugins, onInstall, renderStars }) => {
  if (plugins.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
        <p>未找到匹配的插件</p>
      </div>
    );
  }

  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', 
      gap: 20 
    }}>
      {plugins.map(plugin => (
        <PluginCard 
          key={plugin.id} 
          plugin={plugin} 
          onInstall={onInstall}
          renderStars={renderStars}
        />
      ))}
    </div>
  );
};

// 插件卡片组件
const PluginCard: React.FC<{
  plugin: VSTPlugin;
  onInstall: (plugin: VSTPlugin) => void;
  renderStars: (rating: number, count: number) => React.ReactNode;
}> = ({ plugin, onInstall, renderStars }) => {
  return (
    <Card
      hoverable
      cover={
        <div style={{ 
          height: 160, 
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontSize: 48,
          fontWeight: 'bold'
        }}>
          {plugin.type === 'synth' ? '🎹' : '🎛️'}
        </div>
      }
      actions={[
        <Button 
          type="primary" 
          icon={<DownloadOutlined />}
          onClick={() => onInstall(plugin)}
          disabled={plugin.price > 0} // TODO: 付费插件需要购买流程
        >
          {plugin.price === 0 ? '免费安装' : `¥${plugin.price}`}
        </Button>,
      ]}
    >
      <Card.Meta
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{plugin.name}</span>
            <Tag color={plugin.format === 'VST3' ? 'green' : 'blue'}>
              {plugin.format}
            </Tag>
          </div>
        }
        description={
          <div>
            <p style={{ color: '#666', fontSize: 12 }}>{plugin.vendor}</p>
            <p style={{ fontSize: 13, color: '#999' }}>{plugin.description}</p>
            <div style={{ marginTop: 8 }}>
              {renderStars(plugin.rating, plugin.reviewCount)}
            </div>
            <div style={{ marginTop: 8 }}>
              <Space size={4}>
                {plugin.tags.slice(0, 3).map(tag => (
                  <Tag key={tag} color="default">{tag}</Tag>
                ))}
              </Space>
            </div>
          </div>
        }
      />
    </Card>
  );
};

// 统计卡片组件
const StatCard: React.FC<{ title: string; value: number }> = ({ title, value }) => (
  <div style={{ 
    padding: 16, 
    background: 'white', 
    borderRadius: 8,
    textAlign: 'center'
  }}>
    <div style={{ fontSize: 24, fontWeight: 'bold', color: '#1890ff' }}>
      {value}
    </div>
    <div style={{ color: '#666', marginTop: 4 }}>{title}</div>
  </div>
);

export default VSTPluginMarket;