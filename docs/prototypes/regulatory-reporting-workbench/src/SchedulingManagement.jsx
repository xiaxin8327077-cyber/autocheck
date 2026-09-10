import { useMemo, useState } from 'react';

const CHANGED_FILES = [
  { path: '/dm/zxgxdm.kjb', type: '修改', owner: '张三', time: '2026-09-09 10:18:42', summary: '调整报表生成主流程，新增失败分支' },
  { path: '/dm/zg06_companyinfo.ktr', type: '修改', owner: '张三', time: '2026-09-09 10:11:06', summary: '更新公司信息抽取 SQL 和字段选择' },
  { path: '/dm/common/init_report_date.ktr', type: '新增', owner: '李四', time: '2026-09-09 09:46:19', summary: '统一初始化报送期参数' },
];

const VERSION_ROWS = [
  { revision: 'r1842', message: '优化人行逐笔报表生成流程', files: 3, author: '张三', time: '2026-09-09 10:24:16', status: '待发布' },
  { revision: 'r1841', message: '修复公司信息转换空值处理', files: 1, author: '李四', time: '2026-09-08 17:42:09', status: '待发布' },
  { revision: 'r1840', message: '增加全要素月末日期参数', files: 2, author: '王五', time: '2026-09-08 15:19:38', status: '待发布' },
  { revision: 'r1839', message: '1104 八月报表流程正式版本', files: 8, author: '张三', time: '2026-09-08 10:06:32', status: '生产版本' },
  { revision: 'r1838', message: '调整 1104 报文整理步骤', files: 2, author: '赵六', time: '2026-09-07 18:31:20', status: '历史版本' },
];

const SCHEDULE_ROWS = [
  ['1104月报生成', '1104报送', 'KJB', '/dm/zxgxdm.kjb', '每月 2 日 02:00', '生产 r1839', '启用', '2026-10-02 02:00', '成功'],
  ['人行逐笔数据准备', '资管产品模板逐笔', 'KTR', '/pbc/detail_prepare.ktr', '每月末 23:30', '生产 r1839', '启用', '2026-09-30 23:30', '成功'],
  ['EAST5数据归集', 'EAST5.0报送', 'Spider', 'EAST5_数据归集流程', '工作日 21:00', '流程 v27', '启用', '2026-09-09 21:00', '失败'],
  ['全要素季度生成', '21/23版全要素报送', 'KJB', '/all-factor/quarter.kjb', '季末次月 3 日 01:30', '生产 r1839', '停用', '-', '成功'],
];

function StateBadge({ value }) {
  const kind = ['生产版本', '成功', '启用', '已发布'].includes(value) ? 'success'
    : ['待发布', '运行中'].includes(value) ? 'warning'
      : ['失败'].includes(value) ? 'danger' : 'muted';
  return <span className={`schedule-badge schedule-badge-${kind}`}><i />{value}</span>;
}

function CompareModal({ file = CHANGED_FILES[0], onClose }) {
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal diff-modal">
    <div className="modal-head"><div><h3>查看修改 · {file.path.split('/').pop()}</h3><p>对比开发工作区当前文件与 SVN 基准版本 r1842</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="change-summary"><span>修改人</span><strong>{file.owner}</strong><span>修改时间</span><strong>{file.time}</strong><span>变更说明</span><strong>{file.summary}</strong></div>
    <div className="diff-columns">
      <section><header><b>修改前</b><span>SVN r1842</span></header><dl><div><dt>步骤名称</dt><dd>获取公司信息</dd></div><div><dt>数据库连接</dt><dd>ass_man_reg_24</dd></div><div className="diff-line old"><dt>查询条件</dt><dd>report_date = ${'{caldate_t1}'}</dd></div><div><dt>失败处理</dt><dd>停止后续步骤</dd></div><div><dt>输出字段</dt><dd>company_id, company_name, id_no</dd></div></dl></section>
      <section><header><b>修改后</b><span>开发工作区</span></header><dl><div><dt>步骤名称</dt><dd>获取公司信息</dd></div><div><dt>数据库连接</dt><dd>ass_man_reg_24</dd></div><div className="diff-line added"><dt>查询条件</dt><dd>report_date = ${'{report_period}'}</dd></div><div className="diff-line added"><dt>失败处理</dt><dd>记录错误并继续</dd></div><div><dt>输出字段</dt><dd>company_id, company_name, id_no</dd></div></dl></section>
    </div>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>返回</button></div>
  </div></div>;
}

function CommitModal({ onClose, onConfirm }) {
  const [message, setMessage] = useState('优化人行逐笔报表生成流程');
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal commit-modal">
    <div className="modal-head"><div><h3>提交到 SVN</h3><p>把开发工作区的 3 个变更保存为一个新版本</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="modal-body"><label className="stack-field"><span>提交说明</span><textarea value={message} onChange={event => setMessage(event.target.value)} /></label><div className="commit-files">{CHANGED_FILES.map(file => <div key={file.path}><StateBadge value={file.type === '新增' ? '待发布' : '修改'} /><span>{file.path}</span></div>)}</div><p className="inline-notice">提交只生成 SVN 版本，不会自动更新生产目录。</p></div>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className="primary" disabled={!message.trim()} onClick={() => onConfirm(message)}>确认提交</button></div>
  </div></div>;
}

function PublishModal({ revision, restore = false, onClose, onConfirm }) {
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal publish-modal">
    <div className="modal-head"><div><h3>{restore ? '恢复历史版本' : '发布到生产'}</h3><p>{restore ? '把历史 SVN 版本重新发布到生产目录' : '将已提交的 SVN 版本发布到生产目录'}</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="release-route"><div><span>版本来源</span><strong>SVN {revision}</strong><small>已提交、内容不可变</small></div><b>→</b><div><span>发布目标</span><strong>/home/kettle/prod</strong><small>生产目录，只允许平台发布</small></div></div>
    <div className="release-checks"><label><input type="checkbox" defaultChecked />发布前自动备份当前生产版本 r1839</label><label><input type="checkbox" defaultChecked />校验 KJB/KTR 引用文件完整性</label><label><input type="checkbox" defaultChecked />发布后刷新 Kettle 生产目录状态</label></div>
    <p className="danger-notice">发布不会终止正在执行的 Kettle 任务；新任务从发布成功后开始使用新版本。</p>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className={restore ? 'warning-button' : 'primary'} onClick={onConfirm}>{restore ? `确认恢复 ${revision}` : `确认发布 ${revision}`}</button></div>
  </div></div>;
}

function ScheduleModal({ onClose, onConfirm }) {
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal schedule-modal">
    <div className="modal-head"><div><h3>新增定时任务</h3><p>定时任务只能执行生产目录或已登记的 Spider 流程</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="modal-form-grid"><label><span>任务名称</span><input defaultValue="1104月报生成" /></label><label><span>报送类型</span><select defaultValue="1104"><option value="1104">1104报送</option><option>资管产品模板逐笔</option></select></label><label><span>流程类型</span><select defaultValue="KJB"><option>KJB</option><option>KTR</option><option>Spider</option></select></label><label><span>执行环境</span><input value="生产环境" readOnly /></label><label className="span-two"><span>生产流程路径</span><input defaultValue="/dm/zxgxdm.kjb" /></label><label><span>触发方式</span><select defaultValue="month"><option value="month">每月</option><option>每周</option><option>自定义 Cron</option></select></label><label><span>执行时间</span><input defaultValue="每月 2 日 02:00" /></label><label className="span-two"><span>参数</span><input defaultValue="inputdate=${report_period}" /></label></div>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>取消</button><button className="primary" onClick={onConfirm}>保存任务</button></div>
  </div></div>;
}

const FILE_HISTORY_MOCK = {
  '/dm/zxgxdm.kjb': [
    { revision: 'r1842', message: '优化人行逐笔报表生成流程', author: '张三', time: '2026-09-09 10:24:16' },
    { revision: 'r1841', message: '修复公司信息转换空值处理', author: '李四', time: '2026-09-08 17:42:09' },
    { revision: 'r1840', message: '增加全要素月末日期参数', author: '王五', time: '2026-09-08 15:19:38' },
    { revision: 'r1839', message: '1104 八月报表流程正式版本', author: '张三', time: '2026-09-08 10:06:32' },
    { revision: 'r1838', message: '调整 1104 报文整理步骤', author: '赵六', time: '2026-09-07 18:31:20' },
  ],
  '/dm/zg06_companyinfo.ktr': [
    { revision: 'r1841', message: '修复公司信息转换空值处理', author: '李四', time: '2026-09-08 17:42:09' },
    { revision: 'r1840', message: '增加全要素月末日期参数', author: '王五', time: '2026-09-08 15:19:38' },
    { revision: 'r1839', message: '1104 八月报表流程正式版本', author: '张三', time: '2026-09-08 10:06:32' },
  ],
  '/dm/common/init_report_date.ktr': [
    { revision: 'r1842', message: '优化人行逐笔报表生成流程', author: '张三', time: '2026-09-09 10:24:16' },
    { revision: 'r1841', message: '修复公司信息转换空值处理', author: '李四', time: '2026-09-08 17:42:09' },
    { revision: 'r1839', message: '1104 八月报表流程正式版本', author: '张三', time: '2026-09-08 10:06:32' },
  ],
};

function HistoryModal({ filePath, onClose, onRestore }) {
  const versions = FILE_HISTORY_MOCK[filePath] || [];
  return <div className="modal-mask" role="dialog" aria-modal="true"><div className="modal history-modal">
    <div className="modal-head"><div><h3>历史版本 · {filePath.split('/').pop()}</h3><p>{filePath}</p></div><button className="text-btn" onClick={onClose}>关闭</button></div>
    <div className="history-list">
      {versions.length === 0 && <p className="empty-tip">暂无历史版本记录</p>}
      {versions.map(v => <div key={v.revision} className="history-item">
        <div className="history-main"><span className="revision-tag">{v.revision}</span><span className="history-msg">{v.message}</span></div>
        <div className="history-meta"><span>{v.author}</span><span>{v.time}</span></div>
        <button className="restore-btn" onClick={() => onRestore(v.revision)}>恢复到此版本</button>
      </div>)}
    </div>
    <div className="modal-actions"><button className="secondary" onClick={onClose}>关闭</button></div>
  </div></div>;
}

function KettleWorkspace({ notify, onGoVersions }) {
  const [frameKey, setFrameKey] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState(() => new Set());
  const [historyFile, setHistoryFile] = useState(null);

  const devFiles = [
    { path: '/dm/zxgxdm.kjb', modified: true, type: '修改' },
    { path: '/dm/zg06_companyinfo.ktr', modified: true, type: '修改' },
    { path: '/dm/common/init_report_date.ktr', modified: true, type: '新增' },
  ];

  const toggleFile = (path) => {
    const next = new Set(selectedFiles);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    setSelectedFiles(next);
  };

  const allSelected = selectedFiles.size === devFiles.length;
  const someSelected = selectedFiles.size > 0 && !allSelected;
  const toggleAll = () => {
    if (allSelected) setSelectedFiles(new Set());
    else setSelectedFiles(new Set(devFiles.map(f => f.path)));
  };

  const handlePublish = () => {
    const paths = Array.from(selectedFiles);
    if (paths.length === 0) { notify('请先勾选需要发布的文件'); return; }
    setShowFiles(false);
    notify(`已一键发布 ${paths.length} 个文件到生产目录：${paths.join('、')}`);
    onGoVersions();
  };

  return <>
    <div className="kettle-env-bar"><span className="live-dot" /><div><strong>开发目录</strong><code>/home/kettle/dev</code></div><i /><div><strong>生产目录 · 只读</strong><code>/home/kettle/prod</code></div><i /><div><strong>嵌入缩放</strong><code>90%</code></div></div>
    <section className={`webspoon-shell kettle-canvas ${expanded ? 'expanded' : ''}`}>
      <div className="kettle-floating-tools">
        <div className="floating-actions"><button onClick={() => setFrameKey(value => value + 1)}>刷新</button><button className={showFiles ? 'active' : ''} onClick={() => setShowFiles(value => !value)}>版本变更 <b className="count-pill">3</b></button><button className="floating-primary" onClick={() => setExpanded(value => !value)}>{expanded ? '退出全屏' : '全屏'}</button></div>
        {showFiles && <div className="floating-files-panel">
          <div className="files-panel-head"><span>{devFiles.length} 个未提交变更</span><button className="text-btn" onClick={() => setShowFiles(false)}>收起</button></div>
          <div className="files-toolbar"><label className="check-all"><input type="checkbox" checked={allSelected} ref={el => { if (el) el.indeterminate = someSelected; }} onChange={toggleAll} />{allSelected ? '全不选' : '全选'}</label></div>
          <div className="files-list">{devFiles.map(file => <div key={file.path} className="file-item">
            <label className="file-row compact">
              <input type="checkbox" checked={selectedFiles.has(file.path)} onChange={() => toggleFile(file.path)} />
              <span className={`file-badge ${file.type === '新增' ? 'new' : ''}`}>{file.modified ? '有修改' : '未修改'}</span>
              <code className="file-path">{file.path}</code>
              <button className="history-link" onClick={(e) => { e.stopPropagation(); setHistoryFile(file.path); }}>查看历史版本</button>
            </label>
          </div>)}</div>
          <div className="files-panel-foot"><button className="primary" onClick={handlePublish} disabled={selectedFiles.size === 0}>一键发布</button></div>
        </div>}
      </div>
      <div className="webspoon-frame-wrap"><iframe key={frameKey} title="WebSpoon Kettle 在线设计器" src="http://192.168.107.72:8881/spoon/spoon" /><div className="frame-fallback"><strong>正在加载 WebSpoon</strong><span>若服务器禁止嵌入，正式接入时需调整 WebSpoon 的 Frame/CSP 配置。</span></div></div>
    </section>
    {historyFile && <HistoryModal filePath={historyFile} onClose={() => setHistoryFile(null)} onRestore={(rev) => { notify(`已将 ${historyFile} 恢复到 ${rev}`); setHistoryFile(null); }} />}
  </>;
}

function VersionManagement({ notify }) {
  const [compareFile, setCompareFile] = useState(null);
  const [commitOpen, setCommitOpen] = useState(false);
  const [publish, setPublish] = useState(null);
  const [filter, setFilter] = useState('全部版本');
  const versions = useMemo(() => VERSION_ROWS.filter(row => filter === '全部版本' || row.status === filter), [filter]);
  return <>
    <div className="version-overview">
      <section><span>开发工作区</span><strong>SVN r1842</strong><small>3 个未提交变更</small></section><b>→</b><section><span>待发布版本</span><strong>r1842</strong><small>领先生产 3 个版本</small></section><b>→</b><section><span>生产目录</span><strong>SVN r1839</strong><small>2026-09-08 10:10 发布</small></section>
      <div className="overview-actions"><button className="secondary" onClick={() => setCommitOpen(true)}>提交 SVN</button><button className="primary" onClick={() => setPublish({ revision: 'r1842', restore: false })}>一键发布 r1842</button></div>
    </div>
    <section className="panel version-panel"><div className="panel-head"><div><h3>开发工作区变更</h3><p>WebSpoon 保存后产生的文件变化，提交 SVN 前可逐项对比</p></div><StateBadge value="3 个未提交" /></div><table><thead><tr><th>文件</th><th>状态</th><th>变更摘要</th><th>修改人</th><th>修改时间</th><th>操作</th></tr></thead><tbody>{CHANGED_FILES.map(file => <tr key={file.path}><td className="code-cell strong-cell">{file.path}</td><td><span className={`file-change ${file.type === '新增' ? 'new' : ''}`}>{file.type}</span></td><td>{file.summary}</td><td>{file.owner}</td><td>{file.time}</td><td className="actions"><button onClick={() => setCompareFile(file)}>查看修改前后</button></td></tr>)}</tbody></table></section>
    <section className="panel version-panel"><div className="panel-head"><div><h3>SVN 版本历史</h3><p>生产恢复通过“重新发布历史 revision”完成，并形成新的发布记录</p></div><div className="filter-group"><select value={filter} onChange={event => setFilter(event.target.value)}><option>全部版本</option><option>待发布</option><option>生产版本</option><option>历史版本</option></select><button className="secondary" onClick={() => notify('版本历史已刷新')}>刷新</button></div></div><table><thead><tr><th>版本</th><th>提交说明</th><th>文件数</th><th>提交人</th><th>提交时间</th><th>状态</th><th>操作</th></tr></thead><tbody>{versions.map(row => <tr key={row.revision}><td className="revision-cell">{row.revision}</td><td className="strong-cell">{row.message}</td><td>{row.files}</td><td>{row.author}</td><td>{row.time}</td><td><StateBadge value={row.status} /></td><td className="actions"><button onClick={() => setCompareFile(CHANGED_FILES[0])}>查看变更</button>{row.status === '待发布' && <button onClick={() => setPublish({ revision: row.revision, restore: false })}>发布</button>}{row.status === '历史版本' && <button className="warning-link" onClick={() => setPublish({ revision: row.revision, restore: true })}>恢复此版本</button>}</td></tr>)}</tbody></table></section>
    <section className="panel release-history"><div className="panel-head"><div><h3>最近发布记录</h3><p>记录发布前后版本、操作人和结果</p></div></div><table><thead><tr><th>发布时间</th><th>发布类型</th><th>原生产版本</th><th>目标版本</th><th>操作人</th><th>结果</th><th>操作</th></tr></thead><tbody><tr><td>2026-09-08 10:10:18</td><td>正常发布</td><td>r1838</td><td className="revision-cell">r1839</td><td>张三</td><td><StateBadge value="成功" /></td><td className="actions"><button onClick={() => notify('已打开发布日志')}>查看日志</button></td></tr><tr><td>2026-09-05 18:36:44</td><td>版本恢复</td><td>r1837</td><td className="revision-cell">r1836</td><td>管理员</td><td><StateBadge value="成功" /></td><td className="actions"><button onClick={() => notify('已打开恢复记录')}>查看记录</button></td></tr></tbody></table></section>
    {compareFile && <CompareModal file={compareFile} onClose={() => setCompareFile(null)} />}
    {commitOpen && <CommitModal onClose={() => setCommitOpen(false)} onConfirm={() => { setCommitOpen(false); notify('已提交 SVN，新版本为 r1843'); }} />}
    {publish && <PublishModal {...publish} onClose={() => setPublish(null)} onConfirm={() => { const text = publish.restore ? `已创建 ${publish.revision} 的恢复发布任务` : `已开始发布 ${publish.revision} 到生产目录`; setPublish(null); notify(text); }} />}
  </>;
}

function ScheduledTasks({ notify }) {
  const [scheduleOpen, setScheduleOpen] = useState(false);
  return <>
    <div className="schedule-toolbar"><div><h2>生产定时任务</h2><p>所有 KJB/KTR 定时任务固定从生产目录执行；Spider 继续调用现有流程链。</p></div><button className="primary" onClick={() => setScheduleOpen(true)}>新增定时任务</button></div>
    <div className="schedule-metrics"><section><span>任务总数</span><strong>12</strong><small>10 个启用</small></section><section><span>今日待执行</span><strong>4</strong><small>最近 21:00</small></section><section className="success"><span>近 7 日成功</span><strong>98.6%</strong><small>共执行 72 次</small></section><section className="danger"><span>待处理失败</span><strong>1</strong><small>EAST5 数据归集</small></section></div>
    <section className="panel schedule-list"><div className="panel-head"><div><h3>定时任务</h3><p>执行时记录生产 revision、参数快照和完整 Kettle/Spider 日志</p></div><div className="filter-group"><input placeholder="任务名称或流程路径" /><select defaultValue="all"><option value="all">全部类型</option><option>KJB</option><option>KTR</option><option>Spider</option></select><button className="secondary">查询</button></div></div><table><thead><tr><th>任务名称</th><th>报送类型</th><th>类型</th><th>流程入口</th><th>触发规则</th><th>运行版本</th><th>状态</th><th>下次执行</th><th>最近结果</th><th>操作</th></tr></thead><tbody>{SCHEDULE_ROWS.map(row => <tr key={row[0]}><td className="strong-cell">{row[0]}</td><td>{row[1]}</td><td><span className="type-tag">{row[2]}</span></td><td className="code-cell schedule-path">{row[3]}</td><td>{row[4]}</td><td className="revision-cell">{row[5]}</td><td><StateBadge value={row[6]} /></td><td>{row[7]}</td><td><StateBadge value={row[8]} /></td><td className="actions"><button onClick={() => notify(`已手工触发 ${row[0]}`)}>立即执行</button><button onClick={() => setScheduleOpen(true)}>编辑</button><button onClick={() => notify(`已打开 ${row[0]} 的执行记录`)}>记录</button></td></tr>)}</tbody></table></section>
    <section className="panel schedule-history"><div className="panel-head"><div><h3>最近调度执行</h3><p>人工触发和定时触发统一记录，但不与报送生成批次绑定</p></div><button className="text-btn" onClick={() => notify('执行记录已刷新')}>刷新</button></div><table><thead><tr><th>开始时间</th><th>任务名称</th><th>触发方式</th><th>生产版本</th><th>结果</th><th>耗时</th><th>操作</th></tr></thead><tbody><tr><td>2026-09-09 02:00:00</td><td>1104月报生成</td><td>定时触发</td><td className="revision-cell">r1839</td><td><StateBadge value="成功" /></td><td>00:08:42</td><td className="actions"><button onClick={() => notify('已打开 Kettle 完整日志')}>查看日志</button></td></tr><tr><td>2026-09-08 21:00:00</td><td>EAST5数据归集</td><td>定时触发</td><td>流程 v27</td><td><StateBadge value="失败" /></td><td>00:03:17</td><td className="actions"><button onClick={() => notify('已打开 Spider 执行日志')}>查看日志</button><button onClick={() => notify('已重新提交执行')}>重新执行</button></td></tr></tbody></table></section>
    {scheduleOpen && <ScheduleModal onClose={() => setScheduleOpen(false)} onConfirm={() => { setScheduleOpen(false); notify('定时任务已保存'); }} />}
  </>;
}

export function SchedulingManagement({ section, notify, onNavigate }) {
  const subtitles = { KETTLE: '在线编辑开发目录中的 KJB/KTR 文件', 版本管理: '管理 SVN 提交、生产发布与历史恢复', 定时调度: '统一配置 Kettle 与 Spider 的生产定时任务' };
  const kettleMode = section === 'KETTLE';
  return <main className={`page scheduling-page ${kettleMode ? 'kettle-mode' : ''}`}>{!kettleMode && <div className="page-title scheduling-title"><div><span className="page-parent">调度管理</span><h1>{section}</h1><p>{subtitles[section]}</p></div></div>}<div className="scheduling-content">{kettleMode && <KettleWorkspace notify={notify} onGoVersions={() => onNavigate('版本管理')} />}{section === '版本管理' && <VersionManagement notify={notify} />}{section === '定时调度' && <ScheduledTasks notify={notify} />}</div></main>;
}
