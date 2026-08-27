# Experimental Voice Clone Stack

## ⚠️ 实验性/非生产环境

此目录包含声音克隆相关的实验性代码，**不在 V1 生产路径中**。

## 包含组件

1. **GPT-SoVITS Modal 部署** (gpt_sovits_modal.py)
   - T4 GPU 部署，冷启动 >300s，显存不足
   - 仅作技术储备

2. **GPT-SoVITS 客户端** (	ts_client.py, sr_client.py)
   - Modal 函数调用、参考音频上传、ASR 转写

3. **Provider/Orchestrator** (oice_clone_provider.py, oice_clone_orchestrator.py)
   - 统一接口、分段生成、beat alignment、混音

4. **参考音频服务** (oice_reference_service.py)
   - 上传/校验/授权/R2 私有存储/用户隔离

5. **API 路由** (oice_clone_router.py)
   - /api/v1/voice-reference/* 上传/查询/下载/删除

## ⚠️ 已知阻断项

1. **License 红线**: GPT-SoVITS 官方明确禁止商业用途
2. **T4 GPU 不可用**: 显存不足，冷启动 >300s，需 A10G/H100
3. **R2 凭据**: 需配置有效凭据

## 重新启用条件 (V2)

- [ ] 确认商业许可清晰的 Voice Clone 模型
- [ ] 升级 GPU 至 A10G/H100
- [ ] 解决 License 风险
- [ ] 成本模型可控

---

**决策记录**: V1 版本聚焦核心 AI 音乐生成，Voice Clone 作为 V2 独立评估。
