import http from './http'; // default export with get/post

export const getTemplates = () => http.get<Array<any>>('/api/v1/mv/templates');
export const startRender = (payload: {
  audio_url: string;
  template_id: string;
  title?: string;
  subtitles?: string[];
  premium?: boolean;
}) => http.post<{task_id: string}>('/api/v1/mv/render', payload);
export const getStatus = (taskId: string) =>
  http.get<{state: string; progress: number; video_url: string | null}>(`/api/v1/mv/status/${taskId}`);
export const veedProcess = (payload: { video_url: string; add_music?: boolean; remove_bg?: boolean }) =>
  http.post('/api/v1/mv/veed-process', payload);
