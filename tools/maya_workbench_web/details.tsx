import * as React from "react"
import { ArrowLeft, Check, ChevronDown, FolderOpen, X } from "lucide-react"
import { Button } from "./components/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/select"
import { actionHints, fieldHints } from "./hints"

type Field = { value: string | number; options?: string[] }
type CacheDirectory = {
  id: "logs" | "reports"; path: string; exists: boolean; status: "ready" | "missing" | "unavailable"
  bytes: number; eligible_bytes: number
}
type Cache = {
  bytes: number; eligible_bytes: number; eligible_files: number
  removed_bytes: number; removed_files: number; failed_files: number; unavailable?: boolean
  directories?: CacheDirectory[]; open_error?: boolean
}
export type Detail = {
  page: "rules" | "publish" | "log" | "preferences"; section?: string
  toast?: boolean; hostVersion?: string; licenseName?: string; cache?: Cache
  fields?: Record<string, Field>; text?: Record<string, string>
}
export type HostAction = (id: string, payload?: Record<string, string | boolean>) => void

const titles = { rules: "规则与前缀设置", publish: "发布设置", log: "技术日志", preferences: "设置" }
const options: Record<string, string> = {
  pc: "PC", high_end_mobile: "高端移动设备", mobile: "移动设备",
  project_default: "跟随项目默认", overwrite: "覆盖现有包体",
}
function Disclosure({ label, children, open = false }: { label: string; children: React.ReactNode; open?: boolean }) {
  const [expanded, setExpanded] = React.useState(open)
  React.useEffect(() => setExpanded(open), [open])
  return <details className="detail-section" open={expanded} onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary data-tooltip={"展开或收起" + label}
      onPointerDown={event => { event.currentTarget.dataset.pointerFocus = "true" }}
      onKeyDown={event => { delete event.currentTarget.dataset.pointerFocus }}
      onBlur={event => { delete event.currentTarget.dataset.pointerFocus }}>
      <span>{label}</span><ChevronDown aria-hidden="true" />
    </summary>
    <div className="detail-body">{children}</div>
  </details>
}
type DirectoryAction = { available?: boolean; hint?: string; path?: string }
export type FolderActions = Partial<Record<"output" | "textures" | "preset", DirectoryAction>>
export function FolderButton({ id, folder, send, busy = false }: {
  id: "openOutputFolder" | "openTextureFolder" | "openPresetFolder"
  folder?: DirectoryAction; send: HostAction; busy?: boolean
}) {
  const hint = folder?.hint || actionHints[id]
  const help = folder?.available || !folder?.path ? hint : "文件夹尚未建立或无法访问。 " + hint
  return <span className="folder-action" data-tooltip={help}>
    <Button type="button" className="secondary folder-button" variant="outline" size="icon"
      aria-label={hint} data-action={id} disabled={busy || !folder?.available} onClick={() => send(id)}>
      <FolderOpen aria-hidden="true" />
    </Button>
  </span>
}

function SettingField({ field, id, label, send, choose, folder, busy }: {
  field?: Field; id: string; label: string; send: HostAction
  choose?: "chooseOutputFolder" | "chooseTextureFolder"; folder?: DirectoryAction; busy: boolean
}) {
  const inputId = "setting-" + id
  const group = id === "static_mesh_lod_group" || id === "texture_group"
  const value = String(field?.value ?? "")
  const displayValue = group && value === "project_default" ? options.project_default : value
  const numeric = typeof field?.value === "number"
  const [draft, setDraft] = React.useState(displayValue)
  React.useEffect(() => setDraft(displayValue), [displayValue])
  if (!field) return null
  return <div className="detail-field">
    <label id={inputId + "-label"} htmlFor={inputId}>{label}</label>
    <div className="detail-input">
      {field.options ? <Select value={value} disabled={busy} onValueChange={value => send("editDetailField", {name: id, value})}>
        <SelectTrigger id={inputId} className="candidate-trigger detail-select" data-tooltip={fieldHints[id]} aria-labelledby={inputId + "-label"}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="candidate-options" position="popper" align="start" sideOffset={4} collisionPadding={8}>
          {field.options.map(option => <SelectItem key={option} value={option}
            className="candidate-option" data-tooltip={fieldHints[id]}>{options[option] || option}</SelectItem>)}
        </SelectContent>
      </Select> : <input id={inputId} value={draft} spellCheck={false} data-tooltip={fieldHints[id]}
        placeholder={id === "texture_set_token" ? "留空自动匹配，混放时填名称片段" : undefined}
        type={numeric ? "number" : "text"} min={0} max={2147483647}
        disabled={busy} required={numeric} onChange={event => setDraft(event.target.value)}
        onBlur={event => {
          if (!event.currentTarget.validity.valid) setDraft(displayValue)
          else if (draft !== displayValue) send("editDetailField", {name: id, value: draft})
        }}
        onKeyDown={event => {
          if (event.key === "Enter") event.currentTarget.blur()
        }} />}
      {choose && <>
        <Button className="secondary" variant="outline" data-action={choose} disabled={busy}
          data-tooltip={actionHints[choose]} onClick={() => send(choose)} aria-label={"选择" + label}>选择</Button>
        <FolderButton id={choose === "chooseTextureFolder" ? "openTextureFolder" : "openOutputFolder"}
          folder={folder} send={send} busy={busy} />
      </>}
    </div>
  </div>
}

const displaySize = (bytes: number) => bytes >= 1024 ** 3 ? (bytes / (1024 ** 3)).toFixed(1) + " GB"
  : bytes >= 1024 ** 2 ? (bytes / (1024 ** 2)).toFixed(1) + " MB"
    : bytes >= 1024 ? (bytes / 1024).toFixed(1) + " KB" : bytes + " B"

function SettingsCard({ label, children }: { label: string; children: React.ReactNode }) {
  return <section className="detail-section settings-card" aria-label={label}>
    <h2>{label}</h2>
    <div className="detail-body">{children}</div>
  </section>
}

function Preferences({ detail, send }: { detail: Detail; send: HostAction }) {
  const [confirming, confirm] = React.useState(false)
  const cache = detail.cache
  const cancel = React.useRef<HTMLButtonElement>(null)
  React.useEffect(() => { if (confirming) cancel.current?.focus() }, [confirming])
  return <>
    <SettingsCard label="通用偏好">
      <label className="detail-check" data-tooltip={actionHints.toggleToast}>
        <input type="checkbox" data-action="toggleToast" checked={detail.toast ?? true}
          onChange={event => send("toggleToast", {enabled: event.target.checked})} />
        <span className="detail-checkbox-mark" aria-hidden="true"><Check /></span>
        <span>操作引导提示（Toast）</span>
      </label>
    </SettingsCard>
    <SettingsCard label="清理缓存">
      <p className="detail-copy">当前占用 <strong>{cache && !cache.unavailable ? displaySize(cache.bytes) : "暂不可读"}</strong></p>
      {cache && !cache.unavailable && <p className="detail-copy">可清理 {displaySize(cache.eligible_bytes)} · {cache.eligible_files} 个文件</p>}
      {!!cache?.directories?.length && <ul className="cache-locations">
        {cache.directories.map(directory => {
          const label = directory.id === "logs" ? "操作日志" : "工作台报告缓存"
          const status = directory.status === "unavailable" ? "暂不可访问" : "尚未生成"
          return <li key={directory.id}>
            <div className="cache-location-heading">
              <strong>{label}</strong>
              <Button variant="outline" className="secondary" data-action={"openCacheDirectory-" + directory.id}
                aria-label={"打开" + label + "文件夹"} data-tooltip={"在文件资源管理器中打开" + label + "文件夹。"}
                disabled={!directory.exists}
                onClick={() => send("openCacheDirectory", {id: directory.id})}>打开文件夹</Button>
            </div>
            <p className="cache-location-path">{directory.path}</p>
            <p className="detail-copy">{directory.exists
              ? "占用 " + displaySize(directory.bytes) + " · 可清理 " + displaySize(directory.eligible_bytes)
              : status}</p>
          </li>
        })}
      </ul>}
      {cache?.open_error && <p className="detail-copy" role="status">这个文件夹暂时无法打开，请核对上方路径。</p>}
      <Button variant="outline" className="secondary" data-action="clearCache"
        data-tooltip={actionHints.clearCache} disabled={!cache?.eligible_files || confirming} onClick={() => confirm(true)}>清理历史缓存与日志</Button>
      {confirming && <div className="detail-confirm" role="group" aria-label="确认清理">
        <p>确定清理 {displaySize(cache?.eligible_bytes ?? 0)} 的历史缓存与日志？</p>
        <div className="actions">
          <Button className="secondary" variant="outline" ref={cancel} data-action="cancelClearCache" data-tooltip={actionHints.cancelClearCache} onClick={() => confirm(false)}>取消</Button>
          <Button className="primary" data-action="confirmClearCache" data-tooltip={actionHints.confirmClearCache} onClick={() => { confirm(false); send("clearCache", {confirmed: true}) }}>确认清理</Button>
        </div>
      </div>}
      {cache && (cache.removed_files > 0 || cache.failed_files > 0) &&
        <p className="detail-copy" role="status">{cache.unavailable ? "缓存目录暂不可访问。"
          : "已清理 " + cache.removed_files + " 个文件，释放 " + displaySize(cache.removed_bytes) +
            (cache.failed_files ? "。未能清理 " + cache.failed_files + " 个文件。" : "。")}</p>}
    </SettingsCard>
    <SettingsCard label="关于与更新">
      <p className="detail-copy"><strong>DCC AssetForge</strong> · v0.2.0</p>
      <p className="detail-copy">宿主版本 · Maya {detail.hostVersion || "未知"}</p>
      <p className="detail-copy">开发者：卓雨 (Elviszhuoyu)</p>
      <p className="detail-copy">© 2026 Elviszhuoyu · {detail.licenseName || "许可文件暂不可读"}</p>
      <Button className="secondary" variant="outline" data-action="openReleases" data-tooltip={actionHints.openReleases}
        onClick={() => send("openReleases")}>前往 GitHub Releases 检查更新</Button>
      <div className="actions">
        <Button className="secondary" variant="outline" data-action="openProjectHome" data-tooltip={actionHints.openProjectHome}
          onClick={() => send("openProjectHome")}>项目主页</Button>
        <Button className="secondary" variant="outline" data-action="openAuthorHome" data-tooltip={actionHints.openAuthorHome}
          onClick={() => send("openAuthorHome")}>作者主页</Button>
      </div>
    </SettingsCard>
  </>
}

export function SceneTextureCounts({ connected = 0, inferred }: { connected?: number; inferred?: number | null }) {
  return <p className="detail-copy" data-scene-texture-counts>
    场景节点已连 {connected} 张<br />
    {inferred == null ? "同目录自动补齐 · 待检查" : "同目录自动补齐 " + inferred + " 张"}
  </p>
}

type Props = {
  detail: Detail; send: HostAction; floating: boolean; busy: boolean
  host: {
    textureFolder?: string; sceneTextureCount?: number; sceneInferredTextureCount?: number | null
    folderActions?: FolderActions; folderNotice?: string; presetPath?: string; presetRules?: string
  }
}
export function SecondaryPage({ detail, send, floating, host, busy }: Props) {
  const scroll = React.useRef<HTMLElement>(null)
  const texture = React.useRef<HTMLDivElement>(null)
  React.useLayoutEffect(() => {
    if (scroll.current) scroll.current.scrollTop = 0
    requestAnimationFrame(() => {
      if (detail.section === "textures") texture.current?.scrollIntoView({block: "start"})
      scroll.current?.focus({preventScroll: true})
    })
  }, [detail.page, detail.section])
  const field = (id: string, label: string, choose?: "chooseOutputFolder" | "chooseTextureFolder") =>
    <SettingField field={detail.fields?.[id]} {...{ id, label, send, choose, busy }}
      folder={host.folderActions?.[choose === "chooseTextureFolder" ? "textures" : "output"]} />
  const action = (id: string, label: string, disabled = busy) =>
    <Button className="secondary" variant="outline" data-action={id} data-tooltip={actionHints[id] || label}
      disabled={disabled} onClick={() => send(id)}>{label}</Button>
  const copy = (key: string) => detail.text?.[key] && <p className="detail-copy">{detail.text[key]}</p>
  const read = (key: string) => detail.text?.[key] && <pre className="detail-report">{detail.text[key]}</pre>
  return <div className="workspace detail-workspace" data-floating={floating} data-detail-page={detail.page}>
    <header className="detail-topbar">
      <Button className="detail-navigation" variant="ghost" size="icon" data-action="backDetail" aria-label="返回工作台"
        data-tooltip="返回工作台" onClick={() => send("backDetail")}><ArrowLeft aria-hidden="true" /></Button>
      <h1 onMouseDown={event => { if (floating && event.button === 0) send("startDrag") }}>{titles[detail.page]}</h1>
      {floating && <Button className="detail-navigation" variant="ghost" size="icon" data-action="close"
        data-tooltip="关闭工作台" aria-label="关闭工作台" onClick={() => send("close")}><X aria-hidden="true" /></Button>}
    </header>
    <main className="detail-main" ref={scroll} tabIndex={-1} aria-label={titles[detail.page]}>
      {host.folderNotice && <p className="folder-notice" role="status">{host.folderNotice}</p>}
      {detail.page === "preferences" && <Preferences detail={detail} send={send} />}
      {(detail.page === "rules" || detail.page === "publish") && <>
        <Disclosure label="规范与预算" open={detail.section !== "textures"}>
        {field("name_prefix", "模型前缀")}
        {field("texture_prefix", "贴图前缀")}
        {field("triangle_budget", "三角面预算")}
        {field("material_slot_budget", "材质槽预算")}
        {field("platform", "目标平台")}
        {field("material_profile", "材质匹配规则")}
        {field("normal_format", "源法线坐标格式")}
        <p className="detail-copy">按源贴图选择 DirectX 或 OpenGL。UE 会使用对应的绿色通道方向。</p>
        </Disclosure>
        <Disclosure label="发布目标" open={detail.page === "publish"}>
          {field("target_path", "UE 目标路径")}{field("target_engine_version", "目标 UE 版本")}
          {field("output_dir", "导出根目录", "chooseOutputFolder")}
        </Disclosure>
        <div ref={texture}><Disclosure label="贴图匹配" open={detail.section === "textures"}>
          {!host.textureFolder && <SceneTextureCounts connected={host.sceneTextureCount} inferred={host.sceneInferredTextureCount} />}
          {field("texture_folder", "贴图目录", "chooseTextureFolder")}
          {host.textureFolder && <>
            {action("followSceneTextures", "取消覆盖 / 跟随场景贴图")}
            {field("texture_set_token", "贴图名筛选词（可选）")}
            <div className="detail-actions">
              {action("scanTextures", "扫描贴图目录")}
              {action("bindTextureSets", "手动绑定材质槽贴图")}{action("repairTexturePrefix", "修复贴图前缀")}
            </div>
          </>}
          <Disclosure label="贴图详情" open={Boolean(host.textureFolder)}>{read("texture_details")}</Disclosure>
        </Disclosure></div>
        <Disclosure label="资产设置">
          {copy("asset_hint")}{field("asset_name_override", "包体/文件夹名")}{field("package_version_mode", "包体迭代模式")}
          <div className="detail-actions">{action("repairAssetPrefix", "修复资产名前缀")}{action("applyTransform", "应用 Transform")}</div>
          <Disclosure label="资产详情">{read("asset_details")}</Disclosure>
        </Disclosure>
        <Disclosure label="项目预设">
          <p className="detail-copy">修改本页规范、预算与发布目标后，点「保存预设」可导出为标准 UTF-8 JSON（*.assetforge.json），支持用 VS Code / 记事本直接编辑并与团队共享。</p>
          <div className="preset-location">
            <span className="detail-copy">{host.presetPath || "尚未加载或保存预设"}</span>
            <FolderButton id="openPresetFolder" folder={host.folderActions?.preset} send={send} busy={busy} />
          </div>
          {host.presetRules && <p className="detail-copy">{host.presetRules}</p>}
          <Disclosure label="预设详情">{read("preset_summary")}</Disclosure>
          <div className="detail-actions">{action("loadPreset", "加载预设")}{action("savePreset", "保存预设")}{action("applyPreset", "应用当前预设")}</div>
        </Disclosure>
        <Disclosure label="基础导入">
          <p className="detail-copy">Maya 生成 Package 和导入建议。UE 门禁会在导入前检查包体。</p>
        </Disclosure>
        <Disclosure label="网格构建">
          {field("nanite_policy", "Nanite 策略建议")}{field("static_mesh_lod_group", "Mesh LODGroup 建议")}
          {field("static_mesh_lod_import_policy", "Mesh LOD 导入策略建议")}
        </Disclosure>
        <Disclosure label="材质贴图">
          {field("virtual_texture_policy", "Virtual Texture 策略建议")}
          {field("texture_streaming_policy", "Texture Streaming 策略建议")}{field("texture_group", "Texture Group 建议")}
        </Disclosure>
      </>}
      {detail.page === "log" && <>
        <Disclosure label="Maya MCP">
          {copy("mcp_status")}<div className="detail-actions">{action("startMcp", "启动")}{action("showMcp", "状态")}</div>
        </Disclosure>
        <Disclosure label="检查详情">
          {copy("preflight_hint")}{read("preflight")}
        </Disclosure>
        <Disclosure label="Maya 操作日志" open>
          {read("log")}
        </Disclosure>
        {detail.text?.results && <Disclosure label="操作结果">{read("results")}</Disclosure>}
        <Disclosure label="调试操作" open>
          <div className="detail-actions">{action("scanOnly", "只扫描")}{action("exportDebug", "导出调试信息")}
            {action("openLastDirectory", "打开导出目录")}{action("analyze", "AI 分析")}</div>
        </Disclosure>
      </>}
    </main>
  </div>
}
