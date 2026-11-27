import * as React from "react"
import { createRoot } from "react-dom/client"
import { WorkbenchTooltip } from "./tooltip"
import { FolderButton, SceneTextureCounts, SecondaryPage, type Detail, type FolderActions, type HostAction } from "./details"
import { actionHints } from "./hints"
import { ChevronDown, FolderOpen, Images, PackageOpen, PictureInPicture2, ScanSearch, ScrollText, Settings, SlidersHorizontal, X } from "lucide-react"
import { Button } from "./components/button"
import { Badge } from "./components/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./components/select"

type HostTools = {
  platform?: string; targetPath?: string; materialProfile?: string; presetName?: string
  presetPath?: string; textureFolder?: string; textureSummary?: string; outputFolder?: string
  exportedPackage?: string; exportedDisplayPath?: string; logLines?: string[]
  textureDirectoryLabel?: string; sceneTextureCount?: number; sceneInferredTextureCount?: number | null
  folderActions?: FolderActions; folderNotice?: string; presetRules?: string
}
const tools = [
  {id: "inspect", label: "资产检查", shortcut: "检查", icon: ScanSearch},
  {id: "publish", label: "打包发布", shortcut: "发布", icon: PackageOpen},
  {id: "textures", label: "贴图检查", shortcut: "贴图", icon: Images},
  {id: "preset", label: "项目预设", shortcut: "预设", icon: SlidersHorizontal},
  {id: "log", label: "技术日志", shortcut: "日志", icon: ScrollText},
] as const
type ToolId = typeof tools[number]["id"]

function InfoRow({ label, value, path, action }: { label: string; value?: string; path?: boolean; action?: React.ReactNode }) {
  if (!value && !action) return null
  const name = path && value ? value.replace(/[\\/]+$/, "").split(/[\\/]/).pop() || value : value
  return <div className="info-row"><span>{label}</span>
    <div className="info-value">
      {path && name !== value ? <details><summary data-tooltip={value}>{name}</summary><p>{value}</p></details> : <span>{name || "未设置"}</span>}
      {action}
    </div>
  </div>
}

type Diagnostic = {
  title: string; severity: "blocked" | "warning" | "pass" | "needs_review"
  summary: string; export_impact: string; fix_guidance: string; action_kind: string
  component_label: string; actions: {id: string; label: string}[]
}
type Issue = {
  id: string; label: string; severity: string; objectName: string; countText: string
  detail: string; canLocate: boolean; diagnostic: Diagnostic
}
type Choice = { id: string; label: string; chosen?: string; options: { value: string; label: string }[] }
type WorkbenchState = {
  asset: string; status: string; statusText: string; statusDetail?: string; issues: Issue[]; selectedId: string
  checkNotice?: {tone?: "ok" | "warning" | "error"; text?: string}
  actionButton?: {action?: string; label?: string; busy?: boolean}
  feedback: string; canLocate: boolean; canRescan: boolean; hasSelection: boolean
  canAttemptPublish?: boolean; canPublish: boolean; tools?: HostTools; candidates: Choice[]; floating: boolean
  selectionNote?: {canSelect?: boolean; switchTo?: string; missing?: boolean}
  checked?: boolean; passed?: Diagnostic[]; detail?: Detail
}
type Bridge = {
  dispatch(action: string, payload: string): void
  getState(callback: (json: string | WorkbenchState) => void): void
  stateChanged: { connect(callback: (json: string | WorkbenchState) => void): void }
}
declare global {
  interface Window {
    qt: { webChannelTransport: unknown }
    QWebChannel: new (transport: unknown, ready: (channel: { objects: {workbench: Bridge} }) => void) => void
    assetForgeReady: boolean
  }
}

function Workbench({ bridge }: { bridge: Bridge }) {
  const [state, update] = React.useState<WorkbenchState | null>(null)
  const [message, setMessage] = React.useState("正在连接 Maya…")
  const [menu, setMenu] = React.useState(false)
  const submittedCandidate = React.useRef<string | null>(null)
  const pendingLocation = React.useRef<string | null>(null)
  const pendingPublish = React.useRef(false)
  const activeDiagnostic = React.useRef<HTMLDivElement>(null)
  const exportNotice = React.useRef<HTMLDivElement>(null)
  const inspectButton = React.useRef<HTMLButtonElement>(null)
  const [expanded, setExpanded] = React.useState<Record<ToolId, boolean>>({
    inspect: true, publish: true, textures: false, preset: false, log: false,
  })
  const [active, setActive] = React.useState<ToolId>("inspect")
  const groupHeads = React.useRef<Partial<Record<ToolId, HTMLButtonElement | null>>>({})
  const menuBox = React.useRef<HTMLDivElement>(null)
  const menuButton = React.useRef<HTMLButtonElement>(null)

  React.useEffect(() => {
    function read(json: string | WorkbenchState) {
      try {
        update(typeof json === "string" ? JSON.parse(json) : json)
      } catch {
        setMessage("无法读取 Maya 工作台状态")
      }
    }
    bridge.stateChanged.connect(read)
    bridge.getState(read)
  }, [bridge])
  React.useEffect(() => {
    window.assetForgeReady = Boolean(state)
    const id = submittedCandidate.current
    if (state && id && !state.candidates.some(choice => choice.id === id)) {
      // A successful Maya recheck removes the trigger that would normally regain focus.
      if (document.activeElement === document.body) inspectButton.current?.focus()
      submittedCandidate.current = null
    }
  }, [state])
  React.useLayoutEffect(() => {
    if (!state) return
    if (pendingLocation.current && state.selectedId === pendingLocation.current) {
      pendingLocation.current = null
      activeDiagnostic.current?.scrollIntoView({block: "nearest", inline: "nearest"})
    }
    if (!pendingPublish.current || state.actionButton?.busy) return
    pendingPublish.current = false
    if (state.tools?.exportedPackage) {
      exportNotice.current?.scrollIntoView({block: "nearest", inline: "nearest"})
    } else if (/error|block|reject/.test(state.status)) {
      setExpanded(previous => ({...previous, inspect: true}))
      setActive("inspect")
      requestAnimationFrame(() => groupHeads.current.inspect?.scrollIntoView({block: "start", inline: "nearest"}))
    }
  }, [state])
  React.useEffect(() => {
    if (!menu) return
    const outside = (event: MouseEvent) => {
      if (!menuBox.current?.contains(event.target as Node)) setMenu(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMenu(false); menuButton.current?.focus() }
    }
    document.addEventListener("mousedown", outside)
    document.addEventListener("keydown", escape)
    return () => {
      document.removeEventListener("mousedown", outside)
      document.removeEventListener("keydown", escape)
    }
  }, [menu])
  if (!state) return <p className="connection">{message}</p>
  const send: HostAction = (action, payload = {}) => {
    setMenu(false)
    bridge.dispatch(action, JSON.stringify(payload))
  }
  const statusTone = /error|block|reject|danger/.test(state.status) ? "error"
    : /warning|fix/.test(state.status) ? "warning"
    : /pass|success|ready/.test(state.status) ? "pass"
    : /info|pending/.test(state.status) ? "info" : "idle"
  const mixed = /^(\d+)\s*阻断\s*·\s*(\d+)\s*警告$/.exec(state.statusText)
  const number = !mixed && /^(\d+)\s*(?:项阻断|个警告)$/.exec(state.statusText)
  const host = state.tools || {}
  const button = state.actionButton
  const busy = !!button?.busy
  const selection = state.selectionNote
  const passed = state.passed || []
  const gear = <Button variant="ghost" size="icon" className="preferences-gear" data-action="preferences"
    aria-label="设置" data-tooltip="设置" disabled={busy} onClick={() => send("preferences")}>
    <Settings aria-hidden="true" focusable="false" strokeWidth={1.85} />
  </Button>
  if (state.detail?.page) return <>
    <SecondaryPage key={state.detail.page + ":" + state.detail.section} detail={state.detail}
      send={send} floating={state.floating} busy={busy} host={host} />
    <WorkbenchTooltip />
  </>
  const recheck = <Button variant="outline" className="secondary" data-action="rescan"
    disabled={busy || !state.canRescan} aria-busy={busy && button?.action === "rescan"} data-tooltip={actionHints.rescan}
    onClick={() => send("rescan")}>{button?.action === "rescan" ? button.label : "复检当前网格"}</Button>
  const badge = <Badge variant="outline" className={mixed ? "status status-mixed" : number ? "status status-numbered" : "status"} data-status={statusTone} role="status" data-tooltip={state.statusDetail || state.statusText} aria-label={state.statusDetail || state.statusText}>
          <span className="dot" aria-hidden="true" />
          <span className="status-long">{state.statusText}</span>
          {number && <span className="compact-count" aria-hidden="true">{number[1]}</span>}
          {mixed && <span className="mixed-counts" aria-hidden="true">{mixed[1]}<span className="dot warning-dot" />{mixed[2]}</span>}
        </Badge>
  const goto = (id: ToolId) => {
    setActive(id)
    setExpanded(previous => ({...previous, [id]: true}))
    requestAnimationFrame(() => {
      const head = groupHeads.current[id]
      if (head) {
        head.focus({preventScroll: true})
        head.scrollIntoView({block: "start", inline: "nearest"})
      }
    })
  }
  function selectIssue(issue: Issue) {
    pendingLocation.current = issue.canLocate ? issue.id : null
    send("selectIssue", {id: issue.id})
  }
  function action(id: string, label: string, disabled = false, compact?: string) {
    return <Button variant="outline" className="secondary" data-action={id} disabled={disabled}
      aria-label={label} data-tooltip={actionHints[id] || label} onClick={() => send(id)}>
      {compact ? <><span className="full-label">{label}</span><span className="compact-label">{compact}</span></> : label}
    </Button>
  }
  const panels: Record<ToolId, React.ReactNode> = {
    inspect: <div className="inspection-panel">
          <div className="asset-block">
            <div className="asset-heading">
              <p className="asset-name" data-asset>{state.asset || "未选择资产"}</p>
              {selection?.canSelect && action("selectAsset", "选中对象", busy)}
            </div>
            {(selection?.switchTo || selection?.missing) && <div className="selection-note">
              {selection.missing && <p>已检查的对象已删除。可保留报告以核对问题。</p>}
              {selection.switchTo && <><p>视口已选 <strong>{selection.switchTo}</strong></p>{action("switchAsset", button?.action === "switch" ? button.label || "检查中…" : "切换并检查", busy)}</>}
            </div>}
            <Button variant="outline" className="secondary inspect" ref={inspectButton} data-action="inspect"
              disabled={busy || !state.hasSelection} aria-busy={busy && button?.action === "inspect"} data-tooltip={actionHints.inspect}
              onClick={() => send("inspect")}>{button?.action === "inspect" ? button.label : "检查资产"}</Button>
            {state.checkNotice?.text && <p className="check-notice" role="status" data-check-result={state.checkNotice.tone}>
              {state.checkNotice.text.split(" · ").map((phrase, index, phrases) =>
                <React.Fragment key={index}><span>{phrase}{index < phrases.length - 1 ? " ·" : ""}</span>{index < phrases.length - 1 ? " " : ""}</React.Fragment>)}
            </p>}
          </div>
          {state.issues.map(issue => {
            const diagnostic = issue.diagnostic
            const candidate = state.candidates.find(choice => choice.id === issue.id)
            return <React.Fragment key={issue.id}>
            <button className="issue-row" type="button"
              data-issue-id={issue.id} data-selected={issue.id === state.selectedId}
              data-status={/error|block|reject|danger/.test(issue.severity) ? "error" : /warn/.test(issue.severity) ? "warning" : "info"}
              aria-expanded={issue.id === state.selectedId} disabled={busy}
              data-tooltip={issue.canLocate ? "展开原因并在视口定位受影响的组件。" : "展开问题原因和处理步骤。"}
              onClick={() => selectIssue(issue)}>
              <span className="dot" aria-hidden="true" />
              <span className="issue-copy">
                <span className="issue-name">{issue.label}</span>
                <span className="issue-object">{issue.objectName}</span>
              </span>
              {issue.countText && <span className="count">{issue.countText}</span>}
            </button>
            {issue.id === state.selectedId && <div className="diagnostic" ref={issue.canLocate ? activeDiagnostic : undefined}>
              <p data-diagnostic-summary>{diagnostic.summary}</p>
              <p className="diagnostic-impact">{diagnostic.export_impact}</p>
              <p className="diagnostic-guidance">{diagnostic.fix_guidance}</p>
              {candidate && <Select disabled={busy || !state.canRescan} value={candidate.chosen || ""} onValueChange={value => {
                submittedCandidate.current = candidate.id
                send("chooseCandidate", {id: candidate.id, value})
              }}>
                <SelectTrigger data-candidate-id={candidate.id} className="candidate-trigger" aria-label={candidate.label + " 贴图集"} data-tooltip={actionHints.bindTextureSets}>
                  <SelectValue placeholder="选择贴图集" />
                </SelectTrigger>
                <SelectContent data-candidate-list={candidate.id} className="candidate-options" position="popper"
                  align="start" sideOffset={4} collisionPadding={8} aria-label={candidate.label + " 候选贴图集"}>
                  {candidate.options.map(item =>
                    <SelectItem key={item.value} value={item.value} data-candidate-value={item.value}
                      textValue={item.label} className="candidate-option" data-tooltip={"把 " + item.label + " 绑定到这个材质槽。"}>{item.label}</SelectItem>)}
                </SelectContent>
              </Select>}
              {issue.canLocate && <p className="feedback diagnostic-feedback" data-feedback aria-live="polite">
                {state.feedback || ("受影响组件：" + issue.countText)}
              </p>}
              <div className="diagnostic-actions" data-component-actions={issue.canLocate || undefined}>
                {diagnostic.actions.map(item => <Button key={item.id} variant="outline" className="secondary"
                  data-action={item.id} disabled={busy || !state.canRescan} data-tooltip={item.label + "，处理当前检查项。"}
                  onClick={() => send("diagnostic", {id: issue.id, action: item.id})}>{item.label}</Button>)}
                {issue.canLocate && <>
                  {action("original", diagnostic.component_label || "选原组件", busy || !state.canLocate)}
                  {action("grow", "扩选一圈", busy || !state.canLocate)}
                  {action("vertices", "转为顶点", busy || !state.canLocate)}
                </>}
                {recheck}
              </div>
            </div>}
            </React.Fragment>
          })}
          {state.checked && <details className="passed-checks">
            <summary data-tooltip="查看本次已通过的检查项。"><span className="pass-check" aria-hidden="true">✓</span> 已通过检查项（{passed.length} 项）</summary>
            <ul>{passed.map((item, index) => <li key={index}>{item.title}</li>)}</ul>
          </details>}
        </div>,
    publish: <div className="tool-body">
      <InfoRow label="目标平台" value={host.platform} />
      <InfoRow label="导出根目录" value={host.outputFolder} path
        action={<FolderButton id="openOutputFolder" folder={host.folderActions?.output} send={send} busy={busy} />} />
      <Button className="primary" data-action="publish" disabled={busy || !(state.canAttemptPublish ?? state.canPublish)} aria-busy={busy && button?.action === "publish"} data-tooltip={actionHints.publish}
        onClick={() => { pendingPublish.current = true; send("publish") }}>{button?.action === "publish" ? button.label : "检查并导出 Package"}</Button>
      <div className="actions">
        {action("chooseOutputFolder", "选择输出目录", false, "输出目录")}{action("settings", "发布设置")}
      </div>
      {host.exportedPackage && <div className="export-notice" ref={exportNotice} role="status" data-export-result>
        <span>已导出至 <strong data-tooltip={host.exportedPackage}>{host.exportedDisplayPath || host.exportedPackage}</strong> · 前往 UE「AssetForge 工作台 → 包体导入」选包</span>
        <Button className="secondary open-package" variant="outline" size="icon" data-action="openPackage"
          aria-label="打开本次导出的包体文件夹" data-tooltip={actionHints.openPackage} onClick={() => send("openPackage")}><FolderOpen aria-hidden="true" /></Button>
      </div>}
    </div>,
    textures: <div className="tool-body">
      <InfoRow label="贴图目录" value={host.textureDirectoryLabel || host.textureFolder || "自动跟随场景"} path={!!host.textureFolder}
        action={<FolderButton id="openTextureFolder" folder={host.folderActions?.textures} send={send} busy={busy} />} />
      {host.textureFolder
        ? <InfoRow label="扫描结果" value={host.textureSummary || "未扫描"} />
        : <SceneTextureCounts connected={host.sceneTextureCount} inferred={host.sceneInferredTextureCount} />}
      {host.textureFolder ? <>
        <div className="actions">{action("chooseTextureFolder", "更换贴图目录", busy, "更换目录")}{action("scanTextures", "扫描贴图目录", busy, "扫描贴图")}</div>
        {action("followSceneTextures", "取消覆盖 / 跟随场景贴图", busy)}
      </> : action("chooseTextureFolder", "选择外部贴图目录", busy)}
      {action("textureSettings", "查看贴图详情", busy)}
    </div>,
    preset: <div className="tool-body">
      <InfoRow label="当前预设" value={host.presetPath || host.presetName || "未加载"} path
        action={<FolderButton id="openPresetFolder" folder={host.folderActions?.preset} send={send} busy={busy} />} />
      <InfoRow label="规范与预算" value={host.presetRules} />
      <InfoRow label="UE 路径" value={host.targetPath} />
      <InfoRow label="材质规则" value={host.materialProfile} />
      <div className="actions">{action("loadPreset", "加载预设", busy)}{action("savePreset", "保存预设", busy)}</div>
      {action("rules", "规则与前缀设置", busy)}
    </div>,
    log: <div className="tool-body">
      {host.logLines?.length ? <ul className="log-list">{host.logLines.map((line, index) =>
        <li key={index}>{line}</li>)}</ul> : <p className="feedback">暂无操作记录</p>}
      {action("log", "打开完整日志")}
    </div>,
  }
  return <div className="workspace" data-floating={state.floating}>
    {state.floating && <header className="topbar">
      <div className="title-drag" data-window-drag={state.floating ? "" : undefined}
        data-tooltip={state.floating ? "拖动工作台" : undefined}
        onMouseDown={event => {
          if (state.floating && event.button === 0) {
            event.preventDefault()
            send("startDrag")
          }
        }}>
        <h1>
          <img src="../brand/af_shelf.png" width="28" height="28" alt="" />
          <span className="brand-text">AssetForge <span className="version">v0.2</span></span>
        </h1>
      </div>
      <div className="title-status">{badge}{gear}</div>
      <div className="menu-box" ref={menuBox}>
        <Button variant="ghost" size="icon" className="more" data-action="menu"
          aria-label="更多操作" data-tooltip="更多操作" aria-expanded={menu} aria-controls="more-actions"
          ref={menuButton} onClick={() => setMenu(!menu)}>⋯</Button>
        {menu && <div id="more-actions" className="menu-panel">
          {[["dock", "停靠到 Maya"]].map(([action, label]) =>
            <Button key={action} variant="ghost" data-action={action} data-tooltip="将工作台停靠在 Maya 主窗口内。" onClick={() => send(action)}>{label}</Button>)}
        </div>}
      </div>
      {state.floating && <Button variant="ghost" size="icon" className="close-window" data-action="close"
        aria-label="关闭工作台" data-tooltip="关闭工作台" onClick={() => send("close")}><X aria-hidden="true" focusable="false" strokeWidth={1.8} /></Button>}
    </header>}
    <nav className="tool-rail" aria-label="工具组快捷定位">
      <div className="tool-shortcuts">
        {tools.map(({id, shortcut, icon: Icon}) => <Button key={id} variant="ghost" size="icon"
          className="tool-shortcut" data-tool-toggle={id} aria-expanded={expanded[id]}
          aria-controls={"tool-" + id} aria-current={active === id ? "true" : undefined}
          aria-label={shortcut} data-tooltip={"定位并展开" + tools.find(tool => tool.id === id)?.label}
          onClick={() => goto(id)}><Icon size={20} strokeWidth={1.8} absoluteStrokeWidth aria-hidden="true" /></Button>)}
      </div>
      {state.floating && <div className="rail-status">{badge}{gear}</div>}
      {!state.floating && <Button variant="ghost" size="icon" className="undock" data-action="dock"
        data-tooltip="悬浮工作台" aria-label="悬浮工作台" onClick={() => send("dock")}><PictureInPicture2 aria-hidden="true" /></Button>}
    </nav>
    <main data-workbench-scroll tabIndex={-1}>
      {host.folderNotice && <p className="folder-notice" role="status">{host.folderNotice}</p>}
      {tools.map(({id, label, icon: Icon}) => <section key={id} className="tool-group" data-tool-group={id}
        onFocusCapture={() => setActive(id)} onClickCapture={() => setActive(id)}
        onPointerDownCapture={() => setActive(id)}>
        <div className="group-strip">
          <h2><button type="button" className="group-toggle" data-group-toggle={id}
            id={"head-" + id} data-tooltip={"展开或收起" + label} aria-expanded={expanded[id]} aria-controls={"tool-" + id}
            ref={node => {groupHeads.current[id] = node}}
            onClick={() => { setActive(id); setExpanded(previous => ({...previous, [id]: !previous[id]})) }}>
            <Icon className="group-icon" aria-hidden="true" /><span>{label}</span>
            <ChevronDown className="disclosure" aria-hidden="true" />
          </button></h2>
          {id === "inspect" && <Button variant="ghost" size="icon" className="rules-shortcut"
            data-action="rules" onClick={() => send("rules")} disabled={busy} aria-label="规则与前缀设置" data-tooltip={actionHints.rules}>
            规则
          </Button>}
          {!state.floating && id === "inspect" && <div className="dock-status">{badge}{gear}</div>}
        </div>
        <div id={"tool-" + id} data-tool-content={id} role="region" aria-labelledby={"head-" + id} hidden={!expanded[id]}>
          {panels[id]}
        </div>
      </section>)}
    </main>
    <WorkbenchTooltip />
  </div>
}

const container = document.getElementById("workbench")!
const root = createRoot(container)
if (window.qt?.webChannelTransport && window.QWebChannel) {
  new window.QWebChannel(window.qt.webChannelTransport, channel => {
    root.render(<Workbench bridge={channel.objects.workbench} />)
  })
} else {
  root.render(<p className="connection">请在 Maya 中打开工作台</p>)
}
