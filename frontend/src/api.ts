import type { AISettings, AIUsage, ApplicationUpdate, ApplicationUpdateProgress, Capabilities, EditorRevision, FacebookPage, FacebookSettings, GeneratedCopy, ImagePostCopy, MusicTrack, OverlayRegion, Project, Publication, SubtitleSegment } from './types';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `คำขอไม่สำเร็จ (${response.status})`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === 'string') message = payload.detail;
    } catch {
      // Keep the readable fallback for non-JSON server errors.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: () => request<Capabilities>('/api/capabilities'),
  checkApplicationUpdates: () => request<ApplicationUpdate>('/api/updates'),
  applicationUpdateSession: () => request<ApplicationUpdateProgress | null>('/api/updates/session'),
  installApplicationUpdate: (version: string) => request<Omit<ApplicationUpdateProgress, 'progress'>>('/api/updates/install', { method: 'POST', body: JSON.stringify({ version }) }),
  applicationUpdateProgress: (id: string) => request<ApplicationUpdateProgress>(`/api/updates/progress/${encodeURIComponent(id)}`),
  projects: (query = '') => request<Project[]>(`/api/projects${query ? `?q=${encodeURIComponent(query)}` : ''}`),
  project: (id: string) => request<Project>(`/api/projects/${encodeURIComponent(id)}`),
  createProject: (data: { title: string; product_name: string; product_details: string; review_evidence: string; discount_text: string; copy_style: Project['copy_style']; affiliate_url: string; source_url: string }) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),
  updateProject: (id: string, data: { title: string; product_name: string; product_details: string; review_evidence: string; discount_text: string; copy_style: Project['copy_style']; affiliate_url: string; source_url: string }) =>
    request<Project>(`/api/projects/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  uploadAsset: (projectId: string, file: File, kind: 'source_video' | 'music_track' = 'source_video') => {
    const body = new FormData();
    body.append('file', file, file.name);
    return request<{ asset: Project['assets'][number]; job: Project['jobs'][number] }>(
      `/api/projects/${encodeURIComponent(projectId)}/assets?kind=${kind}`,
      { method: 'POST', body },
    );
  },
  uploadVideo: (projectId: string, file: File) => api.uploadAsset(projectId, file, 'source_video'),
  musicLibrary: () => request<MusicTrack[]>('/api/music-library'),
  uploadMusicTrack: (file: File) => {
    const body = new FormData(); body.append('file', file, file.name);
    return request<MusicTrack>('/api/music-library', { method: 'POST', body });
  },
  editor: (projectId: string) => request<EditorRevision>(`/api/projects/${encodeURIComponent(projectId)}/editor`),
  saveSubtitles: (revisionId: string, items: Array<Pick<SubtitleSegment, 'stable_id' | 'start_ms' | 'end_ms' | 'source_text' | 'translated_text' | 'review_flag'>>) =>
    request<EditorRevision>(`/api/revisions/${encodeURIComponent(revisionId)}/subtitles`, { method: 'PUT', body: JSON.stringify({ items }) }),
  importSrt: (revisionId: string, content: string) =>
    request<EditorRevision>(`/api/revisions/${encodeURIComponent(revisionId)}/subtitles/import-srt`, { method: 'POST', body: JSON.stringify({ content }) }),
  saveOverlays: (revisionId: string, items: OverlayRegion[]) =>
    request<EditorRevision>(`/api/revisions/${encodeURIComponent(revisionId)}/overlays`, { method: 'PUT', body: JSON.stringify({ items }) }),
  saveSettings: (revisionId: string, settings: NonNullable<EditorRevision['settings']>) =>
    request<EditorRevision>(`/api/revisions/${encodeURIComponent(revisionId)}/settings`, { method: 'PATCH', body: JSON.stringify(settings) }),
  downloadSrt: async (revisionId: string) => {
    const response = await fetch(`/api/revisions/${encodeURIComponent(revisionId)}/subtitles/export.srt`);
    if (!response.ok) throw new ApiError('ดาวน์โหลด SRT ไม่สำเร็จ', response.status);
    return response.blob();
  },
  render: (revisionId: string) => request<{ render_id: string; asset: Project['assets'][number]; job: Project['jobs'][number] }>(
    `/api/revisions/${encodeURIComponent(revisionId)}/render`, { method: 'POST', body: '{}' },
  ),
  createPublication: (revisionId: string, data: { render_asset_id: string; caption: string; comment_text: string }) =>
    request<Publication>(`/api/revisions/${encodeURIComponent(revisionId)}/publications`, { method: 'POST', body: JSON.stringify(data) }),
  generateImagePostCopy: (product_details: string, affiliate_url: string) => request<ImagePostCopy>('/api/image-posts/generate-copy', {
    method: 'POST', body: JSON.stringify({ product_details, affiliate_url }),
  }),
  createImagePost: (imageFiles: File[], data: { caption: string; comment_text: string; affiliate_url: string; product_details: string }) => {
    const body = new FormData();
    imageFiles.forEach((imageFile) => body.append('image_files', imageFile, imageFile.name));
    body.append('caption', data.caption);
    body.append('comment_text', data.comment_text);
    body.append('affiliate_url', data.affiliate_url);
    body.append('product_details', data.product_details);
    return request<Publication>('/api/image-posts', { method: 'POST', body });
  },
  publications: (status = '') => request<Publication[]>(`/api/publications${status ? `?status=${encodeURIComponent(status)}` : ''}`),
  replacePublicationImage: (publicationId: string, assetId: string, file: File) => {
    const body = new FormData();
    body.append('image_file', file, file.name);
    return request<Publication>(
      `/api/publications/${encodeURIComponent(publicationId)}/images/${encodeURIComponent(assetId)}`,
      { method: 'PUT', body },
    );
  },
  updatePublication: (id: string, data: { caption: string; comment_text: string; scheduled_at: string | null }) =>
    request<Publication>(`/api/publications/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  cancelPublication: (id: string) => request<Publication>(`/api/publications/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }),
  publishNow: (id: string) => request<Publication>(`/api/publications/${encodeURIComponent(id)}/publish-now`, { method: 'POST', body: '{}' }),
  retryPublicationComment: (id: string) => request<Publication>(`/api/publications/${encodeURIComponent(id)}/retry-comment`, { method: 'POST', body: '{}' }),
  facebookSettings: () => request<FacebookSettings>('/api/settings/facebook'),
  connectFacebookPage: (page_id: string, page_access_token: string) => request<FacebookPage>('/api/settings/facebook/connect', { method: 'POST', body: JSON.stringify({ page_id, page_access_token }) }),
  testFacebookPage: (id: string) => request<{ ok: boolean; page_id: string; page_name: string; api_version: string }>(`/api/settings/facebook/${encodeURIComponent(id)}/test`, { method: 'POST', body: '{}' }),
  selectFacebookPage: (id: string) => request<FacebookPage>(`/api/settings/facebook/${encodeURIComponent(id)}/select`, { method: 'PATCH', body: '{}' }),
  disconnectFacebookPage: (id: string) => request<void>(`/api/settings/facebook/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  downloadBackup: async () => {
    const response = await fetch('/api/maintenance/backup');
    if (!response.ok) {
      let message = 'สำรองข้อมูลไม่สำเร็จ';
      try { const payload = await response.json(); if (typeof payload.detail === 'string') message = payload.detail; } catch { /* Keep the readable fallback. */ }
      throw new ApiError(message, response.status);
    }
    const disposition = response.headers.get('content-disposition') ?? '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? 'kodkon-studio-backup.zip';
    return { blob: await response.blob(), filename };
  },
  aiSettings: () => request<AISettings>('/api/settings/ai'),
  aiUsage: () => request<AIUsage>('/api/settings/ai/usage'),
  saveGeminiKey: (api_key: string) => request<void>('/api/settings/ai/key', { method: 'PUT', body: JSON.stringify({ api_key }) }),
  removeGeminiKey: () => request<void>('/api/settings/ai/key', { method: 'DELETE' }),
  setGeminiModel: (model: string) => request<{ model: string }>('/api/settings/ai/model', { method: 'PATCH', body: JSON.stringify({ model }) }),
  testGemini: () => request<{ ok: boolean; model: string }>('/api/settings/ai/test', { method: 'POST', body: '{}' }),
  queueOcr: (revisionId: string) => request<Project['jobs'][number]>(`/api/revisions/${encodeURIComponent(revisionId)}/ocr`, { method: 'POST', body: '{}' }),
  queueTranslation: (revisionId: string) => request<Project['jobs'][number]>(`/api/revisions/${encodeURIComponent(revisionId)}/translate`, { method: 'POST', body: '{}' }),
  queueCopyPart: (revisionId: string, part: 'script' | 'caption') => request<Project['jobs'][number]>(`/api/revisions/${encodeURIComponent(revisionId)}/generate-copy-part`, { method: 'POST', body: JSON.stringify({ part }) }),
  queueVoiceover: (revisionId: string, voice: string) => request<Project['jobs'][number]>(`/api/revisions/${encodeURIComponent(revisionId)}/generate-voiceover`, { method: 'POST', body: JSON.stringify({ voice }) }),
  job: (jobId: string) => request<Project['jobs'][number]>(`/api/jobs/${encodeURIComponent(jobId)}`),
  generatedCopy: (revisionId: string) => request<GeneratedCopy>(`/api/revisions/${encodeURIComponent(revisionId)}/copy`),
  saveGeneratedCopy: (revisionId: string, data: Omit<GeneratedCopy, 'model_name' | 'updated_at'>) => request<GeneratedCopy>(`/api/revisions/${encodeURIComponent(revisionId)}/copy`, { method: 'PUT', body: JSON.stringify(data) }),
};

export function assetFileUrl(assetId: string): string {
  return `/api/assets/${encodeURIComponent(assetId)}/file`;
}

export function musicTrackFileUrl(trackId: string): string {
  return `/api/music-library/${encodeURIComponent(trackId)}/file`;
}
