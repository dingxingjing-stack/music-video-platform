/**
 * IndexedDB 离线存储 (P3-6)
 * 精简版：KISS + DRY
 */

const DB_NAME = 'hermes-offline-db';
const DB_VERSION = 1;

export interface OfflineProject {
  id: string;
  name: string;
  data: any;
  lastModified: number;
  synced: boolean;
}

export interface PendingUpload {
  id: string;
  type: 'audio' | 'video' | 'project';
  file: File;
  endpoint: string;
  retries: number;
  createdAt: number;
}

class OfflineDB {
  private db: IDBDatabase | null = null;

  private async open(): Promise<IDBDatabase> {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onerror = () => reject(req.error);
      req.onsuccess = () => { this.db = req.result; resolve(req.result); };
      req.onupgradeneeded = (e: any) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains('projects')) {
          const ps = db.createObjectStore('projects', { keyPath: 'id' });
          ps.createIndex('lastModified', 'lastModified');
          ps.createIndex('synced', 'synced');
        }
        if (!db.objectStoreNames.contains('pendingUploads')) {
          const us = db.createObjectStore('pendingUploads', { keyPath: 'id' });
          us.createIndex('createdAt', 'createdAt');
          us.createIndex('type', 'type');
        }
        if (!db.objectStoreNames.contains('settings')) {
          db.createObjectStore('settings', { keyPath: 'key' });
        }
      };
    });
  }

  async saveProject(p: OfflineProject): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction('projects', 'readwrite');
      tx.objectStore('projects').put(p);
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }

  async getProject(id: string): Promise<OfflineProject | null> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const req = db.transaction('projects').objectStore('projects').get(id);
      req.onsuccess = () => res(req.result || null);
      req.onerror = () => rej(req.error);
    });
  }

  async getAllProjects(): Promise<OfflineProject[]> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const req = db.transaction('projects').objectStore('projects').getAll();
      req.onsuccess = () => res(req.result);
      req.onerror = () => rej(req.error);
    });
  }

  async getUnsyncedProjects(): Promise<OfflineProject[]> {
    const all = await this.getAllProjects();
    return all.filter(p => !p.synced);
  }

  async markProjectSynced(id: string): Promise<void> {
    const p = await this.getProject(id);
    if (p) { p.synced = true; await this.saveProject(p); }
  }

  async deleteProject(id: string): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction('projects', 'readwrite');
      tx.objectStore('projects').delete(id);
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }

  async addToUploadQueue(u: PendingUpload): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction('pendingUploads', 'readwrite');
      tx.objectStore('pendingUploads').add(u);
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }

  async getPendingUploads(): Promise<PendingUpload[]> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const req = db.transaction('pendingUploads').objectStore('pendingUploads').getAll();
      req.onsuccess = () => res(req.result);
      req.onerror = () => rej(req.error);
    });
  }

  async removePendingUpload(id: string): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction('pendingUploads', 'readwrite');
      tx.objectStore('pendingUploads').delete(id);
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }

  async setSetting(key: string, value: any): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction('settings', 'readwrite');
      tx.objectStore('settings').put({ key, value });
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }

  async getSetting(key: string): Promise<any> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const req = db.transaction('settings').objectStore('settings').get(key);
      req.onsuccess = () => res(req.result?.value || null);
      req.onerror = () => rej(req.error);
    });
  }

  async clearAll(): Promise<void> {
    const db = await this.open();
    return new Promise((res, rej) => {
      const tx = db.transaction(['projects', 'pendingUploads', 'settings'], 'readwrite');
      tx.objectStore('projects').clear();
      tx.objectStore('pendingUploads').clear();
      tx.objectStore('settings').clear();
      tx.oncomplete = () => res();
      tx.onerror = () => rej(tx.error);
    });
  }
}

export const offlineDB = new OfflineDB();

// 便捷函数
export const saveProjectOffline = (p: OfflineProject) => offlineDB.saveProject(p);
export const getProjectOffline = (id: string) => offlineDB.getProject(id);
export const getUnsyncedProjectsOffline = () => offlineDB.getUnsyncedProjects();
export const markProjectSyncedOffline = (id: string) => offlineDB.markProjectSynced(id);
export const addToUploadQueueOffline = (u: PendingUpload) => offlineDB.addToUploadQueue(u);
export const getPendingUploadsOffline = () => offlineDB.getPendingUploads();
export const removePendingUploadOffline = (id: string) => offlineDB.removePendingUpload(id);

// 自动初始化
if (typeof indexedDB !== 'undefined') {
  offlineDB.open().catch(console.error);
}