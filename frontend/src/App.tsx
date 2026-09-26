import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowUpRight,
  AudioLines,
  CalendarClock,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clapperboard,
  Clock3,
  Download,
  ExternalLink,
  FileText,
  FileVideo2,
  Film,
  FolderKanban,
  HardDrive,
  Image as ImageIcon,
  LayoutDashboard,
  Link2,
  LoaderCircle,
  MessageCircle,
  Music2,
  Moon,
  Plus,
  Search,
  Save,
  Send,
  Settings2,
  Sparkles,
  Sun,
  Upload,
  VolumeX,
  Trash2,
  X,
  type LucideIcon,
} from 'lucide-react';
import { api, assetFileUrl, ApiError, musicTrackFileUrl } from './api';
import type { Asset, Capabilities, EditorRevision, GeneratedCopy, Job, MusicTrack, OverlayRegion, Project, Publication, Render, SubtitleSegment } from './types';

type Page = 'overview' | 'create' | 'projects' | 'image-posts' | 'posts' | 'settings';

const navItems: { id: Page; label: string; icon: LucideIcon; soon?: boolean }[] = [
  { id: 'overview', label: 'ศูนย์ควบคุม', icon: LayoutDashboard },
  { id: 'create', label: 'สร้างคอนเทนต์', icon: Sparkles },
  { id: 'projects', label: 'คลังงาน', icon: FolderKanban },
  { id: 'posts', label: 'คิวโพสต์', icon: Clapperboard },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} ไบต์`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes / 1024;
  let unit = units[0];
  for (let index = 1; size >= 1024 && index < units.length; index += 1) {
    size /= 1024;
    unit = units[index];
  }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${unit}`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return 'ยังไม่ทราบความยาว';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')} นาที`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('th-TH', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value));
}

function assetLabel(asset: Asset): { text: string; tone: string } {
  if (asset.state === 'ready') return { text: 'พร้อมใช้งาน', tone: 'success' };
  if (asset.state === 'failed') return { text: 'อ่านไฟล์ไม่สำเร็จ', tone: 'danger' };
  if (asset.kind === 'rendered_video') return { text: 'กำลังเรนเดอร์', tone: 'working' };
  return { text: 'กำลังอ่านไฟล์', tone: 'working' };
}

function projectCover(project: Project): Asset | undefined {
  return project.assets.find((asset) => asset.kind === 'source_video')
    ?? project.assets.find((asset) => asset.kind === 'post_image')
    ?? project.assets.find((asset) => asset.kind === 'product_image');
}

function App() {
  const [page, setPage] = useState<Page>('overview');
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    if (typeof window === 'undefined') return 'light';
    return window.localStorage.getItem('kodkon-theme') === 'dark' ? 'dark' : 'light';
  });
  const [projects, setProjects] = useState<Project[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem('kodkon-theme', theme);
  }, [theme]);

  const loadProjects = useCallback(async (query = search) => {
    try {
      const data = await api.projects(query.trim());
      setProjects(data);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'โหลดโปรเจกต์ไม่สำเร็จ');
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void loadProjects('');
    void api.capabilities().then(setCapabilities).catch(() => setCapabilities(null));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadProjects(search), 220);
    return () => window.clearTimeout(timer);
  }, [search, loadProjects]);

  useEffect(() => {
    const hasProcessing = projects.some((project) => project.assets.some((asset) => asset.state === 'processing'));
    if (!hasProcessing) return;
    const timer = window.setInterval(() => void loadProjects(search), 1600);
    return () => window.clearInterval(timer);
  }, [projects, search, loadProjects]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedId) ?? null,
    [projects, selectedId],
  );
  const videoCount = projects.reduce((total, project) => total + project.assets.filter((asset) => asset.kind === 'source_video').length, 0);
  const pendingCount = projects.reduce((total, project) => total + project.assets.filter((asset) => asset.state === 'processing').length, 0);

  const createProject = async () => {
    setError('');
    try {
      const created = await api.createProject({
        title: `วิดีโอใหม่ ${new Intl.DateTimeFormat('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date())}`,
        product_name: '', product_details: '', review_evidence: '', discount_text: '', copy_style: 'problem_solution', affiliate_url: '', source_url: '',
      });
      setProjects((items) => [created, ...items]);
      setSelectedId(created.id);
      setPage('projects');
      setSearch('');
      void loadProjects('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'สร้างโปรเจกต์ไม่สำเร็จ');
    }
  };

  const deleteProject = async (project: Project) => {
    const confirmed = window.confirm(
      `ลบโปรเจกต์ “${project.title}” และไฟล์สื่อทั้งหมดที่เก็บไว้ในเครื่องหรือไม่?\n\nรายการโพสต์และการตั้งเวลาที่ผูกกับโปรเจกต์นี้จะถูกลบจาก Studio ด้วย ส่วนโพสต์ที่เผยแพร่บน Facebook แล้วจะยังอยู่บนเพจ`,
    );
    if (!confirmed) return;
    setDeletingProjectId(project.id);
    setError('');
    try {
      await api.deleteProject(project.id);
      setProjects((items) => items.filter((item) => item.id !== project.id));
      if (selectedId === project.id) setSelectedId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'ลบโปรเจกต์ไม่สำเร็จ');
    } finally {
      setDeletingProjectId(null);
    }
  };

  const openNav = (next: Page) => {
    setSelectedId(null);
    setPage(next);
    setError('');
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <img src="/mascot-avatar.png" alt="มาสคอตเพจ กดก่อนคิดทีหลัง" className="brand-avatar" />
          <div className="brand-copy">
            <span className="brand-name">กดก่อนคิดทีหลัง</span>
            <span className="brand-product">STUDIO</span>
          </div>
        </div>

        <div className="sidebar-label">พื้นที่ทำงาน</div>
        <nav className="side-nav" aria-label="เมนูหลัก">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = (page === item.id || (item.id === 'create' && page === 'image-posts')) && !selectedProject;
            return (
              <button key={item.id} className={`nav-item ${isActive ? 'active' : ''}`} aria-label={item.label} onClick={() => openNav(item.id)}>
                <Icon size={18} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="sidebar-label sidebar-label-lower">เครื่องมือ</div>
        <nav className="side-nav" aria-label="เครื่องมือ">
          <button className={`nav-item ${page === 'settings' ? 'active' : ''}`} aria-label="ตั้งค่าโปรแกรม" onClick={() => openNav('settings')}>
            <Settings2 size={18} strokeWidth={1.8} />
            <span>ตั้งค่าโปรแกรม</span>
          </button>
        </nav>

        <div className="sidebar-bottom">
          <div className="local-card">
            <div className="local-card-icon"><HardDrive size={16} /></div>
            <div>
              <strong>ทำงานบนเครื่องนี้</strong>
              <span>{capabilities ? `เวอร์ชัน ${capabilities.version}` : 'ข้อมูลจัดเก็บในเครื่อง'}</span>
            </div>
            <span className="online-dot" title="โปรแกรมทำงานบนเครื่องนี้" />
          </div>
          <div className="help-row"><CircleHelp size={16} /><span>ต้องการความช่วยเหลือ?</span></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>กดก่อนคิดทีหลัง Studio</span>
            <ChevronRight size={15} />
            <strong>{selectedProject ? selectedProject.title : page === 'image-posts' ? 'สร้างโพสต์ภาพ' : navItems.find((item) => item.id === page)?.label ?? 'ตั้งค่าโปรแกรม'}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-badge"><span className="online-dot" /> จัดเก็บในเครื่อง</span>
            <button
              className="theme-toggle"
              type="button"
              onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}
              aria-label={theme === 'light' ? 'เปิดโหมดมืด' : 'เปิดโหมดสว่าง'}
              title={theme === 'light' ? 'เปิดโหมดมืด' : 'เปิดโหมดสว่าง'}
            >
              {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <div className="top-avatar-wrap"><img src="/mascot-avatar.png" alt="" className="top-avatar" /></div>
          </div>
        </header>

        {error && <div className="global-error" role="alert"><CircleHelp size={17} />{error}<button onClick={() => setError('')} aria-label="ปิดข้อความ"><X size={16} /></button></div>}

        {selectedProject ? selectedProject.assets.some((asset) => asset.kind === 'post_image') && !selectedProject.assets.some((asset) => asset.kind === 'source_video') ? (
          <ImageProjectDetail
            project={selectedProject}
            openPosts={() => { setSelectedId(null); setPage('posts'); }}
            goBack={() => { setSelectedId(null); setPage('projects'); }}
          />
        ) : (
          <ProjectDetail
            project={selectedProject}
            refresh={() => loadProjects()}
            openPosts={() => { setSelectedId(null); setPage('posts'); }}
            goBack={() => { setSelectedId(null); setPage('projects'); }}
          />
        ) : page === 'projects' ? (
          <ProjectsPage
            projects={projects}
            loading={loading}
            search={search}
            setSearch={setSearch}
            openProject={(project) => setSelectedId(project.id)}
            createProject={() => openNav('create')}
            videoCount={videoCount}
            pendingCount={pendingCount}
            onDeleteProject={deleteProject}
            deletingProjectId={deletingProjectId}
          />
        ) : page === 'overview' ? (
          <OverviewPage
            projectCount={projects.length}
            videoCount={videoCount}
            pendingCount={pendingCount}
            projects={projects.slice(0, 4)}
            openProject={(project) => { setPage('projects'); setSelectedId(project.id); }}
            goProjects={() => openNav('projects')}
            createContent={() => openNav('create')}
            openQueue={() => openNav('posts')}
          />
        ) : page === 'create' ? (
          <ContentStudioPage
            startVideo={() => void createProject()}
            startPhoto={() => openNav('image-posts')}
            openProjects={() => openNav('projects')}
            openQueue={() => openNav('posts')}
            projectCount={projects.length}
            pendingCount={pendingCount}
          />
        ) : page === 'image-posts' ? (
          <ImagePostPage onSaved={() => { setSelectedId(null); setPage('posts'); void loadProjects(''); }} />
        ) : page === 'posts' ? (
          <PostsPage onCreateImagePost={() => openNav('create')} />
        ) : (
          <SettingsPage capabilities={capabilities} />
        )}
      </main>
    </div>
  );
}

function PageTitle({ eyebrow, title, subtitle, action }: { eyebrow: string; title: string; subtitle: string; action?: ReactNode }) {
  return (
    <div className="page-title-row">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {action}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, footnote, tone }: { icon: LucideIcon; label: string; value: string | number; footnote: string; tone: string }) {
  return (
    <div className="stat-card">
      <div className={`stat-icon ${tone}`}><Icon size={19} strokeWidth={1.9} /></div>
      <div className="stat-body"><span>{label}</span><strong>{value}</strong><small>{footnote}</small></div>
      <div className={`stat-spark ${tone}`}><span /><span /><span /><span /><span /></div>
    </div>
  );
}

function ProjectsPage({
  projects, loading, search, setSearch, openProject, createProject, videoCount, pendingCount, onDeleteProject, deletingProjectId,
}: {
  projects: Project[]; loading: boolean; search: string; setSearch: (value: string) => void;
  openProject: (project: Project) => void; createProject: () => void; videoCount: number; pendingCount: number;
  onDeleteProject: (project: Project) => void; deletingProjectId: string | null;
}) {
  return (
    <section className="page-content">
      <PageTitle
        eyebrow="ไลบรารีสื่อและสินค้า"
        title="คลังงาน"
        subtitle="เปิดงานที่บันทึกไว้ หรือเริ่มเวิร์กโฟลว์วิดีโอและภาพจากจุดเดียว"
        action={<button className="button button-primary" onClick={createProject}><Plus size={17} />สร้างคอนเทนต์</button>}
      />

      <div className="stat-grid">
        <StatCard icon={FolderKanban} label="โปรเจกต์ทั้งหมด" value={projects.length} footnote="งานที่บันทึกไว้" tone="violet" />
        <StatCard icon={Film} label="วิดีโอในคลัง" value={videoCount} footnote="ไฟล์ต้นฉบับที่นำเข้า" tone="blue" />
        <StatCard icon={Clock3} label="กำลังตรวจไฟล์" value={pendingCount} footnote="งานจะทำต่อในพื้นหลัง" tone="amber" />
      </div>

      <div className="section-heading-row">
        <div><h2>งานทั้งหมด <span className="count-pill">{projects.length}</span></h2><p>เลือกโปรเจกต์เพื่อจัดการวิดีโอและข้อมูลสินค้า</p></div>
        <label className="search-field">
          <Search size={17} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาชื่อโปรเจกต์หรือสินค้า" aria-label="ค้นหาโปรเจกต์" />
          {search && <button className="icon-button clear-search" onClick={() => setSearch('')} aria-label="ล้างคำค้น"><X size={15} /></button>}
        </label>
      </div>

      {loading ? (
        <div className="loading-panel"><LoaderCircle className="spin" size={22} /><span>กำลังโหลดโปรเจกต์...</span></div>
      ) : projects.length === 0 ? (
        <EmptyProjects hasSearch={Boolean(search)} clearSearch={() => setSearch('')} createProject={createProject} />
      ) : (
        <div className="project-grid">
          {projects.map((project, index) => <ProjectCard key={project.id} project={project} index={index} open={() => openProject(project)} onDelete={() => onDeleteProject(project)} deleting={deletingProjectId === project.id} />)}
          <button className="new-project-card" onClick={createProject}>
            <span className="new-project-icon"><Plus size={22} /></span>
            <strong>สร้างคอนเทนต์</strong>
            <span>เลือกวิดีโอหรือภาพสินค้า</span>
          </button>
        </div>
      )}
      <div className="page-footnote"><span className="online-dot" /> โปรเจกต์และไฟล์ต้นฉบับจัดเก็บไว้ในเครื่องนี้</div>
    </section>
  );
}

function EmptyProjects({ hasSearch, clearSearch, createProject }: { hasSearch: boolean; clearSearch: () => void; createProject: () => void }) {
  return (
    <div className="empty-state">
      <div className="empty-art">
        <div className="empty-art-card card-back"><span /><span /><span /></div>
        <div className="empty-art-card card-front"><FileVideo2 size={35} strokeWidth={1.4} /><span className="play-dot">▶</span></div>
        <div className="empty-spark spark-a">✦</div><div className="empty-spark spark-b">✦</div>
      </div>
      <h3>{hasSearch ? 'ไม่เจองานที่ค้นหา' : 'เริ่มสร้างคอนเทนต์ชิ้นแรก'}</h3>
      <p>{hasSearch ? 'ลองเปลี่ยนคำค้น หรือกลับไปดูงานทั้งหมด' : 'เลือกภาพหรือวิดีโอ ระบบจะเก็บต้นฉบับและงานที่เตรียมไว้ในคลังนี้'}</p>
      {hasSearch ? <button className="button button-secondary" onClick={clearSearch}>ล้างคำค้น</button> : <button className="button button-primary" onClick={createProject}><Plus size={17} />เลือกประเภทคอนเทนต์</button>}
    </div>
  );
}

function ProjectCard({ project, index, open, onDelete, deleting = false }: { project: Project; index: number; open: () => void; onDelete?: () => void; deleting?: boolean }) {
  const asset = projectCover(project);
  const status = asset ? assetLabel(asset) : { text: 'ยังไม่มีวิดีโอ', tone: 'muted' };
  const cardTones = ['lavender', 'peach', 'mint', 'sky'];
  return (
    <article className="project-card" onClick={open} onKeyDown={(event) => { if (event.key === 'Enter') open(); }} tabIndex={0} role="button" aria-label={`เปิดโปรเจกต์ ${project.title}`}>
      <div className={`project-card-art ${cardTones[index % cardTones.length]}`}>
        {asset?.state === 'ready' ? (
          asset.kind === 'source_video'
            ? <video className="project-card-video" src={assetFileUrl(asset.id)} muted preload="metadata" />
            : <img className="project-card-image" src={assetFileUrl(asset.id)} alt="ภาพสินค้า" />
        ) : <div className="project-card-placeholder"><FileVideo2 size={30} strokeWidth={1.4} /><span>{asset?.state === 'processing' ? 'กำลังอ่านไฟล์' : 'วิดีโอสินค้า'}</span></div>}
        <span className={`status-chip ${status.tone}`}><span className="status-dot" />{status.text}</span>
        <button className="card-open" onClick={(event) => { event.stopPropagation(); open(); }} aria-label="เปิดโปรเจกต์"><ArrowUpRight size={16} /></button>
        {onDelete && <button className="card-delete" onClick={(event) => { event.stopPropagation(); onDelete(); }} disabled={deleting} aria-label={`ลบโปรเจกต์ ${project.title}`} title="ลบโปรเจกต์">{deleting ? <LoaderCircle className="spin" size={15} /> : <Trash2 size={15} />}</button>}
      </div>
      <div className="project-card-body">
        <div className="project-card-copy">
          <h3>{project.title}</h3>
          <p>{project.product_name || (project.product_details || project.product_source_details || project.review_evidence || project.product_review_summary ? 'มีข้อมูลสินค้าแล้ว' : 'ยังไม่ได้ใส่ข้อมูลสินค้า')}</p>
        </div>
        <div className="project-card-meta">
          <span>{asset?.kind === 'source_video' ? <FileVideo2 size={14} /> : <ImageIcon size={14} />}{asset?.kind === 'source_video' ? formatDuration(asset.duration_ms) : `${project.assets.filter((item) => item.kind === 'product_image').length} ภาพต้นฉบับ`}</span>
          <span>{formatDate(project.updated_at)}</span>
        </div>
      </div>
    </article>
  );
}

function ImageProjectDetail({ project, openPosts, goBack }: { project: Project; openPosts: () => void; goBack: () => void }) {
  const output = project.assets.find((asset) => asset.kind === 'post_image');
  const originals = project.assets.filter((asset) => asset.kind === 'product_image');
  return (
    <section className="page-content image-project-detail">
      <div className="project-back-row"><button className="text-button" onClick={goBack}><ArrowLeft size={15} />กลับไปโปรเจกต์ทั้งหมด</button></div>
      <PageTitle eyebrow="คลังภาพสินค้า" title={project.title} subtitle="ภาพจัดองค์ประกอบและภาพต้นฉบับที่ใช้ทำโพสต์" action={<button className="button button-primary" onClick={openPosts}><Clapperboard size={15} />ดูรายการโพสต์</button>} />
      {output && <div className="image-project-output content-panel"><div><span className="eyebrow">ภาพโพสต์</span><h2>ภาพจัดองค์ประกอบ</h2><p>{formatBytes(output.byte_size)} · บันทึกในเครื่องนี้</p></div><img src={assetFileUrl(output.id)} alt="ภาพโพสต์ที่จัดองค์ประกอบแล้ว" /></div>}
      <div className="image-originals-panel content-panel"><div className="section-heading-row"><div><h2>ภาพต้นฉบับ <span className="count-pill">{originals.length}</span></h2><p>รูปสินค้าที่นำมาใช้สร้างภาพโพสต์</p></div></div><div className="image-original-grid">{originals.map((asset) => <img key={asset.id} src={assetFileUrl(asset.id)} alt={asset.original_name} title={asset.original_name} />)}</div></div>
    </section>
  );
}

function productInfoForEditing(project: Project): string {
  const sections: string[] = [];
  const add = (value: string | null | undefined, label?: string) => {
    const text = value?.trim();
    if (!text || sections.some((section) => section === text || section.endsWith(`\n${text}`))) return;
    sections.push(label ? `${label}:\n${text}` : text);
  };
  add(project.product_name, 'ชื่อสินค้า');
  add(project.product_details);
  add(project.product_source_details, 'รายละเอียดสินค้าที่บันทึกไว้');
  add(project.review_evidence, 'รีวิว/ความคิดเห็น');
  add(project.product_review_summary, 'สรุปรีวิวที่บันทึกไว้');
  if (project.product_average_rating && project.product_average_rating > 0) {
    add(`${project.product_average_rating.toFixed(1)}/5${project.product_review_count ? ` จาก ${project.product_review_count.toLocaleString()} รีวิว` : ''}`, 'คะแนนที่บันทึกไว้');
  }
  add(project.discount_text, 'โปรโมชัน/ส่วนลดที่ยืนยันแล้ว');
  return sections.join('\n\n');
}

function ProjectDetail({ project, refresh, goBack, openPosts }: { project: Project; refresh: () => void; goBack: () => void; openPosts: () => void }) {
  const [productInfo, setProductInfo] = useState(() => productInfoForEditing(project));
  const [affiliateUrl, setAffiliateUrl] = useState(project.affiliate_url ?? '');
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [productOpen, setProductOpen] = useState(false);
  const [message, setMessage] = useState('');
  const [formError, setFormError] = useState('');

  useEffect(() => {
    setProductInfo(productInfoForEditing(project));
    setAffiliateUrl(project.affiliate_url ?? '');
  }, [project.id, project.product_name, project.product_details, project.product_source_details, project.review_evidence, project.product_average_rating, project.product_review_count, project.product_review_summary, project.discount_text, project.source_url, project.affiliate_url]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true); setFormError(''); setMessage('');
    try {
      await api.updateProject(project.id, { title: project.title, product_name: '', product_details: productInfo, review_evidence: '', discount_text: '', copy_style: project.copy_style ?? 'problem_solution', affiliate_url: affiliateUrl, source_url: '' });
      setMessage('บันทึกข้อมูลสินค้าแล้ว'); refresh();
    } catch (reason) { setFormError(reason instanceof Error ? reason.message : 'บันทึกไม่สำเร็จ'); }
    finally { setSaving(false); }
  };

  const upload = async (event: FormEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]; event.currentTarget.value = '';
    if (!file) return;
    if (file.size > 2 * 1024 * 1024 * 1024) { setFormError('ไฟล์ใหญ่เกินขนาดที่โปรแกรมรองรับ 2 GB'); return; }
    setUploading(true); setFormError(''); setMessage('');
    try { await api.uploadVideo(project.id, file); setMessage(`รับไฟล์ “${file.name}” แล้ว กำลังตรวจวิดีโอ`); refresh(); }
    catch (reason) { setFormError(reason instanceof ApiError ? reason.message : 'อัปโหลดไฟล์ไม่สำเร็จ'); }
    finally { setUploading(false); }
  };

  const sourceReady = project.assets.some((asset) => asset.kind === 'source_video' && asset.state === 'ready');
  const sourceProcessing = project.assets.some((asset) => asset.kind === 'source_video' && asset.state === 'processing');

  return (
    <section className={`page-content detail-page ${sourceReady ? 'detail-editing' : 'detail-uploading'}`}>
      <div className="detail-toolbar">
        <button className="back-button" onClick={goBack}><ArrowLeft size={16} /><span>โปรเจกต์ทั้งหมด</span></button>
        <div className="detail-project-heading"><span className="eyebrow">โปรเจกต์วิดีโอ</span><strong>{project.title}</strong></div>
        <button className="button button-secondary product-info-trigger" onClick={() => setProductOpen(true)}><Link2 size={15} />ข้อมูลสินค้า <span>ไม่บังคับ</span></button>
      </div>

      {sourceReady ? (
        <div className="detail-workspace"><VideoEditor key={project.id} project={project} refresh={refresh} openPosts={openPosts} openProductInfo={() => setProductOpen(true)} /></div>
      ) : (
        <div className="upload-first-panel">
          <div className="upload-first-copy"><span className="dropzone-icon"><FileVideo2 size={25} /></span><span className="panel-kicker">เริ่มต้นง่าย ๆ</span><h1>{sourceProcessing ? 'กำลังเตรียมวิดีโอของคุณ' : 'เพิ่มวิดีโอเพื่อเริ่มโปรเจกต์'}</h1><p>{sourceProcessing ? 'อ่านรายละเอียดไฟล์อยู่สักครู่ คุณไม่ต้องตั้งค่าอะไรเพิ่ม' : 'เลือกวิดีโอจากเครื่อง แล้วค่อยเลือกซับและเพลงที่ต้องการในขั้นถัดไป'}</p></div>
          <label className={`upload-dropzone upload-first-dropzone ${uploading ? 'uploading' : ''}`}>
            <input type="file" accept="video/mp4,video/quicktime,video/x-m4v,video/x-matroska,video/webm,.mp4,.mov,.m4v,.mkv,.webm" disabled={uploading} onChange={upload} />
            <span className="dropzone-icon">{uploading ? <LoaderCircle className="spin" size={26} /> : <Upload size={25} />}</span>
            <strong>{uploading ? 'กำลังรับไฟล์วิดีโอ…' : 'วางไฟล์วิดีโอที่นี่ หรือคลิกเพื่อเลือก'}</strong>
            <span>รองรับ MP4, MOV, M4V, MKV และ WEBM · สูงสุด 2 GB</span>
          </label>
          {project.assets.length > 0 && <div className="upload-asset-list">{project.assets.filter((asset) => asset.kind === 'source_video').map((asset) => <AssetRow key={asset.id} asset={asset} />)}</div>}
          {formError && <div className="form-error">{formError}</div>}{message && <div className="form-success"><CheckCircle2 size={15} />{message}</div>}
          <div className="upload-local-note"><HardDrive size={15} /><span>วิดีโอและข้อมูลของคุณจัดเก็บไว้ในเครื่องนี้</span></div>
        </div>
      )}

      {productOpen && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setProductOpen(false); }}>
        <form className="modal-card product-info-modal" onSubmit={save}>
          <div className="modal-header"><button type="button" className="icon-button modal-close" onClick={() => setProductOpen(false)} aria-label="ปิด"><X size={19} /></button><span className="eyebrow">ข้อมูลสินค้า</span><h2>ข้อมูลสินค้าและลิงก์</h2><p>ใส่รายละเอียด รีวิว และโปรโมชันที่ยืนยันไว้ในช่องเดียว</p></div>
          <div className="modal-form">
            <label className="form-label">ข้อมูลสินค้าและรีวิว<textarea rows={7} maxLength={24000} value={productInfo} onChange={(event) => setProductInfo(event.target.value)} placeholder="วางชื่อสินค้า จุดเด่น วิธีใช้ รีวิว คะแนน ราคา หรือโปรโมชันที่ยืนยันแล้วได้ที่นี่" /></label>
            <label className="form-label">ลิงก์ Affiliate <span className="optional-label">แนบทั้งในโพสต์และคอมเมนต์</span><input type="url" value={affiliateUrl} onChange={(event) => setAffiliateUrl(event.target.value)} placeholder="https://s.shopee.co.th/..." /></label>
            <p className="product-input-hint">AI จะอ้างอิงข้อมูลในช่องนี้ และไม่แต่งรายละเอียดหรือรีวิวเพิ่มเอง</p>
            {formError && <div className="form-error">{formError}</div>}{message && <div className="form-success"><CheckCircle2 size={15} />{message}</div>}
            <div className="modal-actions"><button type="button" className="button button-secondary" onClick={() => setProductOpen(false)}>ปิด</button><button className="button button-primary" disabled={saving}>{saving ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}{saving ? 'กำลังบันทึก…' : 'บันทึกข้อมูล'}</button></div>
          </div>
        </form>
      </div>}
    </section>
  );
}

function AssetRow({ asset }: { asset: Asset }) {
  const status = assetLabel(asset);
  const audioAsset = asset.kind === 'music_track';
  return (
    <div className="asset-row">
      <div className="asset-preview">
        {audioAsset ? <AudioLines size={25} strokeWidth={1.5} /> : asset.state === 'ready' ? <video src={assetFileUrl(asset.id)} preload="metadata" muted /> : <FileVideo2 size={25} strokeWidth={1.5} />}
      </div>
      <div className="asset-info">
        <strong title={asset.original_name}>{asset.original_name}</strong>
        <span>{asset.state === 'ready' ? `${audioAsset ? 'เพลงประกอบ' : `${asset.width ?? '?'} × ${asset.height ?? '?'} px`} · ${formatDuration(asset.duration_ms)} · ${formatBytes(asset.byte_size)}` : asset.error_message ?? formatBytes(asset.byte_size)}</span>
      </div>
      <span className={`status-chip ${status.tone}`}><span className="status-dot" />{status.text}</span>
      {asset.state === 'ready' && <a className="asset-open" href={assetFileUrl(asset.id)} target="_blank" rel="noreferrer" aria-label={audioAsset ? 'เปิดไฟล์เสียง' : 'เปิดไฟล์วิดีโอ'}>{audioAsset ? <Music2 size={16} /> : <ArrowUpRight size={16} />}</a>}
    </div>
  );
}

function VideoEditor({ project, refresh, openPosts, openProductInfo }: { project: Project; refresh: () => void; openPosts: () => void; openProductInfo: () => void }) {
  const source = project.assets.find((asset) => asset.kind === 'source_video' && asset.state === 'ready');
  const musicAssets = project.assets.filter((asset) => asset.kind === 'music_track');
  const [editor, setEditor] = useState<EditorRevision | null>(null);
  const [subtitles, setSubtitles] = useState<SubtitleSegment[]>([]);
  const [overlays, setOverlays] = useState<OverlayRegion[]>([]);
  const [busy, setBusy] = useState(false);
  const [uploadingMusic, setUploadingMusic] = useState(false);
  const [musicLibrary, setMusicLibrary] = useState<MusicTrack[]>([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [playheadMs, setPlayheadMs] = useState(0);
  const [aiSettings, setAISettings] = useState<{ key_configured: boolean } | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [copy, setCopy] = useState<GeneratedCopy | null>(null);
  const [savingCopy, setSavingCopy] = useState(false);
  const [voiceName, setVoiceName] = useState('Kore');
  const [activePanel, setActivePanel] = useState<'audio' | 'subtitles' | 'overlays' | 'copy'>('audio');

  useEffect(() => {
    if (!source) return;
    let alive = true;
    void api.editor(project.id).then(async (data) => {
      if (!alive) return;
      setEditor(data);
      setSubtitles(data.subtitles);
      setOverlays(data.overlays);
      const [ai, generated, tracks] = await Promise.all([api.aiSettings(), api.generatedCopy(data.id), api.musicLibrary()]);
      if (alive) { setAISettings(ai); setCopy(generated); setMusicLibrary(tracks); }
    }).catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : 'โหลดเครื่องมือตัดต่อไม่สำเร็จ'); });
    return () => { alive = false; };
  }, [project.id, source?.id]);

  useEffect(() => {
    if (!activeJob || ['succeeded', 'failed', 'cancelled'].includes(activeJob.state)) return;
    const timer = window.setTimeout(() => {
      void api.job(activeJob.id).then(async (job) => {
        setActiveJob(job);
        if (job.state === 'succeeded') {
          const [data, generated] = await Promise.all([api.editor(project.id), editor ? api.generatedCopy(editor.id) : Promise.resolve(null)]);
          setEditor(data); setSubtitles(data.subtitles); setOverlays(data.overlays);
          if (generated) setCopy(generated);
          refresh();
          if (job.job_type === 'ocr_subtitles' && data.subtitles.some((item) => item.source_text.trim())) {
            setNotice(`พบซับ ${data.subtitles.length} ช่วง · กำลังแปลไทยต่อให้อัตโนมัติ`);
            setActiveJob(await api.queueTranslation(data.id));
          } else {
            setNotice(job.job_type === 'ocr_subtitles' ? 'ไม่พบซับในคลิป · ข้ามขั้นตอนนี้แล้วไปเรนเดอร์ได้เลย' : job.job_type === 'translate_subtitles' ? 'แปลซับไทยแล้ว ตรวจดูตัวอย่างก่อนเรนเดอร์' : job.job_type === 'generate_script' ? 'ได้บทพากย์แล้ว ตรวจทานและกดสร้างเสียงพากย์ไทย' : job.job_type === 'generate_caption' ? 'ได้แคปชั่นแล้ว เลือกข้อความก่อนเตรียมโพสต์' : job.job_type === 'generate_voiceover' ? 'เสียงพากย์ไทยพร้อมฟังแล้ว และจะถูกมิกซ์ในวิดีโอเมื่อเรนเดอร์' : 'งาน AI เสร็จแล้ว');
            setActiveJob(null);
          }
        } else if (job.state === 'failed') { setError(job.error_message ?? 'งาน AI ไม่สำเร็จ'); setActiveJob(null); }
      }).catch((reason) => { setError(reason instanceof Error ? reason.message : 'ตรวจสอบสถานะงาน AI ไม่สำเร็จ'); setActiveJob(null); });
    }, 1300);
    return () => window.clearTimeout(timer);
  }, [activeJob, editor, project.id]);

  useEffect(() => {
    if (!editor || !editor.renders.some((item) => item.state === 'queued' || item.state === 'running')) return;
    const timer = window.setTimeout(() => {
      void api.editor(project.id).then((data) => {
        const wasRendering = editor.renders.some((item) => item.state === 'queued' || item.state === 'running');
        const previousLatest = editor.renders[0];
        const latest = data.renders[0];
        if (wasRendering && previousLatest && latest?.id === previousLatest.id && latest.state === 'succeeded') {
          setNotice(`เรนเดอร์เสร็จแล้ว${latest.output_asset?.original_name ? ` · ${latest.output_asset.original_name}` : ''} ดาวน์โหลดไฟล์หรือเตรียมโพสต์ต่อได้เลย`);
        } else if (wasRendering && previousLatest && latest?.id === previousLatest.id && latest.state === 'failed') {
          setError(latest.error_message ?? 'เรนเดอร์ไม่สำเร็จ ลองอีกครั้งได้');
        }
        setEditor(data); refresh();
      }).catch((reason) => setError(reason instanceof Error ? reason.message : 'ตรวจสอบสถานะเรนเดอร์ไม่สำเร็จ'));
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [editor, project.id, refresh]);

  if (!source) return null;
  const duration = source.duration_ms ?? 0;
  const settings = editor?.settings ?? {};
  const style = settings.subtitle_style ?? {};
  const saveCall = async (action: () => Promise<EditorRevision>, done: string) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await action();
      setEditor(data); setNotice(done);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'บันทึกไม่สำเร็จ');
    } finally { setBusy(false); }
  };
  const setSubtitle = (stableId: string, field: keyof SubtitleSegment, value: string | number | boolean) => {
    setSubtitles((items) => items.map((item) => item.stable_id === stableId ? { ...item, [field]: value } : item));
  };
  const setOverlay = (id: string, field: keyof OverlayRegion, value: string | number) => {
    setOverlays((items) => items.map((item) => item.id === id ? { ...item, [field]: value } : item));
  };
  const addSubtitle = () => {
    const start = Math.min(playheadMs, Math.max(0, duration - 2000));
    setSubtitles((items) => [...items, { stable_id: crypto.randomUUID(), position: items.length, start_ms: start, end_ms: Math.min(duration || start + 2500, start + 2500), source_text: '', translated_text: '', ocr_confidence: null, review_flag: false }]);
  };
  const addOverlay = () => setOverlays((items) => [...items, { id: crypto.randomUUID(), label: 'กรอบปิดซับเดิม', x: 0.05, y: 0.76, width: 0.9, height: 0.17, start_ms: 0, end_ms: duration || 10000, color: '#111111', opacity: 0.92 }]);
  const importSrtFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]; event.currentTarget.value = '';
    if (!file || !editor) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const data = await api.importSrt(editor.id, await file.text());
      setEditor(data); setSubtitles(data.subtitles); setOverlays(data.overlays); setNotice(`นำเข้า ${data.subtitles.length} ช่วงจากไฟล์ SRT แล้ว`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'นำเข้า SRT ไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const uploadMusicFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0]; event.currentTarget.value = '';
    if (!file) return;
    setUploadingMusic(true); setError(''); setNotice('');
    try {
      const track = await api.uploadMusicTrack(file);
      setMusicLibrary((items) => [track, ...items]);
      setEditor((current) => current ? { ...current, settings: { ...current.settings, audio_mode: 'music', music_asset_id: null, music_library_id: track.id } } : current);
      setNotice(`เพิ่ม “${file.name}” ไว้ในคลังเพลงแล้ว และเลือกใช้กับวิดีโอนี้`);
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'เพิ่มเพลงไม่สำเร็จ'); }
    finally { setUploadingMusic(false); }
  };
  const saveSettings = () => {
    if (!editor) return;
    const mode = settings.audio_mode === 'music' ? 'music' : 'mute';
    void saveCall(() => api.saveSettings(editor.id, {
      audio_mode: mode,
      source_audio_enabled: settings.source_audio_enabled ?? false,
      music_asset_id: settings.music_asset_id ?? null,
      music_library_id: settings.music_library_id ?? null,
      music_volume: settings.music_volume ?? 0.22,
      music_fade_ms: settings.music_fade_ms ?? 700,
      voiceover_asset_id: settings.voiceover_asset_id ?? null,
      voiceover_volume: settings.voiceover_volume ?? 1,
      subtitle_style: {
        font_size: style.font_size ?? 52, font_color: style.font_color ?? '#FFFFFF', box_color: style.box_color ?? '#111111',
        box_opacity: style.box_opacity ?? 0.92, margin_bottom: style.margin_bottom ?? 80,
      },
    }), 'บันทึกการตั้งค่าเสียงและซับแล้ว');
  };
  const startAIJob = async (start: () => Promise<Job>, queuedMessage: string) => {
    setError(''); setNotice('');
    try { const job = await start(); setActiveJob(job); setNotice(queuedMessage); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'เริ่มงาน AI ไม่สำเร็จ'); }
  };
  const saveCopy = async () => {
    if (!editor || !copy) return;
    setSavingCopy(true); setError(''); setNotice('');
    try {
      const saved = await api.saveGeneratedCopy(editor.id, { script_text: copy.script_text, caption_candidates: copy.caption_candidates, selected_caption: copy.selected_caption, comment_text: copy.comment_text, review_score: copy.review_score, review_summary: copy.review_summary });
      setCopy(saved); setNotice('บันทึกสคริปต์ แคปชั่น และข้อความคอมเมนต์แล้ว');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'บันทึกข้อความไม่สำเร็จ'); }
    finally { setSavingCopy(false); }
  };
  const exportSrt = async () => {
    if (!editor) return;
    setError('');
    try {
      const blob = await api.downloadSrt(editor.id); const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${project.title}-th.srt`; anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'ดาวน์โหลด SRT ไม่สำเร็จ'); }
  };
  const render = async () => {
    if (!editor) return;
    if (settings.audio_mode === 'music' && !settings.music_library_id && !settings.music_asset_id) {
      setActivePanel('audio');
      setError('เลือกเพลงจากคลังหรือปิดเพลงพื้นหลังก่อนเรนเดอร์');
      return;
    }
    setBusy(true); setError(''); setNotice('');
    try {
      await api.saveSubtitles(editor.id, subtitles);
      await api.saveOverlays(editor.id, overlays);
      await api.saveSettings(editor.id, {
        audio_mode: settings.audio_mode === 'music' ? 'music' : 'mute',
        source_audio_enabled: settings.source_audio_enabled ?? false,
        music_asset_id: settings.music_asset_id ?? null,
        music_library_id: settings.music_library_id ?? null,
        music_volume: settings.music_volume ?? 0.22,
        music_fade_ms: settings.music_fade_ms ?? 700,
        voiceover_asset_id: settings.voiceover_asset_id ?? null,
        voiceover_volume: settings.voiceover_volume ?? 1,
        subtitle_style: {
          font_size: style.font_size ?? 52, font_color: style.font_color ?? '#FFFFFF', box_color: style.box_color ?? '#111111',
          box_opacity: style.box_opacity ?? 0.92, margin_bottom: style.margin_bottom ?? 80,
        },
      });
      await api.render(editor.id);
      setEditor(await api.editor(project.id));
      setNotice('บันทึกงานตัดต่อและส่ง MP4 เข้าคิวเรนเดอร์แล้ว'); refresh();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'เริ่มเรนเดอร์ไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const readyRenders = editor?.renders.filter((item) => item.state === 'succeeded' && item.output_asset?.state === 'ready' && item.output_asset.kind === 'rendered_video') ?? [];
  const latestRender: Render | undefined = editor?.renders[0];
  const latestReadyRender = latestRender?.state === 'succeeded' && latestRender.output_asset?.state === 'ready' && latestRender.output_asset.kind === 'rendered_video'
    ? latestRender : undefined;
  const renderInProgress = latestRender?.state === 'queued' || latestRender?.state === 'running';
  const preparePost = async () => {
    if (!editor || !copy?.selected_caption.trim() || !readyRenders[0]?.output_asset) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await api.createPublication(editor.id, {
        render_asset_id: readyRenders[0].output_asset.id,
        caption: copy.selected_caption,
        comment_text: copy.comment_text,
      });
      setNotice('เตรียมดราฟต์พร้อม MP4 แคปชั่น และลิงก์สินค้าแล้ว');
      openPosts();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'เตรียมโพสต์ไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const activeOverlay = overlays.filter((item) => playheadMs >= item.start_ms && playheadMs <= item.end_ms);
  const activeSubtitle = subtitles.find((item) => playheadMs >= item.start_ms && playheadMs <= item.end_ms && item.translated_text.trim());

  const musicSelection = settings.music_library_id ? `library:${settings.music_library_id}` : settings.music_asset_id ? `asset:${settings.music_asset_id}` : '';
  const selectedLibraryTrack = musicLibrary.find((track) => track.id === settings.music_library_id);
  const changeMusic = (value: string) => setEditor({ ...editor!, settings: {
    ...settings,
    music_library_id: value.startsWith('library:') ? value.slice('library:'.length) : null,
    music_asset_id: value.startsWith('asset:') ? value.slice('asset:'.length) : null,
  } });

  return (
    <section className="content-panel video-editor-panel">
      <div className="video-editor-heading">
        <div><span className="panel-kicker">ตัดต่อบนเครื่อง</span><h1>ปรับวิดีโอ</h1><p>{editor ? `เวอร์ชัน ${editor.version} · ${source.width ?? '?'} × ${source.height ?? '?'} · ${formatDuration(duration)}` : 'กำลังเตรียมเครื่องมือตัดต่อ...'}</p></div>
        <div className="editor-header-actions">
          <button className="button button-secondary" onClick={() => void preparePost()} disabled={!editor || busy || !readyRenders.length || !copy?.selected_caption.trim()} title={!readyRenders.length ? 'เรนเดอร์วิดีโอให้เสร็จก่อน' : !copy?.selected_caption.trim() ? 'เขียนแคปชั่นก่อน' : undefined}><Send size={15} />เตรียมโพสต์</button>
          <button className="button button-primary" onClick={() => void render()} disabled={!editor || busy || renderInProgress || (settings.audio_mode === 'music' && !settings.music_library_id && !settings.music_asset_id)}>{renderInProgress ? <LoaderCircle className="spin" size={16} /> : <Clapperboard size={16} />}{busy || renderInProgress ? 'กำลังเรนเดอร์…' : 'เรนเดอร์ MP4'}</button>
        </div>
      </div>
      {error && <div className="form-error editor-feedback">{error}</div>}{notice && <div className="form-success editor-feedback"><CheckCircle2 size={15} />{notice}</div>}
      {renderInProgress && <div className="render-result-card render-working" role="status"><LoaderCircle className="spin" size={20} /><div><strong>กำลังเรนเดอร์ MP4</strong><span>รอให้เสร็จสักครู่ แล้วไฟล์จะปรากฏตรงนี้โดยอัตโนมัติ</span></div></div>}
      {latestReadyRender?.output_asset && <div className="render-result-card render-complete" role="status"><CheckCircle2 size={20} /><div className="render-result-copy"><strong>เรนเดอร์เสร็จแล้ว</strong><span>{latestReadyRender.output_asset.original_name} · {formatBytes(latestReadyRender.output_asset.byte_size)} · เก็บไว้ในคลังไฟล์ของโปรเจกต์นี้</span><small>ขั้นต่อไป: ดาวน์โหลด MP4 หรือเตรียมโพสต์เพื่อเพิ่มแคปชั่นและลิงก์สินค้า</small></div><div className="render-result-actions"><a className="button button-secondary" href={assetFileUrl(latestReadyRender.output_asset.id)} download={latestReadyRender.output_asset.original_name || `${project.title}.mp4`}><Download size={15} />ดาวน์โหลด MP4</a><button className="button button-primary" onClick={() => copy?.selected_caption.trim() ? void preparePost() : setActivePanel('copy')} disabled={busy}>{copy?.selected_caption.trim() ? <Send size={15} /> : <ChevronRight size={15} />}{copy?.selected_caption.trim() ? 'เตรียมโพสต์' : 'เพิ่มแคปชั่นก่อน'}</button></div></div>}
      {latestRender?.state === 'failed' && <div className="render-result-card render-failed" role="alert"><CircleHelp size={20} /><div><strong>เรนเดอร์ไม่สำเร็จ</strong><span>{latestRender.error_message ?? 'ตรวจสอบการตั้งค่าแล้วลองเรนเดอร์อีกครั้ง'}</span></div></div>}
      {!editor ? <div className="loading-panel"><LoaderCircle className="spin" size={20} />กำลังโหลดข้อมูลตัดต่อ</div> : <>
        <div className="video-editor-workarea">
          <div className="editor-video-column">
            <div className="video-preview" style={{ aspectRatio: `${source.width || 9} / ${source.height || 16}` }}>
              <video src={assetFileUrl(source.id)} controls muted={!settings.source_audio_enabled} onTimeUpdate={(event) => setPlayheadMs(event.currentTarget.currentTime * 1000)} />
              {activeOverlay.map((item) => <span key={item.id} className="video-mask" style={{ left: `${item.x * 100}%`, top: `${item.y * 100}%`, width: `${item.width * 100}%`, height: `${item.height * 100}%`, backgroundColor: item.color, opacity: item.opacity }} />)}
              {activeSubtitle && <span className="video-subtitle-preview" style={{ bottom: `${Math.max(2, (style.margin_bottom ?? 80) / 10)}%`, color: style.font_color ?? '#FFFFFF', backgroundColor: `${style.box_color ?? '#111111'}${Math.round((style.box_opacity ?? 0.92) * 255).toString(16).padStart(2, '0')}`, fontSize: `clamp(12px, ${(style.font_size ?? 52) / 5}px, 34px)` }}>{activeSubtitle.translated_text}</span>}
            </div>
            <div className="video-preview-caption"><span><VolumeX size={14} />เสียงต้นฉบับ: {settings.source_audio_enabled ? 'เปิด' : 'ปิด'}</span><span>พรีวิวแสดงซับและกรอบตามเวลาที่เล่น</span></div>
          </div>
          <div className="editor-control-column">
            <div className="editor-tabs" role="tablist" aria-label="เครื่องมือตัดต่อ">
              {([
                ['audio', 'เสียง'], ['subtitles', `ซับไทย${subtitles.length ? ` · ${subtitles.length}` : ''}`], ['overlays', `ปิดซับเดิม${overlays.length ? ` · ${overlays.length}` : ''}`], ['copy', 'บทพากย์/โพสต์'],
              ] as const).map(([id, label]) => <button key={id} role="tab" aria-selected={activePanel === id} className={activePanel === id ? 'active' : ''} onClick={() => setActivePanel(id)}>{label}</button>)}
            </div>
            <div className="editor-panel-content">
              {activePanel === 'audio' && <div className="editor-tab-panel">
                <div className="editor-tab-title"><div><h2>เสียงวิดีโอ</h2><p>ตั้งเสียงจากคลิปและเพลงพื้นหลังแยกกัน</p></div><VolumeX size={19} /></div>
                <label className={`audio-source-toggle ${source.has_audio === false ? 'unavailable' : ''}`}>
                  <span className="audio-source-copy"><strong>เสียงต้นฉบับจากวิดีโอ</strong><small>{source.has_audio === false ? 'วิดีโอนี้ไม่มีเสียงต้นฉบับ' : settings.source_audio_enabled ? 'เปิดอยู่ · จะมิกซ์กับเพลงพื้นหลัง' : 'ปิดอยู่ · เปิดได้แม้เลือกเพลงพื้นหลัง'}</small></span>
                  <input className="switch-input" type="checkbox" checked={Boolean(settings.source_audio_enabled)} disabled={source.has_audio === false} onChange={(event) => setEditor({ ...editor, settings: { ...settings, source_audio_enabled: event.target.checked } })} />
                  <span className="switch-ui" aria-hidden="true" />
                </label>
                <div className="editor-subheading editor-subheading-spaced"><Music2 size={16} /><strong>เพลงพื้นหลัง</strong></div>
                <label className="choice-row"><input type="radio" checked={settings.audio_mode !== 'music'} onChange={() => setEditor({ ...editor, settings: { ...settings, audio_mode: 'mute', music_library_id: null, music_asset_id: null } })} /><span><strong>ไม่ใส่เพลงพื้นหลัง</strong><small>เสียงต้นฉบับเลือกเปิดหรือปิดได้ด้านบน</small></span></label>
                <label className="choice-row"><input type="radio" checked={settings.audio_mode === 'music'} onChange={() => setEditor({ ...editor, settings: { ...settings, audio_mode: 'music' } })} /><span><strong>ใส่เพลงพื้นหลัง</strong><small>เพลงจะเล่นร่วมกับเสียงต้นฉบับเมื่อเปิดสวิตช์</small></span></label>
                {settings.audio_mode === 'music' && <>
                  <label className="form-label music-picker-label">เลือกเพลงจากคลัง
                    <select value={musicSelection} onChange={(event) => changeMusic(event.target.value)}>
                      <option value="">เลือกเพลงที่เคยเพิ่มไว้</option>
                      {musicLibrary.map((track) => <option key={track.id} value={`library:${track.id}`}>{track.original_name}</option>)}
                      {musicAssets.filter((asset) => asset.state === 'ready').length > 0 && <optgroup label="เพลงเดิมในโปรเจกต์">{musicAssets.filter((asset) => asset.state === 'ready').map((asset) => <option key={asset.id} value={`asset:${asset.id}`}>{asset.original_name}</option>)}</optgroup>}
                    </select>
                  </label>
                  {(selectedLibraryTrack || settings.music_asset_id) && <audio className="music-audio-preview" controls preload="none" src={selectedLibraryTrack ? musicTrackFileUrl(selectedLibraryTrack.id) : assetFileUrl(settings.music_asset_id!)} />}
                  <label className="form-label music-volume-label">ระดับเสียงเพลง <strong>{Math.round((settings.music_volume ?? 0.22) * 100)}%</strong>
                    <input type="range" min="0" max="1" step="0.01" value={settings.music_volume ?? 0.22} onChange={(event) => setEditor({ ...editor, settings: { ...settings, music_volume: Number(event.target.value) } })} />
                  </label>
                </>}
                <label className="upload-music button button-secondary"><input type="file" accept=".mp3,.m4a,.aac,.wav,.ogg,.flac,.opus,audio/*" disabled={uploadingMusic} onChange={uploadMusicFile} />{uploadingMusic ? <LoaderCircle className="spin" size={15} /> : <Music2 size={15} />}{uploadingMusic ? 'กำลังเพิ่มเพลง…' : 'เพิ่มเพลงเข้าในคลัง'}</label>
                <p className="editor-helper-text">เพิ่มครั้งเดียว แล้วเลือกเพลงนี้ใช้กับโปรเจกต์อื่นได้ด้วย</p>
                <button className="button button-secondary editor-save-settings" onClick={saveSettings} disabled={busy}><Save size={15} />บันทึกการตั้งค่าเสียง</button>
              </div>}

              {activePanel === 'subtitles' && <div className="editor-tab-panel subtitle-tab-panel">
                <div className="editor-tab-title"><div><h2>ซับไทย <span className="count-pill">{subtitles.length}</span></h2><p>เป็นตัวเลือก จะใส่คำแปลหรือปล่อยวิดีโอไม่มีซับก็ได้</p></div><AudioLines size={19} /></div>
                <div className="subtitle-quick-actions">
                  {!subtitles.length ? <button className="button button-primary" onClick={() => editor && void startAIJob(() => api.queueOcr(editor.id), 'กำลังอ่านซับและจะแปลเป็นไทยต่อให้อัตโนมัติ')} disabled={!aiSettings?.key_configured || busy || Boolean(activeJob)}><Sparkles size={15} />ทำซับไทยอัตโนมัติ</button> : subtitles.some((item) => item.source_text.trim() && !item.translated_text.trim()) ? <button className="button button-primary" onClick={() => editor && void startAIJob(() => api.queueTranslation(editor.id), 'กำลังแปลซับเป็นไทย')} disabled={!aiSettings?.key_configured || busy || Boolean(activeJob)}><Sparkles size={15} />แปลซับไทย</button> : <span className="subtitle-ready-note"><CheckCircle2 size={15} />ซับไทยพร้อมแล้ว</span>}
                  <label className="button button-secondary file-button"><input type="file" accept=".srt,text/plain" onChange={importSrtFile} disabled={busy} /><Upload size={15} />นำเข้า SRT</label>
                </div>
                {activeJob && <div className="ai-job-status"><LoaderCircle className="spin" size={15} />{activeJob.state === 'queued' ? 'รอคิว AI…' : `กำลังทำงาน ${activeJob.progress}%`}</div>}
                {subtitles.length ? <>
                  <div className="subtitle-table-head"><span>เวลาเริ่ม / จบ (วินาที)</span><span>ซับต้นฉบับ</span><span>ภาษาไทย</span><span /></div>
                  <div className="subtitle-list subtitle-list-scroll">{subtitles.map((item) => <div className="subtitle-edit-row" key={item.stable_id}>
                    <div className="subtitle-time-fields"><input aria-label="เวลาเริ่มซับเป็นวินาที" type="number" min="0" step="0.1" value={(item.start_ms / 1000).toFixed(1)} onChange={(event) => setSubtitle(item.stable_id, 'start_ms', Math.round(Number(event.target.value) * 1000))} /><span>ถึง</span><input aria-label="เวลาจบซับเป็นวินาที" type="number" min="0.1" step="0.1" value={(item.end_ms / 1000).toFixed(1)} onChange={(event) => setSubtitle(item.stable_id, 'end_ms', Math.round(Number(event.target.value) * 1000))} /><button className="text-button" onClick={() => setPlayheadMs(item.start_ms)} title="ไปยังจุดเริ่มซับ"><ArrowUpRight size={13} /></button></div>
                    <textarea aria-label="ซับต้นฉบับ" value={item.source_text} rows={2} placeholder="ข้อความจากคลิป" onChange={(event) => setSubtitle(item.stable_id, 'source_text', event.target.value)} />
                    <textarea aria-label="คำแปลภาษาไทย" value={item.translated_text} rows={2} placeholder="คำแปลภาษาไทย" onChange={(event) => setSubtitle(item.stable_id, 'translated_text', event.target.value)} />
                    <button className="icon-button delete-icon" title="ลบช่วงซับ" onClick={() => setSubtitles((items) => items.filter((row) => row.stable_id !== item.stable_id))}><Trash2 size={16} /></button>
                  </div>)}</div>
                </> : <div className="subtitle-optional-empty"><AudioLines size={22} /><strong>ไม่มีซับให้แปลก็ข้ามได้เลย</strong><span>หรือกด “ทำซับไทยอัตโนมัติ” ระบบจะอ่านและแปลให้ในขั้นตอนเดียว</span></div>}
                <details className="subtitle-advanced"><summary>ตั้งค่าเพิ่มเติม</summary>
                <div className="editor-toolbar editor-toolbar-wrap subtitle-manual-actions"><button className="button button-secondary" onClick={() => void exportSrt()} disabled={busy || !subtitles.length}><Download size={15} />ส่งออก SRT</button><button className="button button-secondary" onClick={addSubtitle}><Plus size={15} />เพิ่มช่วงซับเอง</button></div>
                <div className="editor-tab-title style-title"><div><h2>รูปแบบซับไทย</h2><p>ค่าเริ่มต้นพร้อมใช้งานแล้ว ปรับเฉพาะเมื่อต้องการ</p></div></div>
                <div className="style-input-grid">
                  <label className="form-label">สีตัวอักษร<input type="color" value={style.font_color ?? '#FFFFFF'} onChange={(event) => setEditor({ ...editor, settings: { ...settings, subtitle_style: { ...style, font_color: event.target.value } } })} /></label>
                  <label className="form-label">สีพื้นหลัง<input type="color" value={style.box_color ?? '#111111'} onChange={(event) => setEditor({ ...editor, settings: { ...settings, subtitle_style: { ...style, box_color: event.target.value } } })} /></label>
                  <label className="form-label">ขนาดตัวอักษร<input type="number" min="18" max="96" value={style.font_size ?? 52} onChange={(event) => setEditor({ ...editor, settings: { ...settings, subtitle_style: { ...style, font_size: Number(event.target.value) } } })} /></label>
                  <label className="form-label">ความทึบพื้นหลัง<input type="range" min="0.2" max="1" step="0.02" value={style.box_opacity ?? 0.92} onChange={(event) => setEditor({ ...editor, settings: { ...settings, subtitle_style: { ...style, box_opacity: Number(event.target.value) } } })} /></label>
                </div>
                </details>
                {subtitles.length > 0 && <div className="editor-actions"><span>ตรวจคำแปลจากตัวอย่างวิดีโอได้</span><button className="button button-secondary" onClick={() => editor && void saveCall(() => api.saveSubtitles(editor.id, subtitles), 'บันทึกซับแล้ว')} disabled={busy}><Save size={15} />บันทึกซับ</button></div>}
              </div>}

              {activePanel === 'overlays' && <div className="editor-tab-panel">
                <div className="editor-tab-title"><div><h2>ปิดซับเดิม</h2><p>เพิ่มกรอบสีทึบเพื่อวางทับตำแหน่งซับในวิดีโอต้นฉบับ</p></div><button className="button button-secondary" onClick={addOverlay}><Plus size={15} />เพิ่มกรอบ</button></div>
                {overlays.length ? <div className="overlay-list overlay-list-scroll">{overlays.map((item, index) => <div className="overlay-edit-row" key={item.id}>
                  <strong>กรอบ {index + 1}</strong><label>ซ้าย %<input type="number" min="0" max="100" value={Math.round(item.x * 100)} onChange={(event) => setOverlay(item.id, 'x', Number(event.target.value) / 100)} /></label><label>บน %<input type="number" min="0" max="100" value={Math.round(item.y * 100)} onChange={(event) => setOverlay(item.id, 'y', Number(event.target.value) / 100)} /></label><label>กว้าง %<input type="number" min="1" max="100" value={Math.round(item.width * 100)} onChange={(event) => setOverlay(item.id, 'width', Number(event.target.value) / 100)} /></label><label>สูง %<input type="number" min="1" max="100" value={Math.round(item.height * 100)} onChange={(event) => setOverlay(item.id, 'height', Number(event.target.value) / 100)} /></label><label>เริ่มวิ<input type="number" min="0" step="0.1" value={(item.start_ms / 1000).toFixed(1)} onChange={(event) => setOverlay(item.id, 'start_ms', Math.round(Number(event.target.value) * 1000))} /></label><label>จบวิ<input type="number" min="0.1" step="0.1" value={(item.end_ms / 1000).toFixed(1)} onChange={(event) => setOverlay(item.id, 'end_ms', Math.round(Number(event.target.value) * 1000))} /></label><input className="overlay-color" aria-label="สีกรอบปิดทับ" type="color" value={item.color} onChange={(event) => setOverlay(item.id, 'color', event.target.value)} /><button className="icon-button delete-icon" onClick={() => setOverlays((items) => items.filter((row) => row.id !== item.id))} title="ลบกรอบ"><Trash2 size={15} /></button>
                </div>)}</div> : <div className="subtitle-optional-empty"><span className="dropzone-icon"><Check size={18} /></span><strong>ยังไม่มีกรอบปิดซับ</strong><span>ถ้าวิดีโอไม่มีซับเดิม ข้ามส่วนนี้ได้เลย</span></div>}
                <div className="editor-actions"><span>ตั้งตำแหน่งและเวลาให้ตรงกับซับเดิม</span><button className="button button-secondary" onClick={() => editor && void saveCall(() => api.saveOverlays(editor.id, overlays), 'บันทึกกรอบปิดทับแล้ว')} disabled={busy}><Save size={15} />บันทึกกรอบ</button></div>
              </div>}

              {activePanel === 'copy' && <div className="editor-tab-panel copy-tab-panel">
                <div className="editor-tab-title"><div><h2>บทพากย์และข้อความโพสต์</h2><p>แคปชั่นละเอียดจากข้อมูลสินค้า พร้อมภาพและซับในคลิป</p></div><div className="copy-header-actions"><button className="button button-secondary" type="button" onClick={openProductInfo}><FileText size={15} />ข้อมูลสินค้า</button><button className="button button-primary" onClick={() => editor && void startAIJob(() => api.queueCopyPart(editor.id, 'script'), 'กำลังอ่านข้อมูลสินค้าและเขียนบทพากย์')} disabled={!aiSettings?.key_configured || busy || Boolean(activeJob)}><Sparkles size={15} />สร้างบทพากย์</button></div></div>
                {activeJob && <div className="ai-job-status"><LoaderCircle className="spin" size={15} />{activeJob.state === 'queued' ? 'รอคิว AI…' : `กำลังทำงาน ${activeJob.progress}%`}</div>}
                {copy ? <div className="copy-editor">
                  <label className="form-label">บทพากย์ไทย<textarea rows={6} value={copy.script_text} onChange={(event) => { setCopy({ ...copy, script_text: event.target.value }); setEditor((current) => current ? { ...current, settings: { ...current.settings, voiceover_asset_id: null } } : current); }} placeholder="AI จะเขียนบทให้พูดได้ทันภายในความยาวคลิป คุณแก้ไขก่อนสร้างเสียงได้" /></label>
                  <div className="voiceover-box"><div className="voiceover-heading"><div><strong>เสียงพากย์ไทย</strong><small>กดสร้างเพื่อฟังตัวอย่าง แล้วเสียงจะถูกวางตั้งแต่ต้นคลิปตอนเรนเดอร์</small></div><select value={voiceName} onChange={(event) => setVoiceName(event.target.value)} aria-label="เลือกเสียงพากย์"><option value="Kore">Kore · ชัดเจน</option><option value="Aoede">Aoede · นุ่มเป็นกันเอง</option><option value="Sulafat">Sulafat · อบอุ่น</option><option value="Achird">Achird · เป็นมิตร</option><option value="Leda">Leda · สดใส</option><option value="Charon">Charon · ให้ข้อมูล</option></select></div><div className="voiceover-actions"><button className="button button-secondary" onClick={() => editor && void startAIJob(() => api.queueVoiceover(editor.id, voiceName), 'กำลังสร้างเสียงพากย์ไทย · ข้อความจะถูกส่งไปประมวลผลด้วย Gemini')} disabled={!aiSettings?.key_configured || !copy.script_text.trim() || busy || Boolean(activeJob)}><AudioLines size={15} />สร้างเสียงพากย์</button>{editor?.voiceover_asset?.state === 'ready' && settings.voiceover_asset_id === editor.voiceover_asset.id && <audio controls preload="none" src={assetFileUrl(editor.voiceover_asset.id)} />}</div><small>สคริปต์จะส่งไป Google Gemini เพื่อสร้างเสียง · Gemini TTS เป็นรุ่นทดลอง · เสียงเริ่มที่วินาที 0 และตัดให้พอดีกับความยาววิดีโอ</small></div>
                  <div className="section-heading-row"><strong>แคปชั่นและคอมเมนต์</strong><button className="button button-secondary" onClick={() => editor && void startAIJob(() => api.queueCopyPart(editor.id, 'caption'), 'กำลังเรียบเรียงรายละเอียดสินค้าเป็นแคปชั่น')} disabled={!aiSettings?.key_configured || busy || Boolean(activeJob)}><Sparkles size={14} />สร้างแคปชั่นละเอียด</button></div>
                  <div className="caption-options">{copy.caption_candidates.map((caption, index) => <button type="button" key={`${index}-${caption}`} className={`caption-option ${copy.selected_caption === caption ? 'selected' : ''}`} onClick={() => setCopy({ ...copy, selected_caption: caption })}>ตัวเลือก {index + 1}</button>)}</div>
                  <label className="form-label long-caption-field">แคปชั่นที่เลือก<textarea rows={10} value={copy.selected_caption} onChange={(event) => setCopy({ ...copy, selected_caption: event.target.value })} placeholder="แก้แคปชั่นก่อนนำไปใช้" /></label>
                  <label className="form-label">ข้อความคอมเมนต์<textarea rows={3} value={copy.comment_text} onChange={(event) => setCopy({ ...copy, comment_text: event.target.value })} placeholder="ระบบแนบลิงก์ Affiliate ตอนเตรียมโพสต์" /></label>
                  <div className="editor-actions"><span>{copy.model_name ? `สร้างด้วย ${copy.model_name}` : 'แก้ไขข้อความก่อนบันทึกได้'}</span><button className="button button-secondary" onClick={() => void saveCopy()} disabled={savingCopy}><Save size={15} />{savingCopy ? 'กำลังบันทึก…' : 'บันทึกข้อความ'}</button></div>
                </div> : <div className="editor-empty-row">{aiSettings?.key_configured ? 'เพิ่มข้อมูลสินค้าได้ในช่อง “ข้อมูลสินค้า” แล้วให้ AI ช่วยเขียน' : 'ตั้งค่า Gemini API key แล้วจึงใช้ AI เขียนสคริปต์ได้'}</div>}
              </div>}
            </div>
          </div>
        </div>
      </>}
    </section>
  );
}

function OverviewPage({ projectCount, videoCount, pendingCount, projects, openProject, goProjects, createContent, openQueue }: {
  projectCount: number; videoCount: number; pendingCount: number; projects: Project[]; openProject: (project: Project) => void;
  goProjects: () => void; createContent: () => void; openQueue: () => void;
}) {
  return (
    <section className="page-content automation-overview">
      <PageTitle
        eyebrow="ศูนย์ควบคุม"
        title="ภาพรวมการทำงาน"
        subtitle="จัดการงานสินค้า ตรวจสถานะ และไปต่อยังขั้นตอนเผยแพร่ได้จากหน้าเดียว"
        action={<><button className="button button-secondary" onClick={openQueue}><Clapperboard size={16} />คิวโพสต์</button><button className="button button-primary" onClick={createContent}><Plus size={17} />สร้างคอนเทนต์</button></>}
      />

      <section className="workflow-panel content-panel" aria-labelledby="workflow-heading">
        <div className="workflow-panel-heading">
          <div><span className="panel-kicker">เวิร์กโฟลว์</span><h2 id="workflow-heading">จากสื่อสินค้าไปถึงโพสต์</h2><p>AI ช่วยเตรียมงาน คุณตรวจทานก่อนเผยแพร่ทุกครั้ง</p></div>
          <span className="workflow-ready"><span className="online-dot" />ระบบพร้อมทำงาน</span>
        </div>
        <ol className="automation-steps">
          <li><span className="automation-step-number">01</span><div><strong>เพิ่มสื่อ</strong><small>วิดีโอหรือภาพสินค้า</small></div><ChevronRight size={17} /></li>
          <li><span className="automation-step-number">02</span><div><strong>ให้ AI เตรียมโพสต์</strong><small>ซับ สคริปต์ หรือจัดองค์ประกอบ</small></div><ChevronRight size={17} /></li>
          <li><span className="automation-step-number">03</span><div><strong>ตรวจทาน</strong><small>ดูภาพ เสียง และข้อความ</small></div><ChevronRight size={17} /></li>
          <li><span className="automation-step-number">04</span><div><strong>ตั้งเวลา / เผยแพร่</strong><small>จัดการในคิวโพสต์</small></div></li>
        </ol>
      </section>

      <div className="stat-grid overview-stats">
        <StatCard icon={FolderKanban} label="งานในคลัง" value={projectCount} footnote="โปรเจกต์ที่บันทึกไว้" tone="violet" />
        <StatCard icon={Film} label="วิดีโอต้นฉบับ" value={videoCount} footnote="ไฟล์ที่นำเข้าแล้ว" tone="blue" />
        <StatCard icon={Clock3} label="กำลังประมวลผล" value={pendingCount} footnote="ระบบจะอัปเดตสถานะให้อัตโนมัติ" tone="amber" />
      </div>

      <div className="section-heading-row overview-project-heading">
        <div><h2>ทำงานต่อ</h2><p>เปิดงานล่าสุดเพื่อไปต่อจากจุดเดิม</p></div>
        <button className="text-button" onClick={goProjects}>เปิดคลังงาน <ArrowUpRight size={15} /></button>
      </div>
      {projects.length
        ? <div className="project-grid compact-grid">{projects.map((project, index) => <ProjectCard key={project.id} project={project} index={index} open={() => openProject(project)} />)}</div>
        : <div className="overview-empty content-panel"><div><span className="dropzone-icon"><FolderKanban size={21} /></span><strong>ยังไม่มีงานที่บันทึกไว้</strong><p>เริ่มด้วยภาพหรือวิดีโอ ระบบจะเก็บงานให้กลับมาทำต่อได้</p></div><button className="button button-primary" onClick={createContent}><Plus size={16} />เริ่มสร้างคอนเทนต์</button></div>}
    </section>
  );
}

function ContentStudioPage({ startVideo, startPhoto, openProjects, openQueue, projectCount, pendingCount }: {
  startVideo: () => void; startPhoto: () => void; openProjects: () => void; openQueue: () => void; projectCount: number; pendingCount: number;
}) {
  return (
    <section className="page-content content-studio-page">
      <PageTitle eyebrow="สร้างคอนเทนต์" title="สร้างโพสต์ใหม่" subtitle="เลือกรูปแบบโพสต์เพื่อเริ่มต้น" action={<button className="button button-secondary" onClick={openQueue}><Clapperboard size={16} />คิวโพสต์</button>} />

      <div className="content-studio-flow content-panel">
        <ol className="automation-steps compact-steps">
          <li><span className="automation-step-number">1</span><div><strong>เลือกสื่อ</strong></div><ChevronRight size={16} /></li>
          <li><span className="automation-step-number">2</span><div><strong>เตรียมโพสต์</strong></div><ChevronRight size={16} /></li>
          <li><span className="automation-step-number">3</span><div><strong>ตรวจแล้วโพสต์</strong></div></li>
        </ol>
      </div>

      <div className="content-choice-grid">
        <article className="content-choice-card content-panel">
          <div className="content-choice-icon video-choice"><FileVideo2 size={22} /></div>
          <div className="content-choice-copy"><h2>โพสต์วิดีโอ</h2><p>เพิ่มคลิป แล้วเตรียมเสียง ซับ และแคปชั่น</p></div>
          <button className="button button-primary" onClick={startVideo}><Plus size={16} />เริ่มทำวิดีโอ<ArrowUpRight size={15} /></button>
        </article>

        <article className="content-choice-card content-panel">
          <div className="content-choice-icon image-choice"><ImageIcon size={22} /></div>
          <div className="content-choice-copy"><h2>โพสต์รูปภาพ</h2><p>แนบภาพที่จัดเอง แล้วให้ AI เขียนแคปชั่นกับคอมเมนต์</p></div>
          <button className="button button-primary" onClick={startPhoto}><Plus size={16} />เริ่มทำรูปภาพ<ArrowUpRight size={15} /></button>
        </article>
      </div>

      <div className="content-studio-footer content-panel"><strong>คลังงาน {projectCount} งาน{pendingCount > 0 ? ` · กำลังทำ ${pendingCount}` : ''}</strong><button className="text-button" onClick={openProjects}>เปิดคลังงาน<ArrowUpRight size={15} /></button></div>
    </section>
  );
}

function imagePostError(reason: unknown): string {
  if (reason instanceof ApiError) {
    const message = reason.message.toLowerCase();
    if (reason.status === 429 || message.includes('โควตา') || message.includes('ขีดจำกัด') || message.includes('rate limit')) {
      return 'Gemini ถึงขีดจำกัดการใช้งานช่วงนี้แล้ว รอให้โควตารีเซ็ตก่อนลองใหม่ ภาพและข้อมูลที่เลือกยังอยู่ในหน้านี้';
      }
      if (reason.status >= 500) {
        return `${reason.message} · ระบบลองซ้ำให้อัตโนมัติแล้ว ภาพและข้อมูลที่เลือกยังอยู่ครบ`;
      }
    return reason.message;
  }
  return reason instanceof Error ? reason.message : 'ทำรายการไม่สำเร็จ ข้อมูลที่กรอกยังอยู่ในหน้านี้';
}

function ImagePostPage({ onSaved }: { onSaved: () => void }) {
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [productInfo, setProductInfo] = useState('');
  const [affiliateUrl, setAffiliateUrl] = useState('');
  const [caption, setCaption] = useState('');
  const [comment, setComment] = useState('');
  const [copySource, setCopySource] = useState('');
  const [copyAffiliateSource, setCopyAffiliateSource] = useState('');
  const [generating, setGenerating] = useState(false);
  const [modelName, setModelName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    const urls = imageFiles.map((file) => URL.createObjectURL(file));
    setPreviews(urls);
    return () => urls.forEach((url) => URL.revokeObjectURL(url));
  }, [imageFiles]);

  const selectImage = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = '';
    setNotice(''); setError('');
    if (!selected.length) return;
    const invalidType = selected.find((file) => !['image/jpeg', 'image/png'].includes(file.type));
    if (invalidType) {
      setError('รองรับเฉพาะภาพ JPG หรือ PNG เพื่อโพสต์หลายภาพบน Facebook');
      return;
    }
    if (selected.some((file) => file.size > 10 * 1024 * 1024)) {
      setError('ภาพแต่ละไฟล์ต้องไม่เกิน 10 MB');
      return;
    }
    const next = [...imageFiles, ...selected];
    if (next.length > 6) {
      setError('โพสต์ได้สูงสุด 6 รูป · เลือกรูปเพิ่มได้หลังลบบางรูปออก');
      return;
    }
    if (next.reduce((total, file) => total + file.size, 0) > 36 * 1024 * 1024) {
      setError('ภาพทั้งหมดรวมกันต้องไม่เกิน 36 MB');
      return;
    }
    setImageFiles(next);
  };

  const removeImage = (index: number) => setImageFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));

  const syncAffiliateLink = (text: string, url: string, label: string) => {
    const linkLabels = ['🛒 พิกัดสินค้า กดดูตรงนี้:', '👉 กดสั่ง/ดูรายละเอียด:'];
    const body = text.split(/\r?\n/).filter((line) => !linkLabels.some((prefix) => line.trim().startsWith(prefix))).join('\n').trim();
    return body && url.trim() ? `${body}\n\n${label}: ${url.trim()}` : body;
  };

  const generateCopy = async () => {
    setGenerating(true); setError(''); setNotice('');
    try {
      const source = productInfo.trim();
      const link = affiliateUrl.trim();
      const result = await api.generateImagePostCopy(source, link);
      setCaption(result.caption); setComment(result.comment_text); setCopySource(source); setCopyAffiliateSource(link); setModelName(result.model_name);
      setNotice('ได้แคปชั่นและคอมเมนต์แล้ว · ตรวจแก้ได้ก่อนบันทึก');
    } catch (reason) { setError(imagePostError(reason)); }
    finally { setGenerating(false); }
  };

  const save = async () => {
    if (!imageFiles.length) return;
    setSaving(true); setError(''); setNotice('');
    try {
      await api.createImagePost(imageFiles, { caption, comment_text: comment, affiliate_url: affiliateUrl, product_details: productInfo });
      onSaved();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'บันทึกดราฟต์ภาพไม่สำเร็จ'); }
    finally { setSaving(false); }
  };

  return (
    <section className="page-content image-post-page">
      <PageTitle eyebrow="โพสต์ภาพสินค้า" title="เตรียมโพสต์ภาพ" subtitle="แนบภาพที่จัดเอง ใส่ข้อมูลกับลิงก์ แล้วให้ AI เขียนแคปชั่นและคอมเมนต์" action={<button className="button button-secondary" onClick={onSaved}><ArrowLeft size={15} />กลับรายการโพสต์</button>} />
      {error && <div className="image-error-banner" role="alert"><CircleHelp size={18} /><div><strong>ทำรายการไม่สำเร็จ</strong><span>{error}</span><small>รูปและข้อมูลที่กรอกยังอยู่ในหน้านี้</small></div><button className="icon-button" onClick={() => setError('')} aria-label="ปิดข้อความผิดพลาด"><X size={16} /></button></div>}{notice && <div className="form-success"><CheckCircle2 size={15} />{notice}</div>}
      <div className="image-composer-grid">
        <div className="image-composer-controls content-panel">
          <div className="panel-heading compact"><div><span className="panel-kicker">ขั้นตอนที่ 1</span><h2>ภาพและข้อมูลสินค้า</h2></div><span className="optional-label">ภาพที่จัดเอง</span></div>
          <label className="image-upload-drop"><Upload size={20} /><strong>{imageFiles.length ? 'เพิ่มรูปที่จัดเตรียมไว้' : 'เลือกรูปที่จัดเตรียมไว้'}</strong><span>เลือกพร้อมกันหรือเพิ่มทีหลังได้ · JPG, PNG · สูงสุด 6 รูป · รูปละ 10 MB</span><input type="file" accept="image/jpeg,image/png" multiple onChange={selectImage} /></label>
          {!!imageFiles.length && <div className="image-post-gallery" aria-label={`เลือกแล้ว ${imageFiles.length} รูป`}>
            {imageFiles.map((file, index) => <div className="image-post-thumb" key={`${file.name}-${file.lastModified}-${index}`}><img src={previews[index]} alt={`ภาพโพสต์ ${index + 1}`} /><span>{index === 0 ? 'ปก' : `${index + 1}`}</span><button type="button" onClick={() => removeImage(index)} aria-label={`ลบภาพที่ ${index + 1}`}><X size={13} /></button><small title={file.name}>{file.name}</small></div>)}
          </div>}
          <label className="form-label image-details-field">ข้อมูลสินค้า<textarea value={productInfo} onChange={(event) => setProductInfo(event.target.value)} rows={7} maxLength={24000} placeholder="ใส่ชื่อสินค้า จุดเด่น สเปกสำคัญ ราคา/โปร และข้อมูลรีวิวที่อยากให้ AI ใช้" /></label>
          <label className="form-label">ลิงก์ Affiliate <span className="optional-label">จำเป็นสำหรับพิกัดสั่งซื้อ</span><input required value={affiliateUrl} onChange={(event) => { const value = event.target.value; setAffiliateUrl(value); setCaption((current) => syncAffiliateLink(current, value, '🛒 พิกัดสินค้า กดดูตรงนี้')); setComment((current) => syncAffiliateLink(current, value, '👉 กดสั่ง/ดูรายละเอียด')); }} placeholder="วางลิงก์สินค้า Affiliate เช่น https://s.shopee.co.th/..." /></label>
          <p className="product-input-hint">AI ใช้ข้อมูลสินค้าเขียนใหม่ · ระบบแทรกลิงก์จริงท้ายแคปชันและคอมเมนต์ · รูปไม่ส่งให้ AI</p>
        </div>

        <div className="image-copy-panel content-panel">
          <div className="panel-heading compact"><div><span className="panel-kicker">ขั้นตอนที่ 2</span><h2>แคปชั่นและคอมเมนต์</h2></div><span className="optional-label">แก้ได้ก่อนบันทึก</span></div>
          <button className="button button-secondary image-ai-button" onClick={() => void generateCopy()} disabled={!productInfo.trim() || !affiliateUrl.trim() || generating || saving}><Sparkles size={16} />{generating ? 'กำลังเขียนโพสต์…' : 'ให้ AI เขียนแคปชั่น + คอมเมนต์'}</button>
          <div className={`image-link-target ${affiliateUrl.trim() ? 'ready' : 'missing'}`}><Link2 size={15} /><div><strong>{affiliateUrl.trim() ? 'พิกัดสั่งซื้อที่จะใส่ในโพสต์และคอมเมนต์' : 'ยังไม่มีลิงก์สินค้า'}</strong><span>{affiliateUrl.trim() || 'วางลิงก์ Affiliate ในช่องฝั่งซ้ายก่อนสร้างข้อความ'}</span></div></div>
          {modelName && <p className="product-input-hint">สร้างด้วย {modelName}{copySource !== productInfo.trim() || copyAffiliateSource !== affiliateUrl.trim() ? ' · ข้อมูลสินค้าหรือลิงก์เปลี่ยนแล้ว กดสร้างใหม่เพื่ออัปเดตข้อความ' : ''}</p>}
          <label className="form-label long-caption-field">แคปชั่น<textarea value={caption} onChange={(event) => setCaption(event.target.value)} rows={8} placeholder="แคปชั่นกวน ๆ ขายตรงจากข้อมูลสินค้าจะอยู่ตรงนี้" /></label>
          <label className="form-label">คอมเมนต์<textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={3} placeholder="ข้อความสั้นชวนกดดูสินค้า · ระบบเติมลิงก์ให้อัตโนมัติ" /></label>
          <div className="image-save-row"><span>{!affiliateUrl.trim() ? 'ใส่ลิงก์ Affiliate ก่อนบันทึกโพสต์' : imageFiles.length ? `แนบ ${imageFiles.length} รูป · ลิงก์อยู่ในโพสต์และคอมเมนต์แล้ว` : 'ใช้ภาพที่แนบตรง ๆ ไม่มีการจัดหรือแก้ภาพด้วย AI'}</span><button className="button button-primary" onClick={() => void save()} disabled={!imageFiles.length || !caption.trim() || !affiliateUrl.trim() || saving || generating}><Save size={15} />{saving ? 'กำลังบันทึก…' : 'บันทึกดราฟต์ภาพ'}</button></div>
        </div>
      </div>
    </section>
  );
}

const publicationFilters = [
  { value: '', label: 'ทั้งหมด' },
  { value: 'draft', label: 'ดราฟต์' },
  { value: 'scheduled', label: 'ตั้งเวลา' },
  { value: 'publishing', label: 'กำลังส่ง' },
  { value: 'processing', label: 'กำลังประมวลผล' },
  { value: 'needs_attention', label: 'ต้องดำเนินการ' },
  { value: 'published', label: 'เผยแพร่แล้ว' },
  { value: 'cancelled', label: 'ยกเลิก' },
];

function publicationStatus(status: Publication['status']): { label: string; tone: string } {
  if (status === 'scheduled') return { label: 'ตั้งเวลาไว้', tone: 'working' };
  if (status === 'publishing') return { label: 'กำลังส่งวิดีโอ', tone: 'working' };
  if (status === 'processing') return { label: 'Facebook กำลังประมวลผล', tone: 'working' };
  if (status === 'needs_attention') return { label: 'ต้องดำเนินการ', tone: 'danger' };
  if (status === 'published') return { label: 'เผยแพร่แล้ว', tone: 'success' };
  if (status === 'failed') return { label: 'ไม่สำเร็จ', tone: 'danger' };
  if (status === 'cancelled') return { label: 'ยกเลิก', tone: 'muted' };
  return { label: 'ดราฟต์', tone: 'muted' };
}

function localDateTimeInput(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function PostsPage({ onCreateImagePost }: { onCreateImagePost: () => void }) {
  const [posts, setPosts] = useState<Publication[]>([]);
  const [filter, setFilter] = useState('');
  const [mediaFilter, setMediaFilter] = useState<'all' | 'video' | 'image'>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [caption, setCaption] = useState('');
  const [comment, setComment] = useState('');
  const [scheduledLocal, setScheduledLocal] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [postingId, setPostingId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [facebookReady, setFacebookReady] = useState(false);

  const load = async () => {
    try { setPosts(await api.publications()); setError(''); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'โหลดรายการโพสต์ไม่สำเร็จ'); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    void load();
    void api.facebookSettings().then((settings) => setFacebookReady(settings.pages.some((page) => page.is_active && page.token_configured))).catch(() => setFacebookReady(false));
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const visiblePosts = posts.filter((post) => {
    const matchesStatus = !filter || post.status === filter;
    const matchesMedia = mediaFilter === 'all' || post.media_type === mediaFilter;
    return matchesStatus && matchesMedia;
  });
  const selected = visiblePosts.find((post) => post.id === selectedId) ?? null;
  useEffect(() => {
    if (!selected) return;
    setCaption(selected.caption);
    setComment(selected.comment_text);
    setScheduledLocal(localDateTimeInput(selected.scheduled_at));
  }, [selected?.id, selected?.caption, selected?.comment_text, selected?.scheduled_at]);

  const save = async () => {
    if (!selected) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const scheduled_at = scheduledLocal ? new Date(scheduledLocal).toISOString() : null;
      const updated = await api.updatePublication(selected.id, { caption, comment_text: comment, scheduled_at });
      setPosts((items) => items.map((item) => item.id === updated.id ? updated : item));
      setNotice(updated.status === 'scheduled' ? (facebookReady ? 'บันทึกเวลาแล้ว · worker จะเผยแพร่เมื่อถึงกำหนดขณะโปรแกรมเปิดอยู่' : 'บันทึกเวลาแล้ว · เชื่อม Facebook Page ก่อนถึงกำหนดเพื่อให้เผยแพร่อัตโนมัติ') : 'บันทึกดราฟต์แล้ว');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'บันทึกรายการไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!selected) return;
    setBusy(true); setError(''); setNotice('');
    try { const updated = await api.cancelPublication(selected.id); setPosts((items) => items.map((item) => item.id === updated.id ? updated : item)); setNotice('ยกเลิกรายการแล้ว'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'ยกเลิกรายการไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const sendNow = async (post: Publication) => {
    setBusy(true); setPostingId(post.id); setError(''); setNotice('');
    try {
      const queued = await api.publishNow(post.id);
      setPosts((items) => items.map((item) => item.id === queued.id ? queued : item));
      setNotice(post.media_type === 'image' ? 'ส่งโพสต์ภาพเข้าคิว Facebook แล้ว · ระบบจะแสดงสถานะการเผยแพร่ที่นี่' : 'ส่ง Reel เข้าคิว Facebook แล้ว · โปรแกรมจะแสดงสถานะระหว่างอัปโหลดและประมวลผล');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'ส่งโพสต์เข้าคิวไม่สำเร็จ'); }
    finally { setBusy(false); setPostingId(null); }
  };
  const confirmAndSendNow = (post: Publication) => {
    const mediaName = post.media_type === 'image' ? 'โพสต์ภาพ' : 'โพสต์วิดีโอ';
    const pageName = post.page_name ? `บนเพจ “${post.page_name}”` : 'บน Facebook Page ที่เชื่อมต่อ';
    const commentNote = post.comment_text.trim() ? '\nระบบจะส่งคอมเมนต์ที่บันทึกไว้ตามหลังเมื่อโพสต์สำเร็จ' : '';
    if (window.confirm(`ส่ง${mediaName}เข้าคิวเผยแพร่ทันที ${pageName}?\n\nระบบจะใช้แคปชัน รูป/วิดีโอ และคอมเมนต์ที่บันทึกไว้${commentNote}\n\nหากเป็นรายการตั้งเวลา ระบบจะเปลี่ยนเป็นเผยแพร่ทันที`)) {
      void sendNow(post);
    }
  };
  const retryComment = async (post: Publication) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const queued = await api.retryPublicationComment(post.id);
      setPosts((items) => items.map((item) => item.id === queued.id ? queued : item));
      setNotice('ส่งคอมเมนต์เข้าคิวอีกครั้งแล้ว');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'ส่งคอมเมนต์เข้าคิวไม่สำเร็จ'); }
    finally { setBusy(false); }
  };

  return (
    <section className="page-content posts-page">
      <PageTitle eyebrow="เผยแพร่คอนเทนต์" title="คิวโพสต์" subtitle="แยกจัดการโพสต์รูปภาพและวิดีโอ พร้อมติดตามสถานะ Facebook ได้จากที่เดียว" action={<button className="button button-primary" onClick={onCreateImagePost}><Sparkles size={15} />สร้างคอนเทนต์</button>} />
      <div className="media-type-switch" role="tablist" aria-label="เลือกประเภทโพสต์">
        <button className={mediaFilter === 'all' ? 'active' : ''} onClick={() => { setMediaFilter('all'); setSelectedId(null); }} role="tab" aria-selected={mediaFilter === 'all'}><Clapperboard size={15} />ทั้งหมด<span>{posts.length}</span></button>
        <button className={mediaFilter === 'video' ? 'active video' : 'video'} onClick={() => { setMediaFilter('video'); setSelectedId(null); }} role="tab" aria-selected={mediaFilter === 'video'}><FileVideo2 size={15} />วิดีโอ<span>{posts.filter((post) => post.media_type === 'video').length}</span></button>
        <button className={mediaFilter === 'image' ? 'active image' : 'image'} onClick={() => { setMediaFilter('image'); setSelectedId(null); }} role="tab" aria-selected={mediaFilter === 'image'}><ImageIcon size={15} />รูปภาพ<span>{posts.filter((post) => post.media_type === 'image').length}</span></button>
      </div>
      <div className="post-filters" role="tablist" aria-label="กรองรายการโพสต์">
        {publicationFilters.map((item) => <button key={item.value} className={`post-filter ${filter === item.value ? 'active' : ''}`} onClick={() => { setFilter(item.value); setSelectedId(null); }} role="tab" aria-selected={filter === item.value}>{item.label}<span>{item.value ? posts.filter((post) => post.status === item.value).length : posts.length}</span></button>)}
      </div>
      {error && <div className="form-error">{error}</div>}{notice && <div className="form-success"><CheckCircle2 size={15} />{notice}</div>}
      {loading ? <div className="loading-panel"><LoaderCircle className="spin" size={19} />กำลังโหลดรายการโพสต์</div> : !visiblePosts.length ? (
        <div className="posts-empty content-panel"><div className="roadmap-icon"><Clapperboard size={24} /></div><h2>{filter ? 'ไม่มีรายการในสถานะนี้' : 'ยังไม่มีดราฟต์โพสต์'}</h2><p>เริ่มจากวิดีโอหรือภาพสินค้า แล้วงานที่เตรียมไว้จะมาแสดงในคิวนี้</p><button className="button button-secondary" onClick={onCreateImagePost}><Sparkles size={15} />เริ่มเวิร์กโฟลว์</button></div>
      ) : (
        <div className="publication-list">{visiblePosts.map((post) => {
          const status = publicationStatus(post.status);
          const editable = ['draft', 'scheduled', 'needs_attention'].includes(post.status) && !post.remote_stage && !post.remote_video_id;
          return <article className={`publication-card content-panel ${selectedId === post.id ? 'expanded' : ''}`} key={post.id}>
            <div className="publication-main">
              <div className={`publication-video ${post.media_type === 'image' ? 'publication-image' : ''}`}>{post.render_asset ? post.media_type === 'image' ? <img src={assetFileUrl(post.render_asset.id)} alt="ภาพปกโพสต์" /> : <video src={assetFileUrl(post.render_asset.id)} controls preload="metadata" /> : post.media_type === 'image' ? <ImageIcon size={25} /> : <FileVideo2 size={25} />}{post.media_type === 'image' && post.media_assets.length > 1 && <span className="publication-image-count">{post.media_assets.length} รูป</span>}</div>
              <div className="publication-summary">
                <div className="publication-title-row"><div><span className="panel-kicker">{post.media_type === 'image' ? 'โพสต์ภาพ' : 'โพสต์วิดีโอ'} · {post.project_title}</span><h2>{post.page_name ?? 'Facebook Page · ยังไม่เชื่อม'}</h2></div><span className={`status-chip ${status.tone}`}><span className="status-dot" />{status.label}</span></div>
                <p className="publication-caption-preview">{post.caption}</p>
                <div className="publication-meta"><span><CalendarClock size={13} />{post.published_at ? `เผยแพร่ ${formatDateTime(post.published_at)}` : post.scheduled_at ? formatDateTime(post.scheduled_at) : 'ยังไม่ตั้งเวลา'}</span><span><MessageCircle size={13} />คอมเมนต์: {post.comment_status === 'not_set' ? 'ไม่มี' : post.comment_status === 'waiting_for_publish' ? 'รอโพสต์' : post.comment_status === 'queued' ? 'กำลังส่ง' : post.comment_status === 'published' ? 'ลงแล้ว' : post.comment_status === 'failed' ? 'ไม่สำเร็จ' : 'ต้องดำเนินการ'}</span><span>เพิ่ม {formatDateTime(post.created_at)}</span></div>
                {post.last_error && <div className="publication-warning">{post.last_error}</div>}
                {post.external_post_id && <a className="publication-link" href={post.media_type === 'image' ? `https://www.facebook.com/${encodeURIComponent(post.external_post_id)}` : `https://www.facebook.com/reel/${encodeURIComponent(post.external_post_id)}`} target="_blank" rel="noreferrer"><ExternalLink size={13} />เปิด{post.media_type === 'image' ? 'โพสต์ภาพ' : 'Reel'}บน Facebook</a>}
                {post.affiliate_url && <a className="publication-link" href={post.affiliate_url} target="_blank" rel="noreferrer"><Link2 size={13} />{post.affiliate_url}</a>}
              </div>
              <div className="publication-card-actions">
                {editable && <button className="button button-primary small publication-send-button" onClick={() => confirmAndSendNow(post)} disabled={busy || !facebookReady} title={facebookReady ? 'เผยแพร่รายการที่บันทึกไว้ทันที' : 'เชื่อมต่อ Facebook Page ก่อน'}><Send size={13} />{postingId === post.id ? 'กำลังส่ง…' : 'โพสต์เลย'}</button>}
                <button className="button button-secondary small publication-edit-button" onClick={() => setSelectedId(selectedId === post.id ? null : post.id)}>{selectedId === post.id ? 'ปิดรายละเอียด' : editable ? 'แก้ไข / ตั้งเวลา' : 'ดูรายละเอียด'}</button>
              </div>
            </div>
            {selectedId === post.id && <div className="publication-details">
              {editable ? <>
                <label className="form-label">แคปชั่น<textarea rows={4} value={caption} onChange={(event) => setCaption(event.target.value)} /></label>
                <label className="form-label">คอมเมนต์ที่จะลงหลังโพสต์<textarea rows={3} value={comment} onChange={(event) => setComment(event.target.value)} /></label>
                <label className="form-label schedule-input">ตั้งเวลาโพสต์ <span className="optional-label">เว้นว่างเพื่อเก็บเป็นดราฟต์</span><input type="datetime-local" value={scheduledLocal} onChange={(event) => setScheduledLocal(event.target.value)} /></label>
                <div className="publication-actions"><span>{facebookReady ? `ตั้งเวลาแล้ว worker จะส่ง${post.media_type === 'image' ? 'ภาพ' : 'Reel'}เมื่อถึงกำหนดและโปรแกรมเปิดอยู่` : 'เชื่อม Facebook Page ในหน้าตั้งค่าก่อนโพสต์อัตโนมัติ'}</span><div>{post.status !== 'needs_attention' && <button className="button button-secondary small" onClick={() => void cancel()} disabled={busy}>ยกเลิกรายการ</button>}{facebookReady && <button className="button button-secondary small" onClick={() => void sendNow(post)} disabled={busy}><Send size={13} />โพสต์ทันที</button>}<button className="button button-primary small" onClick={() => void save()} disabled={busy || !caption.trim()}><Save size={14} />{busy ? 'กำลังบันทึก…' : scheduledLocal ? 'บันทึกเวลา' : 'บันทึกดราฟต์'}</button></div></div>
              </> : <>
                <div className="publication-copy-preview"><strong>แคปชั่น</strong><p>{post.caption}</p><strong>คอมเมนต์</strong><p>{post.comment_text || 'ไม่ได้ตั้งคอมเมนต์'}</p></div>
                {post.status === 'published' && post.comment_status === 'failed' && <div className="publication-actions"><span>Meta ปฏิเสธคอมเมนต์ครั้งก่อน ลองอีกครั้งได้หลังตรวจสิทธิ์เพจ</span><button className="button button-secondary small" onClick={() => void retryComment(post)} disabled={busy}><MessageCircle size={13} />ลองคอมเมนต์อีกครั้ง</button></div>}
              </>}
              <div className="publication-history"><strong>ประวัติรายการ</strong>{post.events.map((event) => <div key={event.id}><span>{formatDateTime(event.created_at)}</span><p>{event.message}</p></div>)}</div>
            </div>}
          </article>;
        })}</div>
      )}
    </section>
  );
}

function SettingsPage({ capabilities }: { capabilities: Capabilities | null }) {
  const [aiSettings, setAiSettings] = useState<import('./types').AISettings | null>(null);
  const [aiUsage, setAiUsage] = useState<import('./types').AIUsage | null>(null);
  const [facebookSettings, setFacebookSettings] = useState<import('./types').FacebookSettings | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [pageId, setPageId] = useState('');
  const [pageToken, setPageToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [usageBusy, setUsageBusy] = useState(false);
  const [facebookBusy, setFacebookBusy] = useState(false);
  const [backupBusy, setBackupBusy] = useState(false);
  const [backupMessage, setBackupMessage] = useState('');
  const [backupError, setBackupError] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [facebookMessage, setFacebookMessage] = useState('');
  const [facebookError, setFacebookError] = useState('');
  const [updateInfo, setUpdateInfo] = useState<import('./types').ApplicationUpdate | null>(null);
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateInstallBusy, setUpdateInstallBusy] = useState(false);
  const [updateError, setUpdateError] = useState('');
  const [updateMessage, setUpdateMessage] = useState('');

  useEffect(() => {
    void Promise.all([api.aiSettings(), api.facebookSettings(), api.aiUsage()])
      .then(([ai, facebook, usage]) => { setAiSettings(ai); setFacebookSettings(facebook); setAiUsage(usage); })
      .catch((reason) => setError(reason instanceof Error ? reason.message : 'อ่านค่าตั้งค่าโปรแกรมไม่สำเร็จ'));
  }, []);

  const refreshAIUsage = async () => {
    setUsageBusy(true);
    try { setAiUsage(await api.aiUsage()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'อ่านประวัติการใช้ Gemini ไม่สำเร็จ'); }
    finally { setUsageBusy(false); }
  };

  const saveKey = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true); setError(''); setMessage('');
    try {
      await api.saveGeminiKey(apiKey);
      setApiKey(''); setAiSettings(await api.aiSettings()); setMessage('เก็บ API key ใน Windows Credential Protection แล้ว');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'บันทึก API key ไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const testKey = async () => {
    setTesting(true); setError(''); setMessage('');
    try { const response = await api.testGemini(); setMessage(`เชื่อม Gemini ได้แล้ว · ${response.model}`); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'ทดสอบ Gemini ไม่สำเร็จ'); }
    finally { setTesting(false); }
  };
  const deleteKey = async () => {
    setBusy(true); setError(''); setMessage('');
    try { await api.removeGeminiKey(); setAiSettings(await api.aiSettings()); setMessage('ลบ API key ที่เก็บไว้แล้ว'); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'ลบ API key ไม่สำเร็จ'); }
    finally { setBusy(false); }
  };
  const changeModel = async (model: string) => {
    setError(''); setMessage('');
    try { await api.setGeminiModel(model); setAiSettings((current) => current ? { ...current, model } : current); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'เปลี่ยนโมเดลไม่สำเร็จ'); }
  };
  const connectPage = async (event: FormEvent) => {
    event.preventDefault(); setFacebookBusy(true); setFacebookError(''); setFacebookMessage('');
    try {
      const page = await api.connectFacebookPage(pageId.trim(), pageToken.trim());
      setPageToken(''); setPageId(''); setFacebookSettings(await api.facebookSettings()); setFacebookMessage(`ยืนยันและเชื่อมเพจ “${page.name}” แล้ว · token ถูกเก็บด้วย Windows DPAPI`);
    } catch (reason) { setFacebookError(reason instanceof Error ? reason.message : 'เชื่อม Facebook Page ไม่สำเร็จ'); }
    finally { setFacebookBusy(false); }
  };
  const testPage = async (id: string) => {
    setFacebookBusy(true); setFacebookError(''); setFacebookMessage('');
    try { const result = await api.testFacebookPage(id); setFacebookMessage(`เชื่อมต่อ ${result.page_name} ได้ · Graph API ${result.api_version}`); setFacebookSettings(await api.facebookSettings()); }
    catch (reason) { setFacebookError(reason instanceof Error ? reason.message : 'ทดสอบ Facebook Page ไม่สำเร็จ'); }
    finally { setFacebookBusy(false); }
  };
  const selectPage = async (id: string) => {
    setFacebookBusy(true); setFacebookError(''); setFacebookMessage('');
    try { await api.selectFacebookPage(id); setFacebookSettings(await api.facebookSettings()); setFacebookMessage('เลือกเพจสำหรับคิวโพสต์แล้ว'); }
    catch (reason) { setFacebookError(reason instanceof Error ? reason.message : 'เลือกเพจไม่สำเร็จ'); }
    finally { setFacebookBusy(false); }
  };
  const disconnectPage = async (id: string) => {
    setFacebookBusy(true); setFacebookError(''); setFacebookMessage('');
    try { await api.disconnectFacebookPage(id); setFacebookSettings(await api.facebookSettings()); setFacebookMessage('ลบ Page token ที่เข้ารหัสไว้แล้ว'); }
    catch (reason) { setFacebookError(reason instanceof Error ? reason.message : 'ยกเลิกการเชื่อมเพจไม่สำเร็จ'); }
    finally { setFacebookBusy(false); }
  };
  const downloadBackup = async () => {
    setBackupBusy(true); setBackupError(''); setBackupMessage('');
    try {
      const result = await api.downloadBackup();
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement('a');
      link.href = url; link.download = result.filename; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setBackupMessage('ดาวน์โหลดไฟล์สำรองแล้ว · ไม่มี Gemini API key หรือ Facebook Page token อยู่ในไฟล์');
    } catch (reason) { setBackupError(reason instanceof Error ? reason.message : 'สำรองข้อมูลไม่สำเร็จ'); }
    finally { setBackupBusy(false); }
  };
  const checkForUpdates = async () => {
    setUpdateBusy(true); setUpdateError(''); setUpdateMessage('');
    try { setUpdateInfo(await api.checkApplicationUpdates()); }
    catch (reason) { setUpdateError(reason instanceof Error ? reason.message : 'ตรวจสอบอัปเดตไม่สำเร็จ'); }
    finally { setUpdateBusy(false); }
  };
  const installUpdate = async () => {
    if (!updateInfo?.latest_version || !updateInfo.installable) return;
    const confirmed = window.confirm(`อัปเดตเป็นเวอร์ชัน ${updateInfo.latest_version} เลยไหม?\n\nโปรแกรมจะปิดและเปิดใหม่อัตโนมัติ ข้อมูลใน Data จะไม่ถูกแตะต้อง และจะตรวจสอบไฟล์ด้วย SHA-256 ก่อนติดตั้ง`);
    if (!confirmed) return;
    setUpdateInstallBusy(true); setUpdateError(''); setUpdateMessage('');
    try {
      const result = await api.installApplicationUpdate();
      setUpdateMessage(`${result.message} · v${result.version}`);
    } catch (reason) { setUpdateError(reason instanceof Error ? reason.message : 'เริ่มติดตั้งอัปเดตไม่สำเร็จ'); }
    finally { setUpdateInstallBusy(false); }
  };

  return (
    <section className="page-content">
      <PageTitle eyebrow="ตั้งค่า" title="สถานะเครื่องนี้" subtitle="ตรวจสอบเครื่องมือและพื้นที่จัดเก็บก่อนเริ่มทำวิดีโอ" />
      <div className="settings-grid">
        <div className="content-panel settings-card"><div className="settings-icon blue"><Film size={19} /></div><div><h2>FFmpeg</h2><p>ใช้สำหรับอ่านข้อมูลและประมวลผลวิดีโอ</p></div><StatusValue ok={capabilities?.ffmpeg_available ?? false} /></div>
        <div className="content-panel settings-card"><div className="settings-icon violet"><FileVideo2 size={19} /></div><div><h2>FFprobe</h2><p>อ่านความละเอียด ความยาว และแทร็กเสียง</p></div><StatusValue ok={capabilities?.ffprobe_available ?? false} /></div>
        <div className="content-panel settings-card"><div className="settings-icon mint"><HardDrive size={19} /></div><div><h2>พื้นที่ว่าง</h2><p>ไฟล์วิดีโอและงานของโปรแกรมเก็บในเครื่องนี้</p></div><strong className="storage-value">{capabilities ? formatBytes(capabilities.storage_available_bytes) : 'กำลังตรวจสอบ'}</strong></div>
        <div className="content-panel settings-card"><div className="settings-icon amber"><Settings2 size={19} /></div><div><h2>ข้อมูลโปรแกรม</h2><p>กดก่อนคิดทีหลัง Studio</p></div><strong className="storage-value">{capabilities ? `v${capabilities.version}` : '—'}</strong></div>
      </div>
      <section className="content-panel update-panel">
        <div className="update-panel-heading"><div className="update-panel-title"><div className="settings-icon violet"><Download size={18} /></div><div><span className="panel-kicker">GitHub Releases · Public</span><h2>อัปเดตโปรแกรม</h2><p>เวอร์ชันที่ติดตั้ง: {capabilities ? `v${capabilities.version}` : 'กำลังตรวจสอบ'}</p></div></div><button className="button button-secondary" onClick={() => void checkForUpdates()} disabled={updateBusy || updateInstallBusy}>{updateBusy ? <LoaderCircle className="spin" size={14} /> : <Download size={14} />}{updateBusy ? 'กำลังตรวจสอบ…' : 'ตรวจสอบอัปเดต'}</button></div>
        {updateInfo && <div className={`update-result ${updateInfo.update_available ? 'available' : 'current'}`}>
          <div className="update-result-heading"><div><strong>{updateInfo.update_available ? `พบเวอร์ชันใหม่ v${updateInfo.latest_version}` : updateInfo.latest_version ? `ใช้งานเวอร์ชันล่าสุด v${updateInfo.latest_version} แล้ว` : 'ยังไม่มีเวอร์ชันเผยแพร่'}</strong>{updateInfo.published_at && <small>เผยแพร่ {formatDateTime(updateInfo.published_at)}</small>}</div><a className="text-button update-release-link" href={updateInfo.release_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />ดู Release</a></div>
          <pre className="update-notes">{updateInfo.notes}</pre>
          {updateInfo.update_available && <div className="update-install-row"><span>{updateInfo.installable ? 'ก่อนติดตั้งจะตรวจ SHA-256 และจะไม่แตะข้อมูลใน Data' : 'Release นี้ยังไม่มีแพ็กเกจ Windows ที่พร้อมติดตั้ง'}</span>{updateInfo.installable && <button className="button button-primary small" onClick={() => void installUpdate()} disabled={updateInstallBusy}>{updateInstallBusy ? <LoaderCircle className="spin" size={14} /> : <Download size={14} />}{updateInstallBusy ? 'กำลังเตรียม…' : 'ดาวน์โหลดและติดตั้ง'}</button>}</div>}
        </div>}
        {!updateInfo && !updateBusy && <p className="update-idle-note">กด “ตรวจสอบอัปเดต” เพื่อดูเวอร์ชันและรายการเปลี่ยนแปลงจาก GitHub</p>}
        {updateError && <div className="form-error update-feedback"><span>{updateError}</span><button className="text-button" onClick={() => void checkForUpdates()} disabled={updateBusy}>ลองอีกครั้ง</button></div>}
        {updateMessage && <div className="form-success update-feedback"><CheckCircle2 size={14} />{updateMessage}</div>}
      </section>
      <section className="content-panel ai-settings-panel">
          <div className="panel-heading compact"><div><span className="panel-kicker">ผู้ช่วยเขียนและแปล</span><h2>Gemini API</h2></div><span className={`settings-status ${aiSettings?.key_configured ? 'success' : 'warning'}`}><span className="status-dot" />{aiSettings?.key_configured ? 'บันทึกคีย์แล้ว' : 'ยังไม่เชื่อมต่อ'}</span></div>
        <div className="ai-settings-layout">
          <div>
            <label className="form-label">โมเดลใช้ฟรี
              <select value={aiSettings?.model ?? 'gemini-3.5-flash-lite'} onChange={(event) => void changeModel(event.target.value)}>
                {(aiSettings?.free_models ?? ['gemini-3.1-flash-lite', 'gemini-3.5-flash-lite']).map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
              <small>โปรแกรมเลือกเฉพาะโมเดลที่กำหนดไว้สำหรับ Free Tier และไม่เปลี่ยนไปใช้โมเดลเสียเงินเอง</small>
            </label>
            <form onSubmit={saveKey}>
              <label className="form-label">Gemini API key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={aiSettings?.key_configured ? 'บันทึกแล้ว · ใส่คีย์ใหม่เพื่อเปลี่ยน' : 'วาง API key จาก Google AI Studio'} /></label>
              <div className="ai-key-actions"><button className="button button-primary small" disabled={busy || apiKey.trim().length < 20}><Save size={14} />{busy ? 'กำลังบันทึก…' : 'บันทึกคีย์'}</button>{aiSettings?.key_configured && <><button type="button" className="button button-secondary small" onClick={() => void testKey()} disabled={testing || busy}>{testing ? <LoaderCircle className="spin" size={14} /> : <CheckCircle2 size={14} />}{testing ? 'กำลังทดสอบ…' : 'ทดสอบการเชื่อมต่อ'}</button><button type="button" className="text-button ai-delete-key" onClick={() => void deleteKey()} disabled={busy}>ลบคีย์</button></>}</div>
            </form>
          </div>
          <div className="ai-privacy-note"><div className="settings-icon violet"><HardDrive size={18} /></div><strong>คีย์เก็บในบัญชี Windows นี้</strong><p>ใช้ Windows DPAPI เข้ารหัสคีย์ไว้ในเครื่อง โปรแกรมไม่แสดงคีย์ที่บันทึกแล้ว และส่งคีย์ให้ Google เฉพาะเมื่อคุณกดเรียก AI หรือทดสอบการเชื่อมต่อ</p><p>เมื่อใช้ OCR, แปลซับ หรือเขียนข้อความวิดีโอ โปรแกรมจะส่งภาพตัวอย่างวิดีโอและข้อความที่เกี่ยวข้องไปยัง Google Gemini ส่วนการสร้างแคปชั่นโพสต์ภาพจะส่งเฉพาะข้อมูลสินค้าเป็นข้อความ รูปและลิงก์จะไม่ถูกส่งให้ AI ด้วย Google ระบุว่า Free Tier อาจใช้ข้อมูลเพื่อปรับปรุงผลิตภัณฑ์ และโควตาขึ้นกับบัญชีและโมเดลปัจจุบัน</p></div>
        </div>
        <div className="ai-quota-card">
          <div className="ai-quota-heading">
            <div><strong>โควตา Gemini</strong><p>จาก API key อย่างเดียว โปรแกรมอ่านยอดคงเหลือจริงไม่ได้ ดูลิมิตและการใช้จริงได้ใน AI Studio</p></div>
            <a className="button button-secondary small" href="https://aistudio.google.com/usage?timeRange=last-28-days&tab=rate-limit" target="_blank" rel="noreferrer"><ExternalLink size={14} />ดูโควตาจริง</a>
          </div>
          <div className="ai-quota-counts">
            <div><span>งาน AI ที่เริ่มในรอบโควตาวันนี้</span><strong>{aiUsage?.ai_jobs_started ?? '—'}</strong><small>นับจากงานในเครื่องนี้</small></div>
            <div><span>งานสร้างเสียงพากย์</span><strong>{aiUsage?.voiceover_jobs_started ?? '—'}</strong><small>รวมงานที่สำเร็จและไม่สำเร็จ</small></div>
            <div><span>สร้างข้อความโพสต์ภาพ</span><strong>{aiUsage?.image_post_copy_requests ?? '—'}</strong><small>ข้อมูลสินค้าที่ส่งให้ Gemini วันนี้</small></div>
          </div>
          <div className="ai-quota-footer"><small>ตัวเลขนี้เป็นสถิติในโปรแกรม ไม่ใช่โควตาที่เหลือ และไม่รวมการใช้คีย์จากที่อื่น · นับวันตามเวลาไทย</small><button className="text-button" onClick={() => void refreshAIUsage()} disabled={usageBusy}>{usageBusy ? 'กำลังอัปเดต…' : 'รีเฟรชตัวเลข'}</button></div>
        </div>
        {error && <div className="form-error">{error}</div>}{message && <div className="form-success"><CheckCircle2 size={15} />{message}</div>}
      </section>
      <section className="content-panel facebook-settings-panel">
        <div className="panel-heading compact"><div><span className="panel-kicker">จัดการโพสต์และคอมเมนต์</span><h2>Facebook Pages</h2></div><span className={`settings-status ${facebookSettings?.pages.some((page) => page.is_active && page.token_configured) ? 'success' : 'warning'}`}><span className="status-dot" />{facebookSettings?.pages.some((page) => page.is_active && page.token_configured) ? 'เพจพร้อมเชื่อม' : 'ยังไม่เชื่อมเพจ'}</span></div>
        <div className="facebook-settings-layout">
          <div className="facebook-connect-help"><strong>วิธีเชื่อมเพจ</strong><ol><li>เปิด <a href="https://developers.facebook.com/tools/explorer/" target="_blank" rel="noreferrer">Meta Graph API Explorer</a> และเลือกแอปที่มีสิทธิ์ของคุณ</li><li>สร้าง Page Access Token ที่มีสิทธิ์ <code>pages_show_list</code>, <code>pages_manage_posts</code>, <code>pages_read_engagement</code> และ <code>pages_manage_engagement</code></li><li>ใส่ Page ID กับ token ด้านขวา ระบบจะตรวจชื่อเพจกับ Meta ก่อนบันทึก</li></ol><p>ผู้ใช้ที่สร้าง token ต้องมีงานเพจสร้างเนื้อหา (CREATE_CONTENT) และดูแลคอมเมนต์ (MODERATE) การอนุมัติแอปและสิทธิ์จริงขึ้นกับ Meta</p></div>
          <form onSubmit={connectPage} className="facebook-connect-form">
            <label className="form-label">Facebook Page ID<input inputMode="numeric" pattern="[0-9]+" value={pageId} onChange={(event) => setPageId(event.target.value)} placeholder="เช่น 123456789012345" required /></label>
            <label className="form-label">Page Access Token<input type="password" autoComplete="new-password" value={pageToken} onChange={(event) => setPageToken(event.target.value)} placeholder="วาง token ที่ได้จาก Meta Graph API Explorer" required /></label>
            <button className="button button-primary small" disabled={facebookBusy || pageId.length < 5 || pageToken.length < 20}>{facebookBusy ? <LoaderCircle className="spin" size={14} /> : <Link2 size={14} />}{facebookBusy ? 'กำลังตรวจสอบกับ Meta…' : 'ตรวจและเชื่อมเพจ'}</button>
            <small>ส่ง token ให้ Meta เพื่อตรวจ Page ID จากนั้นเก็บ token แบบเข้ารหัส DPAPI ในเครื่องนี้ โปรแกรมไม่แสดง token ซ้ำหรือเขียนลง SQLite</small>
          </form>
        </div>
        {facebookSettings?.pages.length ? <div className="facebook-page-list">{facebookSettings.pages.map((page) => <div className="facebook-page-row" key={page.id}><div className="facebook-page-avatar">f</div><div className="facebook-page-info"><strong>{page.name}</strong><span>Page ID {page.id} · {page.token_configured ? 'มี token ที่เข้ารหัสไว้' : 'token หายหรืออ่านไม่ได้'}</span></div>{page.is_active ? <span className="settings-status success"><span className="status-dot" />เพจที่เลือก</span> : <button className="button button-secondary small" onClick={() => void selectPage(page.id)} disabled={facebookBusy}>เลือกเพจ</button>}<button className="text-button" onClick={() => void testPage(page.id)} disabled={facebookBusy}>ทดสอบ</button><button className="text-button ai-delete-key" onClick={() => void disconnectPage(page.id)} disabled={facebookBusy}>ลบการเชื่อม</button></div>)}</div> : <div className="editor-empty-row">ยังไม่มีเพจที่เชื่อมไว้</div>}
        {facebookError && <div className="form-error">{facebookError}</div>}{facebookMessage && <div className="form-success"><CheckCircle2 size={15} />{facebookMessage}</div>}
        <div className="facebook-note"><Sparkles size={15} /><p>ตั้งเวลาโพสต์จะส่ง Reel อัตโนมัติขณะโปรแกรมและเครื่องเปิดอยู่ หลัง Facebook ยืนยันว่าโพสต์สำเร็จ ระบบจึงส่งคอมเมนต์ลิงก์สินค้า หากผล API ไม่ชัดเจน โปรแกรมจะหยุดและให้ตรวจเพจก่อน เพื่อป้องกันโพสต์หรือคอมเมนต์ซ้ำ</p></div>
      </section>
      <section className="content-panel maintenance-panel">
        <div className="panel-heading compact"><div><span className="panel-kicker">เก็บโปรเจกต์และไฟล์วิดีโอ</span><h2>สำรองและกู้คืนข้อมูล</h2></div><div className="settings-icon mint"><HardDrive size={18} /></div></div>
        <p>ไฟล์สำรองมีฐานข้อมูลและสื่อในโปรเจกต์ แต่ไม่มี API key หรือ Page token สำรองเป็น ZIP และเก็บไว้นอกโฟลเดอร์โปรแกรม</p>
        <button className="button button-secondary small" onClick={() => void downloadBackup()} disabled={backupBusy}>{backupBusy ? <LoaderCircle className="spin" size={14} /> : <Download size={14} />}{backupBusy ? 'กำลังสร้างไฟล์สำรอง…' : 'ดาวน์โหลดไฟล์สำรอง'}</button>
        <div className="maintenance-restore-help"><strong>กู้คืนไฟล์สำรอง</strong><p>ปิดโปรแกรมก่อน แล้วเปิด PowerShell ที่โฟลเดอร์โปรแกรมและรันคำสั่งนี้ โดยแทนที่ path ด้วยตำแหน่งไฟล์ ZIP:</p><code>.\scripts\restore.ps1 -BackupPath "C:\path\kodkon-studio-backup.zip"</code><p>ระบบตรวจไฟล์ก่อนแทนข้อมูลเดิมและสร้างสำเนาข้อมูลปัจจุบันไว้ย้อนกลับได้ คีย์ AI/เพจต้องบันทึกใหม่เมื่อย้ายไปเครื่องหรือบัญชี Windows อื่น</p></div>
        {backupError && <div className="form-error">{backupError}</div>}{backupMessage && <div className="form-success"><CheckCircle2 size={15} />{backupMessage}</div>}
      </section>
    </section>
  );
}

function StatusValue({ ok }: { ok: boolean }) {
  return <span className={`settings-status ${ok ? 'success' : 'warning'}`}><span className="status-dot" />{ok ? 'พร้อมใช้งาน' : 'ยังไม่พบ'}</span>;
}

export default App;
