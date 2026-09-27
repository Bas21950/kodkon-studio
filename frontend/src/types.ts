export type JobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
export type AssetState = 'uploading' | 'processing' | 'ready' | 'failed';

export interface Asset {
  id: string;
  project_id: string;
  kind: string;
  original_name: string;
  byte_size: number;
  state: AssetState;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean | null;
  frame_rate: number | null;
  video_codec: string | null;
  container_format: string | null;
  error_message: string | null;
  created_at: string;
}

export interface MusicTrack {
  id: string;
  original_name: string;
  byte_size: number;
  duration_ms: number | null;
  created_at: string;
}

export interface Job {
  id: string;
  project_id: string;
  asset_id: string | null;
  job_type: string;
  state: JobState;
  progress: number;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Project {
  id: string;
  title: string;
  product_name: string | null;
  product_details: string | null;
  product_source_details: string | null;
  review_evidence: string | null;
  product_average_rating: number | null;
  product_review_count: number | null;
  product_review_summary: string | null;
  product_data_read_at: string | null;
  discount_text: string | null;
  copy_style: 'problem_solution' | 'friendly_review' | 'direct_offer';
  affiliate_url: string | null;
  source_url: string | null;
  created_at: string;
  updated_at: string;
  assets: Asset[];
  jobs: Job[];
}

export interface Capabilities {
  app: string;
  version: string;
  ffmpeg_available: boolean;
  ffprobe_available: boolean;
  max_upload_bytes: number;
  storage_available_bytes: number;
  data_directory_name: string;
}

export interface ApplicationUpdate {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  release_url: string;
  published_at: string | null;
  notes: string;
  installable: boolean;
}

export type ApplicationUpdateStatus = 'checking' | 'downloading' | 'verifying' | 'installing' | 'restarting' | 'completed' | 'failed';

export interface ApplicationUpdateProgress {
  update_id: string;
  version: string;
  status: ApplicationUpdateStatus;
  progress: number;
  message: string;
}

export interface SubtitleSegment {
  stable_id: string;
  position: number;
  start_ms: number;
  end_ms: number;
  source_text: string;
  translated_text: string;
  ocr_confidence: number | null;
  review_flag: boolean;
}

export interface OverlayRegion {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  start_ms: number;
  end_ms: number;
  color: string;
  opacity: number;
}

export interface EditorRevision {
  id: string;
  project_id: string;
  version: number;
  state: string;
  source_asset: Asset | null;
  voiceover_asset?: Asset | null;
  settings: {
    audio_mode?: 'mute' | 'music';
    source_audio_enabled?: boolean;
    music_asset_id?: string | null;
    music_library_id?: string | null;
    music_volume?: number;
    music_fade_ms?: number;
    voiceover_asset_id?: string | null;
    voiceover_volume?: number;
    subtitle_style?: {
      font_size?: number;
      font_color?: string;
      box_color?: string;
      box_opacity?: number;
      margin_bottom?: number;
    };
  };
  subtitles: SubtitleSegment[];
  overlays: OverlayRegion[];
  renders: Render[];
}

export interface Render {
  id: string;
  revision_id: string;
  output_asset: Asset | null;
  state: string;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface PublicationEvent {
  id: string;
  event_type: string;
  message: string;
  created_at: string;
}

export interface Publication {
  id: string;
  project_id: string;
  project_title: string;
  revision_id: string | null;
  render_asset: Asset | null;
  media_assets: Asset[];
  platform: string;
  page_id: string | null;
  page_name: string | null;
  media_type: 'video' | 'image';
  status: 'draft' | 'scheduled' | 'publishing' | 'processing' | 'needs_attention' | 'cancelled' | 'published' | 'failed';
  comment_status: 'not_set' | 'waiting_for_publish' | 'queued' | 'needs_attention' | 'published' | 'failed';
  caption: string;
  comment_text: string;
  affiliate_url: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  external_post_id: string | null;
  remote_stage: string | null;
  remote_video_id: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  events: PublicationEvent[];
}

export interface FacebookPage {
  id: string;
  name: string;
  tasks: string[];
  is_active: boolean;
  token_configured: boolean;
  connected_at: string;
}

export interface FacebookSettings {
  provider: string;
  api_version: string;
  pages: FacebookPage[];
}

export interface AISettings {
  provider: string;
  key_configured: boolean;
  model: string;
  free_models: string[];
  key_storage: string;
}

export interface AIUsage {
  period_timezone: string;
  period_resets_at: string;
  ai_jobs_started: number;
  voiceover_jobs_started: number;
  ai_jobs_succeeded: number;
  ai_jobs_failed: number;
  ai_jobs_pending: number;
  image_post_copy_requests: number;
  source: 'local_jobs';
}

export interface ImagePostCopy {
  caption: string;
  comment_text: string;
  model_name: string;
}

export interface GeneratedCopy {
  script_text: string;
  caption_candidates: string[];
  selected_caption: string;
  comment_text: string;
  review_score: number | null;
  review_summary: string;
  model_name: string | null;
  updated_at: string | null;
}
