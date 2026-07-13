/**
 * One Click Publish API
 */

import http from './http';

export interface Platform {
  id: string;
  name: string;
  icon: string;
  supported: boolean;
  authorized: boolean;
  features: string[];
}

export interface PublishRequest {
  video_url: string;
  platforms: string[];
  title: string;
  description: string;
  tags: string[];
  privacy: string;
  cover_image_url?: string;
  youtube_category_id?: string;
  youtube_made_for_kids?: boolean;
  bilibili_tid?: number;
  bilibili_source?: string;
  tiktok_music_info?: any;
}

export interface PublishTask {
  task_id: string;
  platforms: string[];
  title: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'partial';
  progress: number;
  created_at: string;
  results: {
    [platformId: string]: {
      status: 'success' | 'failed';
      video_id?: string;
      url?: string;
      error?: string;
    };
  };
}

export interface PublishStatus {
  task_id: string;
  status: string;
  progress: number;
  message: string;
  results: any;
  platform_results: any;
}

export const getPlatforms = () => http.get<{ platforms: Platform[] }>('/api/v1/publish/platforms');

export const authPlatform = (platform: string, redirect_uri: string) =>
  http.post<{ auth_url?: string; status: string; message: string }>(
    `/api/v1/publish/auth/${platform}`,
    { redirect_uri }
  );

export const uploadVideo = (payload: PublishRequest) =>
  http.post<PublishTask>('/api/v1/publish/upload', payload);

export const getStatus = (taskId: string) =>
  http.get<PublishStatus>(`/api/v1/publish/status/${taskId}`);

export const listTasks = (limit = 20) =>
  http.get<{ tasks: PublishTask[]; total: number }>(`/api/v1/publish/tasks?limit=${limit}`);

export const cancelTask = (taskId: string) =>
  http.post<{ success: boolean; message: string }>(`/api/v1/publish/tasks/${taskId}/cancel`, {});