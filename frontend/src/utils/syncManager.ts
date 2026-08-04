/**
 * 离线同步管理器 (P3-6)
 * 精简版：KISS + DRY
 */

import { getUnsyncedProjectsOffline, markProjectSyncedOffline, getPendingUploadsOffline, removePendingUploadOffline } from './offlineDB';
import type { OfflineProject, PendingUpload } from './offlineDB';

class SyncManager {
  private syncing = false;
  private retryLimit = 3;

  constructor() {
    window.addEventListener('online', () => {
      console.log('✅ 网络恢复，开始同步...');
      this.syncAll();
    });
  }

  async syncAll(): Promise<void> {
    if (this.syncing || !navigator.onLine) return;

    this.syncing = true;
    try {
      await Promise.all([
        this.syncProjects(),
        this.syncPendingUploads(),
      ]);
      console.log('✅ 同步完成');
    } catch (error) {
      console.error('❌ 同步失败:', error);
    } finally {
      this.syncing = false;
    }
  }

  private async syncProjects(): Promise<void> {
    const unsynced = await getUnsyncedProjectsOffline();
    if (!unsynced.length) return;

    console.log(`📝 同步 ${unsynced.length} 个项目`);
    await Promise.all(unsynced.map(p => this.syncProject(p).catch(console.error)));
  }

  private async syncProject(p: OfflineProject): Promise<void> {
    try {
      const res = await fetch('/api/v1/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p.data),
      });

      if (res.ok) {
        await markProjectSyncedOffline(p.id);
        console.log(`✅ ${p.name} 同步成功`);
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (error) {
      console.error(`❌ ${p.name} 同步失败:`, error);
      throw error;
    }
  }

  private async syncPendingUploads(): Promise<void> {
    const pending = await getPendingUploadsOffline();
    if (!pending.length) return;

    console.log(`📤 上传 ${pending.length} 个文件`);
    await Promise.all(pending.map(u => this.processUpload(u)));
  }

  private async processUpload(u: PendingUpload): Promise<void> {
    try {
      const formData = new FormData();
      formData.append('file', u.file);

      const res = await fetch(u.endpoint, { method: 'POST', body: formData });
      if (res.ok) {
        await removePendingUploadOffline(u.id);
        console.log(`✅ ${u.file.name} 上传成功`);
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (error) {
      console.error(`❌ ${u.file.name} 上传失败:`, error);
      if (u.retries < this.retryLimit) {
        u.retries++;
        console.log(`🔄 重试 ${u.retries}/${this.retryLimit}`);
      }
    }
  }

  async forceSync(): Promise<void> {
    return this.syncAll();
  }

  getSyncStatus() {
    return { syncing: this.syncing, online: navigator.onLine };
  }
}

export const syncManager = new SyncManager();

// 自动同步检查
if (typeof window !== 'undefined' && navigator.onLine) {
  syncManager.syncAll().catch(console.error);
}